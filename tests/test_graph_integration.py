"""Graph queries against disposable core-only schemas: no labels exist."""

import os
from datetime import datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from mulegraph.graph import GraphLimitExceeded, Limits, graph_session, statistics
from mulegraph.schema import statement

pytestmark = pytest.mark.integration
START = datetime(2022, 9, 1)
CUTOFF = START + timedelta(hours=2)
A, B = ("1", "000A"), ("2", "000A")


@pytest.fixture
def graph_db():
    dsn = os.environ.get("MULEGRAPH_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set MULEGRAPH_TEST_DATABASE_URL for PostgreSQL tests")
    schema = "mg_test_" + uuid4().hex
    try:
        with psycopg.connect(dsn) as c:
            c.execute(statement("CREATE SCHEMA {core}", schema))
            c.execute(
                statement(
                    """
                CREATE TABLE {core}.datasets
                    (dataset_id bigint PRIMARY KEY, fingerprint text, status text);
                INSERT INTO {core}.datasets VALUES (1,'synthetic','complete'),
                    (2,'other','complete'),(3,'incomplete','loading');
                CREATE TABLE {core}.transactions (
                    dataset_id bigint, source_row bigint, occurred_at timestamp,
                    from_bank_id text, from_account text, to_bank_id text,
                    to_account text, amount_paid numeric, payment_currency text,
                    amount_received numeric, receiving_currency text,
                    payment_format text, PRIMARY KEY(dataset_id,source_row));
                CREATE INDEX sender_idx ON {core}.transactions
                    (dataset_id,from_bank_id,from_account,occurred_at);
                CREATE INDEX receiver_idx ON {core}.transactions
                    (dataset_id,to_bank_id,to_account,occurred_at);
            """,
                    schema,
                )
            )
            records = [
                (1, START, A, B),
                (2, START, A, B),
                (3, START, B, A),
                (4, START, A, A),
                (5, CUTOFF, A, ("1", "C")),
                (6, CUTOFF, A, ("1", "D")),
                (7, CUTOFF + timedelta(seconds=1), A, B),
                (8, START - timedelta(seconds=1), A, B),
            ]
            for row, time, sender, receiver in records:
                c.execute(
                    statement(
                        """INSERT INTO {core}.transactions VALUES
                    (1,%s,%s,%s,%s,%s,%s,1.10,'USD',0.000001,'Bitcoin','ACH')""",
                        schema,
                    ),
                    (row, time, *sender, *receiver),
                )
            c.execute(
                statement(
                    """INSERT INTO {core}.transactions
                SELECT 2,source_row,occurred_at,from_bank_id,from_account,to_bank_id,
                to_account,amount_paid,payment_currency,amount_received,
                receiving_currency,payment_format FROM {core}.transactions
                WHERE source_row=1""",
                    schema,
                )
            )
        yield dsn, schema
    finally:
        assert schema.startswith("mg_test_")
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(statement("DROP SCHEMA IF EXISTS {core} CASCADE", schema))


def test_sql_alignment_temporal_multiedges_and_readonly(graph_db):
    dsn, schema = graph_db
    with graph_session(dsn, 1, schema=schema) as reader:
        assert reader.connection.execute("SHOW transaction_read_only").fetchone() == {
            "transaction_read_only": "on"
        }
        assert reader.connection.execute("SHOW transaction_isolation").fetchone() == {
            "transaction_isolation": "repeatable read"
        }
        history = reader.history(A, START, CUTOFF)
        assert [t.source_row for t in history] == [1, 2, 3, 4]
        result = reader.network(A, START, CUTOFF, 2, 5)
        assert result.focal.source_row == 5
        assert set(result.graph) == {A, B}
        assert statistics(result.graph, A)["account_transactions"] == 4
        assert reader.history(("1", "unknown"), START, CUTOFF) == []
        for row in (1, 7, 999):
            with pytest.raises(ValueError, match="cutoff"):
                reader.focal(row, CUTOFF)
        with pytest.raises(ValueError, match="touch"):
            reader.network(B, START, CUTOFF, focal_source_row=5)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            reader.connection.execute(
                statement("DELETE FROM {core}.transactions", schema)
            )


def test_sql_resource_limits_dataset_scope_and_reproducibility(graph_db):
    dsn, schema = graph_db
    with graph_session(dsn, 1, schema=schema, limits=Limits(max_edges=3)) as reader:
        with pytest.raises(GraphLimitExceeded):
            reader.history(A, START, CUTOFF)
    with graph_session(dsn, 1, schema=schema, limits=Limits(max_edges=4)) as reader:
        a = reader.network(A, START, CUTOFF, 2)
        b = reader.network(A, START, CUTOFF, 2)
        assert list(a.graph.edges(keys=True, data=True)) == list(
            b.graph.edges(keys=True, data=True)
        )
    with graph_session(dsn, 2, schema=schema) as reader:
        assert len(reader.history(A, START, CUTOFF)) == 1
    for dataset in (3, 999):
        with pytest.raises(ValueError, match="complete"):
            with graph_session(dsn, dataset, schema=schema):
                pass


def test_future_insert_and_snapshot_isolation(graph_db):
    dsn, schema = graph_db
    with graph_session(dsn, 1, schema=schema) as reader:
        before = reader.history(A, START, CUTOFF)
        with psycopg.connect(dsn) as writer:
            writer.execute(
                statement(
                    """INSERT INTO {core}.transactions
                SELECT dataset_id,source_row+100,occurred_at,from_bank_id,
                from_account,to_bank_id,to_account,amount_paid,payment_currency,
                amount_received,receiving_currency,payment_format
                FROM {core}.transactions WHERE dataset_id=1 AND source_row IN (5,7)
            """,
                    schema,
                )
            )
        assert reader.history(A, START, CUTOFF) == before
    with graph_session(dsn, 1, schema=schema) as reader:
        assert reader.history(A, START, CUTOFF) == before


def test_statement_timeout_is_enforced(graph_db):
    dsn, schema = graph_db
    with graph_session(
        dsn, 1, schema=schema, limits=Limits(statement_timeout_ms=20)
    ) as reader:
        with pytest.raises(psycopg.errors.QueryCanceled):
            reader.connection.execute("SELECT pg_sleep(0.1)")
