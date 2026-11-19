"""Milestone 4B: freeze first, score and evaluate development holdouts once."""

import argparse
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
from sklearn.metrics import average_precision_score, roc_auc_score

from mulegraph.eda import SPLITS
from mulegraph.features import definition, output_lock, sha256_file
from mulegraph.ml import allowlist, tie_keys
from mulegraph.ml_inference import score_batch
from mulegraph.ml_stabilization import dependencies, snapshot, validate_plan
from mulegraph.ml_training import load_artifact
from mulegraph.rules_baseline import (
    export_labels,
    implementation_hash,
    open_features,
    score_split,
    write_json,
)

VERSION = "supervised-holdout-v1"
HOLDOUTS = ("test", "stress")
MODELS = {
    "lightgbm": ("stable", "history_none"),
    "logistic": ("original", "history_lr_1.0"),
}
METHODS = ("lightgbm", "logistic", "rules", "ach", "prevalence")


def bounds(split: str) -> tuple[datetime, datetime]:
    if split not in HOLDOUTS:
        raise ValueError("Only test/stress are allowed in this evaluation")
    _, start, end = next(s for s in SPLITS if s[0] == split)
    return start, end


def fingerprints() -> dict[str, str]:
    names = (
        "ml_holdout.py",
        "ml.py",
        "ml_inference.py",
        "ml_training.py",
        "ml_stabilization.py",
        "features.py",
        "feature_state.py",
        "eda.py",
        "rules.py",
        "rule_metrics.py",
        "rules_baseline.py",
    )
    return {n: sha256_file(Path(__file__).with_name(n)) for n in names}


def source_hashes(sources: dict[str, Path]) -> dict:
    return {name: snapshot(path) for name, path in sources.items()}


def feature_batches(db: duckdb.DuckDBPyConnection, split: str):
    if split not in ("validation", *HOLDOUTS):
        raise ValueError("Only validation replay or holdout inference allowed")
    nums, cats = allowlist("history")
    names = (*nums, *cats, "source_row", "occurred_at")
    columns = ",".join('"' + n + '"' for n in names)
    for batch in db.execute(
        f"SELECT {columns} FROM features WHERE split=? ORDER BY source_row", [split]
    ).to_arrow_reader(32768):
        yield pa.Table.from_batches([batch])


def inspect_models(sources: dict[str, Path]) -> tuple[dict, dict]:
    artifacts, metadata = {}, {}
    for method, (root, name) in MODELS.items():
        dest = sources[root] / name
        artifact = load_artifact(dest)
        meta = json.loads((dest / "metadata.json").read_text())
        saved_results = json.loads((sources[root] / "results.json").read_text())
        if meta != next(r for r in saved_results["experiments"] if r["name"] == name):
            raise ValueError("Model metadata differs from completed results")
        if (
            artifact["threshold"] != meta["metrics"]["threshold"]
            or artifact["preprocessor"].variant != "history"
            or artifact["model"].n_features_in_ != len(meta["feature_names"])
            or artifact["model"].get_params() != meta["model_parameters"]
        ):
            raise ValueError("Frozen model/preprocessing/threshold mismatch")
        if sha256_file(dest / "validation.parquet") != meta["predictions_sha256"]:
            raise ValueError("Frozen validation predictions changed")
        artifacts[method], metadata[method] = artifact, meta
    a, b = [artifacts[m]["preprocessor"] for m in MODELS]
    np.testing.assert_array_equal(a.mean, b.mean)
    np.testing.assert_array_equal(a.scale, b.scale)
    if (
        a.categories != b.categories
        or a.names != b.names
        or a.training_rows != b.training_rows
    ):
        raise ValueError("Preprocessing isolation provenance mismatch")
    return artifacts, metadata


def freeze(features: Path, sources: dict[str, Path], destination: Path) -> dict:
    if destination.exists():
        raise ValueError("Freeze already exists; do not overwrite")
    stable_plan = json.loads((sources["stable"] / "plan.json").read_text())
    validate_plan(stable_plan, sources["original"])
    old_plan = json.loads((sources["original"] / "plan.json").read_text())
    for name, key in (
        ("ml.py", "inputs_sha256"),
        ("ml_training.py", "implementation_sha256"),
    ):
        if sha256_file(Path(__file__).with_name(name)) != old_plan[key]:
            raise ValueError("Original supervised implementation changed")
    rule = json.loads((sources["rules"] / "rules.json").read_text())
    calibration = json.loads((sources["rules"] / "calibration.json").read_text())
    if (
        sha256_file(sources["rules"] / "rules.json") != calibration["rules_sha256"]
        or rule["implementation_sha256"] != implementation_hash()
    ):
        raise ValueError("Frozen rules integrity mismatch")
    artifacts, metadata = inspect_models(sources)
    with duckdb.connect() as db:
        manifest = open_features(db, features)
        if (
            definition()["sha256"] != manifest["definition"]["sha256"]
            or manifest["file_sha256"] != stable_plan["feature_sha256"]
            or manifest["file_sha256"] != rule["feature_sha256"]
            or manifest["dataset"] != rule["dataset"]
            or manifest["dataset"] != stable_plan["dataset"]
        ):
            raise ValueError("Historical provenance differs from frozen models/rules")
        count = db.execute(
            "SELECT count(*) FROM features WHERE split='train'"
        ).fetchone()[0]
        if any(a["preprocessor"].training_rows != count for a in artifacts.values()):
            raise ValueError("Training population mismatch")
        replay = {}
        for method, artifact in artifacts.items():
            root, name = MODELS[method]
            saved = pq.read_table(sources[root] / name / "validation.parquet")
            offset = 0
            for batch in feature_batches(db, "validation"):
                scores, _ = score_batch(artifact, batch)
                np.testing.assert_array_equal(
                    scores, saved["score"].slice(offset, len(batch)).to_numpy()
                )
                np.testing.assert_array_equal(
                    batch["source_row"].to_numpy(),
                    saved["source_row"].slice(offset, len(batch)).to_numpy(),
                )
                offset += len(batch)
            if offset != len(saved):
                raise ValueError("Validation replay coverage mismatch")
            replay[method] = offset
    thresholds = {m: a["threshold"] for m, a in artifacts.items()}
    thresholds.update(
        rules=rule["threshold"],
        ach=calibration["validation"]["ach_score"]["threshold"],
        prevalence=calibration["validation"]["constant_score"]["threshold"],
    )
    frozen = {
        "version": VERSION,
        "frozen_at": datetime.now(UTC).isoformat(),
        "selected": "lightgbm-stable-v1/history_none",
        "comparison": "supervised-v1/history_lr_1.0",
        "thresholds": thresholds,
        "constant_score": 0.0,
        "sources_sha256": source_hashes(sources),
        "implementation": fingerprints(),
        "dependencies": dependencies(),
        "uv_lock_sha256": sha256_file(Path("uv.lock")),
        "feature_sha256": manifest["file_sha256"],
        "dataset": manifest["dataset"],
        "feature_manifest_sha256": sha256_file(features / "manifest.json"),
        "validation_replay_rows": replay,
        "splits": {s: [d.isoformat() for d in bounds(s)] for s in HOLDOUTS},
        "policy": "No fitting, selection or threshold changes. "
        "Grouped AP; tied-rank AUC; "
        "descending score then frozen identity-hash tie order; K capped at population; "
        "budget=floor(N/100). Constant score AP equals split prevalence; no pooling.",
        "description": "Development holdouts: previous EDA/rules inspection "
        "and reused validation.",
        "descriptive_groups": ["payment_format", "day"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as stream:
        stream.write(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    return frozen


def validate_freeze(path: Path, features: Path, sources: dict[str, Path]) -> dict:
    frozen = json.loads(path.read_text())
    if (
        frozen["version"] != VERSION
        or frozen["implementation"] != fingerprints()
        or frozen["sources_sha256"] != source_hashes(sources)
        or frozen["dependencies"] != dependencies()
        or frozen["uv_lock_sha256"] != sha256_file(Path("uv.lock"))
        or frozen["feature_sha256"] != sha256_file(features / "features.parquet")
        or frozen["feature_manifest_sha256"] != sha256_file(features / "manifest.json")
    ):
        raise ValueError("Frozen input integrity mismatch")
    artifacts, _ = inspect_models(sources)
    rule = json.loads((sources["rules"] / "rules.json").read_text())
    calibration = json.loads((sources["rules"] / "calibration.json").read_text())
    actual = {m: a["threshold"] for m, a in artifacts.items()}
    actual.update(
        rules=rule["threshold"],
        ach=calibration["validation"]["ach_score"]["threshold"],
        prevalence=calibration["validation"]["constant_score"]["threshold"],
    )
    if (
        actual != frozen["thresholds"]
        or frozen["selected"] != "lightgbm-stable-v1/history_none"
        or frozen["constant_score"] != 0.0
        or frozen["splits"] != {s: [d.isoformat() for d in bounds(s)] for s in HOLDOUTS}
    ):
        raise ValueError("Frozen policy mismatch")
    return frozen


def export_holdout(
    database_url: str,
    split: str,
    path: Path,
    freeze_path: Path,
    features: Path,
    sources: dict[str, Path],
    schema: str = "mulegraph",
) -> dict:
    bounds(split)
    frozen = validate_freeze(freeze_path, features, sources)
    verified_at = datetime.now(UTC).isoformat()
    manifest = json.loads((features / "manifest.json").read_text())
    if manifest["dataset"] != frozen["dataset"]:
        raise ValueError("Frozen dataset mismatch")
    access = export_labels(
        database_url, manifest, split, path, frozen=True, schema=schema
    )
    return {
        **access,
        "freeze_verified_at": verified_at,
        "freeze_sha256": sha256_file(freeze_path),
    }


def aligned_labels(ids: np.ndarray, table: pa.Table) -> np.ndarray:
    table = table.sort_by([("source_row", "ascending")])
    actual = table["source_row"].to_numpy()
    if (
        len(ids) == 0
        or len(ids) != len(actual)
        or len(np.unique(ids)) != len(ids)
        or len(np.unique(actual)) != len(actual)
        or not np.array_equal(ids, actual)
    ):
        raise ValueError("Prediction/label coverage or identity mismatch")
    labels = table["is_laundering"].to_numpy()
    if not np.isin(labels, [0, 1]).all():
        raise ValueError("Invalid evaluation label")
    return labels


def metrics(
    y: np.ndarray, scores: np.ndarray, ties: np.ndarray, threshold: float
) -> dict:
    """No threshold search: apply the supplied frozen policy verbatim."""
    if (
        len(y) == 0
        or len(y) != len(scores)
        or len(y) != len(ties)
        or not np.isin(y, [0, 1]).all()
        or not np.isfinite(scores).all()
        or not np.isfinite(threshold)
    ):
        raise ValueError("Invalid metric inputs")
    y, scores = np.asarray(y), np.asarray(scores, dtype=np.float64)
    ranked = y[np.lexsort((ties, -scores))]
    n, positives = len(y), int(y.sum())

    def at(k: int) -> dict:
        effective = min(k, n)
        tp = int(ranked[:effective].sum())
        return {
            "requested_k": k,
            "k": effective,
            "tp": tp,
            "precision": tp / effective if effective else None,
            "recall": tp / positives if positives else None,
        }

    alert = scores >= threshold
    tp, fp = int(y[alert].sum()), int((1 - y[alert]).sum())
    fn, tn = positives - tp, n - positives - fp
    ap = float(average_precision_score(y, scores)) if positives else None
    return {
        "rows": n,
        "positives": positives,
        "prevalence": positives / n,
        "ap": ap,
        "ap_over_prevalence": ap / (positives / n) if positives else None,
        "roc_auc": float(roc_auc_score(y, scores)) if 0 < positives < n else None,
        "at_100": at(100),
        "at_1000": at(1000),
        "budget": at(n // 100),
        "threshold": threshold,
        "alerts": tp + fp,
        "alert_rate": (tp + fp) / n,
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "alert_precision": tp / (tp + fp) if tp + fp else None,
        "alert_recall": tp / positives if positives else None,
        "unique_scores": len(np.unique(scores)),
        "exact_zero": int((scores == 0).sum()),
        "exact_one": int((scores == 1).sum()),
    }


def predict_split(
    db: duckdb.DuckDBPyConnection,
    split: str,
    sources: dict[str, Path],
    frozen: dict,
    working: Path,
) -> pa.Table:
    start, end = bounds(split)
    artifacts, _ = inspect_models(sources)
    ids, scores = [], {m: [] for m in MODELS}
    for batch in feature_batches(db, split):
        times = batch["occurred_at"].to_pylist()
        if any(t < start or t >= end for t in times):
            raise ValueError("Feature split has invalid time boundary")
        ids.append(batch["source_row"].to_numpy())
        for method, artifact in artifacts.items():
            score, _ = score_batch(artifact, batch)
            scores[method].append(score)
    if not ids:
        raise ValueError("Empty evaluation split")
    rows = np.concatenate(ids)
    if len(np.unique(rows)) != len(rows):
        raise ValueError("Duplicate prediction identities")
    rule = json.loads((sources["rules"] / "rules.json").read_text())
    path = working / f"{split}_rule_scratch.parquet"
    score_split(db, rule["profile"], split, path)
    rule_table = pq.read_table(path).sort_by([("source_row", "ascending")])
    np.testing.assert_array_equal(rule_table["source_row"].to_numpy(), rows)
    result = {
        "source_row": rows,
        **{m: np.concatenate(v) for m, v in scores.items()},
        "rules": rule_table["risk_score"].to_numpy(),
        "ach": rule_table["ach_score"].to_numpy(),
        "prevalence": np.full(len(rows), frozen["constant_score"]),
    }
    path.unlink()
    return pa.table(result)


def descriptive(db: duckdb.DuckDBPyConnection) -> dict:
    """Fixed label-free shift summaries; amounts separated by payment currency."""
    result = {}
    for split in ("train", "validation", *HOLDOUTS):
        groups = {}
        for column in ("payment_format", "payment_currency", "receiving_currency"):
            groups[column] = db.execute(
                f"SELECT {column},count(*) FROM features "
                f"WHERE split=? GROUP BY {column} ORDER BY {column}",
                [split],
            ).fetchall()
        groups["history"] = db.execute(
            """SELECT count(*),
            count(*) FILTER(WHERE sender_history_count=0),
            count(*) FILTER(WHERE receiver_history_count=0),
            median(sender_history_count), median(sender_currency_history_count),
            median(sender_seconds_since_last), median(sender_history_age_seconds)
            FROM features WHERE split=?""",
            [split],
        ).fetchone()
        groups["amount_by_currency"] = [
            [str(v) for v in row]
            for row in db.execute(
                """
            SELECT payment_currency,count(*),quantile_disc(amount_paid,.5),
                quantile_disc(amount_paid,.99)
            FROM features WHERE split=?
            GROUP BY payment_currency ORDER BY payment_currency
        """,
                [split],
            ).fetchall()
        ]
        result[split] = groups
    return result


def group_outcomes(
    db: duckdb.DuckDBPyConnection,
    split: str,
    table: pa.Table,
    labels: np.ndarray,
    thresholds: dict,
) -> dict:
    db.register(
        "holdout_outcomes", table.append_column("evaluation_label", pa.array(labels))
    )
    result = {}
    for name, expression in (
        ("payment_format", "f.payment_format"),
        ("day", "CAST(f.occurred_at AS DATE)"),
    ):
        rows = db.execute(
            f"""SELECT {expression},count(*),sum(evaluation_label),
            sum((lightgbm >= ?)::INT),sum((lightgbm >= ? AND evaluation_label=1)::INT),
            sum((logistic >= ?)::INT),sum((logistic >= ? AND evaluation_label=1)::INT)
            FROM features f JOIN holdout_outcomes p USING(source_row) WHERE f.split=?
            GROUP BY 1 ORDER BY 1""",
            [thresholds["lightgbm"]] * 2 + [thresholds["logistic"]] * 2 + [split],
        ).fetchall()
        result[name] = [[str(row[0]), *row[1:]] for row in rows]
    db.unregister("holdout_outcomes")
    return result


def run(
    features: Path,
    sources: dict[str, Path],
    freeze_path: Path,
    output: Path,
    database_url: str,
    schema: str = "mulegraph",
) -> dict:
    started = time.perf_counter()
    with output_lock(output.parent):
        if output.exists():
            raise ValueError("Evaluation already complete; use saved results")
        frozen = validate_freeze(freeze_path, features, sources)
        digest = sha256_file(freeze_path)
        with output.with_suffix(".attempt.json").open("x") as stream:
            json.dump(
                {"freeze_sha256": digest, "started_at": datetime.now(UTC).isoformat()},
                stream,
            )
        with tempfile.TemporaryDirectory(
            prefix=".ml-holdout-", dir=output.parent
        ) as temp:
            work = Path(temp)
            published = work / "published"
            published.mkdir()
            shutil.copyfile(freeze_path, published / "freeze.json")
            report = {
                "version": VERSION,
                "freeze_sha256": digest,
                "selected": frozen["selected"],
                "splits": {},
                "label_access": [],
                "prediction_sha256": {},
            }
            with duckdb.connect() as db:
                open_features(db, features)
                # Produce BOTH split prediction files before retrieving any labels.
                for split in HOLDOUTS:
                    table = predict_split(db, split, sources, frozen, work)
                    path = published / f"{split}.parquet"
                    pq.write_table(table, path, compression="zstd")
                    report["prediction_sha256"][split] = sha256_file(path)
                    print(
                        f"Scored frozen models on {split}: {len(table):,} rows",
                        flush=True,
                    )
                report["shift"] = descriptive(db)
                for split in HOLDOUTS:
                    if sha256_file(freeze_path) != digest:
                        raise ValueError("Freeze file changed during evaluation")
                    path = work / "labels.parquet"
                    access = export_holdout(
                        database_url,
                        split,
                        path,
                        freeze_path,
                        features,
                        sources,
                        schema,
                    )
                    report["label_access"].append(access)
                    table = pq.read_table(published / f"{split}.parquet")
                    ids = table["source_row"].to_numpy()
                    y = aligned_labels(ids, pq.read_table(path))
                    path.unlink()
                    ties = tie_keys(ids, frozen["dataset"]["fingerprint"])
                    result = {
                        m: metrics(
                            y, table[m].to_numpy(), ties, frozen["thresholds"][m]
                        )
                        for m in METHODS
                    }
                    report["splits"][split] = {
                        "metrics": result,
                        "groups": group_outcomes(
                            db, split, table, y, frozen["thresholds"]
                        ),
                    }
            validate_freeze(freeze_path, features, sources)
            report.update(
                elapsed_seconds=time.perf_counter() - started,
                completed_at=datetime.now(UTC).isoformat(),
                originals_unchanged=True,
            )
            write_json(published / "results.json", report)
            shutil.move(published, output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("freeze", "evaluate"), required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--original", type=Path, default=Path("data/ml/supervised-v1"))
    parser.add_argument(
        "--stable", type=Path, default=Path("data/ml/lightgbm-stable-v1")
    )
    parser.add_argument("--rules", type=Path, default=Path("data/rules/rules-v1"))
    parser.add_argument(
        "--freeze", type=Path, default=Path("docs/ml_holdout_freeze_v1.json")
    )
    parser.add_argument("--output", type=Path, default=Path("data/ml") / VERSION)
    args = parser.parse_args()
    sources = {n: getattr(args, n) for n in ("original", "stable", "rules")}
    if args.phase == "freeze":
        freeze(args.features_dir, sources, args.freeze)
    else:
        if not os.environ.get("DATABASE_URL"):
            parser.error("DATABASE_URL is required")
        result = run(
            args.features_dir,
            sources,
            args.freeze,
            args.output,
            os.environ["DATABASE_URL"],
        )
        print(json.dumps({k: result[k] for k in ("selected", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
