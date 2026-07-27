"""Runtime configuration shared by every subsystem.

Environment-driven (ADR-013/ADR-014). All variables carry the ``ASTROCYTE_``
prefix (e.g. ``ASTROCYTE_HA_URL``); deployment env files live under
``deploy/``.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AstrocyteSettings(BaseSettings):
    """Process-wide settings, loaded from the environment."""

    model_config = SettingsConfigDict(env_prefix="ASTROCYTE_")

    # --- Own API (CLI + interim auth, ADR-014) ------------------------------
    api_url: str = "http://localhost:8000"
    api_token: str = ""  # interim bearer token; empty disables auth (dev only)

    # --- Integrations (ADR-011, ADR-012) ------------------------------------
    mqtt_url: str = "mqtt://localhost:1883"
    ha_url: str = "http://localhost:8123"
    ha_token: str = ""

    # --- Policy & audit (ADR-014) --------------------------------------------
    policy_file: Path | None = None
    audit_log: Path | None = None
    # SQLite path for persisted pending approvals; None = in-memory (dev/tests).
    approvals_db: Path | None = None

    # --- Model routing (ADR-013) ---------------------------------------------
    models_file: Path | None = None


@lru_cache
def get_settings() -> AstrocyteSettings:
    """Return the memoized process settings."""
    return AstrocyteSettings()
