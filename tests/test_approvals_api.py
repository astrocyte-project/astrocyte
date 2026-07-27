"""/v1/approvals endpoint tests (ADR-014)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from astrocyte.api import create_app
from astrocyte.api.approvals import get_approval_store
from astrocyte.core.config import get_settings
from astrocyte.core.policy import Action, ApprovalStatus, InMemoryApprovalStore

ACTION = Action(domain="water_heater", service="turn_on", targets=("wh.main",))


@pytest.fixture
def store() -> InMemoryApprovalStore:
    return InMemoryApprovalStore()


@pytest.fixture
def client(store: InMemoryApprovalStore) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_approval_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client


def test_list_empty(client: TestClient) -> None:
    response = client.get("/v1/approvals")
    assert response.status_code == 200
    assert response.json() == []


def test_list_and_approve(client: TestClient, store: InMemoryApprovalStore) -> None:
    approval = store.create(ACTION, ttl_seconds=600)

    listed = client.get("/v1/approvals").json()
    assert [item["approval_id"] for item in listed] == [approval.approval_id]
    assert listed[0]["domain"] == "water_heater"
    assert listed[0]["targets"] == ["wh.main"]

    response = client.post(
        f"/v1/approvals/{approval.approval_id}", json={"approve": True}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    stored = store.get(approval.approval_id)
    assert stored is not None and stored.status is ApprovalStatus.APPROVED


def test_deny(client: TestClient, store: InMemoryApprovalStore) -> None:
    approval = store.create(ACTION, ttl_seconds=600)
    response = client.post(
        f"/v1/approvals/{approval.approval_id}", json={"approve": False}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "denied"


def test_unknown_approval_404(client: TestClient) -> None:
    assert client.post("/v1/approvals/missing", json={}).status_code == 404


def test_double_decide_409(client: TestClient, store: InMemoryApprovalStore) -> None:
    approval = store.create(ACTION, ttl_seconds=600)
    first = client.post(f"/v1/approvals/{approval.approval_id}", json={})
    assert first.status_code == 200
    second = client.post(f"/v1/approvals/{approval.approval_id}", json={})
    assert second.status_code == 409


def test_bearer_token_enforced(
    store: InMemoryApprovalStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASTROCYTE_API_TOKEN", "sekrit")
    get_settings.cache_clear()
    try:
        app = create_app()
        app.dependency_overrides[get_approval_store] = lambda: store
        with TestClient(app) as client:
            assert client.get("/v1/approvals").status_code == 401
            bad = {"Authorization": "Bearer wrong"}
            assert client.get("/v1/approvals", headers=bad).status_code == 401
            good = {"Authorization": "Bearer sekrit"}
            assert client.get("/v1/approvals", headers=good).status_code == 200
    finally:
        get_settings.cache_clear()
