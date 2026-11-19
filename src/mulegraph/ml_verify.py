"""Recheck every persisted validation prediction without retrieving any labels."""

import argparse
import json
import platform
import time
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq

from mulegraph.eda import SPLITS
from mulegraph.features import sha256_file
from mulegraph.ml_inference import score_batch
from mulegraph.ml_training import batches, load_artifact
from mulegraph.rules_baseline import open_features, write_json


def verify(directory: Path, features_dir: Path) -> dict:
    start = time.perf_counter()
    plan = json.loads((directory / "plan.json").read_text())
    results = json.loads((directory / "results.json").read_text())
    for filename, key in (
        ("ml.py", "inputs_sha256"),
        ("ml_training.py", "implementation_sha256"),
    ):
        if sha256_file(Path(__file__).with_name(filename)) != plan[key]:
            raise ValueError("Executed training implementation changed")
    expected = results["baselines"]["constant_score"]["rows"]
    checks = []
    with duckdb.connect() as db:
        manifest = open_features(db, features_dir)
        if manifest["file_sha256"] != plan["feature_sha256"]:
            raise ValueError("Feature provenance changed")
        ids = db.execute(
            "SELECT source_row FROM features WHERE split='validation' "
            "ORDER BY source_row"
        ).fetchnumpy()["source_row"]
        if len(ids) != expected or len(np.unique(ids)) != expected:
            raise ValueError("Validation coverage mismatch")
        for experiment in results["experiments"]:
            name = experiment["name"]
            dest = directory / name
            if json.loads((dest / "metadata.json").read_text()) != experiment:
                raise ValueError("Experiment metadata differs from completed results")
            artifact = load_artifact(dest)
            if artifact["threshold"] != experiment["metrics"]["threshold"]:
                raise ValueError("Saved operating threshold mismatch")
            if (
                artifact["preprocessor"].training_rows
                != results["label_access"][0]["rows"]
            ):
                raise ValueError("Preprocessing population mismatch")
            path = dest / "validation.parquet"
            if sha256_file(path) != experiment["predictions_sha256"]:
                raise ValueError("Prediction checksum mismatch")
            table = pq.read_table(path)
            if table.column_names != ["source_row", "score"]:
                raise ValueError("Unexpected prediction fields")
            np.testing.assert_array_equal(table["source_row"].to_numpy(), ids)
            saved = table["score"].to_numpy().astype(np.float64)
            offset = alerts = 0
            for batch in batches(db, experiment["variant"], "validation"):
                score, alert = score_batch(artifact, batch)
                np.testing.assert_array_equal(
                    score, saved[offset : offset + len(batch)]
                )
                offset += len(batch)
                alerts += int(alert.sum())
            if offset != expected or alerts != experiment["metrics"]["alerts"]:
                raise ValueError("Reloaded coverage/threshold mismatch")
            checks.append(
                {
                    "experiment": name,
                    "rows": offset,
                    "alerts": alerts,
                    "scores_exactly_equal": True,
                }
            )
            print(f"Verified {name}: {offset:,} scores", flush=True)
    result = {
        "experiments": checks,
        "label_accesses": 0,
        "python": platform.python_version(),
        "uv_lock_sha256": sha256_file(Path("uv.lock")),
        "training_validation_boundaries": [
            [n, start.isoformat(), end.isoformat()]
            for n, start, end in SPLITS
            if n in ("train", "validation")
        ],
        "elapsed_seconds": time.perf_counter() - start,
        "feature_sha256": manifest["file_sha256"],
    }
    write_json(directory / "verification.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=Path("data/ml/supervised-v1"))
    parser.add_argument("--features-dir", type=Path, required=True)
    args = parser.parse_args()
    verify(args.artifacts, args.features_dir)


if __name__ == "__main__":
    main()
