"""End-to-end service on the existing disposable core-only graph fixture."""

from datetime import timedelta

import psycopg
import pytest
from test_graph_integration import CUTOFF, START, A
from test_graph_integration import graph_db as graph_db

from mulegraph.graph import graph_session
from mulegraph.investigation import investigate
from mulegraph.schema import statement

pytestmark = pytest.mark.integration


def test_account_and_focal_service_temporal_isolation(graph_db):
    dsn, schema = graph_db
    with psycopg.connect(dsn) as c:
        c.execute(
            statement(
                """INSERT INTO {core}.transactions VALUES
            (1,20,%s,'2','000A','1','C',1,'USD',1,'USD','ACH'),
            (1,21,%s,'1','C','1','000A',1,'USD',1,'USD','ACH')""",
                schema,
            ),
            (START + timedelta(minutes=1), START + timedelta(minutes=2)),
        )
        # Existing incoming transfer is Bitcoin at receiver: keep mismatch test
        # and add a currency-compatible starting edge independently.
        c.execute(
            statement(
                """INSERT INTO {core}.transactions VALUES
            (1,22,%s,'1','000A','2','000A',1,'USD',1,'USD','ACH')""",
                schema,
            ),
            (START,),
        )
    with graph_session(dsn, 1, schema=schema) as reader:
        report = investigate(reader, START, CUTOFF, account=A)
        assert any(f["pattern_type"] == "circular_flow" for f in report["findings"])
        for finding in report["findings"]:
            ids = [t["source_row"] for t in finding["transactions"]]
            assert not set(ids) & {5, 6, 7, 8}
            assert not (1 in ids and 20 in ids)
        focal = investigate(reader, START, CUTOFF, focal_source_row=5)
        assert focal["account"] == A and focal["focal"]["source_row"] == 5
        assert focal["findings"] == report["findings"]
        with pytest.raises(ValueError):
            investigate(reader, START, CUTOFF)
