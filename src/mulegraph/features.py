"""Versioned historical features from label-free PostgreSQL transaction streams."""

import argparse
import fcntl
import hashlib
import heapq
import json
import os
import platform
import resource
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

from mulegraph.eda import SPLITS
from mulegraph.feature_state import Event, account_features
from mulegraph.schema import sql_file, statement

VERSION = "historical-v1"
BATCH_SIZE = 8192
MONEY = pa.decimal128(38, 9)
COUNTS = [
    "history_count",
    "sent_count",
    "received_count",
    "count_1h",
    "count_24h",
    "unique_counterparties",
    "currency_history_count",
    "currency_count_1h",
    "currency_count_24h",
]
FLOATS = [
    "seconds_since_last",
    "history_age_seconds",
    "mean_gap_seconds",
    "frequency_1h",
    "frequency_24h",
]
SUMS = ["currency_history_sum", "currency_sum_1h", "currency_sum_24h"]
HISTORY = COUNTS + FLOATS + SUMS + ["last_activity_at"]
CURRENT = [
    "from_bank_id",
    "from_account",
    "to_bank_id",
    "to_account",
    "amount_paid",
    "amount_received",
    "payment_currency",
    "receiving_currency",
    "payment_format",
    "self_transfer",
    "cross_currency",
]
NULLABLE_HISTORY = {
    "last_activity_at",
    "seconds_since_last",
    "history_age_seconds",
    "mean_gap_seconds",
}


def arrow_schema(role: str) -> pa.Schema:
    fields = [
        ("source_row", pa.int64()),
        ("occurred_at", pa.timestamp("us")),
        ("split", pa.string()),
    ]
    fields += [(name, pa.int64()) for name in COUNTS]
    fields += [(name, pa.float64()) for name in FLOATS]
    fields += [(name, MONEY) for name in SUMS]
    fields += [("last_activity_at", pa.timestamp("us"))]
    if role == "sender":
        fields += [
            (
                name,
                MONEY
                if name.startswith("amount_")
                else pa.bool_()
                if name in {"self_transfer", "cross_currency"}
                else pa.string(),
            )
            for name in CURRENT
        ]
    return pa.schema(fields)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def definition() -> dict:
    dependencies = {name: version(name) for name in ("psycopg", "pyarrow", "duckdb")}
    source = b"".join(
        Path(__file__).with_name(name).read_bytes()
        for name in ("features.py", "feature_state.py")
    )
    source += sql_file("features_sender.sql").encode()
    source += sql_file("features_receiver.sql").encode()
    policy = [(name, start.isoformat(), end.isoformat()) for name, start, end in SPLITS]
    source += json.dumps([VERSION, policy, dependencies], sort_keys=True).encode()
    return {
        "version": VERSION,
        "sha256": hashlib.sha256(source).hexdigest(),
        "splits": policy,
        "dependencies": dependencies,
        "python": platform.python_version(),
    }


def ordered_events(
    connection: psycopg.Connection, schema: str, dataset_id: int, role: str, digest=None
) -> Iterator[Event]:
    with connection.cursor(name=f"features_{role}") as cursor:
        cursor.itersize = BATCH_SIZE
        cursor.execute(
            statement(sql_file(f"features_{role}.sql"), schema), (dataset_id,)
        )
        for row in cursor:
            if digest is not None:
                # Hash only core transaction fields, never label-bearing hashes.
                digest.update(
                    json.dumps(row, default=str, separators=(",", ":")).encode() + b"\n"
                )
            yield Event(*row)


class SideWriter:
    def __init__(self, path: Path, role: str) -> None:
        self.schema = arrow_schema(role)
        self.writer = pq.ParquetWriter(path, self.schema, compression="zstd")
        self.buffer: list[dict] = []
        self.count = 0

    def append(self, row: dict) -> None:
        self.buffer.append(row)
        self.count += 1
        if len(self.buffer) >= BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if self.buffer:
            self.writer.write_table(
                pa.Table.from_pylist(self.buffer, schema=self.schema)
            )
            self.buffer.clear()

    def close(self) -> None:
        self.flush()
        self.writer.close()


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def assemble(directory: Path, dataset: dict, expected: int) -> dict:
    """External-memory join of endpoint histories into one row per source record."""
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit = '256MB'")
        connection.execute("SET threads = 1")
        connection.execute("SET preserve_insertion_order = false")
        connection.execute(
            f"SET temp_directory = {literal(str(directory / 'scratch'))}"
        )
        for role in ("sender", "receiver"):
            connection.read_parquet(str(directory / f"{role}.parquet")).create_view(
                role
            )
            count, distinct = connection.execute(
                f"SELECT count(*), count(DISTINCT source_row) FROM {role}"
            ).fetchone()
            if count != expected or distinct != expected:
                raise ValueError(f"Incomplete or duplicate {role} features")
        selected = [
            f"{dataset['dataset_id']}::BIGINT AS dataset_id",
            f"{literal(dataset['fingerprint'])} AS dataset_fingerprint",
            f"{literal(VERSION)} AS feature_version",
            "s.source_row",
            "s.occurred_at",
            "s.split",
        ]
        selected += [f"s.{name}" for name in CURRENT]
        selected += [
            f"{alias}.{name} AS {role}_{name}"
            for role, alias in (("sender", "s"), ("receiver", "r"))
            for name in HISTORY
        ]
        destination = literal(str(directory / "features.parquet"))
        connection.execute(f"""
            COPY (SELECT {", ".join(selected)} FROM sender s JOIN receiver r
                  USING (source_row, occurred_at, split)
                  ORDER BY s.occurred_at, s.source_row)
            TO {destination} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 32768)
        """)
        connection.read_parquet(str(directory / "features.parquet")).create_view(
            "features"
        )
        required = ["source_row", "occurred_at", "split", *CURRENT]
        required += [
            f"{role}_{name}"
            for role in ("sender", "receiver")
            for name in HISTORY
            if name not in NULLABLE_HISTORY
        ]
        invalid = [f"{name} IS NULL" for name in required]
        for role in ("sender", "receiver"):
            invalid += [
                f"{role}_count_1h > {role}_count_24h",
                f"{role}_count_24h > {role}_history_count",
                f"{role}_last_activity_at >= occurred_at",
                f"{role}_history_count < 0",
                f"({role}_history_count = 0) <> ({role}_last_activity_at IS NULL)",
            ]
        count, bad = connection.execute(
            f"SELECT count(*), count(*) FILTER (WHERE {' OR '.join(invalid)}) "
            "FROM features"
        ).fetchone()
        if count != expected or bad:
            raise ValueError("Feature completeness or cutoff invariant failed")
        splits = connection.execute(
            "SELECT split, count(*) FROM features GROUP BY split ORDER BY split"
        ).fetchall()
        cold = connection.execute(
            "SELECT count(*) FILTER (WHERE sender_history_count=0), "
            "count(*) FILTER (WHERE receiver_history_count=0) FROM features"
        ).fetchone()
        nullable_names = [
            f"{role}_{name}"
            for role in ("sender", "receiver")
            for name in sorted(NULLABLE_HISTORY)
        ]
        null_counts = connection.execute(
            "SELECT "
            + ", ".join(
                f"count(*) FILTER (WHERE {name} IS NULL)" for name in nullable_names
            )
            + " FROM features"
        ).fetchone()
    for role in ("sender", "receiver"):
        (directory / f"{role}.parquet").unlink()
    shutil.rmtree(directory / "scratch", ignore_errors=True)
    return {
        "rows": count,
        "invalid_rows": bad,
        "splits": dict(splits),
        "sender_cold_start_rows": cold[0],
        "receiver_cold_start_rows": cold[1],
        "expected_nullable_counts": dict(zip(nullable_names, null_counts, strict=True)),
    }


@contextmanager
def output_lock(parent: Path):
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / ".build.lock").open("w") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "Another feature build is active in this output directory"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def build_features(
    database_url: str,
    *,
    output_dir: Path = Path("data/features"),
    schema: str = "mulegraph",
    dataset_key: str = "ibm-aml-hi-small-v8",
    progress=print,
) -> dict:
    started = time.monotonic()
    spec = definition()
    with output_lock(output_dir), psycopg.connect(database_url) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL work_mem = '32MB'")
        connection.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        connection.execute("SET LOCAL statement_timeout = '30min'")
        row = connection.execute(
            statement(
                "SELECT dataset_id, fingerprint, status FROM {core}.datasets "
                "WHERE dataset_key = %s",
                schema,
            ),
            (dataset_key,),
        ).fetchone()
        if row is None or row[2] != "complete":
            raise ValueError("Features require a completed ingested dataset")
        dataset = {
            "dataset_id": row[0],
            "fingerprint": row[1],
            "dataset_key": dataset_key,
        }
        expected = connection.execute(
            statement(
                "SELECT count(*) FROM {core}.transactions WHERE dataset_id = %s", schema
            ),
            (row[0],),
        ).fetchone()[0]
        destination = output_dir / VERSION / row[1]
        source_digest = hashlib.sha256()
        if destination.exists():
            manifest = json.loads((destination / "manifest.json").read_text())
            if manifest["definition"]["sha256"] != spec["sha256"]:
                raise ValueError(
                    "Feature definition changed; use an explicit new version"
                )
            progress("Verifying existing artifact and current source stream ...")
            count = sum(
                1
                for _ in ordered_events(
                    connection, schema, row[0], "sender", source_digest
                )
            )
            if (
                manifest["source_sha256"] != source_digest.hexdigest()
                or count != expected
                or count != manifest["completeness"]["rows"]
                or sha256_file(destination / "features.parquet")
                != manifest["file_sha256"]
            ):
                raise ValueError(
                    "Existing features or source data changed; refusing reuse"
                )
            return {
                "outcome": "already_built",
                "path": str(destination),
                "rows": count,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        destination.parent.mkdir(parents=True, exist_ok=True)
        working = Path(tempfile.mkdtemp(prefix=".building-", dir=destination.parent))
        writers = {}
        try:
            for role in ("sender", "receiver"):
                writers[role] = SideWriter(working / f"{role}.parquet", role)
            events = heapq.merge(
                ordered_events(connection, schema, row[0], "sender", source_digest),
                ordered_events(connection, schema, row[0], "receiver"),
                key=lambda event: (
                    event.bank,
                    event.account,
                    event.timestamp,
                    event.source_row,
                    event.role,
                ),
            )
            progress("Streaming account histories from PostgreSQL (no labels) ...")
            for role, features in account_features(events):
                writers[role].append(features)
                if role == "sender" and writers[role].count % 500000 == 0:
                    progress(
                        f"Computed {writers[role].count:,}/{expected:,} transactions"
                    )
            for writer in writers.values():
                writer.close()
            writers.clear()
            progress("Joining endpoint histories and validating persisted features ...")
            completeness = assemble(working, dataset, expected)
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_mib = usage / (1024**2 if sys.platform == "darwin" else 1024)
            manifest = {
                "definition": spec,
                "dataset": dataset,
                "generated_at": datetime.now(UTC).isoformat(),
                "source_sha256": source_digest.hexdigest(),
                "file_sha256": sha256_file(working / "features.parquet"),
                "file_bytes": (working / "features.parquet").stat().st_size,
                "completeness": completeness,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "python_process_peak_rss_mib": round(peak_mib, 2),
                "database_read_only": connection.execute(
                    "SHOW transaction_read_only"
                ).fetchone()[0],
            }
            (working / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
            working.rename(destination)  # Atomic publication on the same filesystem.
            return {"outcome": "built", "path": str(destination), **manifest}
        finally:
            for writer in writers.values():
                writer.writer.close()
            if working.exists():
                shutil.rmtree(working)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/features"))
    args = parser.parse_args()
    if not (dsn := os.environ.get("DATABASE_URL")):
        parser.error("Set DATABASE_URL (use uv --env-file .env)")
    try:
        result = build_features(dsn, output_dir=args.output_dir)
    except (OSError, ValueError, psycopg.Error, duckdb.Error) as error:
        detail = (
            str(error)
            if isinstance(error, ValueError)
            else "See configuration/resources"
        )
        print(
            f"Feature build failed: {type(error).__name__}: {detail}", file=sys.stderr
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
