"""API tests for the FastAPI app factory (ADR-006)."""

from fastapi.testclient import TestClient

from astrocyte.api import create_app


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready() -> None:
    client = TestClient(create_app())
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
