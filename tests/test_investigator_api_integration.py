"""Core-only PostgreSQL service through the real HTTP route."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_graph_integration import CUTOFF, A, graph_db  # noqa: F401

from mulegraph import investigator_api as api
from mulegraph.dashboard_data import DashboardData

pytestmark = pytest.mark.integration


def test_http_temporal_investigation(graph_db, monkeypatch):  # noqa: F811
    dsn, schema = graph_db
    data = DashboardData.__new__(DashboardData)
    data.scores = SimpleNamespace(
        dataset_id=1, model="synthetic", lookup=lambda rows, fingerprint: {}
    )
    original = data.investigate
    data.investigate = lambda *args, **kwargs: original(*args, **kwargs, schema=schema)
    detail = {
        "source_row": 5,
        "status": "UNSCORED_TRAINING_PERIOD",
        "transaction": {
            "source_row": 5,
            "occurred_at": CUTOFF.isoformat(),
            "from_bank_id": A[0],
            "from_account": A[1],
        },
    }
    api.app.dependency_overrides[api.data_service] = lambda: data
    api.app.dependency_overrides[api.explanation_service] = lambda: SimpleNamespace(
        explain=lambda ids: [detail]
    )
    monkeypatch.setenv("DATABASE_URL", dsn)
    try:
        with TestClient(api.app) as client:
            a = client.get("/api/transactions/5/investigation")
            assert a.status_code == 200
            r = a.json()["report"]
            quality = a.json()["evidence_quality"]
            assert quality["version"] == "evidence-quality-v1"
            assert set(quality["findings"]) == {f["id"] for f in r["findings"]}
            assert {t["source_row"] for t in r["transactions"]} == {1, 2, 3, 4}
            assert r["focal"]["source_row"] == 5
            assert all(
                t["score_status"] == "UNSCORED_TRAINING_PERIOD"
                for t in r["transactions"]
            )
            assert a.json() == client.get("/api/transactions/5/investigation").json()
            assert (
                client.get(
                    "/api/transactions/5/investigation?start=2022-09-02T00:00:00"
                ).status_code
                == 422
            )
    finally:
        api.app.dependency_overrides.clear()
