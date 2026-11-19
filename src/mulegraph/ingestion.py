"""Transactional COPY ingestion of validated HI-Small files into PostgreSQL."""

import argparse
import csv
import hashlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from mulegraph.schema import initialize_schema, sql_file, statement
from mulegraph.validation import (
    ACCOUNT_HEADER,
    ACCOUNTS,
    FILES,
    TRANSACTION_HEADER,
    TRANSACTIONS,
    file_fingerprint,
    row_key,
)

BATCH_SIZE = 100_000
NORMALIZATION_VERSION = "bank-padding-v1"


def load_inputs(
    raw_dir: Path, manifest_path: Path, audit_path: Path
) -> tuple[dict, dict, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("errors") != [] or not all(
        audit.get(kind, {}).get("complete")
        for kind in ("accounts", "transactions", "patterns")
    ):
        raise ValueError("A complete validation audit with zero errors is required")
    relationships = audit["relationships"]
    if (
        relationships["bank_normalization_collisions"]
        or relationships["bank_padding_diagnostic"]["unmatched_composite_keys"]
    ):
        raise ValueError(
            "Bank normalization must be collision-free with no unmatched keys"
        )
    fingerprints = {}
    for name in FILES:
        observed = file_fingerprint(raw_dir / name)
        expected = manifest["files"][name]
        if observed != audit["files"][name] or any(
            observed[key] != expected[key] for key in ("sha256", "size_bytes")
        ):
            raise ValueError(
                f"Input differs from acquisition/validation fingerprints: {name}"
            )
        fingerprints[name] = observed
    digest = hashlib.sha256(
        json.dumps(fingerprints, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return manifest, audit, digest


def _copy_file(connection: psycopg.Connection, path: Path, table: str) -> int:
    transactions = table == "stage_transactions"
    expected = TRANSACTION_HEADER if transactions else ACCOUNT_HEADER
    rows = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != expected:
            raise ValueError(f"Unexpected positional header: {path.name}")
        with connection.cursor().copy(
            sql.SQL("COPY {} FROM STDIN").format(sql.Identifier(table))
        ) as copy:
            for rows, row in enumerate(reader, start=1):
                if len(row) != len(expected):
                    raise ValueError(
                        f"Wrong field count: {path.name}, source row {rows}"
                    )
                values = [rows, *row]
                if transactions:
                    values.append(hashlib.sha256(row_key(row).encode("utf-8")).digest())
                copy.write_row(values)
    return rows


def _load_accounts(
    connection: psycopg.Connection, schema: str, dataset_id: int
) -> None:
    # Validate dimensional dependencies before GROUP BY: never pick an arbitrary
    # bank/entity name or silently merge distinct original account identities.
    conflicts = connection.execute(
        statement(
            """
        SELECT
            (SELECT count(*) FROM (
                SELECT {core}.normalize_bank_id(raw_bank_id), account_number
                FROM stage_accounts GROUP BY 1, 2 HAVING count(*) > 1) a),
            (SELECT count(*) FROM (
                SELECT {core}.normalize_bank_id(raw_bank_id) FROM stage_accounts
                GROUP BY 1 HAVING count(DISTINCT bank_name) > 1) b),
            (SELECT count(*) FROM (
                SELECT entity_id FROM stage_accounts GROUP BY 1
                HAVING count(DISTINCT entity_name) > 1) e)
    """,
            schema,
        )
    ).fetchone()
    if any(conflicts):
        raise ValueError(
            "Account normalization collision or conflicting bank/entity metadata"
        )
    connection.execute(
        statement(
            """
        INSERT INTO {core}.banks
        SELECT %s, {core}.normalize_bank_id(raw_bank_id), min(bank_name)
        FROM stage_accounts GROUP BY 2
    """,
            schema,
        ),
        (dataset_id,),
    )
    connection.execute(
        statement(
            """
        INSERT INTO {core}.entities
        SELECT %s, entity_id, min(entity_name) FROM stage_accounts GROUP BY entity_id
    """,
            schema,
        ),
        (dataset_id,),
    )
    connection.execute(
        statement(
            """
        INSERT INTO {core}.accounts
            (dataset_id, source_row, raw_bank_id, account_number, entity_id)
        SELECT %s, source_row, raw_bank_id, account_number, entity_id
        FROM stage_accounts ORDER BY source_row
    """,
            schema,
        ),
        (dataset_id,),
    )
    connection.execute("DROP TABLE stage_accounts")


def _load_transactions(
    connection: psycopg.Connection,
    schema: str,
    dataset_id: int,
    count: int,
    progress: Callable[[str], None],
) -> None:
    connection.execute("ALTER TABLE stage_transactions ADD PRIMARY KEY (source_row)")
    connection.execute("ANALYZE stage_transactions")
    # Bounded INSERT statements also bound PostgreSQL's pending FK trigger memory.
    for first in range(1, count + 1, BATCH_SIZE):
        last = min(first + BATCH_SIZE - 1, count)
        connection.execute(
            statement(
                """
            INSERT INTO {core}.transactions (
                dataset_id, source_row, occurred_at, raw_from_bank_id, from_account,
                raw_to_bank_id, to_account, amount_received, receiving_currency,
                amount_paid, payment_currency, payment_format)
            SELECT %s, source_row, occurred_at::timestamp,
                raw_from_bank_id, from_account, raw_to_bank_id, to_account,
                amount_received::numeric, receiving_currency,
                amount_paid::numeric, payment_currency, payment_format
            FROM stage_transactions WHERE source_row BETWEEN %s AND %s
            ORDER BY source_row
        """,
                schema,
            ),
            (dataset_id, first, last),
        )
        connection.execute(
            statement(
                """
            INSERT INTO {labels}.transaction_labels
            SELECT %s, source_row, is_laundering::smallint, source_record_sha256
            FROM stage_transactions WHERE source_row BETWEEN %s AND %s
            ORDER BY source_row
        """,
                schema,
            ),
            (dataset_id, first, last),
        )
        if last % 500_000 == 0 or last == count:
            progress(f"Loaded {last:,}/{count:,} transaction rows (not yet committed)")
    connection.execute("DROP TABLE stage_transactions")


def ingest(
    database_url: str,
    raw_dir: Path,
    manifest_path: Path,
    audit_path: Path,
    *,
    dataset_key: str = "ibm-aml-hi-small-v8",
    schema: str = "mulegraph",
    verify_only: bool = False,
    progress: Callable[[str], None] = lambda message: None,
) -> dict:
    """Commit all rows only after successful reconciliation, or roll back all writes."""
    from mulegraph.reconciliation import reconcile

    started = perf_counter()
    statement("SELECT 1", schema)  # Validate the schema before opening a connection.
    manifest, audit, fingerprint = load_inputs(raw_dir, manifest_path, audit_path)
    progress("Input hashes match acquisition and validation metadata")
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        if verify_only:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
        else:
            connection.execute("SET LOCAL lock_timeout = '15s'")
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (schema,),
            )
            initialize_schema(connection, schema)
        connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
        connection.execute("SET LOCAL work_mem = '32MB'")
        # Docker's default /dev/shm is small. Avoid parallel hash joins allocating
        # shared-memory segments; keep the existing container configuration intact.
        connection.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        existing = connection.execute(
            statement(
                """
            SELECT dataset_id, fingerprint, status, normalization_version
            FROM {core}.datasets WHERE dataset_key = %s
        """,
                schema,
            ),
            (dataset_key,),
        ).fetchone()
        if existing:
            dataset_id, stored_fingerprint, status, normalization = existing
            if (stored_fingerprint, status, normalization) != (
                fingerprint,
                "complete",
                NORMALIZATION_VERSION,
            ):
                raise ValueError(
                    "Dataset key already exists with different or incomplete inputs"
                )
            progress("Dataset already present; reconciling without inserting rows")
            result = reconcile(connection, schema, dataset_id, audit)
            outcome = "verified" if verify_only else "already_loaded"
        else:
            if verify_only:
                raise ValueError("Dataset has not been ingested")
            dataset_id = connection.execute(
                statement(
                    """
                INSERT INTO {core}.datasets (
                    dataset_key, fingerprint, normalization_version, status,
                    provenance, validation)
                VALUES (%s, %s, %s, 'loading', %s, %s) RETURNING dataset_id
            """,
                    schema,
                ),
                (
                    dataset_key,
                    fingerprint,
                    NORMALIZATION_VERSION,
                    Jsonb(manifest),
                    Jsonb(audit),
                ),
            ).fetchone()[0]
            with connection.cursor() as cursor:
                cursor.executemany(
                    statement(
                        """
                    INSERT INTO {core}.source_files VALUES (%s, %s, %s, %s, %s)
                """,
                        schema,
                    ),
                    [
                        (
                            dataset_id,
                            name,
                            entry["sha256"],
                            entry["size_bytes"],
                            entry["source_url"],
                        )
                        for name, entry in manifest["files"].items()
                        if name in FILES
                    ],
                )
            connection.execute(sql_file("staging.sql"))
            progress("COPY accounts into transaction-local staging")
            accounts = _copy_file(connection, raw_dir / ACCOUNTS, "stage_accounts")
            if accounts != audit["accounts"]["rows"]:
                raise ValueError("Account source-row count differs from validation")
            _load_accounts(connection, schema, dataset_id)
            progress("COPY transactions into transaction-local staging")
            transactions = _copy_file(
                connection, raw_dir / TRANSACTIONS, "stage_transactions"
            )
            if transactions != audit["transactions"]["rows"]:
                raise ValueError("Transaction source-row count differs from validation")
            _load_transactions(connection, schema, dataset_id, transactions, progress)
            progress("Building indexes and reconciling SQL aggregates")
            connection.execute(statement(sql_file("indexes.sql"), schema))
            for table in ("accounts", "transactions"):
                connection.execute(statement("ANALYZE {core}." + table, schema))
            connection.execute(statement("ANALYZE {labels}.transaction_labels", schema))
            result = reconcile(connection, schema, dataset_id, audit)
            connection.execute(
                statement(
                    """
                UPDATE {core}.datasets SET status = 'complete',
                    completed_at = clock_timestamp(), reconciliation = %s
                WHERE dataset_id = %s
            """,
                    schema,
                ),
                (Jsonb(result), dataset_id),
            )
            outcome = "loaded"
        # Re-read bytes before commit, including the provenance-only patterns file.
        for name in FILES:
            if file_fingerprint(raw_dir / name) != audit["files"][name]:
                raise ValueError(f"Raw file changed during ingestion: {name}")
    # The connection context commits before success is returned.
    return {
        "outcome": outcome,
        "dataset_id": dataset_id,
        "dataset_key": dataset_key,
        "fingerprint": fingerprint,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "reconciliation": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/hi-small"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/provenance/hi-small/manifest.json")
    )
    parser.add_argument(
        "--audit", type=Path, default=Path("data/validation/hi-small.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/ingestion/latest.json")
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Set DATABASE_URL before ingestion.", file=sys.stderr)
        return 2
    try:
        if args.output.resolve().is_relative_to(args.raw_dir.resolve()) or (
            args.output.resolve() in (args.manifest.resolve(), args.audit.resolve())
        ):
            raise ValueError(
                "Output must not overwrite raw data, provenance, or validation"
            )
        result = ingest(
            database_url,
            args.raw_dir,
            args.manifest,
            args.audit,
            verify_only=args.verify_only,
            progress=lambda message: print(message, flush=True),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except psycopg.Error as error:
        # Avoid connection strings, row values, or credential-bearing driver details.
        print(
            f"Database operation failed ({type(error).__name__}); "
            "no partial load committed.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, KeyError, csv.Error) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1
    print(
        f"{result['outcome']}: dataset {result['dataset_id']}; "
        f"{result['elapsed_seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
