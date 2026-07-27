"""App-factory tests for the /mcp/ha mount and its interim auth (ADR-014)."""

import pytest
from fastapi.testclient import TestClient

from astrocyte.api import create_app
from astrocyte.core.config import get_settings


@pytest.fixture
def ha_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTROCYTE_HA_TOKEN", "hatoken")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_no_mount_without_ha_token() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        assert client.get("/mcp/ha/").status_code == 404


@pytest.mark.usefixtures("ha_env")
def test_mcp_mounted_when_configured() -> None:
    with TestClient(create_app()) as client:
        # Streamable HTTP rejects a bare GET, but the route must exist.
        response = client.get("/mcp/ha/")
        assert response.status_code != 404


@pytest.mark.usefixtures("ha_env")
def test_mcp_mount_requires_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTROCYTE_API_TOKEN", "sekrit")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        assert client.get("/mcp/ha/").status_code == 401
        ok = client.get("/mcp/ha/", headers={"Authorization": "Bearer sekrit"})
        assert ok.status_code != 401
        # health stays public
        assert client.get("/health").status_code == 200
