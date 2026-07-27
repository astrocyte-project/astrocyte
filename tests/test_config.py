"""Settings tests (astrocyte.core.config)."""

from pathlib import Path

import pytest

from astrocyte.core.config import AstrocyteSettings, get_settings


def test_defaults() -> None:
    settings = AstrocyteSettings()
    assert settings.api_url == "http://localhost:8000"
    assert settings.api_token == ""
    assert settings.ha_url == "http://localhost:8123"
    assert settings.policy_file is None
    assert settings.approvals_db is None


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTROCYTE_HA_URL", "http://coach:8123")
    monkeypatch.setenv("ASTROCYTE_HA_TOKEN", "secret")
    monkeypatch.setenv("ASTROCYTE_POLICY_FILE", "/etc/astrocyte/policy.yml")
    settings = AstrocyteSettings()
    assert settings.ha_url == "http://coach:8123"
    assert settings.ha_token == "secret"
    assert settings.policy_file == Path("/etc/astrocyte/policy.yml")


def test_get_settings_is_memoized() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
