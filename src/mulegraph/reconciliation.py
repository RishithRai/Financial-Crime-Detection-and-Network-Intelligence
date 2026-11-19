"""SQL reconciliation against the byte-matched Milestone 0B audit."""

from decimal import Decimal

import psycopg

from mulegraph.schema import sql_file, statement


def reconcile(
    connection: psycopg.Connection,
    schema: str,
    dataset_id: int,
    audit: dict,
) -> dict:
    """Raise on any mismatch, so callers cannot commit an unreconciled import."""
    checks = []

    def check(name: str, actual: object, expected: object) -> None:
        passed = actual == expected
        checks.append(
            {
                "name": name,
                "passed": passed,
                "actual": str(actual) if isinstance(actual, Decimal) else actual,
                "expected": str(expected)
                if isinstance(expected, Decimal)
                else expected,
            }
        )

    def scalar(query: str) -> object:
        return connection.execute(statement(query, schema), (dataset_id,)).fetchone()[0]

    cursor = connection.execute(
        statement(sql_file("reconcile.sql"), schema),
        {"dataset_id": dataset_id},
    )
    observed = dict(
        zip(
            (column.name for column in cursor.description),
            cursor.fetchone(),
            strict=True,
        )
    )
    transactions = audit["transactions"]
    outside = transactions["timestamps"]["outside_primary_window_by_label"]
    expectations = {
        "transactions": transactions["rows"],
        "first_source_row": 1,
        "last_source_row": transactions["rows"],
        "labels": transactions["rows"],
        "laundering": transactions["categories"]["Is Laundering"].get("1", 0),
        "legitimate": transactions["categories"]["Is Laundering"].get("0", 0),
        "min_timestamp": transactions["timestamps"]["min"],
        "max_timestamp": transactions["timestamps"]["max"],
        "self_transfers": transactions["self_transfers"],
        "cross_currency_rows": transactions["cross_currency_rows"],
        "same_currency_unequal_amounts": transactions["same_currency_unequal_amounts"],
        "outside_window_laundering": outside.get("1", 0),
        "outside_window_legitimate": outside.get("0", 0),
    }
    for name, expected in expectations.items():
        check(name, observed[name], expected)

    for name, query, expected in (
        (
            "accounts",
            "SELECT count(*) FROM {core}.accounts WHERE dataset_id = %s",
            audit["accounts"]["rows"],
        ),
        (
            "first_account_source_row",
            "SELECT min(source_row) FROM {core}.accounts WHERE dataset_id = %s",
            1,
        ),
        (
            "last_account_source_row",
            "SELECT max(source_row) FROM {core}.accounts WHERE dataset_id = %s",
            audit["accounts"]["rows"],
        ),
        (
            "banks",
            "SELECT count(*) FROM {core}.banks WHERE dataset_id = %s",
            audit["relationships"]["account_banks"],
        ),
        (
            "entities",
            "SELECT count(*) FROM {core}.entities WHERE dataset_id = %s",
            audit["relationships"]["entities"],
        ),
        (
            "duplicate_source_records",
            """SELECT count(*) - count(DISTINCT source_record_sha256)
            FROM {labels}.transaction_labels WHERE dataset_id = %s""",
            transactions["duplicate_rows"],
        ),
        (
            "account_numbers_in_multiple_banks",
            """SELECT count(*) FROM (
            SELECT account_number FROM {core}.accounts WHERE dataset_id = %s
            GROUP BY account_number HAVING count(DISTINCT bank_id) > 1) a""",
            audit["relationships"]["account_numbers_in_multiple_banks"],
        ),
        (
            "unmatched_endpoints",
            """SELECT count(*) FROM {core}.transactions t
            LEFT JOIN {core}.accounts a ON (a.dataset_id, a.bank_id, a.account_number)
                = (t.dataset_id, t.from_bank_id, t.from_account)
            LEFT JOIN {core}.accounts b ON (b.dataset_id, b.bank_id, b.account_number)
                = (t.dataset_id, t.to_bank_id, t.to_account)
            WHERE t.dataset_id = %s
                AND (a.source_row IS NULL OR b.source_row IS NULL)""",
            0,
        ),
        (
            "unused_accounts",
            """SELECT count(*) FROM {core}.accounts a
            WHERE a.dataset_id = %s AND NOT EXISTS (
                SELECT 1 FROM {core}.transactions t WHERE t.dataset_id = a.dataset_id
                AND t.from_bank_id = a.bank_id AND t.from_account = a.account_number)
            AND NOT EXISTS (SELECT 1 FROM {core}.transactions t
                WHERE t.dataset_id = a.dataset_id AND t.to_bank_id = a.bank_id
                AND t.to_account = a.account_number)""",
            audit["relationships"]["account_keys_unused_after_bank_normalization"],
        ),
    ):
        value = scalar(query)
        check(name, value, expected)
        observed[name] = value

    source_files = connection.execute(
        statement(
            """
        SELECT file_name, size_bytes, sha256 FROM {core}.source_files
        WHERE dataset_id = %s
    """,
            schema,
        ),
        (dataset_id,),
    ).fetchall()
    check(
        "source_files",
        {
            name: {"size_bytes": size, "sha256": digest}
            for name, size, digest in source_files
        },
        audit["files"],
    )

    for column, category in (
        ("receiving_currency", "Receiving Currency"),
        ("payment_currency", "Payment Currency"),
        ("payment_format", "Payment Format"),
    ):
        rows = connection.execute(
            statement(
                "SELECT " + column + ", count(*) FROM {core}.transactions "
                "WHERE dataset_id = %s GROUP BY " + column,
                schema,
            ),
            (dataset_id,),
        ).fetchall()
        check(category, dict(rows), transactions["categories"][category])

    dates = connection.execute(
        statement(
            """
        SELECT t.occurred_at::date::text || ' | ' || l.is_laundering::text, count(*)
        FROM {core}.transactions t JOIN {labels}.transaction_labels l
        USING (dataset_id, source_row) WHERE t.dataset_id = %s GROUP BY 1
    """,
            schema,
        ),
        (dataset_id,),
    ).fetchall()
    check("dates_by_label", dict(dates), transactions["timestamps"]["dates_by_label"])

    for amount, currency, side in (
        ("amount_received", "receiving_currency", "Amount Received"),
        ("amount_paid", "payment_currency", "Amount Paid"),
    ):
        rows = connection.execute(
            statement(
                f"SELECT {currency}, count(*), min({amount}), max({amount}), "
                f"count(*) FILTER (WHERE {amount} = 0) FROM {{core}}.transactions "
                f"WHERE dataset_id = %s GROUP BY {currency}",
                schema,
            ),
            (dataset_id,),
        ).fetchall()
        for name, count, minimum, maximum, zeros in rows:
            expected = transactions["amounts"][side][name]
            for metric, actual, wanted in (
                ("count", count, expected["finite_count"]),
                ("min", minimum, Decimal(expected["min"])),
                ("max", maximum, Decimal(expected["max"])),
                ("zeros", zeros, expected["zero_count"]),
            ):
                check(f"{side}/{name}/{metric}", actual, wanted)

    failed = [item["name"] for item in checks if not item["passed"]]
    if failed:
        raise ValueError("SQL reconciliation failed: " + ", ".join(failed))
    return {
        "passed": True,
        "check_count": len(checks),
        "observed": observed,
        "checks": checks,
    }
