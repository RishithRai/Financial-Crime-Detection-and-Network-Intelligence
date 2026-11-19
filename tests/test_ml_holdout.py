"""Frozen thresholds, alignment, integrity gates and reproducible inference."""

from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pytest
from test_ml import fixture_table

from mulegraph.ml import Preprocessor
from mulegraph.ml_holdout import (
    aligned_labels,
    bounds,
    export_holdout,
    feature_batches,
    metrics,
    predict_split,
    run,
)
from mulegraph.ml_inference import score_batch
from mulegraph.ml_training import make_model
from mulegraph.rules_baseline import write_json


def test_metrics_tied_ap_auc_frozen_threshold_and_confusion():
    y = np.array([1, 0, 1, 0])
    scores = np.array([0.9, 0.9, 0.1, 0.1])
    m = metrics(y, scores, np.array(["a", "b", "c", "d"]), 0.5)
    assert m["ap"] == m["roc_auc"] == 0.5
    assert m["ap_over_prevalence"] == 1
    assert m["confusion"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert m["alert_rate"] == 0.5
    assert m["budget"]["k"] == 0 and m["budget"]["precision"] is None
    assert m["at_1000"]["k"] == 4
    # The threshold is never replaced by a 1% cap selected from this split.
    n = metrics(np.ones(200), np.ones(200), np.arange(200), 0.5)
    assert n["alerts"] == 200 and n["budget"]["k"] == 2
    assert n["ap"] == 1 and n["roc_auc"] is None
    z = metrics(np.zeros(200), np.zeros(200), np.arange(200), 1)
    assert z["ap"] is None and z["roc_auc"] is None
    assert z["alert_precision"] is None and z["alert_recall"] is None


def test_budget_ranking_and_float64_threshold():
    y = np.zeros(200, dtype=int)
    y[:2] = 1
    s = np.arange(200, 0, -1, dtype=float)
    m = metrics(y, s, np.arange(200), 199)
    assert m["budget"]["tp"] == 2 and m["budget"]["recall"] == 1
    assert m["confusion"] == {"tn": 198, "fp": 0, "fn": 0, "tp": 2}
    m = metrics(
        y,
        np.full(200, 0.5, dtype=np.float32),
        np.arange(200),
        np.nextafter(0.5, np.inf),
    )
    assert m["alerts"] == 0 and m["ap"] == 0.01
    assert m == metrics(
        y,
        np.full(200, 0.5, dtype=np.float32),
        np.arange(200),
        np.nextafter(0.5, np.inf),
    )


@pytest.mark.parametrize(
    "rows,labels", [([1, 1], [0, 1]), ([1, 3], [0, 1]), ([1], [0]), ([1, 2], [0, 2])]
)
def test_alignment_rejects_duplicates_missing_extra_or_bad_labels(rows, labels):
    with pytest.raises(ValueError):
        aligned_labels(
            np.array([1, 2]), pa.table({"source_row": rows, "is_laundering": labels})
        )


def test_alignment_sorts_labels_without_reordering_predictions():
    y = aligned_labels(
        np.array([1, 2]), pa.table({"source_row": [2, 1], "is_laundering": [1, 0]})
    )
    assert y.tolist() == [0, 1]


@pytest.mark.parametrize("split", ["train", "validation", "anything"])
def test_split_guard_precedes_connection(tmp_path, split):
    with pytest.raises(ValueError, match="Only test/stress"):
        export_holdout(
            "invalid", split, tmp_path / "labels", tmp_path / "missing", tmp_path, {}
        )


def test_integrity_gate_precedes_label_connection(tmp_path, monkeypatch):
    calls = []

    def reject(*args):
        raise ValueError("corrupted frozen artifact")

    monkeypatch.setattr("mulegraph.ml_holdout.validate_freeze", reject)
    monkeypatch.setattr(
        "mulegraph.ml_holdout.export_labels", lambda *a, **k: calls.append(a)
    )
    with pytest.raises(ValueError, match="corrupted"):
        export_holdout(
            "invalid", "test", tmp_path / "labels", tmp_path / "freeze", tmp_path, {}
        )
    assert calls == []
    output = tmp_path / "completed"
    output.mkdir()
    with pytest.raises(ValueError, match="already complete"):
        run(tmp_path, {}, tmp_path / "freeze", output, "invalid")


def test_split_boundaries_and_reproducible_predictions(tmp_path, monkeypatch):
    train = fixture_table(1000)
    prep = Preprocessor.fit([train], "history")
    model = make_model("lr", 1, 500, 500).fit(
        prep.transform(train), np.arange(1000) % 2
    )
    bundle = {"model": model, "preprocessor": prep, "threshold": 0.5}
    table = fixture_table(200).append_column("source_row", pa.array(np.arange(1, 201)))
    table = table.set_column(
        table.schema.get_field_index("split"), "split", pa.array(["test"] * 200)
    )
    table = table.append_column("occurred_at", pa.array([datetime(2022, 9, 9)] * 200))
    write_json(tmp_path / "rules.json", {"profile": {}})
    monkeypatch.setattr(
        "mulegraph.ml_holdout.inspect_models",
        lambda sources: ({"lightgbm": bundle, "logistic": bundle}, {}),
    )

    def rule_score(db, profile, split, path):
        import pyarrow.parquet as pq

        pq.write_table(
            pa.table(
                {
                    "source_row": np.arange(1, 201),
                    "risk_score": np.zeros(200),
                    "ach_score": np.ones(200),
                }
            ),
            path,
        )

    monkeypatch.setattr("mulegraph.ml_holdout.score_split", rule_score)
    with duckdb.connect() as db:
        db.register("features", table)
        a = predict_split(
            db, "test", {"rules": tmp_path}, {"constant_score": 0.0}, tmp_path
        )
        b = predict_split(
            db, "test", {"rules": tmp_path}, {"constant_score": 0.0}, tmp_path
        )
        assert a.equals(b)
        assert a.column_names == [
            "source_row",
            "lightgbm",
            "logistic",
            "rules",
            "ach",
            "prevalence",
        ]
        score, _ = score_batch(bundle, table)
        np.testing.assert_array_equal(a["lightgbm"].to_numpy(), score)
        with pytest.raises(ValueError):
            list(feature_batches(db, "train"))
        invalid = table.set_column(
            table.schema.get_field_index("occurred_at"),
            "occurred_at",
            pa.array([datetime(2022, 9, 11)] * 200),
        )
        db.unregister("features")
        db.register("features", invalid)
        with pytest.raises(ValueError, match="boundary"):
            predict_split(
                db, "test", {"rules": tmp_path}, {"constant_score": 0.0}, tmp_path
            )
    assert bounds("test") == (datetime(2022, 9, 9), datetime(2022, 9, 11))
    assert bounds("stress") == (datetime(2022, 9, 11), datetime(2022, 9, 19))


def test_freeze_rejects_changed_artifact_bytes_and_threshold(tmp_path, monkeypatch):
    import json

    from mulegraph.features import sha256_file
    from mulegraph.ml_holdout import (
        VERSION,
        dependencies,
        fingerprints,
        source_hashes,
        validate_freeze,
    )

    features = tmp_path / "features"
    features.mkdir()
    (features / "features.parquet").write_bytes(b"fixture features")
    (features / "manifest.json").write_text("{}")
    sources = {n: tmp_path / n for n in ("original", "stable", "rules")}
    for path in sources.values():
        path.mkdir()
    artifact = sources["stable"] / "model.joblib"
    artifact.write_bytes(b"original model bytes")
    write_json(sources["rules"] / "rules.json", {"threshold": 2})
    write_json(
        sources["rules"] / "calibration.json",
        {
            "validation": {
                "ach_score": {"threshold": 1},
                "constant_score": {"threshold": 1},
            }
        },
    )
    calls = []

    def inspect(paths):
        calls.append(True)
        return {"lightgbm": {"threshold": 0.01}, "logistic": {"threshold": 0.95}}, {}

    monkeypatch.setattr("mulegraph.ml_holdout.inspect_models", inspect)
    frozen = {
        "version": VERSION,
        "implementation": fingerprints(),
        "sources_sha256": source_hashes(sources),
        "dependencies": dependencies(),
        "uv_lock_sha256": sha256_file(Path("uv.lock")),
        "feature_sha256": sha256_file(features / "features.parquet"),
        "feature_manifest_sha256": sha256_file(features / "manifest.json"),
        "thresholds": {
            "lightgbm": 0.01,
            "logistic": 0.95,
            "rules": 2,
            "ach": 1,
            "prevalence": 1,
        },
        "selected": "lightgbm-stable-v1/history_none",
        "constant_score": 0.0,
        "splits": {s: [d.isoformat() for d in bounds(s)] for s in ("test", "stress")},
    }
    path = tmp_path / "freeze.json"
    write_json(path, frozen)
    assert validate_freeze(path, features, sources) == frozen
    artifact.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        validate_freeze(path, features, sources)
    assert len(calls) == 1
    artifact.write_bytes(b"original model bytes")
    frozen["thresholds"]["lightgbm"] = 0.5
    path.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="policy"):
        validate_freeze(path, features, sources)


def test_complete_evaluation_publishes_both_scores_before_labels(tmp_path, monkeypatch):
    import pyarrow.parquet as pq

    from mulegraph.features import sha256_file
    from mulegraph.ml_holdout_report import render, verify

    train = fixture_table(1000)
    prep = Preprocessor.fit([train], "history")
    model = make_model("lr", 1, 500, 500).fit(
        prep.transform(train), np.arange(1000) % 2
    )
    bundle = {"model": model, "preprocessor": prep, "threshold": 0.5}
    table = fixture_table(800).append_column("source_row", pa.array(np.arange(1, 801)))
    table = table.set_column(
        table.schema.get_field_index("split"),
        "split",
        pa.array(
            [s for s in ("train", "validation", "test", "stress") for _ in range(200)]
        ),
    )
    table = table.append_column(
        "occurred_at",
        pa.array([datetime(2022, 9, day) for day in (1, 7, 9, 11) for _ in range(200)]),
    )
    features = tmp_path / "features"
    features.mkdir()
    pq.write_table(table, features / "features.parquet")
    write_json(
        features / "manifest.json",
        {
            "definition": {"version": "historical-v1"},
            "file_sha256": sha256_file(features / "features.parquet"),
        },
    )
    write_json(tmp_path / "rules.json", {"profile": {}})
    monkeypatch.setattr(
        "mulegraph.ml_holdout.inspect_models",
        lambda sources: ({"lightgbm": bundle, "logistic": bundle}, {}),
    )

    def rule_scores(db, profile, split, path):
        ids = db.execute(
            "SELECT source_row FROM features WHERE split=? ORDER BY source_row", [split]
        ).fetchnumpy()["source_row"]
        pq.write_table(
            pa.table(
                {
                    "source_row": ids,
                    "risk_score": np.zeros(len(ids)),
                    "ach_score": ids % 2,
                }
            ),
            path,
        )

    monkeypatch.setattr("mulegraph.ml_holdout.score_split", rule_scores)
    frozen = {
        "selected": "lightgbm-stable-v1/history_none",
        "constant_score": 0.0,
        "thresholds": {
            "lightgbm": 0.5,
            "logistic": 0.5,
            "rules": 2,
            "ach": 1,
            "prevalence": 1,
        },
        "dataset": {"fingerprint": "synthetic"},
        "frozen_at": "2026-01-01",
        "splits": {s: [d.isoformat() for d in bounds(s)] for s in ("test", "stress")},
    }
    freeze_path = tmp_path / "freeze.json"
    write_json(freeze_path, frozen)
    monkeypatch.setattr("mulegraph.ml_holdout.validate_freeze", lambda *a: frozen)
    monkeypatch.setattr(
        "mulegraph.ml_holdout_report.validate_freeze", lambda *a: frozen
    )
    calls = []

    def export(url, split, path, *args):
        published = next(tmp_path.glob(".ml-holdout-*/published"))
        assert (published / "test.parquet").exists() and (
            published / "stress.parquet"
        ).exists()
        calls.append(split)
        ids = np.arange(401, 601) if split == "test" else np.arange(601, 801)
        pq.write_table(pa.table({"source_row": ids, "is_laundering": ids % 2}), path)
        return {
            "split": split,
            "rows": 200,
            "freeze_verified_at": "2026-01-02",
            "retrieved_at": "2026-01-03",
        }

    monkeypatch.setattr("mulegraph.ml_holdout.export_holdout", export)
    output = tmp_path / "completed"
    r = run(features, {"rules": tmp_path}, freeze_path, output, "unused")
    assert calls == ["test", "stress"] and set(r["splits"]) == {"test", "stress"}
    assert not list(tmp_path.glob(".ml-holdout-*"))
    assert not list(output.rglob("*labels*"))
    audit = verify(output, features, {"rules": tmp_path})
    assert audit["label_accesses"] == 0
    assert sum(s["rows"] for s in audit["splits"].values()) == 400
    render(output, tmp_path / "report.md")
    assert "## Test" in (tmp_path / "report.md").read_text()
    (output / "stress.parquet").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        verify(output, features, {"rules": tmp_path})
