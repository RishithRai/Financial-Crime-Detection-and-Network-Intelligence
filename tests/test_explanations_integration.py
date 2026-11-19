"""Case-to-explanation integration using disposable core SQL and synthetic model."""

from datetime import datetime

import psycopg
import pytest
from test_explanations import service as service
from test_graph_integration import graph_db as graph_db

from mulegraph.cases import investigate_cases
from mulegraph.graph import graph_session
from mulegraph.schema import statement

pytestmark = pytest.mark.integration


def test_sql_case_annotations_preserve_case_scores_and_membership(graph_db, service):
    dsn, schema = graph_db
    s, table = service
    # Update only this uniquely named disposable fixture, never application data.
    assert schema.startswith("mg_test_")
    with psycopg.connect(dsn) as connection:
        for row in table.slice(0, 2).to_pylist():
            columns = (
                "occurred_at",
                "from_bank_id",
                "from_account",
                "to_bank_id",
                "to_account",
                "amount_paid",
                "payment_currency",
                "amount_received",
                "receiving_currency",
                "payment_format",
            )
            connection.execute(
                statement(
                    "UPDATE {core}.transactions SET "
                    + ",".join(c + "=%s" for c in columns)
                    + " WHERE dataset_id=1 AND source_row=%s",
                    schema,
                ),
                tuple(row[c] for c in columns) + (row["source_row"],),
            )
    with graph_session(dsn, 1, schema=schema) as reader:
        report = investigate_cases(
            reader,
            datetime(2022, 9, 7),
            datetime(2022, 9, 9),
            account=("1", "A"),
            scores=s.scores,
        )
        result = s.annotate_case_report(report, [1, 2])
        assert (
            result["cases"] == report["cases"]
            and result["accounts"] == report["accounts"]
        )
        assert result["transactions"] == report["transactions"]
        assert all(
            e["status"] == "EXPLAINED"
            for e in result["transaction_explanations"]["items"]
        )
