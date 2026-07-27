"""The Home Assistant MCP server (ADR-011) — astrocyte's first shipped one.

Read tools expose entity state, raw history, and long-term statistics; the
single write tool (``call_service``) passes every invocation through the
actuation policy engine (ADR-014). Guarded calls come back as
``pending_approval`` and are also mirrored into HA as a persistent
notification so they reach the companion app.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

from astrocyte.core.policy import Action, DecisionStatus, PolicyEngine
from astrocyte.ha.client import HAClient
from astrocyte.ha.status import collect_rv_status
from astrocyte.mcp.server import AstrocyteMCP

logger = logging.getLogger(__name__)

_INSTRUCTIONS = """Tools for the coach's Home Assistant instance.
Reads are unrestricted. call_service is policy-gated: a `pending_approval`
result means a human must run `aios approve <approval_id>` before you retry
the same call with that id as approval_token. A `denied` result is final —
do not retry it.
"""


def _trim(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    trimmed: dict[str, Any] = {
        "entity_id": state.get("entity_id"),
        "state": state.get("state"),
    }
    if attributes.get("friendly_name"):
        trimmed["name"] = attributes["friendly_name"]
    if attributes.get("unit_of_measurement"):
        trimmed["unit"] = attributes["unit_of_measurement"]
    if attributes.get("device_class"):
        trimmed["device_class"] = attributes["device_class"]
    return trimmed


def build_ha_mcp(
    client: HAClient,
    policy: PolicyEngine,
    *,
    name: str = "astrocyte-ha",
) -> AstrocyteMCP:
    """Build the HA MCP server bound to a client and policy engine."""
    server = AstrocyteMCP(name, policy, instructions=_INSTRUCTIONS)

    @server.tool
    async def list_entities(
        domain: str | None = None, pattern: str | None = None
    ) -> list[dict[str, Any]]:
        """List entities, optionally filtered by domain and/or id glob."""
        states = await client.get_states()
        out: list[dict[str, Any]] = []
        for state in states:
            entity_id = str(state.get("entity_id", ""))
            if domain and not entity_id.startswith(f"{domain}."):
                continue
            if pattern and not fnmatch.fnmatchcase(entity_id, pattern):
                continue
            out.append(_trim(state))
        return out

    @server.tool
    async def get_state(entity_id: str) -> dict[str, Any] | None:
        """Full state (with attributes) of one entity; None if unknown."""
        return await client.get_state(entity_id)

    @server.tool
    async def get_history(
        entity_id: str, start: str, end: str | None = None
    ) -> list[dict[str, Any]]:
        """Raw recorder history for one entity (ISO-8601 timestamps)."""
        return await client.get_history(entity_id, start, end)

    @server.tool
    async def get_statistics(
        statistic_ids: list[str],
        start: str,
        end: str | None = None,
        period: str = "hour",
    ) -> dict[str, list[dict[str, Any]]]:
        """Long-term statistics (mean/min/max aggregates, kept indefinitely).

        The right tool for trend questions ("is the battery draining faster
        than last week?").
        """
        return await client.get_statistics(
            statistic_ids, start=start, end=end, period=period
        )

    @server.tool
    async def call_service(
        domain: str,
        service: str,
        entity_ids: list[str] | None = None,
        data: dict[str, Any] | None = None,
        approval_token: str | None = None,
    ) -> dict[str, Any]:
        """Actuate: call one HA service. Policy-gated (ADR-014)."""
        action = Action(domain=domain, service=service, targets=tuple(entity_ids or ()))
        decision = server.enforce(action, approval_token)
        if decision.status is not DecisionStatus.ALLOWED:
            payload = AstrocyteMCP.decision_payload(decision)
            if (
                decision.status is DecisionStatus.PENDING_APPROVAL
                and decision.approval is not None
            ):
                await _notify_pending(client, action, decision.approval.approval_id)
            return payload
        changed = await client.call_service(
            domain, service, entity_ids=tuple(entity_ids or ()), data=data
        )
        return {
            "status": "executed",
            "tier": decision.tier.value,
            "changed_entities": len(changed),
        }

    @server.tool
    async def rv_status() -> dict[str, Any]:
        """One-call coach snapshot: battery, fuel, tanks, climate, power."""
        return collect_rv_status(await client.get_states())

    @server.tool
    async def list_pending_approvals() -> list[dict[str, Any]]:
        """Guarded actions currently awaiting a human decision."""
        return [
            {
                "approval_id": approval.approval_id,
                "action": approval.action.to_dict(),
                "expires_at": approval.expires_at,
            }
            for approval in policy.store.list_pending()
        ]

    return server


async def _notify_pending(client: HAClient, action: Action, approval_id: str) -> None:
    """Mirror a pending approval into HA (companion-app visibility)."""
    try:
        await client.call_service(
            "persistent_notification",
            "create",
            data={
                "notification_id": f"astrocyte_approval_{approval_id}",
                "title": "Astrocyte approval needed",
                "message": (
                    f"Agent wants `{action.key}` on "
                    f"{', '.join(action.targets) or 'all targets'}.\n"
                    f"Approve with: `aios approve {approval_id}`"
                ),
            },
        )
    except Exception:  # noqa: BLE001 - notification is best-effort
        logger.warning("could not mirror approval %s into HA", approval_id)
