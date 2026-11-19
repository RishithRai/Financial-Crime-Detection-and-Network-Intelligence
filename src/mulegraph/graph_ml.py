"""Two predeclared graph-feature fits; train/validation only, originals immutable."""

import argparse
import gc
import json
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from mulegraph.features import literal, output_lock, sha256_file
from mulegraph.graph_features import COLUMNS, PLAN, peak_rss, verify_graph
from mulegraph.graph_inputs import GraphPreprocessor
from mulegraph.ml import Preprocessor, allowlist, tie_keys
from mulegraph.ml_stabilization import PARAMETERS, dependencies, fit_one, snapshot
from mulegraph.ml_training import aligned_labels, batches, export_labels, load_artifact
from mulegraph.rules_baseline import open_features, write_json

VERSION = "graph-prediction-v1"
SPLITS = ("train", "validation")
CONFIGS = ("history_control", "history_plus_graph")


def graph_batches(db: duckdb.DuckDBPyConnection, split: str):
    if split not in SPLITS:
        raise ValueError("Only training/validation model input permitted")
    nums, cats = allowlist("history")
    columns = ",".join('"' + n + '"' for n in (*nums, *cats, *COLUMNS, "split"))
    reader = db.execute(
        f"SELECT {columns} FROM joined WHERE split=? ORDER BY source_row", [split]
    ).to_arrow_reader(32768)
    for batch in reader:
        yield pa.Table.from_batches([batch])


def implementation() -> dict:
    names = (
        "graph_features.py",
        "graph_ml.py",
        "graph_inputs.py",
        "ml_stabilization.py",
        "ml.py",
        "ml_training.py",
        "features.py",
        "rules_baseline.py",
        "rule_metrics.py",
        "rules.py",
    )
    return {n: sha256_file(Path(__file__).with_name(n)) for n in names}


def freeze(features: Path, graph: Path, path: Path) -> dict:
    directories = [
        features,
        Path("data/ml/lightgbm-stable-v1"),
        Path("data/ml/supervised-v1"),
        Path("data/rules/rules-v1"),
        Path("data/ml/supervised-holdout-v1"),
    ]
    result = {
        "version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "plan_sha256": sha256_file(PLAN),
        "implementation": implementation(),
        "dependencies": dependencies(),
        "lock_sha256": sha256_file(Path("uv.lock")),
        "parameters": PARAMETERS,
        "configurations": list(CONFIGS),
        "originals": {
            str(d / p): h for d in directories for p, h in snapshot(d).items()
        },
        "graph": {str(graph / p): h for p, h in snapshot(graph).items()},
    }
    if not result["graph"] or not result["originals"]:
        raise ValueError("Missing artifacts")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
    return result


def validate(plan: dict) -> None:
    if (
        plan["version"] != VERSION
        or plan["plan_sha256"] != sha256_file(PLAN)
        or plan["implementation"] != implementation()
        or plan["dependencies"] != dependencies()
        or plan["lock_sha256"] != sha256_file(Path("uv.lock"))
        or plan["parameters"] != PARAMETERS
        or plan["configurations"] != list(CONFIGS)
    ):
        raise ValueError("Frozen experiment changed")
    for path, digest in {**plan["originals"], **plan["graph"]}.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError("Input or original artifact changed")


def connect_graph(db: duckdb.DuckDBPyConnection, features: Path, graph: Path) -> dict:
    manifest = open_features(db, features)
    gm = json.loads((graph / "manifest.json").read_text())
    if (
        gm["historical_sha256"] != manifest["file_sha256"]
        or gm["dataset"] != manifest["dataset"]
        or gm["plan_sha256"] != sha256_file(PLAN)
        or gm["implementation_sha256"]
        != sha256_file(Path(__file__).with_name("graph_features.py"))
        or gm["file_sha256"] != sha256_file(graph / "features.parquet")
    ):
        raise ValueError("Graph provenance mismatch")
    verify_graph(db, graph / "features.parquet")
    db.execute(
        "CREATE VIEW joined AS SELECT f.*, "
        + ",".join("g." + n for n in COLUMNS)
        + " FROM features f JOIN graph_features g USING(source_row)"
    )
    return manifest


def matrix(
    db: duckdb.DuckDBPyConnection, prep, split: str, rows: int, path: Path
) -> np.memmap:
    result = np.memmap(path, mode="w+", dtype="float32", shape=(rows, len(prep.names)))
    offset = 0
    for table in graph_batches(db, split):
        result[offset : offset + len(table)] = prep.transform(table)
        offset += len(table)
    if offset != rows:
        raise ValueError("Matrix row count mismatch")
    result.flush()
    return result


def run(
    features: Path,
    graph: Path,
    plan_path: Path,
    output: Path,
    dsn: str,
    schema: str = "mulegraph",
) -> dict:
    began = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output_lock(output.parent):
        if output.exists():
            raise ValueError("Completed experiment cannot be refitted")
        plan = json.loads(plan_path.read_text())
        validate(plan)
        with output.with_suffix(".attempt.json").open("x") as stream:
            json.dump(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "plan_sha256": sha256_file(plan_path),
                },
                stream,
            )
        with tempfile.TemporaryDirectory(
            prefix=".graph-ml-", dir=output.parent
        ) as temp:
            work = Path(temp)
            published = work / "published"
            published.mkdir()
            with duckdb.connect() as db:
                db.execute(f"SET temp_directory={literal(str(work / 'spill'))}")
                manifest = connect_graph(db, features, graph)
                ids, labels, access = {}, {}, []
                # Verify before each permitted export; no holdout export path exists.
                for split in SPLITS:
                    validate(plan)
                    p = work / f"{split}.labels.parquet"
                    access.append(export_labels(dsn, manifest, split, p, schema))
                    ids[split], labels[split] = aligned_labels(db, split, p)
                    p.unlink()
                before = time.perf_counter()
                base = Preprocessor.fit(batches(db, "history", "train"), "history")
                frozen = load_artifact(Path("data/ml/lightgbm-stable-v1/history_none"))
                np.testing.assert_array_equal(base.mean, frozen["preprocessor"].mean)
                np.testing.assert_array_equal(base.scale, frozen["preprocessor"].scale)
                if (
                    base.names != frozen["preprocessor"].names
                    or base.categories != frozen["preprocessor"].categories
                ):
                    raise ValueError("Control preprocessing differs from frozen model")
                added = GraphPreprocessor.fit(base, graph_batches(db, "train"))
                preprocessing = time.perf_counter() - before
                ties = tie_keys(ids["validation"], manifest["dataset"]["fingerprint"])
                old = pq.read_table(
                    "data/ml/lightgbm-stable-v1/history_none/validation.parquet"
                )
                np.testing.assert_array_equal(
                    old["source_row"].to_numpy(), ids["validation"]
                )
                results = []
                for name, prep in zip(CONFIGS, (base, added), strict=True):
                    before = time.perf_counter()
                    matrices = {
                        s: matrix(db, prep, s, len(ids[s]), work / f"{s}.matrix")
                        for s in SPLITS
                    }
                    matrix_seconds = time.perf_counter() - before
                    print(f"Training {name}", flush=True)
                    result = fit_one(
                        {"name": name, "variant": "history", "weight": "none"},
                        prep,
                        matrices,
                        labels,
                        ids["validation"],
                        ties,
                        published / name,
                    )
                    result["matrix_seconds"] = matrix_seconds
                    if name == "history_control":
                        saved = pq.read_table(published / name / "validation.parquet")
                        np.testing.assert_array_equal(
                            saved["score"].to_numpy(), old["score"].to_numpy()
                        )
                        original = json.loads(
                            Path(
                                "data/ml/lightgbm-stable-v1/history_none/metadata.json"
                            ).read_text()
                        )
                        if result["metrics"] != original["metrics"]:
                            raise ValueError("Control metrics do not match original")
                        result["frozen_control_exact"] = True
                    results.append(result)
                    print(
                        f"Finished {name}: "
                        f"AP={result['metrics']['average_precision']:.8f}",
                        flush=True,
                    )
                    del matrices
                    gc.collect()
                    for s in SPLITS:
                        (work / f"{s}.matrix").unlink()
                validate(plan)
                a, b = results
                promising = (
                    b["stable"]
                    and b["metrics"]["average_precision"]
                    > a["metrics"]["average_precision"]
                    and b["metrics"]["budget_1pct"]["recall"]
                    >= a["metrics"]["budget_1pct"]["recall"]
                )
                result = {
                    "version": VERSION,
                    "experiments": results,
                    "exploratory_promising": promising,
                    "selected_model_unchanged": "lightgbm-stable-v1/history_none",
                    "label_access": access,
                    "training_rows": len(labels["train"]),
                    "training_positives": int(labels["train"].sum()),
                    "preprocessing_seconds": preprocessing,
                    "elapsed_seconds": time.perf_counter() - began,
                    "peak_rss_mib": peak_rss(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "plan_sha256": sha256_file(plan_path),
                }
                shutil.copyfile(plan_path, published / "plan.json")
                write_json(published / "results.json", result)
            shutil.move(published, output)
            return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=("freeze", "train"), required=True)
    p.add_argument("--features-dir", type=Path, required=True)
    p.add_argument(
        "--graph-dir", type=Path, default=Path("data/features/graph-features-v1")
    )
    p.add_argument(
        "--plan", type=Path, default=Path("data/ml/graph-prediction-v1.plan.json")
    )
    p.add_argument("--output", type=Path, default=Path("data/ml") / VERSION)
    args = p.parse_args()
    if args.phase == "freeze":
        freeze(args.features_dir, args.graph_dir, args.plan)
    else:
        result = run(
            args.features_dir,
            args.graph_dir,
            args.plan,
            args.output,
            os.environ["DATABASE_URL"],
        )
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in (
                        "elapsed_seconds",
                        "peak_rss_mib",
                        "exploratory_promising",
                    )
                }
            )
        )


if __name__ == "__main__":
    main()
