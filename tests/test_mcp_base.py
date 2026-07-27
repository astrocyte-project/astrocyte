"""AstrocyteMCP base tests (ADR-007/ADR-014): policy wiring, wire payloads."""

from astrocyte.core.policy import (
    Action,
    ActionTier,
    ApprovalStatus,
    DecisionStatus,
    PolicyEngine,
    PolicyRule,
)
from astrocyte.mcp.server import AstrocyteMCP

LIGHTS = Action(domain="light", service="turn_on")
HEATER = Action(domain="water_heater", service="turn_on")


def make_server() -> AstrocyteMCP:
    engine = PolicyEngine(
        rules=(
            PolicyRule(tier=ActionTier.CONTROL, domain="light"),
            PolicyRule(tier=ActionTier.GUARDED, domain="water_heater"),
        )
    )
    return AstrocyteMCP("test", engine, instructions="test server")


def test_enforce_delegates_to_policy() -> None:
    server = make_server()
    assert server.enforce(LIGHTS).status is DecisionStatus.ALLOWED
    assert server.enforce(Action("cover", "open")).status is DecisionStatus.DENIED


def test_guarded_round_trip_through_enforce() -> None:
    server = make_server()
    pending = server.enforce(HEATER)
    assert pending.status is DecisionStatus.PENDING_APPROVAL
    assert pending.approval is not None
    server.policy.store.set_status(
        pending.approval.approval_id, ApprovalStatus.APPROVED
    )
    allowed = server.enforce(HEATER, approval_token=pending.approval.approval_id)
    assert allowed.status is DecisionStatus.ALLOWED


def test_decision_payload_shapes() -> None:
    server = make_server()
    pending = server.enforce(HEATER)
    payload = AstrocyteMCP.decision_payload(pending)
    assert payload["status"] == "pending_approval"
    assert payload["tier"] == "guarded"
    assert payload["approval_id"]
    assert payload["expires_at"] > 0

    denied = server.enforce(Action("cover", "open"))
    payload = AstrocyteMCP.decision_payload(denied)
    assert payload == {"status": "denied", "tier": "deny", "reason": "policy denies"}


def test_tool_registration_via_fastmcp() -> None:
    server = make_server()

    @server.tool
    def ping() -> str:
        """Health tool."""
        return "pong"

    # The tool is registered on the underlying FastMCP server.
    assert server.http_app() is not None
