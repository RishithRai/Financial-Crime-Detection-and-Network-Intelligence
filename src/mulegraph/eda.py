"""Read-only, aggregate-only EDA; no per-account features or row exports."""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from mulegraph.schema import sql_file, statement

# Calendar boundaries chosen for development, not optimized against model scores.
SPLITS = (
    ("train", datetime(2022, 9, 1), datetime(2022, 9, 7)),
    ("validation", datetime(2022, 9, 7), datetime(2022, 9, 9)),
    ("test", datetime(2022, 9, 9), datetime(2022, 9, 11)),
    ("stress", datetime(2022, 9, 11), datetime(2022, 9, 19)),
)


def split_for(timestamp: datetime) -> str | None:
    """Naive source event time; entire timestamp groups share a split."""
    if timestamp.tzinfo is not None:
        raise ValueError("Source event timestamps have no known timezone")
    return next((name for name, start, end in SPLITS if start <= timestamp < end), None)


def queries() -> dict[str, str]:
    base = sql_file("eda_base.sql")
    sections = sql_file("eda_queries.sql").split("-- name: ")[1:]
    return {part.split("\n", 1)[0]: base + part.split("\n", 1)[1] for part in sections}


def json_value(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)  # Never round NUMERIC money through a binary float.
    raise TypeError(f"Unsupported JSON value: {type(value)}")


def analyze(
    database_url: str,
    *,
    schema: str = "mulegraph",
    dataset_key: str = "ibm-aml-hi-small-v8",
) -> dict:
    """All queries share one read-only repeatable-read database snapshot."""
    started = time.monotonic()
    sql_queries = queries()
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "query_sha256": hashlib.sha256(
            json.dumps(sql_queries, sort_keys=True).encode()
        ).hexdigest(),
        "split_policy": [
            {"split": name, "starts_at": start.isoformat(), "ends_at": end.isoformat()}
            for name, start, end in SPLITS
        ],
    }
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL work_mem = '32MB'")
        connection.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        connection.execute("SET LOCAL statement_timeout = '15min'")
        connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
        result["database"] = connection.execute(
            "SELECT version() AS version, current_setting('transaction_read_only') "
            "AS read_only, current_setting('transaction_isolation') AS isolation"
        ).fetchone()
        result["dataset"] = connection.execute(
            statement(
                "SELECT dataset_id, dataset_key, fingerprint, status, completed_at "
                "FROM {core}.datasets WHERE dataset_key = %s",
                schema,
            ),
            (dataset_key,),
        ).fetchone()
        if not result["dataset"] or result["dataset"]["status"] != "complete":
            raise ValueError("EDA requires a completed ingested dataset")
        parameters = {
            "dataset_id": result["dataset"]["dataset_id"],
            "splits": json.dumps(result["split_policy"]),
        }
        for name, query in sql_queries.items():
            print(f"Aggregating {name} ...", file=sys.stderr, flush=True)
            result[name] = connection.execute(
                statement(query, schema), parameters
            ).fetchall()
            if name == "totals":
                totals = result[name][0]
                if (
                    totals["transactions"] != totals["labels"]
                    or totals["outside_splits"]
                ):
                    raise ValueError(
                        "Missing labels or transactions outside the split policy"
                    )
        result["accounts"] = connection.execute(
            statement(
                "SELECT count(*) AS accounts FROM {core}.accounts WHERE "
                "dataset_id = %s",
                schema,
            ),
            (parameters["dataset_id"],),
        ).fetchone()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    # Public result is JSON-native and contains only aggregates/provenance.
    return json.loads(json.dumps(result, default=json_value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/eda/hi-small.json"))
    parser.add_argument("--report", type=Path, default=Path("docs/eda_report.md"))
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("Set DATABASE_URL (use uv --env-file .env)")
    try:
        result = analyze(dsn)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        from mulegraph.eda_report import render

        render(result, args.report)
    except (OSError, ValueError, psycopg.Error) as error:
        # PostgreSQL errors may contain connection details; don't print DSNs.
        print(
            f"EDA failed: {type(error).__name__}. Check configuration/database.",
            file=sys.stderr,
        )
        return 1
    print(f"Wrote {args.output} and {args.report}; {result['elapsed_seconds']} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
