"""Astrocyte HTTP API (FastAPI).

See ADR-006 for the API framework decision. The app is constructed via the
``create_app`` factory so it can be configured per-environment and tested with
``fastapi.testclient.TestClient``.
"""

from astrocyte.api.app import create_app

__all__ = ["create_app"]
