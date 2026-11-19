"""Native TreeSHAP correctness on disposable synthetic models and saved scores."""

import copy
import json
from datetime import datetime, timedelta

import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_ml import fixture_table

from mulegraph.explanations import (
    ExplanationService,
    checked_contributions,
    feature_description,
    verify_additivity,
)
from mulegraph.features import definition, sha256_file
from mulegraph.graph import Transfer
from mulegraph.investigation import reference
from mulegraph.investigation_scores import FrozenScores, ScoreFile
from mulegraph.ml import Preprocessor


@pytest.fixture
def service(tmp_path):
    training = fixture_table(100)
    prep = Preprocessor.fit([training], "history")
    model = lgb.LGBMClassifier(
        n_estimators=12,
        num_leaves=7,
        min_child_samples=2,
        n_jobs=2,
        verbosity=-1,
        random_state=42,
    )
    model.fit(prep.transform(training), np.arange(100) % 3 == 0)
    data = training.to_pydict()
    data.update(
        dataset_id=[1] * 100,
        dataset_fingerprint=["synthetic"] * 100,
        source_row=list(range(1, 101)),
        occurred_at=[datetime(2022, 9, 8) + timedelta(seconds=i) for i in range(100)],
        from_bank_id=["1"] * 100,
        from_account=["A"] * 100,
        to_bank_id=["2"] * 100,
        to_account=["A"] * 100,
        split=["validation"] * 100,
    )
    table = pa.table(data)
    pq.write_table(table, tmp_path / "features.parquet")
    (tmp_path / "manifest.json").write_text(json.dumps({"definition": definition()}))
    matrix = prep.transform(table)
    values = model.predict_proba(matrix)[:, 1]
    path = tmp_path / "validation.parquet"
    pq.write_table(pa.table({"source_row": data["source_row"], "score": values}), path)
    s = object.__new__(ExplanationService)
    s.features = tmp_path
    s.freeze = {
        "feature_sha256": sha256_file(tmp_path / "features.parquet"),
        "feature_manifest_sha256": sha256_file(tmp_path / "manifest.json"),
    }
    s.artifact = {"preprocessor": prep, "model": model, "threshold": 0.5}
    s.names = prep.names
    s.scores = FrozenScores(
        "synthetic",
        1,
        (
            ScoreFile(
                path,
                sha256_file(path),
                "score",
                datetime(2022, 9, 7),
                datetime(2022, 9, 9),
            ),
        ),
    )
    return s, table


def test_native_additivity_saved_scores_and_repeatability(service):
    s, _ = service
    a = s.explain([10, 2, 70])
    assert a == s.explain([70, 10, 2])
    assert all(x["status"] == "EXPLAINED" and x["additivity_error"] < 1e-8 for x in a)
    assert all(x["saved_score_error"] == 0 for x in a)
    for e in a:
        assert sum(e["grouped_contributions"].values()) + e[
            "base_value"
        ] == pytest.approx(e["raw_margin"])
        assert all(c["raw_contribution"] > 0 for c in e["top_increasing"])
        assert all(c["raw_contribution"] < 0 for c in e["top_decreasing"])
        assert len(e["contributions"]) == len(s.names)


def test_additivity_and_invalid_output_rejection():
    verify_additivity(
        np.array([[1.0, 2.0]]), np.array([3.0]), np.array([1 / (1 + np.exp(-3))]), 1
    )
    with pytest.raises(ValueError, match="additivity"):
        verify_additivity(np.array([[1.0, 2.0]]), np.array([4.0]), np.array([0.5]), 1)
    with pytest.raises(ValueError, match="review score"):
        verify_additivity(np.array([[1.0, 2.0]]), np.array([3.0]), np.array([0.5]), 1)
    with pytest.raises(ValueError, match="nonfinite"):
        verify_additivity(
            np.array([[np.nan, 2.0]]), np.array([3.0]), np.array([0.5]), 1
        )


def test_limits_missing_source_cutoff_and_missing_input(service):
    s, table = service
    for ids in ([], [1, 1], [0], [True], list(range(1, 130))):
        with pytest.raises(ValueError):
            s.explain(ids)
    assert s.explain([999])[0]["status"] == "SOURCE_NOT_FOUND"
    with pytest.raises(ValueError, match="cutoff"):
        s.explain([1], cutoff=datetime(2022, 9, 8))
    with pytest.raises(ValueError, match="naive"):
        s.explain([1], cutoff=datetime.now().astimezone())
    with pytest.raises(KeyError):
        s.artifact["preprocessor"].transform(table.drop(["amount_paid"]))


def test_unscored_training_never_runs_model(service, monkeypatch):
    s, table = service
    index = table.column_names.index("occurred_at")
    table = table.set_column(
        index, "occurred_at", pa.array([datetime(2022, 9, 1)] * 100)
    )
    pq.write_table(table, s.features / "features.parquet")
    s.freeze["feature_sha256"] = sha256_file(s.features / "features.parquet")

    def forbidden(*args, **kwargs):
        raise AssertionError("Training prediction attempted")

    monkeypatch.setattr("mulegraph.explanations.checked_contributions", forbidden)
    assert s.explain([1])[0]["status"] == "UNSCORED_TRAINING_PERIOD"
    assert "raw_margin" not in s.explain([1])[0]


def test_corrupt_features_and_saved_model_disagreement(service):
    s, _ = service
    original = s.artifact["preprocessor"].mean.copy()
    s.artifact["preprocessor"].mean += 100
    with pytest.raises(ValueError, match="saved prediction"):
        s.explain([1, 50])
    s.artifact["preprocessor"].mean = original
    (s.features / "features.parquet").write_bytes(b"broken")
    with pytest.raises(ValueError, match="checksum"):
        s.explain([1])


def test_human_descriptions_and_encoded_categories(service):
    s, table = service
    row = table.to_pylist()[0]
    for name in s.names:
        base, label, value = feature_description(name, row)
        assert base in row and label and value == row[base]
    assert "USD" in feature_description("amount_paid", row)[1]
    assert (
        "Missing-history"
        in feature_description("sender_mean_gap_seconds__missing", row)[1]
    )
    assert "UNKNOWN" in feature_description("payment_currency=<UNKNOWN>", row)[1]
    matrix = s.artifact["preprocessor"].transform(table)
    shap, raw, scores = checked_contributions(s.artifact["model"], matrix[:2])
    assert shap.shape == (2, len(s.names) + 1)


def test_case_annotation_is_additive_and_validates_context(service):
    s, table = service
    rows = table.slice(0, 2).to_pylist()
    predictions = s.explain([1, 2])
    report = {
        "dataset_fingerprint": "synthetic",
        "dataset_id": 1,
        "cutoff": "2022-09-09T00:00:00",
        "cases": [{"id": "unchanged"}],
        "accounts": [{"ml_summary": {"max_transaction_score": 0.9}}],
        "transactions": [
            {
                **reference(
                    Transfer(**{k: r[k] for k in Transfer.__dataclass_fields__})
                ),
                "score": e["saved_review_score"],
            }
            for r, e in zip(rows, predictions, strict=True)
        ],
    }
    before = copy.deepcopy(report)
    annotated = s.annotate_case_report(report, [1])
    assert report == before
    assert {
        k: v for k, v in annotated.items() if k != "transaction_explanations"
    } == report
    assert annotated["transaction_explanations"]["unrequested_transactions"] == 1
    with pytest.raises(ValueError, match="historical"):
        s.annotate_case_report(report, [3])
    bad = copy.deepcopy(report)
    bad["transactions"][0]["amount_paid"] = "999"
    with pytest.raises(ValueError, match="attributes"):
        s.annotate_case_report(bad, [1])
    bad = copy.deepcopy(report)
    bad["transactions"][0]["score"] = 0.123
    with pytest.raises(ValueError, match="score"):
        s.annotate_case_report(bad, [1])
