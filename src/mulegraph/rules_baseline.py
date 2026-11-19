"""Two-phase, versioned rules baseline: calibrate first, then evaluate holdouts once."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

from mulegraph.eda import SPLITS
from mulegraph.features import literal, output_lock, sha256_file
from mulegraph.rule_metrics import select_threshold, summarize
from mulegraph.rules import (
    ALERT_CAP,
    AMOUNT_MULTIPLIER,
    MAX_SCORE,
    MIN_CURRENCY_ROWS,
    MIN_DIRECTION_HISTORY,
    MIN_HISTORY,
    MIN_HOURLY,
    REASONS,
    SURGE_MULTIPLIER,
    TIE_SALT,
    VERSION,
    WARMUP_SECONDS,
    WEIGHTS,
    profile_training,
    register_profile,
    scoring_sql,
)
from mulegraph.schema import statement

SCORES = ("risk_score", "ach_score", "currency_tail_score", "constant_score")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def runtime_contract() -> dict:
    return {
        "dependencies": {
            "duckdb": duckdb.__version__,
            "pyarrow": pa.__version__,
            "psycopg": psycopg.__version__,
        },
        "splits": [
            (name, start.isoformat(), end.isoformat()) for name, start, end in SPLITS
        ],
    }


def implementation_hash() -> str:
    return hashlib.sha256(
        b"".join(
            Path(__file__).with_name(name).read_bytes()
            for name in ("rules.py", "rule_metrics.py", "rules_baseline.py")
        )
        + json.dumps(runtime_contract(), sort_keys=True).encode()
    ).hexdigest()


def open_features(connection: duckdb.DuckDBPyConnection, directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["definition"]["version"] != "historical-v1":
        raise ValueError("Expected historical-v1 features")
    if sha256_file(directory / "features.parquet") != manifest["file_sha256"]:
        raise ValueError("Historical feature checksum mismatch")
    connection.execute("SET memory_limit='256MB'")
    connection.execute("SET threads=1")
    connection.execute("SET preserve_insertion_order=false")
    connection.read_parquet(str(directory / "features.parquet")).create_view("features")
    return manifest


def export_labels(
    database_url: str,
    manifest: dict,
    split: str,
    path: Path,
    *,
    frozen: bool,
    schema: str = "mulegraph",
) -> dict:
    """Never retrieve test/stress labels before a finalized definition is verified."""
    if split not in {"validation", "test", "stress"}:
        raise ValueError("Training labels are not used by this baseline")
    if split != "validation" and not frozen:
        raise ValueError("Holdout labels are sealed until rules are finalized")
    _, start, end = next(s for s in SPLITS if s[0] == split)
    dataset = manifest["dataset"]
    schema_arrow = pa.schema([("source_row", pa.int64()), ("is_laundering", pa.int8())])
    count = 0
    with psycopg.connect(database_url) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        current = connection.execute(
            statement(
                "SELECT fingerprint, status FROM {core}.datasets WHERE dataset_id=%s "
                "AND dataset_key=%s",
                schema,
            ),
            (dataset["dataset_id"], dataset["dataset_key"]),
        ).fetchone()
        if current != (dataset["fingerprint"], "complete"):
            raise ValueError("Database dataset does not match the feature artifact")
        with (
            connection.cursor(name="evaluation_labels") as cursor,
            pq.ParquetWriter(path, schema_arrow, compression="zstd") as writer,
        ):
            cursor.execute(
                statement(
                    """
                SELECT t.source_row, l.is_laundering FROM {core}.transactions t
                JOIN {labels}.transaction_labels l USING (dataset_id, source_row)
                WHERE t.dataset_id=%s AND t.occurred_at >= %s AND t.occurred_at < %s
                ORDER BY t.source_row
            """,
                    schema,
                ),
                (dataset["dataset_id"], start, end),
            )
            while rows := cursor.fetchmany(16384):
                writer.write_table(
                    pa.Table.from_arrays(
                        [
                            pa.array([r[0] for r in rows], type=pa.int64()),
                            pa.array([r[1] for r in rows], type=pa.int8()),
                        ],
                        schema=schema_arrow,
                    )
                )
                count += len(rows)
    return {
        "split": split,
        "rows": count,
        "labels_sha256": sha256_file(path),
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def score_split(
    connection: duckdb.DuckDBPyConnection, profile: dict, split: str, path: Path
) -> None:
    if split not in {"validation", "test", "stress"}:
        raise ValueError("Training scores would be retrospective; not exported")
    register_profile(connection, profile)
    query = scoring_sql(profile).replace("?", literal(split))
    connection.execute(
        f"COPY ({query}) TO {literal(str(path))} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def joined_evaluation(
    connection: duckdb.DuckDBPyConnection, scores: Path, labels: Path
) -> None:
    connection.read_parquet(str(scores)).create_view("predictions", replace=True)
    connection.read_parquet(str(labels)).create_view("evaluation_labels", replace=True)
    counts = connection.execute("""
        SELECT (SELECT count(*) FROM predictions),
               (SELECT count(DISTINCT source_row) FROM predictions),
               (SELECT count(*) FROM evaluation_labels),
               (SELECT count(DISTINCT source_row) FROM evaluation_labels)
    """).fetchone()
    if len(set(counts)) != 1 or not counts[0]:
        raise ValueError("Prediction/label coverage or uniqueness mismatch")
    connection.execute(
        "CREATE OR REPLACE VIEW evaluation AS SELECT p.*, l.is_laundering "
        "FROM predictions p JOIN evaluation_labels l USING (source_row)"
    )
    if connection.execute("SELECT count(*) FROM evaluation").fetchone()[0] != counts[0]:
        raise ValueError("Prediction/label source identities differ")


def histogram(connection: duckdb.DuckDBPyConnection, score: str) -> list:
    if score not in SCORES:
        raise ValueError("Unknown score")
    return connection.execute(
        f"SELECT {score}, count(*), sum(is_laundering) FROM evaluation GROUP BY {score}"
    ).fetchall()


def evaluate(connection: duckdb.DuckDBPyConnection, threshold: int) -> dict:
    result = {}
    for score in SCORES:
        # Tie order never uses chronology, label, or a model feature.
        top = connection.execute(f"""
            SELECT is_laundering FROM evaluation ORDER BY {score} DESC,
            sha256(dataset_fingerprint || ':' || source_row::VARCHAR || ':' ||
                   {literal(TIE_SALT)}), source_row LIMIT 10000
        """).fetchall()
        result[score] = summarize(
            histogram(connection, score),
            [r[0] for r in top],
            threshold if score == "risk_score" else 1,
        )
    triggers = {}
    for code in REASONS:
        n, p = connection.execute(
            f"SELECT count(*), coalesce(sum(is_laundering),0) "
            f"FROM evaluation WHERE {code}"
        ).fetchone()
        triggers[code] = {
            "triggers": n,
            "positives": p,
            "precision": p / n if n else None,
        }
    result["rule_triggers"] = triggers
    result["coverage_flags"] = {
        name: connection.execute(
            f"SELECT count(*) FROM evaluation WHERE {name}"
        ).fetchone()[0]
        for name in (
            "sender_limited_currency_history",
            "receiver_limited_currency_history",
            "sender_unsupported_currency",
            "receiver_unsupported_currency",
        )
    }
    return result


def publish_predictions(
    connection: duckdb.DuckDBPyConnection,
    scores: Path,
    destination: Path,
    threshold: int,
    rules_sha: str,
) -> None:
    connection.read_parquet(str(scores)).create_view("scored", replace=True)
    connection.execute(f"""
        COPY (SELECT *, risk_score >= {int(threshold)} AS suspicious_alert,
              {literal(VERSION)} AS rules_version, {literal(rules_sha)} AS rules_sha256
              FROM scored ORDER BY occurred_at, source_row)
        TO {literal(str(destination))} (FORMAT PARQUET, COMPRESSION ZSTD)
    """)


def calibrate(
    database_url: str, feature_dir: Path, output: Path, *, schema: str = "mulegraph"
) -> dict:
    if output.exists():
        raise ValueError(
            "Calibration output already exists; never refit a finalized version"
        )
    started = time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix=".calibrate-", dir=output.parent))
    try:
        with duckdb.connect() as connection:
            manifest = open_features(connection, feature_dir)
            profile = profile_training(connection)
            score_split(connection, profile, "validation", working / "scores.parquet")
            labels = export_labels(
                database_url,
                manifest,
                "validation",
                working / "labels.parquet",
                frozen=False,
                schema=schema,
            )
            joined_evaluation(
                connection, working / "scores.parquet", working / "labels.parquet"
            )
            threshold, candidates = select_threshold(
                histogram(connection, "risk_score"), MAX_SCORE, ALERT_CAP
            )
            metrics = evaluate(connection, threshold)
            definition = {
                "version": VERSION,
                "runtime_contract": runtime_contract(),
                "implementation_sha256": implementation_hash(),
                "feature_sha256": manifest["file_sha256"],
                "dataset": manifest["dataset"],
                "profile": profile,
                "weights": WEIGHTS,
                "reasons": REASONS,
                "constants": {
                    "minimum_currency_training_rows": MIN_CURRENCY_ROWS,
                    "minimum_currency_history": MIN_HISTORY,
                    "amount_multiplier": AMOUNT_MULTIPLIER,
                    "surge_multiplier": SURGE_MULTIPLIER,
                    "minimum_hourly_activity": MIN_HOURLY,
                    "direction_minimum_history": MIN_DIRECTION_HISTORY,
                    "warmup_seconds": WARMUP_SECONDS,
                },
                "threshold": threshold,
                "selection": {
                    "objective": "validation F2",
                    "maximum_alert_rate": ALERT_CAP,
                    "tie_policy": "higher threshold",
                    "candidates": candidates,
                },
                "ranking_tie_salt": TIE_SALT,
                "finalized_at": datetime.now(UTC).isoformat(),
            }
            write_json(working / "rules.json", definition)
            rules_sha = sha256_file(working / "rules.json")
            publish_predictions(
                connection,
                working / "scores.parquet",
                working / "validation_predictions.parquet",
                threshold,
                rules_sha,
            )
            result = {
                "validation": metrics,
                "label_access": labels,
                "rules_sha256": rules_sha,
                "predictions_sha256": sha256_file(
                    working / "validation_predictions.parquet"
                ),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
            write_json(working / "calibration.json", result)
        (working / "scores.parquet").unlink()
        (working / "labels.parquet").unlink()
        working.rename(output)
        return result
    finally:
        if working.exists():
            shutil.rmtree(working)


def frozen_definition(output: Path) -> dict:
    if not (output / "rules.json").exists():
        raise ValueError("Finalize calibration before opening holdouts")
    calibration = json.loads((output / "calibration.json").read_text())
    if sha256_file(output / "rules.json") != calibration["rules_sha256"]:
        raise ValueError("Finalized rules have been changed")
    definition = json.loads((output / "rules.json").read_text())
    if definition["implementation_sha256"] != implementation_hash():
        raise ValueError("Implementation differs from finalized rules")
    if (output / "holdout").exists():
        raise ValueError("Holdouts already evaluated; read the saved results")
    return definition


def evaluate_holdouts(
    database_url: str, feature_dir: Path, output: Path, *, schema: str = "mulegraph"
) -> dict:
    definition = frozen_definition(output)  # Before connecting to the label database.
    started = time.monotonic()
    working = Path(tempfile.mkdtemp(prefix=".holdout-", dir=output))
    try:
        result = {
            "rules_sha256": sha256_file(output / "rules.json"),
            "label_access": [],
        }
        with duckdb.connect() as connection:
            manifest = open_features(connection, feature_dir)
            if (
                manifest["file_sha256"] != definition["feature_sha256"]
                or manifest["dataset"] != definition["dataset"]
            ):
                raise ValueError("Holdout features differ from finalized input")
            for split in ("test", "stress"):
                print(f"Evaluating frozen rules on {split} ...", flush=True)
                scores, labels = working / "scores.parquet", working / "labels.parquet"
                score_split(connection, definition["profile"], split, scores)
                access = export_labels(
                    database_url, manifest, split, labels, frozen=True, schema=schema
                )
                result["label_access"].append(access)
                joined_evaluation(connection, scores, labels)
                result[split] = evaluate(connection, definition["threshold"])
                prediction = working / f"{split}_predictions.parquet"
                publish_predictions(
                    connection,
                    scores,
                    prediction,
                    definition["threshold"],
                    result["rules_sha256"],
                )
                result[f"{split}_predictions_sha256"] = sha256_file(prediction)
                scores.unlink()
                labels.unlink()
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            write_json(working / "evaluation.json", result)
        working.rename(output / "holdout")
        return result
    finally:
        if working.exists():
            shutil.rmtree(working)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/rules/rules-v1"))
    parser.add_argument("--phase", choices=("calibrate", "evaluate"), required=True)
    args = parser.parse_args()
    if not (dsn := os.environ.get("DATABASE_URL")):
        parser.error("Set DATABASE_URL using the existing .env")
    try:
        with output_lock(args.output_dir.parent):
            run = calibrate if args.phase == "calibrate" else evaluate_holdouts
            result = run(dsn, args.features_dir, args.output_dir)
    except (ValueError, OSError, psycopg.Error, duckdb.Error) as error:
        detail = (
            str(error)
            if isinstance(error, ValueError)
            else "Check configuration/resources"
        )
        print(
            f"Rules baseline failed: {type(error).__name__}: {detail}", file=sys.stderr
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
