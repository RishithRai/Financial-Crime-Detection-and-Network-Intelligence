"""Bounded boosting, fixed selection, atomic publication and original isolation."""

import json
from datetime import datetime

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_ml import fixture_table

from mulegraph.features import sha256_file
from mulegraph.ml import Preprocessor, evaluate, tie_keys
from mulegraph.ml_stabilization import (
    PARAMETERS,
    configurations,
    create_plan,
    leaf_values,
    make_model,
    recommend,
    run,
    score_diagnostics,
    snapshot,
    stable,
    validate_plan,
)
from mulegraph.ml_training import make_model as make_original
from mulegraph.rules_baseline import write_json


def test_fixed_grid_and_training_only_weights():
    assert len(configurations()) == 6
    assert {c["variant"] for c in configurations()} == {"history", "history_no_format"}
    for policy, expected in (("none", 1), ("sqrt", 10), ("full", 100)):
        p = make_model(policy, 10, 1000).get_params()
        assert p["scale_pos_weight"] == expected
        assert p["max_delta_step"] == 2
        assert p["learning_rate"] == 0.03
    for policy, pos, neg in (("other", 10, 10), ("none", 0, 10), ("full", 10, 0)):
        with pytest.raises(ValueError):
            make_model(policy, pos, neg)


def test_saturation_ties_and_nonfinite_rejection():
    d = score_diagnostics(np.array([0, 0.5, 0.5, 1]), np.array([-900, 0, 0, 900]))
    assert d["exact_zero"] == d["exact_one"] == 1
    assert d["largest_tie"] == 2 and d["unique_scores"] == 3
    assert not stable(d)
    assert stable(score_diagnostics(np.array([0.1, 0.9]), np.array([-2.2, 2.2])))
    with pytest.raises(ValueError):
        score_diagnostics(np.array([0.5]), np.array([float("nan")]))


def test_recommendation_requires_stability_ap_and_budget_recall():
    baseline = {"average_precision": 0.26, "budget_1pct": {"recall": 0.58}}
    candidate = {
        "name": "new",
        "stable": True,
        "metrics": {"average_precision": 0.3, "budget_1pct": {"recall": 0.6}},
    }
    assert recommend([candidate], baseline) == "new"
    for field, value in (("average_precision", 0.25), ("budget_1pct", {"recall": 0.5})):
        bad = {**candidate, "metrics": {**candidate["metrics"], field: value}}
        assert recommend([bad], baseline) == "history_lr_1.0"
    assert recommend([{**candidate, "stable": False}], baseline) == "history_lr_1.0"
    assert recommend([candidate, {**candidate, "name": "tie"}], baseline) == "new"


def test_imbalanced_fit_has_bounded_updates_and_is_reproducible():
    rng = np.random.default_rng(42)
    x = rng.normal(size=(3000, 3)).astype(np.float32)
    y = (x[:, 0] > 2).astype(int)
    a = make_model("full", int(y.sum()), int((y == 0).sum())).fit(x, y)
    b = make_model("full", int(y.sum()), int((y == 0).sum())).fit(x, y)
    np.testing.assert_array_equal(a.predict_proba(x), b.predict_proba(x))
    trees = a.booster_.dump_model()["tree_info"]
    assert len(trees) > 1
    bound = PARAMETERS["learning_rate"] * PARAMETERS["max_delta_step"]
    assert (
        max(abs(v) for t in trees[1:] for v in leaf_values(t["tree_structure"]))
        <= bound + 1e-10
    )
    assert stable(
        score_diagnostics(
            a.predict_proba(x)[:, 1], a.booster_.predict(x, raw_score=True)
        )
    )


@pytest.fixture
def pipeline_case(tmp_path):
    feature_dir, original = tmp_path / "features", tmp_path / "original"
    feature_dir.mkdir()
    original.mkdir()
    table = fixture_table(800)
    data = table.to_pydict()
    data["split"] = ["train"] * 600 + ["validation"] * 200
    data["source_row"] = list(range(1, 801))
    data["occurred_at"] = [datetime(2022, 9, 1)] * 600 + [datetime(2022, 9, 7)] * 200
    table = pa.table(data)
    pq.write_table(table, feature_dir / "features.parquet")
    write_json(
        feature_dir / "manifest.json",
        {
            "definition": {"version": "historical-v1"},
            "file_sha256": sha256_file(feature_dir / "features.parquet"),
            "dataset": {
                "fingerprint": "synthetic",
                "dataset_id": 1,
                "dataset_key": "fixture",
            },
        },
    )
    labels = (np.arange(800) % 7 == 0).astype(np.int8)
    results = []
    for variant in ("history", "history_no_format"):
        prep = Preprocessor.fit([table.slice(0, 600)], variant)
        model = make_original("lr", 1, 1, 1).fit(
            prep.transform(table.slice(0, 600)), labels[:600]
        )
        scores = model.predict_proba(prep.transform(table.slice(600)))[:, 1]
        metrics = evaluate(
            labels[600:], scores, tie_keys(np.arange(601, 801), "synthetic")
        )
        dest = original / f"{variant}_lr_1.0"
        dest.mkdir()
        joblib.dump(
            {"model": model, "preprocessor": prep, "threshold": metrics["threshold"]},
            dest / "model.joblib",
        )
        pq.write_table(
            pa.table({"source_row": np.arange(601, 801), "score": scores}),
            dest / "validation.parquet",
        )
        meta = {
            "name": dest.name,
            "metrics": metrics,
            "feature_names": prep.names,
            "model_sha256": sha256_file(dest / "model.joblib"),
            "predictions_sha256": sha256_file(dest / "validation.parquet"),
        }
        write_json(dest / "metadata.json", meta)
        results.append(meta)
    write_json(original / "results.json", {"experiments": results})
    plan = tmp_path / "plan.json"
    create_plan(plan, feature_dir, original)
    return feature_dir, original, plan, labels


def test_staged_pipeline_isolation_and_failure_guards(
    pipeline_case, tmp_path, monkeypatch
):
    feature_dir, original, plan, labels = pipeline_case
    before = snapshot(original)
    calls = []

    def export(url, manifest, split, path, schema):
        assert plan.exists() and split in ("train", "validation")
        calls.append(split)
        sl = slice(0, 600) if split == "train" else slice(600, 800)
        pq.write_table(
            pa.table({"source_row": np.arange(1, 801)[sl], "label": labels[sl]}), path
        )
        return {
            "split": split,
            "rows": len(labels[sl]),
            "completed_at": datetime.now().isoformat(),
        }

    monkeypatch.setattr("mulegraph.ml_stabilization.export_labels", export)
    output = tmp_path / "stable"
    report = run(feature_dir, original, plan, output, "unused")
    assert calls == ["train", "validation"]
    assert len(report["experiments"]) == 6
    assert all(e["reload_exact"] and e["stable"] for e in report["experiments"])
    from mulegraph.ml_stabilization_report import render, verify

    audit = verify(output, feature_dir, original)
    assert audit["label_accesses"] == 0
    assert sum(e["rows"] for e in audit["experiments"]) == 1200
    rendered = tmp_path / "report.md"
    render(output, rendered)
    assert "Frozen history_lr_1.0" in rendered.read_text()
    assert "## Numerical stability and ties" in rendered.read_text()
    assert snapshot(original) == before
    assert not list(tmp_path.glob(".stable-*"))
    assert not list(output.rglob("*labels*"))
    with pytest.raises(ValueError, match="already exists"):
        run(feature_dir, original, plan, output, "unused")
    assert calls == ["train", "validation"]
    with pytest.raises(FileExistsError):
        create_plan(plan, feature_dir, original)
    content = json.loads(plan.read_text())
    content["parameters"]["max_delta_step"] = 0
    with pytest.raises(ValueError, match="changed"):
        validate_plan(content, original)
    prediction = output / "history_none" / "validation.parquet"
    prediction.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        verify(output, feature_dir, original)


def test_failed_attempt_leaves_no_published_artifact(
    pipeline_case, tmp_path, monkeypatch
):
    features, original, plan, _ = pipeline_case

    def fail(*args):
        raise RuntimeError("simulated interrupted export")

    monkeypatch.setattr("mulegraph.ml_stabilization.export_labels", fail)
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError):
        run(features, original, plan, output, "unused")
    assert not output.exists()
    assert not list(tmp_path.glob(".stable-*"))
    with pytest.raises(FileExistsError):
        run(features, original, plan, output, "unused")
