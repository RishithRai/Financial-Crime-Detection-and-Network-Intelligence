"""HTTP contracts, resource guards and safe error responses."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mulegraph import investigator_api as api
from mulegraph.graph import GraphLimitExceeded


@pytest.fixture
def client():
    api.app.dependency_overrides[api.data_service] = lambda: SimpleNamespace(
        queue=lambda *args, **kwargs: (
            [{"source_row": 3, "amount_paid": "1.2300"}],
            False,
        )
    )
    api.app.dependency_overrides[api.explanation_service] = lambda: SimpleNamespace(
        explain=lambda ids: [{"source_row": ids[0], "status": "SOURCE_NOT_FOUND"}]
    )
    with TestClient(api.app) as result:
        yield result
    api.app.dependency_overrides.clear()


def test_queue_and_read_only(client):
    response = client.get("/api/queue")
    assert response.status_code == 200
    assert response.json()["transactions"][0]["amount_paid"] == "1.2300"
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/queue").status_code == 405
    assert client.get("/api/queue?page=1001").status_code == 422
    assert client.get("/api/queue?split=train").status_code == 422
    assert client.get("/api/queue?source=0").status_code == 422
    assert client.get("/api/transactions/4/explanation").status_code == 404


@pytest.mark.parametrize(
    "exception,code",
    [
        (GraphLimitExceeded("private detail"), 422),
        (ValueError("secret"), 409),
        (FileNotFoundError("/private/path"), 503),
    ],
)
def test_sanitized_failures(client, exception, code):
    def fail():
        raise exception

    api.app.dependency_overrides[api.data_service] = fail
    response = client.get("/api/queue")
    assert response.status_code == code
    assert str(exception) not in response.text
    assert "transactions" not in response.json()


def test_concurrency_rejected_without_waiting(client):
    api.slots.acquire()
    api.slots.acquire()
    try:
        assert client.get("/api/queue").status_code == 429
    finally:
        api.slots.release()
        api.slots.release()
    assert client.get("/api/queue").status_code == 200
