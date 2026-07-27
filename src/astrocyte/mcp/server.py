"""Shared FastMCP wiring for Astrocyte MCP servers (ADR-007, ADR-014).

``AstrocyteMCP`` composes a FastMCP server with the actuation policy engine
and audit log so no server can expose a write tool that bypasses policy: write
tools call :meth:`enforce` with the action they are about to perform and only
proceed on an ``allowed`` decision. This class is the seed of the plugin SDK's
MCP base (#34).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from astrocyte.core.policy import Action, Decision, DecisionStatus, PolicyEngine


class AstrocyteMCP:
    """A FastMCP server bound to Astrocyte's policy engine."""

    def __init__(
        self,
        name: str,
        policy: PolicyEngine,
        *,
        instructions: str | None = None,
    ) -> None:
        self.server = FastMCP(name=name, instructions=instructions)
        self.policy = policy
        # Re-exported decorator so subsystems register tools the FastMCP way.
        self.tool = self.server.tool

    def enforce(self, action: Action, approval_token: str | None = None) -> Decision:
        """Authorize (and audit) one write action."""
        return self.policy.authorize(action, approval_token)

    @staticmethod
    def decision_payload(decision: Decision) -> dict[str, Any]:
        """The wire shape write tools return when a call is not executed."""
        payload: dict[str, Any] = {
            "status": decision.status.value,
            "tier": decision.tier.value,
            "reason": decision.reason,
        }
        if (
            decision.status is DecisionStatus.PENDING_APPROVAL
            and decision.approval is not None
        ):
            payload["approval_id"] = decision.approval.approval_id
            payload["expires_at"] = decision.approval.expires_at
        return payload

    def http_app(self, path: str = "/") -> Any:
        """ASGI app for mounting into FastAPI (ADR-011 mounts at ``/mcp/ha``)."""
        return self.server.http_app(path=path)
