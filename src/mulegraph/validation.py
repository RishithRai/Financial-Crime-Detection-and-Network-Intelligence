"""Stream IBM HI-Small audits without changing raw data or using PostgreSQL."""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

TRANSACTIONS = "HI-Small_Trans.csv"
ACCOUNTS = "HI-Small_accounts.csv"
PATTERNS = "HI-Small_Patterns.txt"
FILES = (TRANSACTIONS, ACCOUNTS, PATTERNS)
TRANSACTION_HEADER = [
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]
ACCOUNT_HEADER = ["Bank Name", "Bank ID", "Account Number", "Entity ID", "Entity Name"]
BATCH_SIZE = 5000


def file_fingerprint(path: Path) -> dict:
    """Hash bytes, not decoded/re-serialized text."""
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"size_bytes": path.stat().st_size, "sha256": digest}


def bank_without_padding(bank: str) -> str:
    """Diagnostic comparison only: retain original identifiers everywhere else."""
    return (bank.lstrip("0") or "0") if re.fullmatch(r"[0-9]+", bank) else bank


def row_key(row: list[str]) -> str:
    """Lossless field serialization for exact parsed-record comparisons."""
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


@lru_cache(maxsize=65536)
def parse_timestamp(value: str) -> datetime:
    if not re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}", value):
        raise ValueError("Expected YYYY/MM/DD HH:MM")
    return datetime.strptime(value, "%Y/%m/%d %H:%M")


def transaction_issues(row: list[str]) -> list[str]:
    """Return reason codes; a row can have multiple reasons."""
    if len(row) != len(TRANSACTION_HEADER):
        return ["wrong_field_count"]
    issues = []
    if any(not value.strip() for value in row):
        issues.append("missing_field")
    if any(value != value.strip() for value in row):
        issues.append("surrounding_whitespace")
    for index in (1, 3):
        if not re.fullmatch(r"[0-9]+", row[index]):
            issues.append(f"invalid_bank_{index + 1}")
    try:
        parse_timestamp(row[0])
    except ValueError:
        issues.append("invalid_timestamp")
    for index in (5, 7):
        try:
            amount = Decimal(row[index])
            if not amount.is_finite() or amount < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            issues.append(f"invalid_amount_{index + 1}")
    if row[10] not in ("0", "1"):
        issues.append("invalid_label")
    return issues


def _database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA cache_size = -32768;
        PRAGMA temp_store = FILE;
        CREATE TABLE seen (
            kind TEXT, record TEXT, PRIMARY KEY (kind, record)
        ) WITHOUT ROWID;
        CREATE TABLE accounts (
            bank TEXT, account TEXT, entity TEXT, normalized_bank TEXT,
            PRIMARY KEY (bank, account, entity)
        ) WITHOUT ROWID;
        CREATE TABLE endpoints (
            bank TEXT, account TEXT, normalized_bank TEXT, sent INTEGER,
            received INTEGER, PRIMARY KEY (bank, account)
        ) WITHOUT ROWID;
    """)
    return connection


def _flush(connection: sqlite3.Connection, kind: str, rows: list[list[str]]) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO seen VALUES (?, ?)",
        ((kind, row_key(row)) for row in rows),
    )
    if kind == "accounts":
        connection.executemany(
            "INSERT OR IGNORE INTO accounts VALUES (?, ?, ?, ?)",
            (
                (r[1], r[2], r[3], bank_without_padding(r[1]))
                for r in rows
                if len(r) == 5 and all(r[i].strip() for i in (1, 2, 3))
            ),
        )
    else:
        endpoints = Counter()
        for row in rows:
            if len(row) != 11:
                continue
            for bank_index, direction in ((1, 0), (3, 1)):
                bank, account = row[bank_index : bank_index + 2]
                if bank.strip() and account.strip():
                    endpoints[bank, account, direction] += 1
        connection.executemany(
            """INSERT INTO endpoints VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(bank, account) DO UPDATE SET
               sent = sent + excluded.sent, received = received + excluded.received""",
            (
                (
                    bank,
                    account,
                    bank_without_padding(bank),
                    n if direction == 0 else 0,
                    n if direction == 1 else 0,
                )
                for (bank, account, direction), n in endpoints.items()
            ),
        )
    connection.commit()


def _amount(stats: dict, field: str, currency: str, value: str) -> None:
    summary = stats.setdefault(field, {}).setdefault(
        currency,
        {
            "finite_count": 0,
            "invalid_count": 0,
            "zero_count": 0,
            "negative_count": 0,
            "min": None,
            "max": None,
        },
    )
    try:
        amount = Decimal(value)
        if not amount.is_finite():
            raise ValueError
    except (InvalidOperation, ValueError):
        summary["invalid_count"] += 1
        return
    summary["finite_count"] += 1
    summary["zero_count"] += amount == 0
    summary["negative_count"] += amount < 0
    for key, compare in (("min", min), ("max", max)):
        previous = summary[key]
        summary[key] = str(
            amount if previous is None else compare(Decimal(previous), amount)
        )


def _audit_csv(path: Path, kind: str, connection: sqlite3.Connection) -> dict:
    expected = TRANSACTION_HEADER if kind == "transactions" else ACCOUNT_HEADER
    result = {
        "rows": 0,
        "complete": False,
        "header": [],
        "missing": Counter(),
        "invalid_rows": 0,
        "invalid_reasons": Counter(),
        "duplicate_rows": 0,
        "categories": {},
        "amounts": {},
        "timestamps": {
            "min": None,
            "max": None,
            "adjacent_decreases": 0,
            "outside_primary_window_by_label": Counter(),
            "dates_by_label": Counter(),
        },
        "self_transfers": 0,
        "cross_currency_rows": 0,
        "same_currency_unequal_amounts": 0,
        "bank_values_with_leading_zeros": 0,
    }
    previous_time = None
    batch = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            result["header"] = next(reader, [])
            if result["header"] != expected:
                result["read_error"] = (
                    "Header does not match the inspected positional schema"
                )
                return result
            for row in reader:
                result["rows"] += 1
                batch.append(row)
                for index, value in enumerate(row[: len(expected)]):
                    if not value.strip():
                        result["missing"][f"{index + 1}: {expected[index]}"] += 1
                if kind == "transactions":
                    issues = transaction_issues(row)
                else:
                    issues = []
                    if len(row) != 5:
                        issues.append("wrong_field_count")
                    else:
                        if any(not value.strip() for value in row):
                            issues.append("missing_field")
                        if any(value != value.strip() for value in row):
                            issues.append("surrounding_whitespace")
                        if not re.fullmatch(r"[0-9]+", row[1]):
                            issues.append("invalid_bank")
                result["invalid_rows"] += bool(issues)
                result["invalid_reasons"].update(issues)
                if len(row) == len(expected):
                    bank_indices = (1, 3) if kind == "transactions" else (1,)
                    result["bank_values_with_leading_zeros"] += sum(
                        len(row[i]) > 1 and row[i].startswith("0") for i in bank_indices
                    )
                if kind == "transactions" and len(row) == 11:
                    for index in (6, 8, 9, 10):
                        counts = result["categories"].setdefault(
                            expected[index], Counter()
                        )
                        counts[row[index]] += 1
                    _amount(result["amounts"], "Amount Received", row[6], row[5])
                    _amount(result["amounts"], "Amount Paid", row[8], row[7])
                    result["self_transfers"] += row[1:3] == row[3:5]
                    result["cross_currency_rows"] += row[6] != row[8]
                    if not any(
                        reason.startswith("invalid_amount") for reason in issues
                    ):
                        result["same_currency_unequal_amounts"] += row[6] == row[
                            8
                        ] and Decimal(row[5]) != Decimal(row[7])
                    if "invalid_timestamp" not in issues:
                        timestamp = parse_timestamp(row[0])
                        times = result["timestamps"]
                        times["adjacent_decreases"] += (
                            previous_time is not None and timestamp < previous_time
                        )
                        previous_time = timestamp
                        value = timestamp.isoformat(sep=" ")
                        times["min"] = min(times["min"] or value, value)
                        times["max"] = max(times["max"] or value, value)
                        times["dates_by_label"][f"{timestamp.date()} | {row[10]}"] += 1
                        if (
                            not datetime(2022, 9, 1)
                            <= timestamp
                            < datetime(2022, 9, 11)
                        ):
                            times["outside_primary_window_by_label"][row[10]] += 1
                if len(batch) >= BATCH_SIZE:
                    _flush(connection, kind, batch)
                    batch.clear()
            result["complete"] = True
    except (csv.Error, UnicodeError) as error:
        result["read_error"] = f"{type(error).__name__}: invalid CSV or UTF-8"
    _flush(connection, kind, batch)
    unique = connection.execute(
        "SELECT count(*) FROM seen WHERE kind = ?", (kind,)
    ).fetchone()[0]
    result["duplicate_rows"] = result["rows"] - unique
    result["unique_rows"] = unique
    return result


def _relationships(connection: sqlite3.Connection) -> dict:
    connection.executescript("""
        CREATE INDEX account_normalized ON accounts(normalized_bank, account);
        CREATE INDEX endpoint_normalized ON endpoints(normalized_bank, account);
    """)
    queries = {
        "account_composite_keys": """SELECT count(*) FROM (
            SELECT bank, account FROM accounts GROUP BY bank, account)""",
        "account_numbers": "SELECT count(DISTINCT account) FROM accounts",
        "account_banks": "SELECT count(DISTINCT bank) FROM accounts",
        "entities": "SELECT count(DISTINCT entity) FROM accounts",
        "account_numbers_in_multiple_banks": """SELECT count(*) FROM (
            SELECT account FROM accounts GROUP BY account
            HAVING count(DISTINCT bank) > 1)""",
        "composite_keys_with_multiple_entities": """SELECT count(*) FROM (
            SELECT bank, account FROM accounts GROUP BY bank, account
            HAVING count(*) > 1)""",
        "bank_normalization_collisions": """SELECT count(*) FROM (
            SELECT normalized_bank, account FROM accounts
            GROUP BY normalized_bank, account HAVING count(DISTINCT bank) > 1)""",
        "transaction_composite_keys": "SELECT count(*) FROM endpoints",
        "transaction_normalized_composite_keys": """SELECT count(*) FROM (
            SELECT normalized_bank, account FROM endpoints
            GROUP BY normalized_bank, account)""",
        "account_keys_unused_after_bank_normalization": """SELECT count(*) FROM (
            SELECT bank, account FROM accounts a WHERE NOT EXISTS (
                SELECT 1 FROM endpoints e WHERE e.normalized_bank = a.normalized_bank
                AND e.account = a.account) GROUP BY bank, account)""",
    }
    result = {
        key: connection.execute(query).fetchone()[0] for key, query in queries.items()
    }
    for mode, bank_column in (
        ("literal", "bank"),
        ("bank_padding_diagnostic", "normalized_bank"),
    ):
        record = connection.execute(f"""
            SELECT count(*), coalesce(sum(sent), 0), coalesce(sum(received), 0)
            FROM endpoints e WHERE NOT EXISTS (
                SELECT 1 FROM accounts a
                WHERE a.{bank_column} = e.{bank_column} AND a.account = e.account
            )
        """).fetchone()
        result[mode] = dict(
            zip(
                (
                    "unmatched_composite_keys",
                    "unmatched_sender_rows",
                    "unmatched_receiver_rows",
                ),
                record,
                strict=True,
            )
        )
    return result


def _patterns(path: Path, connection: sqlite3.Connection) -> dict:
    result = {
        "lines": 0,
        "blank_lines": 0,
        "blocks": 0,
        "closed_blocks": 0,
        "types": Counter(),
        "transaction_rows": 0,
        "invalid_rows": 0,
        "structure_errors": 0,
        "non_laundering_rows": 0,
        "unmatched_rows": 0,
        "duplicate_rows": 0,
        "complete": False,
    }
    active = None
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                result["lines"] += 1
                text = line.rstrip("\r\n")
                if not text:
                    result["blank_lines"] += 1
                elif text.startswith("BEGIN LAUNDERING ATTEMPT - "):
                    result["structure_errors"] += active is not None
                    active = text.removeprefix("BEGIN LAUNDERING ATTEMPT - ").split(
                        ":"
                    )[0]
                    result["types"][active] += 1
                    result["blocks"] += 1
                elif text.startswith("END LAUNDERING ATTEMPT - "):
                    result["structure_errors"] += (
                        active is None
                        or text.removeprefix("END LAUNDERING ATTEMPT - ") != active
                    )
                    active = None
                    result["closed_blocks"] += 1
                else:
                    result["transaction_rows"] += 1
                    result["structure_errors"] += active is None
                    row = next(csv.reader([text], strict=True))
                    result["invalid_rows"] += bool(transaction_issues(row))
                    result["non_laundering_rows"] += len(row) == 11 and row[10] != "1"
                    key = row_key(row)
                    result["unmatched_rows"] += not connection.execute(
                        "SELECT 1 FROM seen WHERE kind = 'transactions' AND record = ?",
                        (key,),
                    ).fetchone()
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO seen VALUES ('patterns', ?)",
                        (key,),
                    )
                    result["duplicate_rows"] += cursor.rowcount == 0
            result["complete"] = True
    except (csv.Error, UnicodeError):
        result["read_error"] = "Invalid CSV record or UTF-8 in patterns"
    result["structure_errors"] += active is not None
    result["unique_transaction_rows"] = (
        result["transaction_rows"] - result["duplicate_rows"]
    )
    return result


def _findings(report: dict) -> None:
    errors, warnings = report["errors"], report["warnings"]
    for kind in ("accounts", "transactions"):
        audit = report.get(kind)
        if not audit:
            continue
        if not audit["complete"]:
            errors.append(f"{kind}: incomplete audit / schema or decoding failure")
        if audit["rows"] == 0:
            errors.append(f"{kind}: no data rows")
        if audit["invalid_rows"]:
            errors.append(f"{kind}: {audit['invalid_rows']:,} invalid records")
        if audit["duplicate_rows"]:
            warnings.append(
                f"{kind}: {audit['duplicate_rows']:,} repeated parsed records; retained"
            )
    transactions = report.get("transactions", {})
    times = transactions.get("timestamps", {})
    if times.get("adjacent_decreases"):
        warnings.append(
            "Transactions are not globally sorted by timestamp; file "
            "order is not chronology."
        )
    if times.get("outside_primary_window_by_label"):
        warnings.append(
            "Transactions exist outside the advertised September "
            "1–10 primary window; retained."
        )
    labels = transactions.get("categories", {}).get("Is Laundering", {})
    total = labels.get("0", 0) + labels.get("1", 0)
    if total:
        transactions["laundering_rate_percent"] = 100 * labels.get("1", 0) / total
        if min(labels.get("0", 0), labels.get("1", 0)) / total < 0.01:
            warnings.append(
                "Severe class imbalance: the minority class is below 1% "
                "of valid binary labels."
            )
    if transactions.get("self_transfers"):
        warnings.append(
            "Self-transfers exist; they are observations, not "
            "automatically invalid records."
        )
    if any(
        values["zero_count"]
        for currencies in transactions.get("amounts", {}).values()
        for values in currencies.values()
    ):
        warnings.append("Zero amounts exist; retained for review rather than rejected.")
    if transactions.get("cross_currency_rows") or transactions.get(
        "same_currency_unequal_amounts"
    ):
        warnings.append(
            "Currency or amount differences exist; do not compare or "
            "sum money across currencies."
        )
    relations = report.get("relationships")
    if relations:
        if relations["literal"]["unmatched_composite_keys"]:
            warnings.append(
                "Literal bank-account joins have unmatched keys; inspect "
                "the bank-padding diagnostic."
            )
        if relations["bank_padding_diagnostic"]["unmatched_composite_keys"]:
            warnings.append(
                "Some transaction keys remain unmatched after diagnostic "
                "bank-padding removal."
            )
        if relations["composite_keys_with_multiple_entities"]:
            errors.append("Some bank-account composite keys map to multiple entities.")
        if relations["bank_normalization_collisions"]:
            warnings.append(
                "Bank-padding removal merges distinct account metadata "
                "keys; do not apply automatically."
            )
    patterns = report.get("patterns")
    if patterns:
        if (
            not patterns["complete"]
            or any(
                patterns[k]
                for k in (
                    "invalid_rows",
                    "structure_errors",
                    "non_laundering_rows",
                    "unmatched_rows",
                )
            )
            or not patterns["blocks"]
        ):
            errors.append(
                "Patterns contain structural/record/reference errors or no blocks."
            )
        if patterns["duplicate_rows"]:
            warnings.append(
                "Patterns contain repeated transaction annotations; no "
                "records were removed."
            )
    warnings.append(
        "Timestamps have no timezone or availability time; "
        "historical availability cannot be verified."
    )
    warnings.append(
        "Labels and pattern annotations are outcome information, "
        "not historical predictor inputs."
    )


def validate_dataset(
    raw_dir: Path,
    *,
    provenance_path: Path | None = None,
    scratch_dir: Path | None = None,
) -> dict:
    """Audit all three files. Disk indexes are deleted even if validation fails."""
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "files": {},
        "errors": [],
        "warnings": [],
        "provenance": {},
    }
    if provenance_path is not None:
        report["provenance"] = json.loads(provenance_path.read_text(encoding="utf-8"))
    else:
        report["warnings"].append(
            "No acquisition manifest supplied; source provenance is unverified."
        )
    for name in FILES:
        path = raw_dir / name
        if not path.is_file():
            report["errors"].append(f"Missing required file: {name}")
            continue
        report["files"][name] = file_fingerprint(path)
        expected = report["provenance"].get("files", {}).get(name)
        if provenance_path is not None:
            if not expected:
                report["errors"].append(f"No provenance entry for {name}")
            elif any(
                expected.get(k) != report["files"][name][k]
                for k in ("size_bytes", "sha256")
            ):
                report["errors"].append(f"Acquisition fingerprint mismatch: {name}")
    if len(report["files"]) != len(FILES):
        return report
    if scratch_dir is not None:
        scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="mulegraph-audit-", dir=scratch_dir
    ) as temporary:
        connection = _database(Path(temporary) / "audit.sqlite")
        try:
            report["accounts"] = _audit_csv(raw_dir / ACCOUNTS, "accounts", connection)
            report["transactions"] = _audit_csv(
                raw_dir / TRANSACTIONS, "transactions", connection
            )
            if report["accounts"]["complete"] and report["transactions"]["complete"]:
                report["relationships"] = _relationships(connection)
                report["patterns"] = _patterns(raw_dir / PATTERNS, connection)
        finally:
            connection.close()
    for name, before in report["files"].items():
        if file_fingerprint(raw_dir / name) != before:
            report["errors"].append(f"Raw file changed during validation: {name}")
    _findings(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/hi-small"))
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--scratch-dir", type=Path, default=Path("data/work"))
    parser.add_argument(
        "--json-output", type=Path, default=Path("data/validation/hi-small.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("docs/data_validation_report.md")
    )
    args = parser.parse_args()
    try:
        outputs = (args.json_output.resolve(), args.report.resolve())
        if outputs[0] == outputs[1]:
            raise ValueError("JSON and Markdown output paths must differ")
        for output in outputs:
            if output.is_relative_to(args.raw_dir.resolve()) or (
                args.provenance is not None and output == args.provenance.resolve()
            ):
                raise ValueError("Outputs must not overwrite raw data or provenance")
        report = validate_dataset(
            args.raw_dir,
            provenance_path=args.provenance,
            scratch_dir=args.scratch_dir,
        )
        from mulegraph.validation_report import render_report

        for path, contents in (
            (args.json_output, json.dumps(report, indent=2, sort_keys=True) + "\n"),
            (args.report, render_report(report)),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Validation could not finish: {error}", file=sys.stderr)
        return 2
    print(
        f"Validation: {len(report['errors'])} errors, "
        f"{len(report['warnings'])} warnings"
    )
    print(f"Report: {args.report}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
