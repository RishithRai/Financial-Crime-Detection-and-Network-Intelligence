"""Small synthetic fixtures exercise audit behavior without downloading data."""

import csv
import json
from pathlib import Path

import pytest

from mulegraph import validation as audit
from mulegraph.validation_report import render_report


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def dataset(tmp_path):
    accounts = [
        ["Bank A", "1", "000A", "entity-1", "Alice"],
        ["Bank B", "2", "000A", "entity-2", "Bob"],
    ]
    transaction = [
        "2022/09/01 00:00",
        "001",
        "000A",
        "002",
        "000A",
        "1.10",
        "US Dollar",
        "1.10",
        "US Dollar",
        "ACH",
        "1",
    ]
    write_csv(tmp_path / audit.ACCOUNTS, audit.ACCOUNT_HEADER, accounts)
    write_csv(tmp_path / audit.TRANSACTIONS, audit.TRANSACTION_HEADER, [transaction])
    (tmp_path / audit.PATTERNS).write_text(
        "BEGIN LAUNDERING ATTEMPT - CYCLE\n"
        + ",".join(transaction)
        + "\nEND LAUNDERING ATTEMPT - CYCLE\n",
        encoding="utf-8",
    )
    return tmp_path, accounts, transaction


def test_positional_headers_composite_identity_and_unchanged_bytes(
    dataset, monkeypatch
):
    root, _, _ = dataset
    monkeypatch.setattr(audit, "BATCH_SIZE", 1)
    before = {name: audit.file_fingerprint(root / name) for name in audit.FILES}
    result = audit.validate_dataset(root, scratch_dir=root / "scratch")
    assert result["errors"] == []
    assert result["transactions"]["header"].count("Account") == 2
    assert result["transactions"]["rows"] == 1
    assert result["transactions"]["self_transfers"] == 0
    relationships = result["relationships"]
    assert relationships["account_composite_keys"] == 2
    assert relationships["account_numbers"] == 1
    assert relationships["account_numbers_in_multiple_banks"] == 1
    assert relationships["literal"]["unmatched_composite_keys"] == 2
    assert relationships["bank_padding_diagnostic"]["unmatched_composite_keys"] == 0
    assert result["patterns"]["unmatched_rows"] == 0
    assert before == {name: audit.file_fingerprint(root / name) for name in audit.FILES}
    assert list((root / "scratch").iterdir()) == []
    markdown = render_report(result)
    assert "Positions **3 and 5" in markdown
    assert "000A" not in markdown


def test_exact_duplicates_across_batches_and_account_metadata(dataset, monkeypatch):
    root, accounts, row = dataset
    monkeypatch.setattr(audit, "BATCH_SIZE", 2)
    changed = row.copy()
    changed[5] = "1.100"  # Different original field representation, same decimal value.
    write_csv(root / audit.TRANSACTIONS, audit.TRANSACTION_HEADER, [row, changed, row])
    write_csv(root / audit.ACCOUNTS, audit.ACCOUNT_HEADER, accounts + [accounts[0]])
    result = audit.validate_dataset(root)
    assert result["transactions"]["rows"] == 3
    assert result["transactions"]["duplicate_rows"] == 1
    assert result["accounts"]["duplicate_rows"] == 1
    assert result["relationships"]["literal"]["unmatched_sender_rows"] == 3
    assert result["transactions"]["same_currency_unequal_amounts"] == 0


@pytest.mark.parametrize(
    ("index", "value", "reason"),
    [
        (0, "2022/02/30 00:00", "invalid_timestamp"),
        (0, "2022/9/01 00:00", "invalid_timestamp"),
        (1, "bank", "invalid_bank_2"),
        (5, "NaN", "invalid_amount_6"),
        (5, "Infinity", "invalid_amount_6"),
        (7, "-0.01", "invalid_amount_8"),
        (7, "text", "invalid_amount_8"),
        (10, "2", "invalid_label"),
        (2, "", "missing_field"),
        (2, " 000A", "surrounding_whitespace"),
    ],
)
def test_invalid_transaction_fields(dataset, index, value, reason):
    _, _, original = dataset
    row = original.copy()
    row[index] = value
    assert reason in audit.transaction_issues(row)


def test_invalid_rows_missing_values_and_short_records(dataset):
    root, _, original = dataset
    row = original.copy()
    row[2], row[5], row[10] = "", "NaN", "bad"
    write_csv(
        root / audit.TRANSACTIONS, audit.TRANSACTION_HEADER, [original, row, ["short"]]
    )
    result = audit.validate_dataset(root)
    transactions = result["transactions"]
    assert transactions["invalid_rows"] == 2
    assert transactions["missing"]["3: Account"] == 1
    assert transactions["invalid_reasons"]["wrong_field_count"] == 1
    assert transactions["amounts"]["Amount Received"]["US Dollar"]["invalid_count"] == 1
    assert any("2 invalid records" in error for error in result["errors"])


def test_time_order_outside_window_class_counts_and_money(dataset):
    root, _, original = dataset
    early, late = original.copy(), original.copy()
    early[10] = "0"
    early[5] = early[7] = "0"
    late[0], late[5], late[6] = "2022/09/12 00:00", "0.90", "Euro"
    write_csv(
        root / audit.TRANSACTIONS, audit.TRANSACTION_HEADER, [late, original, early]
    )
    result = audit.validate_dataset(root)["transactions"]
    assert result["timestamps"]["adjacent_decreases"] == 1
    assert result["timestamps"]["outside_primary_window_by_label"] == {"1": 1}
    assert result["timestamps"]["min"] == "2022-09-01 00:00:00"
    assert result["categories"]["Is Laundering"] == {"0": 1, "1": 2}
    assert result["laundering_rate_percent"] == pytest.approx(200 / 3)
    assert result["cross_currency_rows"] == 1
    assert result["amounts"]["Amount Received"]["Euro"]["max"] == "0.90"
    assert result["amounts"]["Amount Paid"]["US Dollar"]["zero_count"] == 1


def test_unmatched_accounts_conflicting_entities_and_padding_collision(dataset):
    root, accounts, row = dataset
    accounts += [
        ["Bank A", "1", "000A", "other-entity", "Other"],
        ["Bank A padded", "01", "000A", "entity-1", "Alice"],
    ]
    row[4] = "A"  # Never normalize leading zeros in account identifiers.
    write_csv(root / audit.ACCOUNTS, audit.ACCOUNT_HEADER, accounts)
    write_csv(root / audit.TRANSACTIONS, audit.TRANSACTION_HEADER, [row])
    result = audit.validate_dataset(root)
    assert result["relationships"]["composite_keys_with_multiple_entities"] == 1
    assert result["relationships"]["bank_normalization_collisions"] == 1
    assert (
        result["relationships"]["bank_padding_diagnostic"]["unmatched_receiver_rows"]
        == 1
    )
    assert any("multiple entities" in error for error in result["errors"])


def test_bad_patterns_structure_labels_and_references(dataset):
    root, _, row = dataset
    row[10] = "0"
    (root / audit.PATTERNS).write_text(
        "BEGIN LAUNDERING ATTEMPT - CYCLE\n"
        + ",".join(row)
        + "\n"
        + ",".join(row)
        + "\nEND LAUNDERING ATTEMPT - FAN-OUT\n",
        encoding="utf-8",
    )
    result = audit.validate_dataset(root)
    assert result["patterns"]["structure_errors"] == 1
    assert result["patterns"]["non_laundering_rows"] == 2
    assert result["patterns"]["unmatched_rows"] == 2
    assert result["patterns"]["duplicate_rows"] == 1
    assert result["errors"]


def test_wrong_header_stops_positional_interpretation(dataset):
    root, _, row = dataset
    header = audit.TRANSACTION_HEADER.copy()
    header[4] = "Account.1"
    write_csv(root / audit.TRANSACTIONS, header, [row])
    result = audit.validate_dataset(root)
    assert not result["transactions"]["complete"]
    assert "relationships" not in result
    assert result["errors"]


def test_malformed_csv_marks_audit_incomplete(dataset):
    root, _, _ = dataset
    with (root / audit.TRANSACTIONS).open("a") as stream:
        stream.write('"unterminated')
    result = audit.validate_dataset(root)
    assert not result["transactions"]["complete"]
    assert result["errors"]


def test_provenance_integrity_mismatch(dataset):
    root, _, _ = dataset
    fingerprints = {name: audit.file_fingerprint(root / name) for name in audit.FILES}
    fingerprints[audit.TRANSACTIONS]["sha256"] = "0" * 64
    provenance = root / "manifest.json"
    provenance.write_text(json.dumps({"files": fingerprints}))
    result = audit.validate_dataset(root, provenance_path=provenance)
    assert any("fingerprint mismatch" in error for error in result["errors"])


def test_missing_files_are_errors_and_report_has_no_invented_counts(tmp_path):
    result = audit.validate_dataset(tmp_path)
    assert len(result["errors"]) == 3
    assert "transactions" not in result
    assert "Missing required file" in render_report(result)


def test_cli_writes_reports_and_returns_validation_status(dataset, monkeypatch):
    root, _, _ = dataset
    json_path = root.parent / f"{root.name}-audit.json"
    report_path = root.parent / f"{root.name}-audit.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate",
            "--raw-dir",
            str(root),
            "--scratch-dir",
            str(root / "scratch"),
            "--json-output",
            str(json_path),
            "--report",
            str(report_path),
        ],
    )
    assert audit.main() == 0
    assert json.loads(json_path.read_text())["transactions"]["rows"] == 1
    assert "0 errors" in report_path.read_text()
    (root / audit.PATTERNS).unlink()
    assert audit.main() == 1
    assert "Missing required file" in report_path.read_text()


def test_cli_rejects_output_over_raw_input(dataset, monkeypatch):
    root, _, _ = dataset
    target = root / audit.TRANSACTIONS
    before = target.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate",
            "--raw-dir",
            str(root),
            "--report",
            str(target),
        ],
    )
    assert audit.main() == 2
    assert target.read_bytes() == before
