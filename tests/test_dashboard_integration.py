"""Dashboard delegates core-only, strictly historical PostgreSQL investigations."""

from types import SimpleNamespace

import pytest
from test_graph_integration import CUTOFF, START, A, graph_db  # noqa: F401

from mulegraph.dashboard_data import DashboardData

pytestmark = pytest.mark.integration


def test_dashboard_readonly_case_adapter(graph_db):  # noqa: F811
    dsn, schema = graph_db
    data = DashboardData.__new__(DashboardData)
    data.scores = SimpleNamespace(
        dataset_id=1, model="synthetic", lookup=lambda rows, fingerprint: {}
    )
    report = data.investigate(dsn, START, CUTOFF, account=A, hops=1, schema=schema)
    assert {t["source_row"] for t in report["transactions"]} == {1, 2, 3, 4}
    assert all(
        t["score_status"] == "UNSCORED_TRAINING_PERIOD" for t in report["transactions"]
    )
    assert report == data.investigate(
        dsn, START, CUTOFF, account=A, hops=1, schema=schema
    )
    with pytest.raises(ValueError):
        data.investigate(dsn, START, CUTOFF, account=A, nodes=501, schema=schema)


def test_one_click_workflow_and_navigation(graph_db, monkeypatch):  # noqa: F811
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    dsn, schema = graph_db
    data = DashboardData.__new__(DashboardData)
    data.scores = SimpleNamespace(
        dataset_id=1, model="synthetic", lookup=lambda rows, fingerprint: {}
    )
    row = dict(
        source_row=5,
        occurred_at=CUTOFF,
        from_bank_id=A[0],
        from_account=A[1],
        to_bank_id="1",
        to_account="C",
        amount_paid="1.10",
        payment_currency="USD",
        amount_received="0.000001",
        receiving_currency="Bitcoin",
        payment_format="ACH",
        score=0.9,
    )
    monkeypatch.setattr(data, "queue", lambda *args, **kwargs: ([row], False))
    original = data.investigate
    calls = []

    def query(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs, schema=schema)

    monkeypatch.setattr(data, "investigate", query)
    monkeypatch.setattr("mulegraph.dashboard.DashboardData", lambda: data)
    monkeypatch.setenv("DATABASE_URL", dsn)
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    next(b for b in app.button if b.label == "Investigate").click().run()
    assert not app.exception and not app.error
    assert len(calls) == 1 and calls[0]["focal"] == 5 and calls[0]["account"] == A
    report = app.session_state["report"]
    assert {t["source_row"] for t in report["transactions"]} == {1, 2, 3, 4}
    for section in [
        "Investigation Cases",
        "Transaction Queue",
        "Network Explorer",
        "Home",
    ]:
        app.radio[0].set_value(section).run()
        assert not app.exception and not app.error
        assert app.session_state["report"] == report
        assert app.session_state["focal_context"]["source_row"] == 5
    assert len(calls) == 1
