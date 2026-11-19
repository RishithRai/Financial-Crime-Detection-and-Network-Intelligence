"""Independent PostgreSQL counts against the graph SQL using core-only fixtures."""

import duckdb
import pyarrow as pa
import pytest
from test_graph_integration import graph_db  # noqa: F401

from mulegraph.graph import graph_session
from mulegraph.graph_features import COLUMNS, SQL
from mulegraph.schema import statement

pytestmark = pytest.mark.integration


def test_pair_history_against_postgresql(graph_db):  # noqa: F811
    dsn, schema = graph_db
    with graph_session(dsn, 1, schema=schema) as reader:
        rows = reader.connection.execute(
            statement(
                """
          SELECT source_row,occurred_at,from_bank_id,from_account,to_bank_id,to_account,
                 'train' AS split FROM {core}.transactions WHERE dataset_id=1
                 ORDER BY source_row
        """,
                schema,
            )
        ).fetchall()
        with duckdb.connect() as db:
            db.register("features", pa.Table.from_pylist(rows))
            actual = db.execute(SQL).to_arrow_table().to_pylist()
        for t, a in zip(rows, actual, strict=True):
            result = []
            for reverse in (False, True):
                sender = (
                    (t["to_bank_id"], t["to_account"])
                    if reverse
                    else (t["from_bank_id"], t["from_account"])
                )
                receiver = (
                    (t["from_bank_id"], t["from_account"])
                    if reverse
                    else (t["to_bank_id"], t["to_account"])
                )
                n, last = (
                    reader.connection.execute(
                        statement(
                            """
                    SELECT count(*) AS n,max(occurred_at) AS last
                    FROM {core}.transactions
                    WHERE dataset_id=1 AND from_bank_id=%s AND from_account=%s
                    AND to_bank_id=%s AND to_account=%s AND occurred_at<%s
                """,
                            schema,
                        ),
                        (*sender, *receiver, t["occurred_at"]),
                    )
                    .fetchone()
                    .values()
                )
                if reverse and sender == receiver:
                    n, last = 0, None
                result.append(
                    (n, (t["occurred_at"] - last).total_seconds() if last else None)
                )
            assert [a[n] for n in COLUMNS] == [
                result[0][0],
                result[1][0],
                result[0][1],
                result[1][1],
            ]
