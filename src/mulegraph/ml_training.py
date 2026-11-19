"""Milestone 4A: bounded CPU experiments, exclusively training and validation."""

import argparse
import gc
import json
import os
import resource
import shutil
import sys
import tempfile
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import sklearn
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

from mulegraph.eda import SPLITS
from mulegraph.features import literal, output_lock, sha256_file
from mulegraph.ml import VARIANTS, VERSION, Preprocessor, allowlist, evaluate, tie_keys
from mulegraph.rules_baseline import open_features, write_json
from mulegraph.schema import statement


def export_labels(
    database_url: str, manifest: dict, split: str, path: Path, schema: str = "mulegraph"
) -> dict:
    """Hard boundary: this module never opens test or stress labels."""
    if split not in ("train", "validation"):
        raise ValueError("Milestone 4A permits only train/validation labels")
    _, start, end = next(s for s in SPLITS if s[0] == split)
    dataset = manifest["dataset"]
    count = 0
    with psycopg.connect(database_url) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        current = db.execute(
            statement(
                "SELECT fingerprint, status FROM {core}.datasets WHERE dataset_id=%s "
                "AND dataset_key=%s",
                schema,
            ),
            (dataset["dataset_id"], dataset["dataset_key"]),
        ).fetchone()
        if current != (dataset["fingerprint"], "complete"):
            raise ValueError("Database/feature identity mismatch")
        with (
            db.cursor(name="ml_labels") as cursor,
            pq.ParquetWriter(
                path,
                pa.schema([("source_row", pa.int64()), ("label", pa.int8())]),
                compression="zstd",
            ) as writer,
        ):
            cursor.execute(
                statement(
                    "SELECT t.source_row,l.is_laundering FROM {core}.transactions t "
                    "JOIN {labels}.transaction_labels l USING(dataset_id,source_row) "
                    "WHERE t.dataset_id=%s AND t.occurred_at >= %s "
                    "AND t.occurred_at < %s "
                    "ORDER BY t.source_row",
                    schema,
                ),
                (dataset["dataset_id"], start, end),
            )
            while rows := cursor.fetchmany(32768):
                writer.write_table(
                    pa.table(
                        {
                            "source_row": pa.array([r[0] for r in rows], pa.int64()),
                            "label": pa.array([r[1] for r in rows], pa.int8()),
                        }
                    )
                )
                count += len(rows)
    return {
        "split": split,
        "rows": count,
        "sha256": sha256_file(path),
        "completed_at": datetime.now(UTC).isoformat(),
    }


def batches(db: duckdb.DuckDBPyConnection, variant: str, split: str):
    if split not in ("train", "validation"):
        raise ValueError("Only train/validation feature rows allowed")
    nums, cats = allowlist(variant)
    columns = ",".join(('"' + n + '"') for n in (*nums, *cats, "split"))
    reader = db.execute(
        f"SELECT {columns} FROM features WHERE split=? ORDER BY source_row", [split]
    ).to_arrow_reader(32768)
    for batch in reader:
        yield pa.Table.from_batches([batch])


def aligned_labels(db: duckdb.DuckDBPyConnection, split: str, path: Path) -> tuple:
    if split not in ("train", "validation"):
        raise ValueError("Only train/validation alignment allowed")
    _, start, end = next(s for s in SPLITS if s[0] == split)
    db.read_parquet(str(path)).create_view("ml_labels", replace=True)
    checks = db.execute(
        """
        SELECT count(*),count(DISTINCT f.source_row),count(l.label),
            count(*) FILTER(WHERE f.occurred_at < ? OR f.occurred_at >= ?),
            count(*) FILTER(WHERE l.label NOT IN (0,1))
        FROM features f LEFT JOIN ml_labels l USING(source_row) WHERE f.split=?
    """,
        [start, end, split],
    ).fetchone()
    count_labels = db.execute("SELECT count(*) FROM ml_labels").fetchone()[0]
    if not checks[0] or len(set((*checks[:3], count_labels))) != 1 or any(checks[3:]):
        raise ValueError("Feature/label coverage, boundary or uniqueness mismatch")
    table = db.execute(
        """
        SELECT f.source_row,l.label FROM features f JOIN ml_labels l USING(source_row)
        WHERE f.split=? ORDER BY f.source_row
    """,
        [split],
    ).to_arrow_table()
    return table["source_row"].to_numpy(), table["label"].to_numpy()


def experiments() -> list[dict]:
    plan = [
        {"variant": v, "family": f, "setting": 1.0 if f == "lr" else 15}
        for v in VARIANTS
        for f in ("lr", "lightgbm")
    ]
    return plan + [
        {"variant": "history", "family": "lr", "setting": 0.1},
        {"variant": "history", "family": "lightgbm", "setting": 31},
    ]


def make_model(family: str, setting: float, positives: int, negatives: int):
    if family == "lr":
        return LogisticRegression(
            C=setting,
            solver="lbfgs",
            max_iter=200,
            class_weight="balanced",
            random_state=42,
            tol=1e-4,
        )
    return lgb.LGBMClassifier(
        n_estimators=120,
        learning_rate=0.05,
        num_leaves=int(setting),
        max_bin=63,
        min_child_samples=200,
        reg_lambda=1.0,
        n_jobs=2,
        random_state=42,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
        scale_pos_weight=negatives / positives,
    )


def predict(model, matrix: np.ndarray) -> np.ndarray:
    return np.concatenate(
        [
            model.predict_proba(matrix[i : i + 32768])[:, 1]
            for i in range(0, len(matrix), 32768)
        ]
    )


def load_artifact(directory: Path) -> dict:
    """Load only trusted local joblib artifacts; verify integrity before unpickling."""
    metadata = json.loads((directory / "metadata.json").read_text())
    if sha256_file(directory / "model.joblib") != metadata["model_sha256"]:
        raise ValueError("Model artifact checksum mismatch")
    artifact = joblib.load(directory / "model.joblib")
    if artifact["preprocessor"].names != metadata["feature_names"]:
        raise ValueError("Model feature alignment mismatch")
    return artifact


def run(
    features_dir: Path,
    output: Path,
    database_url: str,
    rules_dir: Path = Path("data/rules/rules-v1"),
    schema: str = "mulegraph",
) -> dict:
    start = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output_lock(output.parent):
        if output.exists():
            raise ValueError("Version already exists; do not silently refit validation")
        with tempfile.TemporaryDirectory(prefix=".ml-", dir=output.parent) as temp:
            work = Path(temp)
            published = work / "published"
            published.mkdir()
            db = duckdb.connect()
            try:
                manifest = open_features(db, features_dir)
                db.execute(f"SET temp_directory={literal(str(work / 'spill'))}")
                plan = {
                    "version": VERSION,
                    "seed": 42,
                    "threads": 2,
                    "selection": "highest validation AP; ties prefer earlier run",
                    "threshold": "whole score tiers within 1% validation cap",
                    "experiments": experiments(),
                    "created_at": datetime.now(UTC).isoformat(),
                    "feature_sha256": manifest["file_sha256"],
                    "dataset": manifest["dataset"],
                    "implementation_sha256": sha256_file(Path(__file__)),
                    "inputs_sha256": sha256_file(Path(__file__).with_name("ml.py")),
                    "dependencies": {
                        "numpy": np.__version__,
                        "sklearn": sklearn.__version__,
                        "lightgbm": lgb.__version__,
                        "pyarrow": pa.__version__,
                        "duckdb": duckdb.__version__,
                    },
                }
                write_json(published / "plan.json", plan)
                access, labels, rows = [], {}, {}
                for split in ("train", "validation"):
                    path = work / f"{split}_labels.parquet"
                    access.append(
                        export_labels(database_url, manifest, split, path, schema)
                    )
                    rows[split], labels[split] = aligned_labels(db, split, path)
                    path.unlink()
                if not 0 < labels["train"].sum() < len(labels["train"]):
                    raise ValueError("Training requires both classes")
                ties = tie_keys(rows["validation"], manifest["dataset"]["fingerprint"])
                results = []
                for variant in VARIANTS:
                    prep_start = time.perf_counter()
                    prep = Preprocessor.fit(batches(db, variant, "train"), variant)
                    matrices = {}
                    for split in ("train", "validation"):
                        matrix = np.memmap(
                            work / f"{split}.matrix",
                            mode="w+",
                            dtype="float32",
                            shape=(len(rows[split]), len(prep.names)),
                        )
                        offset = 0
                        for batch in batches(db, variant, split):
                            matrix[offset : offset + len(batch)] = prep.transform(batch)
                            offset += len(batch)
                        if offset != len(matrix):
                            raise ValueError("Matrix coverage mismatch")
                        matrix.flush()
                        matrices[split] = matrix
                    prep_seconds = time.perf_counter() - prep_start
                    for config in (c for c in experiments() if c["variant"] == variant):
                        name = f"{variant}_{config['family']}_{config['setting']}"
                        print(f"Training {name}", flush=True)
                        model = make_model(
                            config["family"],
                            config["setting"],
                            int(labels["train"].sum()),
                            int((labels["train"] == 0).sum()),
                        )
                        fit_start = time.perf_counter()
                        with (
                            warnings.catch_warnings(record=True) as caught,
                            threadpool_limits(limits=2),
                        ):
                            warnings.simplefilter("always")
                            model.fit(matrices["train"], labels["train"])
                        fit_seconds = time.perf_counter() - fit_start
                        score_start = time.perf_counter()
                        with threadpool_limits(limits=2):
                            scores = predict(model, matrices["validation"])
                        prediction_seconds = time.perf_counter() - score_start
                        metrics = evaluate(labels["validation"], scores, ties)
                        dest = published / name
                        dest.mkdir()
                        joblib.dump(
                            {
                                "model": model,
                                "preprocessor": prep,
                                "threshold": metrics["threshold"],
                            },
                            dest / "model.joblib",
                            compress=3,
                        )
                        pq.write_table(
                            pa.table(
                                {"source_row": rows["validation"], "score": scores}
                            ),
                            dest / "validation.parquet",
                            compression="zstd",
                        )
                        result = {
                            "name": name,
                            **config,
                            "metrics": metrics,
                            "model_parameters": model.get_params(),
                            "preprocessing_seconds": prep_seconds,
                            "fit_seconds": fit_seconds,
                            "prediction_seconds": prediction_seconds,
                            "warnings": sorted({str(w.message) for w in caught}),
                            "feature_names": prep.names,
                            "model_sha256": sha256_file(dest / "model.joblib"),
                            "predictions_sha256": sha256_file(
                                dest / "validation.parquet"
                            ),
                        }
                        if config["family"] == "lr":
                            result["coefficients"] = dict(
                                zip(prep.names, model.coef_[0].tolist(), strict=True)
                            )
                            result["iterations"] = model.n_iter_.tolist()
                        else:
                            result["gain_importance"] = dict(
                                zip(
                                    prep.names,
                                    model.booster_.feature_importance(
                                        importance_type="gain"
                                    ).tolist(),
                                    strict=True,
                                )
                            )
                        write_json(dest / "metadata.json", result)
                        loaded = load_artifact(dest)
                        with threadpool_limits(limits=2):
                            reloaded_scores = predict(
                                loaded["model"], matrices["validation"][:32768]
                            )
                        np.testing.assert_array_equal(reloaded_scores, scores[:32768])
                        results.append(result)
                        print(
                            f"Finished {name}: AP={metrics['average_precision']:.6f}, "
                            f"fit={fit_seconds:.1f}s",
                            flush=True,
                        )
                        del model, loaded
                        gc.collect()
                    del matrix, matrices
                    gc.collect()
                    for split in ("train", "validation"):
                        (work / f"{split}.matrix").unlink()
                # Read only the previously frozen VALIDATION predictions.
                calibration = json.loads((rules_dir / "calibration.json").read_text())
                rule_path = rules_dir / "validation_predictions.parquet"
                rule_hash = sha256_file(rule_path)
                if rule_hash != calibration["predictions_sha256"]:
                    raise ValueError("Frozen validation predictions checksum mismatch")
                rule_table = pq.read_table(rule_path).sort_by(
                    [("source_row", "ascending")]
                )
                np.testing.assert_array_equal(
                    rule_table["source_row"].to_numpy(), rows["validation"]
                )
                baselines = {
                    n: evaluate(labels["validation"], rule_table[n].to_numpy(), ties)
                    for n in ("risk_score", "ach_score", "constant_score")
                }
                selected = max(results, key=lambda r: r["metrics"]["average_precision"])
                if (
                    sha256_file(features_dir / "features.parquet")
                    != manifest["file_sha256"]
                ):
                    raise ValueError("Features changed during training")
                report = {
                    "version": VERSION,
                    "experiments": results,
                    "baselines": baselines,
                    "recommended": selected["name"],
                    "label_access": access,
                    "training_positives": int(labels["train"].sum()),
                    "frozen_validation_predictions_sha256": rule_hash,
                    "elapsed_seconds": time.perf_counter() - start,
                    "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    / (1024**2 if sys.platform == "darwin" else 1024),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "feature_sha256_unchanged": manifest["file_sha256"],
                }
                write_json(published / "results.json", report)
                shutil.move(published, output)
                return report
            finally:
                db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/ml/supervised-v1"))
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is required")
    try:
        result = run(args.features_dir, args.output, os.environ["DATABASE_URL"])
    except (ValueError, OSError, psycopg.Error) as exc:
        print(f"Training failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {k: result[k] for k in ("recommended", "elapsed_seconds", "peak_rss_mib")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
