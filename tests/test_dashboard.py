"""Bounded presentation adapters and real Streamlit session smoke tests."""

from datetime import datetime
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from streamlit.testing.v1 import AppTest

from mulegraph.dashboard_data import DashboardData
from mulegraph.features import sha256_file
from mulegraph.investigation_scores import ScoreFile


@pytest.fixture
def data(tmp_path):
    rows = []
    for i in range(1, 5):
        rows.append(
            dict(
                dataset_id=1,
                source_row=i,
                occurred_at=datetime(2022, 9, 9),
                from_bank_id="1",
                from_account="A",
                to_bank_id="2",
                to_account="A",
                amount_paid="1.01",
                amount_received="1.01",
                payment_currency="USD",
                receiving_currency="USD",
                payment_format="ACH",
            )
        )
    features = tmp_path / "features.parquet"
    scores = tmp_path / "scores.parquet"
    pq.write_table(pa.Table.from_pylist(rows), features)
    pq.write_table(
        pa.table({"source_row": [1, 2, 3, 4], "score": [0.2, 0.9, 0.9, 0.0]}), scores
    )
    obj = DashboardData.__new__(DashboardData)
    obj.features = features
    obj.freeze = {
        "feature_sha256": sha256_file(features),
        "thresholds": {"lightgbm": 0.5},
    }
    artifact = ScoreFile(
        scores,
        sha256_file(scores),
        "score",
        datetime(2022, 9, 9),
        datetime(2022, 9, 11),
    )
    obj.scores = SimpleNamespace(files=(artifact, artifact, artifact))
    return obj


def test_queue_pagination_filters_and_ties(data):
    rows, more = data.queue(size=2)
    assert [r["source_row"] for r in rows] == [2, 3] and more
    rows, more = data.queue(size=2, page=1)
    assert [r["source_row"] for r in rows] == [1, 4] and not more
    assert data.queue(bank="3", account="A")[0] == []
    assert len(data.queue(bank="2", account="A", alerts_only=True)[0]) == 2
    assert data.queue(source=1)[0][0]["amount_paid"] == "1.01"
    assert data.queue(payment_format="ACH' OR 1=1 --")[0] == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size": 101},
        {"page": 1001},
        {"order": "score; DROP TABLE x"},
        {"split": "train"},
        {"bank": "1"},
        {"source": 0},
    ],
)
def test_queue_rejects_unbounded_or_invalid(data, kwargs):
    with pytest.raises(ValueError):
        data.queue(**kwargs)


def test_queue_integrity(data):
    data.features.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        data.queue()


def test_app_navigation_and_failure(monkeypatch, data):
    monkeypatch.setattr("mulegraph.dashboard.DashboardData", lambda: data)
    app = AppTest.from_file("../streamlit_app.py").run()
    assert not app.exception
    assert not app.error
    app.radio[0].set_value("Transaction Queue").run()
    assert not app.exception
    next(b for b in app.button if b.label == "Search saved transactions").click().run()
    assert not app.error
    assert any(b.label == "Investigate" for b in app.button)
    next(b for b in app.button if b.label == "Investigate").click().run()
    assert app.radio[0].value == "Network Explorer" and not app.exception
    app.radio[0].set_value("Investigation Cases").run()
    assert not app.exception


def test_failed_investigation_clears_stale_evidence(monkeypatch, data):
    from mulegraph.graph import GraphLimitExceeded

    def fail(*args, **kwargs):
        raise GraphLimitExceeded("sensitive internal details")

    monkeypatch.setattr("mulegraph.dashboard.DashboardData", lambda: data)
    monkeypatch.setattr(data, "investigate", fail)
    monkeypatch.setenv("DATABASE_URL", "secret-dsn-never-display")
    app = AppTest.from_file("../streamlit_app.py").run()
    app.radio[0].set_value("Network Explorer").run()
    next(t for t in app.text_input if t.label == "Root bank").set_value("1")
    next(t for t in app.text_input if t.label == "Root account").set_value("A")
    app.session_state["report"] = {"stale": True}
    next(b for b in app.button if b.label == "Run bounded investigation").click().run()
    assert not app.exception
    assert "report" not in app.session_state
    assert "No partial result" in app.warning[0].value
    assert "secret-dsn" not in str(app)


def test_network_figure_is_bounded_and_directed():
    from mulegraph.dashboard import network_figure

    report = {
        "accounts": [{"account": ["1", "A"]}, {"account": ["2", "A"]}],
        "transactions": [
            {
                "from_bank_id": "1",
                "from_account": "A",
                "to_bank_id": "2",
                "to_account": "A",
            }
        ],
    }
    fig = network_figure(report, ("1", "A"))
    assert len(fig.data[0].x) == 2
    assert len(fig.layout.annotations) == 1
    assert fig.layout.annotations[0].arrowhead == 2


@pytest.mark.parametrize("value", ["-1", "1.5", "abc", "0"])
def test_source_input_recovery(value):
    from mulegraph.dashboard import parse_source

    with pytest.raises(ValueError, match="positive digits"):
        parse_source(value)
