"""FastAPI application factory.

Conventions follow ADR-006:
- ``create_app()`` factory for configurable, testable construction
- liveness (``/health``) and readiness (``/ready``) probes for Docker/compose
  healthchecks (ADR-001)
- a versioned ``/v1`` router as the mount point for subsystem APIs.

When the ``ha``/``mcp`` extras are installed and ``ASTROCYTE_HA_TOKEN`` is
set, the Home Assistant MCP server (ADR-011) is mounted at ``/mcp/ha``; all
``/mcp/*`` paths sit behind the interim bearer token (ADR-014).
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from astrocyte import __version__
from astrocyte.api import approvals
from astrocyte.core.config import get_settings

v1_router = APIRouter(prefix="/v1", tags=["v1"])
v1_router.include_router(approvals.router)


def _build_ha_mcp_app() -> Any | None:
    """The HA MCP ASGI app, when extras and configuration allow."""
    try:
        from astrocyte.core.policy import AuditLog, PolicyEngine
        from astrocyte.ha.client import HAClient
        from astrocyte.ha.mcp import build_ha_mcp
    except ImportError:  # pragma: no cover - extras not installed
        return None
    settings = get_settings()
    if not settings.ha_token:
        return None
    # Share the approvals store with /v1/approvals so `aios approve` resolves
    # the very approvals the MCP server creates.
    store = approvals.get_approval_store()
    audit = AuditLog(settings.audit_log)
    if settings.policy_file is not None:
        policy = PolicyEngine.from_file(settings.policy_file, store=store, audit=audit)
    else:
        # No policy file: the default-deny engine refuses all actuation.
        policy = PolicyEngine(store=store, audit=audit)
    client = HAClient(settings.ha_url, settings.ha_token)
    return build_ha_mcp(client, policy).http_app(path="/")


def create_app() -> FastAPI:
    """Build and return the Astrocyte FastAPI application."""
    mcp_app = _build_ha_mcp_app()
    app = FastAPI(
        title="Astrocyte",
        version=__version__,
        summary="Self-Hosted AI Operating System managed by agents.",
        lifespan=mcp_app.lifespan if mcp_app is not None else None,
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    def ready() -> dict[str, str]:
        """Readiness probe.

        Returns ready unconditionally for now; later phases gate this on
        downstream dependencies (vector store, LLM runtime, etc.).
        """
        return {"status": "ready"}

    # Prometheus metrics for the observability stack (ADR-006). Exposed at
    # /metrics (unauthenticated, but the API binds loopback/tailnet only — the
    # coach-LAN is never a client, ADR-014). The probes are excluded to keep
    # request-metric cardinality focused on real traffic.
    Instrumentator(excluded_handlers=["/metrics", "/health", "/ready"]).instrument(
        app
    ).expose(app, endpoint="/metrics", include_in_schema=False, tags=["system"])

    app.include_router(v1_router)
    if mcp_app is not None:
        app.mount("/mcp/ha", mcp_app)

    @app.middleware("http")
    async def mcp_bearer_auth(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Interim ADR-014 auth for mounted MCP apps (which bypass Depends)."""
        token = get_settings().api_token
        if (
            token
            and request.url.path.startswith("/mcp/")
            and request.headers.get("authorization") != f"Bearer {token}"
        ):
            return JSONResponse(
                {"detail": "missing or invalid bearer token"}, status_code=401
            )
        return await call_next(request)

    return app
