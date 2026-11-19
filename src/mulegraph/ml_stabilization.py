"""Fixed Milestone 4A.1 experiment: train/validation only, immutable originals."""

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
from importlib.metadata import version
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

from mulegraph.features import literal, output_lock, sha256_file
from mulegraph.ml import Preprocessor, evaluate, tie_keys
from mulegraph.ml_training import aligned_labels, batches, export_labels, load_artifact
from mulegraph.rules_baseline import open_features, write_json

VERSION = "lightgbm-stable-v1"
VARIANTS = ("history", "history_no_format")
WEIGHTS = ("none", "sqrt", "full")
PARAMETERS = {
    "objective": "binary",
    "n_estimators": 240,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "max_depth": 6,
    "max_bin": 63,
    "min_child_samples": 200,
    "min_child_weight": 10.0,
    "reg_alpha": 1.0,
    "reg_lambda": 10.0,
    "max_delta_step": 2.0,
    "random_state": 42,
    "n_jobs": 2,
    "deterministic": True,
    "force_col_wise": True,
    "verbosity": -1,
}


def configurations() -> list[dict]:
    return [
        {"name": f"{v}_{w}", "variant": v, "weight": w}
        for v in VARIANTS
        for w in WEIGHTS
    ]


def implementation() -> dict[str, str]:
    names = (
        "ml_stabilization.py",
        "ml.py",
        "ml_training.py",
        "features.py",
        "feature_state.py",
        "rules_baseline.py",
        "rule_metrics.py",
        "rules.py",
        "eda.py",
    )
    return {n: sha256_file(Path(__file__).with_name(n)) for n in names}


def snapshot(directory: Path) -> dict[str, str]:
    return {
        str(p.relative_to(directory)): sha256_file(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def dependencies() -> dict[str, str]:
    return {
        n: version(n)
        for n in (
            "lightgbm",
            "numpy",
            "scikit-learn",
            "pyarrow",
            "duckdb",
            "joblib",
            "threadpoolctl",
        )
    }


def create_plan(path: Path, features: Path, original: Path) -> dict:
    """Persist the fixed grid and selection criteria before opening any labels."""
    manifest = json.loads((features / "manifest.json").read_text())
    if sha256_file(features / "features.parquet") != manifest["file_sha256"]:
        raise ValueError("Feature checksum mismatch")
    plan = {
        "version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "experiments": configurations(),
        "parameters": PARAMETERS,
        "weighting": "1, sqrt(train negatives/positives), train negatives/positives",
        "selection": "Highest AP among stable candidates; ties follow plan order. "
        "Recommend over frozen LR only if AP is strictly higher and 1% budget "
        "recall is no lower; otherwise retain LR. No early stopping or grid expansion.",
        "stability": "Finite train/validation margins; abs(raw)<=30; "
        "zero exact probability endpoints; <=0.1% scores within 1e-12 of endpoints; "
        "post-initial tree leaves bounded by learning_rate*max_delta_step; "
        "finite training loss; exact full-validation reload equality.",
        "threshold": "Largest complete score tiers within 1% validation cap",
        "splits": {
            "train": ["2022-09-01", "2022-09-07"],
            "validation": ["2022-09-07", "2022-09-09"],
        },
        "feature_sha256": manifest["file_sha256"],
        "dataset": manifest["dataset"],
        "original_sha256": snapshot(original),
        "implementation": implementation(),
        "dependencies": dependencies(),
        "uv_lock_sha256": sha256_file(Path("uv.lock")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return plan


def validate_plan(plan: dict, original: Path) -> None:
    if (
        plan["version"] != VERSION
        or plan["experiments"] != configurations()
        or plan["parameters"] != PARAMETERS
        or plan["implementation"] != implementation()
        or plan["dependencies"] != dependencies()
        or plan["uv_lock_sha256"] != sha256_file(Path("uv.lock"))
        or plan["original_sha256"] != snapshot(original)
    ):
        raise ValueError("Plan, implementation, dependencies or originals changed")


def make_model(weight: str, positives: int, negatives: int) -> lgb.LGBMClassifier:
    if weight not in WEIGHTS or positives <= 0 or negatives <= 0:
        raise ValueError("Expected approved weight policy and both training classes")
    ratio = negatives / positives
    scale = {"none": 1.0, "sqrt": ratio**0.5, "full": ratio}[weight]
    return lgb.LGBMClassifier(**PARAMETERS, scale_pos_weight=scale)


def score_diagnostics(scores: np.ndarray, raw: np.ndarray) -> dict:
    if (
        len(scores) == 0
        or len(scores) != len(raw)
        or not np.isfinite(scores).all()
        or not np.isfinite(raw).all()
        or (scores < 0).any()
        or (scores > 1).any()
    ):
        raise ValueError("Invalid predictions")
    _, counts = np.unique(scores, return_counts=True)
    return {
        "rows": len(scores),
        "raw_min": float(raw.min()),
        "raw_max": float(raw.max()),
        "raw_quantiles": np.quantile(raw, [0, 0.01, 0.5, 0.99, 1]).tolist(),
        "exact_zero": int((scores == 0).sum()),
        "exact_one": int((scores == 1).sum()),
        "near_endpoint": int(((scores <= 1e-12) | (scores >= 1 - 1e-12)).sum()),
        "unique_scores": len(counts),
        "largest_tie": int(counts.max()),
        "top_tie": int((scores == scores.max()).sum()),
    }


def stable(diagnostics: dict) -> bool:
    return (
        max(abs(diagnostics["raw_min"]), abs(diagnostics["raw_max"])) <= 30
        and diagnostics["exact_zero"] == diagnostics["exact_one"] == 0
        and diagnostics["near_endpoint"] / diagnostics["rows"] <= 0.001
    )


def raw_predict(model: lgb.LGBMClassifier, matrix: np.ndarray) -> np.ndarray:
    return np.concatenate(
        [
            model.booster_.predict(matrix[i : i + 32768], raw_score=True)
            for i in range(0, len(matrix), 32768)
        ]
    )


def leaf_values(node: dict) -> list[float]:
    if "leaf_value" in node:
        return [node["leaf_value"]]
    return leaf_values(node["left_child"]) + leaf_values(node["right_child"])


def recommend(results: list[dict], baseline: dict) -> str:
    candidates = [r for r in results if r["stable"]]
    if candidates:
        best = max(candidates, key=lambda r: r["metrics"]["average_precision"] or -1)
        if (
            best["metrics"]["average_precision"] is not None
            and best["metrics"]["average_precision"] > baseline["average_precision"]
            and best["metrics"]["budget_1pct"]["recall"]
            >= baseline["budget_1pct"]["recall"]
        ):
            return best["name"]
    return "history_lr_1.0"


def build_matrix(
    db: duckdb.DuckDBPyConnection, prep: Preprocessor, split: str, rows: int, path: Path
) -> np.memmap:
    matrix = np.memmap(path, mode="w+", dtype="float32", shape=(rows, len(prep.names)))
    offset = 0
    for batch in batches(db, prep.variant, split):
        matrix[offset : offset + len(batch)] = prep.transform(batch)
        offset += len(batch)
    if offset != rows:
        raise ValueError("Matrix coverage mismatch")
    matrix.flush()
    return matrix


def fit_one(
    config: dict,
    prep: Preprocessor,
    matrices: dict,
    labels: dict,
    rows: np.ndarray,
    ties: np.ndarray,
    destination: Path,
) -> dict:
    model = make_model(
        config["weight"], int(labels["train"].sum()), int((labels["train"] == 0).sum())
    )
    history = {}
    start = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=2):
        warnings.simplefilter("always")
        model.fit(
            matrices["train"],
            labels["train"],
            eval_set=[(matrices["train"], labels["train"])],
            eval_names=["train"],
            eval_metric="binary_logloss",
            callbacks=[lgb.record_evaluation(history)],
        )
    fit_seconds = time.perf_counter() - start
    diagnostics = {}
    start = time.perf_counter()
    with threadpool_limits(limits=2):
        for split in ("train", "validation"):
            raw = raw_predict(model, matrices[split])
            scores = model.predict_proba(matrices[split])[:, 1]
            diagnostics[split] = score_diagnostics(scores, raw)
    prediction_seconds = time.perf_counter() - start
    metrics = evaluate(labels["validation"], scores, ties)
    trees = model.booster_.dump_model()["tree_info"]
    # The first tree incorporates the initial intercept; subsequent trees do not.
    max_update = max(
        (abs(v) for t in trees[1:] for v in leaf_values(t["tree_structure"])),
        default=0.0,
    )
    loss = history["train"]["binary_logloss"]
    bounded = (
        max_update <= PARAMETERS["learning_rate"] * PARAMETERS["max_delta_step"] + 1e-10
    )
    destination.mkdir()
    joblib.dump(
        {"model": model, "preprocessor": prep, "threshold": metrics["threshold"]},
        destination / "model.joblib",
        compress=3,
    )
    pq.write_table(
        pa.table({"source_row": rows, "score": scores}),
        destination / "validation.parquet",
        compression="zstd",
    )
    result = {
        **config,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "model_parameters": model.get_params(),
        "feature_names": prep.names,
        "training_rows": prep.training_rows,
        "fit_seconds": fit_seconds,
        "prediction_seconds": prediction_seconds,
        "warnings": sorted({str(w.message) for w in caught}),
        "training_logloss": loss,
        "trees": len(trees),
        "max_post_initial_leaf": max_update,
        "leaf_bound_passed": bounded,
        "gain_importance": dict(
            zip(
                prep.names,
                model.booster_.feature_importance(importance_type="gain").tolist(),
                strict=True,
            )
        ),
        "model_sha256": sha256_file(destination / "model.joblib"),
        "predictions_sha256": sha256_file(destination / "validation.parquet"),
    }
    write_json(destination / "metadata.json", result)
    loaded = load_artifact(destination)
    with threadpool_limits(limits=2):
        reloaded = loaded["model"].predict_proba(matrices["validation"])[:, 1]
    np.testing.assert_array_equal(reloaded, scores)
    saved = pq.read_table(destination / "validation.parquet")
    assert saved.column_names == ["source_row", "score"]
    np.testing.assert_array_equal(saved["source_row"].to_numpy(), rows)
    np.testing.assert_array_equal(saved["score"].to_numpy(), scores)
    assert int((reloaded >= loaded["threshold"]).sum()) == metrics["alerts"]
    result["reload_exact"] = True
    result["stable"] = (
        all(stable(d) for d in diagnostics.values())
        and bounded
        and bool(np.isfinite(loss).all())
    )
    write_json(destination / "metadata.json", result)
    return result


def run(
    features: Path,
    original: Path,
    plan_path: Path,
    output: Path,
    database_url: str,
    schema: str = "mulegraph",
) -> dict:
    start = time.perf_counter()
    with output_lock(output.parent):
        if output.exists():
            raise ValueError("Version already exists; refusing refit")
        plan = json.loads(plan_path.read_text())
        validate_plan(plan, original)
        # A durable attempt record prevents silent re-search after a failed run.
        attempt = output.with_suffix(".attempt.json")
        with attempt.open("x") as stream:
            json.dump(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "plan_sha256": sha256_file(plan_path),
                },
                stream,
            )
        with tempfile.TemporaryDirectory(prefix=".stable-", dir=output.parent) as temp:
            work = Path(temp)
            published = work / "published"
            published.mkdir()
            with duckdb.connect() as db:
                manifest = open_features(db, features)
                if (
                    manifest["file_sha256"] != plan["feature_sha256"]
                    or manifest["dataset"] != plan["dataset"]
                ):
                    raise ValueError("Feature identity differs from plan")
                db.execute(f"SET temp_directory={literal(str(work / 'spill'))}")
                shutil.copyfile(plan_path, published / "plan.json")
                labels, ids, access = {}, {}, []
                for split in ("train", "validation"):
                    path = work / f"{split}_labels.parquet"
                    access.append(
                        export_labels(database_url, manifest, split, path, schema)
                    )
                    ids[split], labels[split] = aligned_labels(db, split, path)
                    path.unlink()
                if not 0 < labels["validation"].sum() < len(labels["validation"]):
                    raise ValueError("Validation requires both classes for comparison")
                ties = tie_keys(ids["validation"], manifest["dataset"]["fingerprint"])
                old_results = json.loads((original / "results.json").read_text())
                baseline_meta = next(
                    r
                    for r in old_results["experiments"]
                    if r["name"] == "history_lr_1.0"
                )
                path = original / "history_lr_1.0" / "validation.parquet"
                if sha256_file(path) != baseline_meta["predictions_sha256"]:
                    raise ValueError("Frozen LR prediction checksum mismatch")
                baseline_table = pq.read_table(path)
                np.testing.assert_array_equal(
                    baseline_table["source_row"].to_numpy(), ids["validation"]
                )
                baseline = evaluate(
                    labels["validation"], baseline_table["score"].to_numpy(), ties
                )
                if baseline != baseline_meta["metrics"]:
                    raise ValueError("Frozen LR validation metrics changed")
                results, preprocessing = [], {}
                for variant in VARIANTS:
                    before = time.perf_counter()
                    prep = Preprocessor.fit(batches(db, variant, "train"), variant)
                    old = load_artifact(original / f"{variant}_lr_1.0")["preprocessor"]
                    np.testing.assert_array_equal(prep.mean, old.mean)
                    np.testing.assert_array_equal(prep.scale, old.scale)
                    assert prep.categories == old.categories and prep.names == old.names
                    matrices = {
                        s: build_matrix(db, prep, s, len(ids[s]), work / f"{s}.matrix")
                        for s in ("train", "validation")
                    }
                    preprocessing[variant] = time.perf_counter() - before
                    for config in (
                        c for c in plan["experiments"] if c["variant"] == variant
                    ):
                        print(f"Training {config['name']}", flush=True)
                        result = fit_one(
                            config,
                            prep,
                            matrices,
                            labels,
                            ids["validation"],
                            ties,
                            published / config["name"],
                        )
                        results.append(result)
                        print(
                            f"Finished {config['name']}: "
                            f"AP={result['metrics']['average_precision']:.6f}; "
                            f"stable={result['stable']}",
                            flush=True,
                        )
                    del matrices
                    gc.collect()
                    for split in ("train", "validation"):
                        (work / f"{split}.matrix").unlink()
                validate_plan(plan, original)
                if sha256_file(features / "features.parquet") != plan["feature_sha256"]:
                    raise ValueError("Historical features changed")
                report = {
                    "version": VERSION,
                    "experiments": results,
                    "frozen_lr": baseline,
                    "recommended": recommend(results, baseline),
                    "label_access": access,
                    "training_positives": int(labels["train"].sum()),
                    "training_rows": len(labels["train"]),
                    "preprocessing_seconds": preprocessing,
                    "elapsed_seconds": time.perf_counter() - start,
                    "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    / (1024**2 if sys.platform == "darwin" else 1024),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "plan_sha256": sha256_file(plan_path),
                    "originals_unchanged": True,
                    "feature_sha256": plan["feature_sha256"],
                }
                write_json(published / "results.json", report)
            shutil.move(published, output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("plan", "train"), required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--original", type=Path, default=Path("data/ml/supervised-v1"))
    parser.add_argument(
        "--plan", type=Path, default=Path("docs/ml_stabilization_plan_v1.json")
    )
    parser.add_argument("--output", type=Path, default=Path("data/ml") / VERSION)
    args = parser.parse_args()
    if args.phase == "plan":
        create_plan(args.plan, args.features_dir, args.original)
    else:
        if not os.environ.get("DATABASE_URL"):
            parser.error("DATABASE_URL is required")
        result = run(
            args.features_dir,
            args.original,
            args.plan,
            args.output,
            os.environ["DATABASE_URL"],
        )
        print(json.dumps({k: result[k] for k in ("recommended", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
