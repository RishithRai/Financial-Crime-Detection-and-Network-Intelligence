"""Read-only account/focal case service on disposable PostgreSQL transactions."""

import pytest
from test_graph_integration import CUTOFF, START, A
from test_graph_integration import graph_db as graph_db

from mulegraph.cases import investigate_cases
from mulegraph.graph import graph_session

pytestmark = pytest.mark.integration


def test_case_history_focal_exclusion_training_and_reproducibility(graph_db):
    dsn, schema = graph_db
    with graph_session(dsn, 1, schema=schema) as reader:
        a = investigate_cases(reader, START, CUTOFF, account=A)
        b = investigate_cases(reader, START, CUTOFF, focal_source_row=5)
        assert a["cases"] == b["cases"] and a["accounts"] == b["accounts"]
        assert b["focal"]["source_row"] == 5 and not b["focal_included_in_aggregation"]
        assert [t["source_row"] for t in b["transactions"]] == [1, 2, 3, 4]
        root = next(x for x in b["accounts"] if x["account"] == A)
        assert root["history"]["complete_for_account"]
        assert root["ml_summary"]["distinct_transactions"] == 4
        assert root["ml_summary"]["unscored_reasons"] == {"UNSCORED_TRAINING_PERIOD": 4}
        assert root["history"]["self_transfers"] == 1
        assert b["completeness"]["search_completed_within_limits"]
        assert b == investigate_cases(reader, START, CUTOFF, focal_source_row=5)
