"""Supervised input isolation, train-only fitting, ranking and artifact contracts."""

import json

import joblib
import numpy as np
import pyarrow as pa
import pytest

from mulegraph.features import sha256_file
from mulegraph.ml import CURRENT, HISTORY, Preprocessor, allowlist, evaluate, tie_keys
from mulegraph.ml_training import export_labels, load_artifact, make_model, predict


def fixture_table(n=12):
    data = {name: np.arange(n, dtype=float) for name in CURRENT + HISTORY}
    data.update(
        payment_currency=["USD"] * n,
        receiving_currency=["USD"] * n,
        payment_format=["ACH", "Wire"] * (n // 2),
        split=["train"] * n,
    )
    return pa.table(data)


def test_explicit_allowlist_and_metadata_invariance():
    t = fixture_table()
    p = Preprocessor.fit([t], "history")
    augmented = t.append_column("is_laundering", pa.array([1] * len(t)))
    for field in (
        "source_row",
        "from_bank_id",
        "from_account",
        "future_balance",
        "dataset_fingerprint",
        "occurred_at",
        "sender_last_activity_at",
    ):
        augmented = augmented.append_column(
            field, pa.array(["never a predictor"] * len(t))
        )
    np.testing.assert_array_equal(p.transform(t), p.transform(augmented))
    assert "payment_format" not in allowlist("history_no_format")[1]
    assert not set(HISTORY) & set(allowlist("current")[0])
    with pytest.raises(ValueError):
        allowlist("arbitrary")


def test_preprocessing_training_only_alignment_unknown_and_missing():
    t = fixture_table()
    p = Preprocessor.fit([t.slice(0, 6), t.slice(6)], "history")
    q = Preprocessor.fit([t], "history")
    np.testing.assert_allclose(p.mean, q.mean)
    np.testing.assert_allclose(p.scale, q.scale)
    data = t.to_pydict()
    data["split"] = ["validation"] * len(t)
    data["payment_currency"] = ["UNSEEN"] * len(t)
    data["sender_mean_gap_seconds"] = [None] * len(t)
    val = pa.table(data)
    with pytest.raises(ValueError, match="training"):
        Preprocessor.fit([val], "history")
    before = p.mean.copy()
    x = p.transform(val)
    assert x[:, p.names.index("sender_mean_gap_seconds__missing")].all()
    assert x[:, p.names.index("payment_currency=<UNKNOWN>")].all()
    np.testing.assert_array_equal(before, p.mean)
    np.testing.assert_array_equal(
        x, p.transform(val.select(list(reversed(val.column_names))))
    )
    with pytest.raises(KeyError):
        p.transform(val.drop(["amount_paid"]))


@pytest.mark.parametrize("split", ["test", "stress", "other"])
def test_holdout_label_guard_precedes_connection(tmp_path, split):
    with pytest.raises(ValueError, match="only train/validation"):
        export_labels("invalid", {}, split, tmp_path / "never.parquet")
    assert not (tmp_path / "never.parquet").exists()


def test_metrics_hand_calculated_ties_auc_and_empty_classes():
    y = np.array([1, 0, 1, 0])
    ties = np.array(["a", "b", "c", "d"])
    m = evaluate(y, np.array([0.9, 0.9, 0.1, 0.1]), ties)
    assert m["average_precision"] == 0.5
    assert m["roc_auc"] == 0.5
    assert m["at_k"][0]["k"] == 4
    assert m["at_k"][0]["recall"] == 1
    assert m["alerts"] == 0
    z = evaluate(np.zeros(4), np.zeros(4), ties)
    assert z["average_precision"] is None and z["roc_auc"] is None
    assert z["alert_precision"] is None
    with pytest.raises(ValueError):
        evaluate(y, np.zeros(2), ties)


def test_one_percent_budget_whole_tiers_and_determinism():
    y = np.zeros(200, dtype=int)
    y[:2] = 1
    scores = np.arange(200, 0, -1, dtype=float)
    ties = tie_keys(np.arange(200), "fixture")
    a = evaluate(y, scores, ties)
    assert a["alerts"] == 2
    assert a["budget_1pct"]["precision"] == 1
    assert a["alert_recall"] == 1
    assert a == evaluate(y, scores, ties)
    tied = evaluate(y, np.ones(200), ties)
    assert tied["alerts"] == 0
    assert tied["average_precision"] == 0.01


@pytest.mark.parametrize("family,setting", [("lr", 1), ("lightgbm", 15)])
def test_model_reproducibility_and_artifact_roundtrip(tmp_path, family, setting):
    t = fixture_table(1000)
    p = Preprocessor.fit([t], "current")
    x = p.transform(t)
    y = np.arange(1000) % 2
    a = make_model(family, setting, 500, 500).fit(x, y)
    b = make_model(family, setting, 500, 500).fit(x, y)
    assert np.ptp(predict(a, x)) > 0.1
    np.testing.assert_array_equal(predict(a, x), predict(b, x))
    joblib.dump({"model": a, "preprocessor": p}, tmp_path / "model.joblib")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "model_sha256": sha256_file(tmp_path / "model.joblib"),
                "feature_names": p.names,
            }
        )
    )
    loaded = load_artifact(tmp_path)
    np.testing.assert_array_equal(
        predict(a, x), predict(loaded["model"], loaded["preprocessor"].transform(t))
    )
    (tmp_path / "model.joblib").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_artifact(tmp_path)


def test_threshold_inference_preserves_float64_cutoff():
    from mulegraph.ml_inference import score_batch

    class Prep:
        def transform(self, table):
            return np.ones((len(table), 1), dtype=np.float32)

    class Model:
        n_features_in_ = 1

        def predict_proba(self, matrix):
            return np.full((len(matrix), 2), 0.5, dtype=np.float32)

    artifact = {
        "preprocessor": Prep(),
        "model": Model(),
        "threshold": float(np.nextafter(0.5, np.inf)),
    }
    scores, alerts = score_batch(artifact, pa.table({"anything": [1, 2]}))
    assert scores.dtype == np.float64
    assert not alerts.any()


def test_invalid_numeric_inputs_are_rejected():
    data = fixture_table().to_pydict()
    for bad in (-1, float("inf"), None):
        data["amount_paid"][0] = bad
        with pytest.raises(ValueError):
            Preprocessor.fit([pa.table(data)], "current")


def test_alignment_rejects_mislabeled_temporal_split(tmp_path):
    from datetime import datetime

    import duckdb
    import pyarrow.parquet as pq

    from mulegraph.ml_training import aligned_labels, batches

    path = tmp_path / "labels.parquet"
    pq.write_table(pa.table({"source_row": [1], "label": [0]}), path)
    with duckdb.connect() as db:
        db.register(
            "features",
            pa.table(
                {
                    "source_row": [1],
                    "split": ["train"],
                    "occurred_at": [datetime(2022, 9, 7)],
                }
            ),
        )
        with pytest.raises(ValueError, match="boundary"):
            aligned_labels(db, "train", path)
        with pytest.raises(ValueError, match="Only train/validation"):
            list(batches(db, "current", "test"))


def test_completed_version_cannot_be_silently_refit(tmp_path):
    from mulegraph.ml_training import run

    output = tmp_path / "completed"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("unchanged")
    with pytest.raises(ValueError, match="already exists"):
        run(tmp_path / "no_features", output, "invalid_database_url")
    assert sentinel.read_text() == "unchanged"
