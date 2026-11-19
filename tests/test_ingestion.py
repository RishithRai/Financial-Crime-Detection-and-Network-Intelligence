"""PostgreSQL integration tests use only disposable, uniquely named schemas."""

import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from mulegraph.ingestion import ingest
from mulegraph.schema import statement
from mulegraph.validation import (
    ACCOUNT_HEADER,
    ACCOUNTS,
    PATTERNS,
    TRANSACTION_HEADER,
    TRANSACTIONS,
    validate_dataset,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def ingestion_case(tmp_path):
    dsn = os.environ.get("MULEGRAPH_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set MULEGRAPH_TEST_DATABASE_URL for ingestion integration tests")
    schema = "mg_test_" + uuid4().hex
    raw = tmp_path / "raw"
    raw.mkdir()
    accounts = [
        ["Bank One", "1", "000A", "E001", "Company,\nOne"],
        ["Bank Two", "2", "000A", "E002", "Company Two"],
    ]
    transaction = [
        "2022/09/01 00:00",
        "001",
        "000A",
        "0002",
        "000A",
        "0.000001",
        "Bitcoin",
        "1.10",
        "US Dollar",
        "ACH",
        "1",
    ]
    legitimate = transaction.copy()
    legitimate[0], legitimate[10] = "2022/09/12 00:00", "0"
    for name, header, rows in (
        (ACCOUNTS, ACCOUNT_HEADER, accounts),
        (TRANSACTIONS, TRANSACTION_HEADER, [transaction, transaction, legitimate]),
    ):
        with (raw / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
    (raw / PATTERNS).write_text(
        "BEGIN LAUNDERING ATTEMPT - CYCLE\n"
        + ",".join(transaction)
        + "\nEND LAUNDERING ATTEMPT - CYCLE\n",
        encoding="utf-8",
    )
    audit = validate_dataset(raw)
    assert not audit["errors"]
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit))
    manifest = {
        "dataset_version": "synthetic",
        "files": {
            name: {**values, "source_url": "synthetic-fixture"}
            for name, values in audit["files"].items()
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    yield {
        "database_url": dsn,
        "raw_dir": raw,
        "manifest_path": manifest_path,
        "audit_path": audit_path,
        "schema": schema,
        "dataset_key": "synthetic-test",
    }
    # Never drop the application schema; these names are created above by this test.
    assert schema.startswith("mg_test_")
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(statement("DROP SCHEMA IF EXISTS {labels} CASCADE", schema))
        connection.execute(statement("DROP SCHEMA IF EXISTS {core} CASCADE", schema))


def test_copy_preserves_duplicates_identifiers_money_and_labels(ingestion_case):
    result = ingest(**ingestion_case)
    assert result["outcome"] == "loaded"
    assert result["reconciliation"]["observed"]["duplicate_source_records"] == 1
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        rows = connection.execute(
            statement(
                """
            SELECT source_row, raw_from_bank_id, from_bank_id, from_account,
                raw_to_bank_id, to_bank_id, amount_received, amount_paid
            FROM {core}.transactions ORDER BY source_row
        """,
                schema,
            )
        ).fetchall()
        assert [row[0] for row in rows] == [1, 2, 3]
        assert rows[0][1:] == (
            "001",
            "1",
            "000A",
            "0002",
            "2",
            Decimal("0.000001"),
            Decimal("1.10"),
        )
        assert rows[0][1:] == rows[1][1:]
        assert (
            connection.execute(
                statement(
                    "SELECT count(*) FROM {core}.accounts "
                    "WHERE account_number = '000A'",
                    schema,
                )
            ).fetchone()[0]
            == 2
        )
        columns = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'transactions'",
            (schema,),
        ).fetchall()
        assert ("is_laundering",) not in columns
        assert ("source_record_sha256",) not in columns
        assert (
            connection.execute(
                statement(
                    "SELECT count(*) FROM {labels}.transaction_labels",
                    schema,
                )
            ).fetchone()[0]
            == 3
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM pg_namespace n, LATERAL aclexplode(n.nspacl) a "
                "WHERE n.nspname = %s AND a.grantee = 0",
                (schema + "_labels",),
            ).fetchone()[0]
            == 0
        )


def test_normalization_is_textual_and_validated(ingestion_case):
    ingest(**ingestion_case)
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        for original, expected in (
            ("000", "0"),
            ("001", "1"),
            ("10", "10"),
            ("000123456789012345678901234567890", "123456789012345678901234567890"),
            ("", None),
            (" 01", None),
            ("1A", None),
            ("١", None),
        ):
            assert (
                connection.execute(
                    statement(
                        "SELECT {core}.normalize_bank_id(%s)",
                        ingestion_case["schema"],
                    ),
                    (original,),
                ).fetchone()[0]
                == expected
            )


def test_rerun_and_read_only_verification_do_not_add_rows(ingestion_case):
    first = ingest(**ingestion_case)
    rerun = ingest(**ingestion_case)
    verified = ingest(**ingestion_case, verify_only=True)
    assert first["dataset_id"] == rerun["dataset_id"] == verified["dataset_id"]
    assert rerun["outcome"] == "already_loaded"
    assert verified["outcome"] == "verified"
    assert (
        first["reconciliation"] == rerun["reconciliation"] == verified["reconciliation"]
    )
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        assert (
            connection.execute(
                statement(
                    "SELECT count(*) FROM {core}.datasets",
                    ingestion_case["schema"],
                )
            ).fetchone()[0]
            == 1
        )


def test_concurrent_reruns_serialize(ingestion_case):
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(lambda _: ingest(**ingestion_case)["outcome"], range(2))
        )
    assert sorted(outcomes) == ["already_loaded", "loaded"]


def test_constraints_reject_bad_money_labels_and_references(ingestion_case):
    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"], autocommit=True) as connection:
        for amount in ("-1", "NaN", "Infinity", "-Infinity"):
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(
                    statement(
                        "UPDATE {core}.transactions SET amount_paid = %s "
                        "WHERE source_row = 1",
                        schema,
                    ),
                    (Decimal(amount),),
                )
        for query, error in (
            (
                "UPDATE {labels}.transaction_labels SET is_laundering = 2",
                psycopg.errors.CheckViolation,
            ),
            (
                "UPDATE {core}.transactions SET from_account = 'missing' "
                "WHERE source_row = 1",
                psycopg.errors.ForeignKeyViolation,
            ),
            (
                "UPDATE {core}.transactions SET raw_from_bank_id = 'bank' "
                "WHERE source_row = 1",
                psycopg.errors.NotNullViolation,
            ),
            (
                "UPDATE {core}.transactions SET source_row = 1 WHERE source_row = 2",
                psycopg.errors.UniqueViolation,
            ),
            (
                "UPDATE {labels}.transaction_labels SET source_row = 999 "
                "WHERE source_row = 1",
                psycopg.errors.ForeignKeyViolation,
            ),
            (
                "UPDATE {core}.accounts SET raw_bank_id = '01' WHERE source_row = 2",
                psycopg.errors.UniqueViolation,
            ),
        ):
            with pytest.raises(error), connection.transaction():
                connection.execute(statement(query, schema))


def test_failed_reconciliation_rolls_back_entire_load(ingestion_case):
    path = ingestion_case["audit_path"]
    audit = json.loads(path.read_text())
    audit["transactions"]["duplicate_rows"] = 0
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="SQL reconciliation failed"):
        ingest(**ingestion_case)
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        assert (
            connection.execute(
                "SELECT to_regclass(%s)", (ingestion_case["schema"] + ".datasets",)
            ).fetchone()[0]
            is None
        )


def test_changed_raw_file_is_rejected(ingestion_case):
    ingest(**ingestion_case)
    with (ingestion_case["raw_dir"] / TRANSACTIONS).open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="fingerprints"):
        ingest(**ingestion_case)


def test_rerun_detects_missing_label_without_repairing_data(ingestion_case):
    ingest(**ingestion_case)
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "DELETE FROM {labels}.transaction_labels WHERE source_row = 1",
                ingestion_case["schema"],
            )
        )
    with pytest.raises(ValueError, match="SQL reconciliation failed"):
        ingest(**ingestion_case)


def test_eda_aggregates_preserve_duplicates_composite_accounts_and_money(
    ingestion_case,
):
    from mulegraph.eda import analyze

    ingest(**ingestion_case)
    result = analyze(
        ingestion_case["database_url"],
        schema=ingestion_case["schema"],
        dataset_key="synthetic-test",
    )
    assert result["database"]["read_only"] == "on"
    assert result["database"]["isolation"] == "repeatable read"
    assert result["totals"][0]["transactions"] == 3
    assert [
        (r["split"], r["transactions"], r["positives"]) for r in result["splits"]
    ] == [("train", 2, 2), ("validation", 0, 0), ("test", 0, 0), ("stress", 1, 0)]
    assert [r["active_accounts"] for r in result["activity"]] == [2, 2]
    assert [r["newly_observed_accounts"] for r in result["activity"]] == [2, 0]
    assert result["activity"][0]["p50"] == 2
    assert result["activity"][0]["touches_positive"] == 2
    assert result["ties"][0]["transactions_in_ties"] == "2"
    assert result["ties"][0]["largest_group"] == 2
    assert all(r["self_transfers"] == 0 for r in result["daily"])
    assert [r["cross_currency"] for r in result["daily"]] == [2, 1]
    paid = next(
        r for r in result["amounts"] if r["side"] == "paid" and r["period"] == "primary"
    )
    assert paid["transactions"] == 2
    assert Decimal(paid["p50"]) == Decimal("1.10")
    assert Decimal(paid["total"]) == Decimal("2.20")
    received = next(
        r
        for r in result["amounts"]
        if r["side"] == "received" and r["period"] == "primary"
    )
    assert Decimal(received["p99"]) == Decimal("0.000001")
    assert sum(r["transactions"] for r in result["hours"]) == 3
    assert ingest(**ingestion_case, verify_only=True)["outcome"] == "verified"


def test_eda_sql_boundaries_and_missing_labels(ingestion_case):
    from datetime import datetime, timedelta

    from mulegraph.eda import SPLITS, analyze, queries, split_for

    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(statement("DELETE FROM {labels}.transaction_labels", schema))
        # All fixture records share a timestamp; ties cannot split.
        for _, start, end in SPLITS:
            for timestamp in (start, end - timedelta(microseconds=1)):
                connection.execute(
                    statement(
                        "UPDATE {core}.transactions SET occurred_at = %s", schema
                    ),
                    (timestamp,),
                )
                rows = connection.execute(
                    statement(queries()["splits"], schema),
                    {
                        "dataset_id": 1,
                        "splits": json.dumps(
                            [
                                {
                                    "split": name,
                                    "starts_at": a.isoformat(),
                                    "ends_at": b.isoformat(),
                                }
                                for name, a, b in SPLITS
                            ]
                        ),
                    },
                ).fetchall()
                assert [(r[0], r[3]) for r in rows if r[3]] == [
                    (split_for(timestamp), 3)
                ]
        connection.execute(
            statement("UPDATE {core}.transactions SET occurred_at = %s", schema),
            (datetime(2022, 9, 1),),
        )
    with pytest.raises(ValueError, match="Missing labels"):
        analyze(
            ingestion_case["database_url"], schema=schema, dataset_key="synthetic-test"
        )


def test_eda_self_transfer_counts_once_and_rejects_unassigned_dates(ingestion_case):
    from mulegraph.eda import analyze

    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET raw_to_bank_id = raw_from_bank_id, "
                "to_account = from_account WHERE source_row = 3",
                schema,
            )
        )
    result = analyze(
        ingestion_case["database_url"], schema=schema, dataset_key="synthetic-test"
    )
    tail = result["activity"][1]
    assert tail["active_accounts"] == 1
    assert tail["senders"] == tail["receivers"] == tail["p50"] == 1
    assert result["daily"][1]["self_transfers"] == 1
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET occurred_at = '2022-09-19' "
                "WHERE source_row = 3",
                schema,
            )
        )
    with pytest.raises(ValueError, match="outside the split policy"):
        analyze(
            ingestion_case["database_url"], schema=schema, dataset_key="synthetic-test"
        )


def test_eda_exact_numeric_percentiles_and_category_counts(ingestion_case):
    from mulegraph.eda import analyze

    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET occurred_at = '2022-09-01', "
                "amount_paid = CASE source_row WHEN 1 THEN 0.01 "
                "WHEN 2 THEN 10.123456789 ELSE 1000000000000.99 END",
                schema,
            )
        )
        connection.execute(
            statement(
                "UPDATE {labels}.transaction_labels SET is_laundering = 0", schema
            )
        )
    result = analyze(
        ingestion_case["database_url"], schema=schema, dataset_key="synthetic-test"
    )
    paid = next(r for r in result["amounts"] if r["side"] == "paid")
    assert Decimal(paid["p50"]) == Decimal("10.123456789")
    assert Decimal(paid["p90"]) == Decimal("1000000000000.99")
    assert Decimal(paid["total"]) == Decimal("1000000000011.123456789")
    formats = [r for r in result["categories"] if r["category"] == "payment_format"]
    assert len(formats) == 1
    assert formats[0]["value"] == "ACH"
    assert formats[0]["transactions"] == 3


def test_feature_pipeline_persistence_reuse_and_label_isolation(
    ingestion_case, tmp_path
):
    import pyarrow.parquet as pq

    from mulegraph.features import build_features

    ingest(**ingestion_case)
    options = {
        "schema": ingestion_case["schema"],
        "dataset_key": "synthetic-test",
        "output_dir": tmp_path / "features",
        "progress": lambda _: None,
    }
    result = build_features(ingestion_case["database_url"], **options)
    from pathlib import Path

    rows = pq.read_table(Path(result["path"]) / "features.parquet").to_pylist()
    assert result["completeness"]["rows"] == 3
    assert result["completeness"]["invalid_rows"] == 0
    assert rows[0]["sender_history_count"] == rows[1]["sender_history_count"] == 0
    assert rows[2]["sender_history_count"] == rows[2]["receiver_history_count"] == 2
    assert rows[2]["sender_currency_history_sum"] == Decimal("2.2")
    assert rows[2]["receiver_currency_history_sum"] == Decimal("0.000002")
    assert rows[2]["sender_count_24h"] == 0
    assert rows[2]["split"] == "stress"
    assert rows[0]["from_bank_id"] == "1" and rows[0]["from_account"] == "000A"
    assert rows[0]["to_bank_id"] == "2" and not rows[0]["self_transfer"]
    assert not any("launder" in name or "label" in name for name in rows[0])
    # The pipeline must still succeed when every row-level label is absent.
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "DELETE FROM {labels}.transaction_labels", ingestion_case["schema"]
            )
        )
    reused = build_features(ingestion_case["database_url"], **options)
    assert reused["outcome"] == "already_built"
    fresh = build_features(
        ingestion_case["database_url"],
        **{**options, "output_dir": tmp_path / "label_free"},
    )
    assert pq.read_table(Path(fresh["path"]) / "features.parquet").to_pylist() == rows


def test_feature_pipeline_future_and_peer_invariance(ingestion_case, tmp_path):
    from pathlib import Path

    import pyarrow.parquet as pq

    from mulegraph.features import build_features

    ingest(**ingestion_case)
    options = {
        "schema": ingestion_case["schema"],
        "dataset_key": "synthetic-test",
        "progress": lambda _: None,
    }
    before = build_features(
        ingestion_case["database_url"], output_dir=tmp_path / "before", **options
    )
    original = pq.read_table(Path(before["path"]) / "features.parquet").to_pylist()
    # New peer of row 3 and a future transaction. No labels added or consulted.
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        for source, timestamp in ((4, "2022-09-12"), (5, "2022-09-13")):
            connection.execute(
                statement(
                    "INSERT INTO {core}.transactions "
                    "(dataset_id, source_row, occurred_at, "
                    "raw_from_bank_id, from_account, raw_to_bank_id, to_account, "
                    "amount_received, receiving_currency, "
                    "amount_paid, payment_currency, "
                    "payment_format) SELECT dataset_id, %s, %s::timestamp, "
                    "raw_from_bank_id, "
                    "from_account, raw_to_bank_id, to_account, "
                    "999, receiving_currency, "
                    "999, payment_currency, payment_format FROM {core}.transactions "
                    "WHERE source_row = 3",
                    ingestion_case["schema"],
                ),
                (source, timestamp),
            )
    after = build_features(
        ingestion_case["database_url"], output_dir=tmp_path / "after", **options
    )
    expanded = pq.read_table(Path(after["path"]) / "features.parquet").to_pylist()
    assert expanded[:3] == original
    assert expanded[-1]["sender_history_count"] == 4
    with pytest.raises(ValueError, match="changed"):
        build_features(
            ingestion_case["database_url"], output_dir=tmp_path / "before", **options
        )


def test_failed_features_do_not_publish_partial_artifacts(ingestion_case, tmp_path):
    from mulegraph.features import build_features

    ingest(**ingestion_case)
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET amount_paid = 0.0000000001 "
                "WHERE source_row = 3",
                ingestion_case["schema"],
            )
        )
    destination = tmp_path / "features"
    with pytest.raises(ValueError, match="precision"):
        build_features(
            ingestion_case["database_url"],
            output_dir=destination,
            schema=ingestion_case["schema"],
            dataset_key="synthetic-test",
        )
    assert not list(destination.rglob("*.parquet"))
    assert not list(destination.rglob("manifest.json"))


def test_rules_staged_pipeline_freezes_before_holdouts(
    ingestion_case, tmp_path, monkeypatch
):
    from pathlib import Path

    import pyarrow.parquet as pq

    import mulegraph.rules_baseline as pipeline
    from mulegraph.features import build_features

    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET occurred_at='2022-09-07' "
                "WHERE source_row=3",
                schema,
            )
        )
        connection.execute(
            statement(
                "UPDATE {labels}.transaction_labels SET is_laundering=1 "
                "WHERE source_row=3",
                schema,
            )
        )
        for source, at, label in (
            (4, "2022-09-09", 1),
            (5, "2022-09-11", 0),
            (6, "2022-09-08", 0),
        ):
            connection.execute(
                statement(
                    """
                INSERT INTO {core}.transactions (dataset_id, source_row, occurred_at,
                    raw_from_bank_id, from_account, raw_to_bank_id, to_account,
                    amount_received, receiving_currency, amount_paid, payment_currency,
                    payment_format)
                SELECT dataset_id, %s, %s::timestamp, raw_from_bank_id, from_account,
                    raw_to_bank_id, to_account, amount_received, receiving_currency,
                    amount_paid, payment_currency, payment_format
                FROM {core}.transactions WHERE source_row=3
            """,
                    schema,
                ),
                (source, at),
            )
            connection.execute(
                statement(
                    """
                INSERT INTO {labels}.transaction_labels
                SELECT dataset_id, %s, %s, source_record_sha256
                FROM {labels}.transaction_labels WHERE source_row=3
            """,
                    schema,
                ),
                (source, label),
            )
    features = build_features(
        ingestion_case["database_url"],
        output_dir=tmp_path / "features",
        schema=schema,
        dataset_key="synthetic-test",
        progress=lambda _: None,
    )
    feature_dir = Path(features["path"])
    output = tmp_path / "rules"
    access = []
    original = pipeline.export_labels

    def record_access(*args, **kwargs):
        access.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "export_labels", record_access)
    with pytest.raises(ValueError, match="Finalize"):
        pipeline.evaluate_holdouts("invalid", feature_dir, output, schema=schema)
    assert access == []
    calibrated = pipeline.calibrate(
        ingestion_case["database_url"], feature_dir, output, schema=schema
    )
    assert access == ["validation"]
    assert calibrated["validation"]["risk_score"]["rows"] == 2
    assert calibrated["validation"]["risk_score"]["average_precision"] == 0.5
    assert calibrated["validation"]["risk_score"]["alerts"] == 0
    before = (output / "rules.json").read_bytes()
    predictions = pq.read_table(output / "validation_predictions.parquet")
    assert "is_laundering" not in predictions.column_names
    result = pipeline.evaluate_holdouts(
        ingestion_case["database_url"], feature_dir, output, schema=schema
    )
    assert access == ["validation", "test", "stress"]
    assert result["test"]["risk_score"]["average_precision"] == 1
    assert result["stress"]["risk_score"]["average_precision"] is None
    assert (output / "rules.json").read_bytes() == before
    with pytest.raises(ValueError, match="already evaluated"):
        pipeline.evaluate_holdouts("invalid", feature_dir, output)
    with pytest.raises(ValueError, match="already exists"):
        pipeline.calibrate("invalid", feature_dir, output)
    assert access == ["validation", "test", "stress"]
    assert not list(output.rglob("labels.parquet"))
    from mulegraph.features import sha256_file

    assert sha256_file(feature_dir / "features.parquet") == features["file_sha256"]


def test_ml_label_access_is_train_validation_only(ingestion_case, tmp_path):
    import duckdb

    from mulegraph.ml_training import aligned_labels, export_labels

    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        dataset_id, fingerprint = connection.execute(
            statement("SELECT dataset_id,fingerprint FROM {core}.datasets", schema)
        ).fetchone()
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET occurred_at='2022-09-07' "
                "WHERE source_row=2",
                schema,
            )
        )
    manifest = {
        "dataset": {
            "dataset_id": dataset_id,
            "fingerprint": fingerprint,
            "dataset_key": ingestion_case["dataset_key"],
        }
    }
    paths = {}
    for split in ("train", "validation"):
        path = tmp_path / f"ml_{split}.parquet"
        paths[split] = path
        evidence = export_labels(
            ingestion_case["database_url"], manifest, split, path, schema
        )
        assert evidence["rows"] == 1
    # Row 3 is in the stress period and must be absent from BOTH exports.
    from datetime import datetime

    import pyarrow as pa
    import pyarrow.parquet as pq

    assert pq.read_table(paths["train"])["source_row"].to_pylist() == [1]
    assert pq.read_table(paths["validation"])["source_row"].to_pylist() == [2]
    with duckdb.connect() as db:
        db.register(
            "features",
            pa.table(
                {
                    "source_row": [1],
                    "split": ["train"],
                    "occurred_at": [datetime(2022, 9, 1)],
                }
            ),
        )
        rows, labels = aligned_labels(db, "train", paths["train"])
        assert rows.tolist() == [1] and labels.tolist() == [1]
        with pytest.raises(ValueError, match="coverage"):
            aligned_labels(db, "train", paths["validation"])


def test_supervised_holdout_export_dates_and_freeze_gate(
    ingestion_case, tmp_path, monkeypatch
):
    import pyarrow.parquet as pq

    from mulegraph.ml_holdout import export_holdout

    ingest(**ingestion_case)
    schema = ingestion_case["schema"]
    with psycopg.connect(ingestion_case["database_url"]) as connection:
        dataset_id, fingerprint = connection.execute(
            statement("SELECT dataset_id,fingerprint FROM {core}.datasets", schema)
        ).fetchone()
        connection.execute(
            statement(
                "UPDATE {core}.transactions SET occurred_at=CASE source_row "
                "WHEN 1 THEN TIMESTAMP '2022-09-09' "
                "WHEN 2 THEN TIMESTAMP '2022-09-18 23:59' "
                "ELSE TIMESTAMP '2022-09-19' END",
                schema,
            )
        )
    manifest = {
        "dataset": {
            "dataset_id": dataset_id,
            "fingerprint": fingerprint,
            "dataset_key": ingestion_case["dataset_key"],
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}")
    checked = []

    def validated(*args):
        checked.append(True)
        return manifest

    monkeypatch.setattr("mulegraph.ml_holdout.validate_freeze", validated)
    for split, expected in (("test", [1]), ("stress", [2])):
        path = tmp_path / f"{split}_holdout_labels.parquet"
        access = export_holdout(
            ingestion_case["database_url"], split, path, freeze, tmp_path, {}, schema
        )
        assert (
            access["rows"] == 1
            and access["freeze_verified_at"] < access["retrieved_at"]
        )
        assert pq.read_table(path)["source_row"].to_pylist() == expected
    assert len(checked) == 2
