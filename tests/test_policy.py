"""Policy engine tests (ADR-014): tiers, approvals, rate limits, audit."""

import json
from pathlib import Path
from typing import Any

import pytest

from astrocyte.core.policy import (
    Action,
    ActionTier,
    ApprovalStatus,
    AuditLog,
    DecisionStatus,
    InMemoryApprovalStore,
    PolicyEngine,
    PolicyRule,
    RateLimiter,
    SqliteApprovalStore,
)

LIGHTS = Action(domain="light", service="turn_on", targets=("light.galley",))
GENERATOR = Action(domain="switch", service="turn_on", targets=("switch.generator",))
WATER_HEATER = Action(domain="water_heater", service="turn_on")


def make_engine(**kwargs: Any) -> PolicyEngine:
    rules = (
        PolicyRule(tier=ActionTier.DENY, targets=("switch.generator",)),
        PolicyRule(tier=ActionTier.CONTROL, domain="light", rate_limit_per_minute=2),
        PolicyRule(tier=ActionTier.GUARDED, domain="water_heater"),
    )
    return PolicyEngine(rules=rules, **kwargs)


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


# --- tier resolution ---------------------------------------------------------


def test_first_match_wins_and_default_deny() -> None:
    engine = make_engine()
    assert engine.resolve(GENERATOR) is ActionTier.DENY
    assert engine.resolve(LIGHTS) is ActionTier.CONTROL
    assert engine.resolve(WATER_HEATER) is ActionTier.GUARDED
    unknown = Action(domain="cover", service="open_cover")
    assert engine.resolve(unknown) is ActionTier.DENY


def test_rule_requires_every_target_covered() -> None:
    rule = PolicyRule(tier=ActionTier.CONTROL, domain="light", targets=("light.*",))
    mixed = Action(
        domain="light", service="turn_on", targets=("light.galley", "switch.pump")
    )
    assert not rule.matches(mixed)


def test_target_restricted_rule_never_claims_targetless_actions() -> None:
    # A targetless call is unscoped (may fan out to a whole domain); only
    # rules without target restrictions may claim it.
    restricted = PolicyRule(tier=ActionTier.CONTROL, targets=("light.galley",))
    unrestricted = PolicyRule(tier=ActionTier.CONTROL)
    targetless = Action(domain="light", service="turn_on")
    assert not restricted.matches(targetless)
    assert unrestricted.matches(targetless)


def test_denied_action() -> None:
    decision = make_engine().authorize(GENERATOR)
    assert decision.status is DecisionStatus.DENIED
    assert decision.tier is ActionTier.DENY


def test_control_allowed() -> None:
    decision = make_engine().authorize(LIGHTS)
    assert decision.status is DecisionStatus.ALLOWED
    assert decision.tier is ActionTier.CONTROL


# --- rate limiting -----------------------------------------------------------


def test_control_rate_limited() -> None:
    engine = make_engine()
    assert engine.authorize(LIGHTS).status is DecisionStatus.ALLOWED
    assert engine.authorize(LIGHTS).status is DecisionStatus.ALLOWED
    limited = engine.authorize(LIGHTS)
    assert limited.status is DecisionStatus.RATE_LIMITED
    assert "rate limit" in limited.reason


def test_rate_limiter_window_slides() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    assert limiter.allow("k", 1)
    assert not limiter.allow("k", 1)
    clock.now += 61.0
    assert limiter.allow("k", 1)


# --- guarded approval flow ---------------------------------------------------


def test_guarded_flow_pending_then_approved() -> None:
    engine = make_engine()
    pending = engine.authorize(WATER_HEATER)
    assert pending.status is DecisionStatus.PENDING_APPROVAL
    assert pending.approval is not None
    approval_id = pending.approval.approval_id

    # Re-invoking before the human decides stays pending (no new approval).
    still_pending = engine.authorize(WATER_HEATER, approval_token=approval_id)
    assert still_pending.status is DecisionStatus.PENDING_APPROVAL

    engine.store.set_status(approval_id, ApprovalStatus.APPROVED)
    allowed = engine.authorize(WATER_HEATER, approval_token=approval_id)
    assert allowed.status is DecisionStatus.ALLOWED


def test_approval_token_is_single_use() -> None:
    engine = make_engine()
    pending = engine.authorize(WATER_HEATER)
    assert pending.approval is not None
    token = pending.approval.approval_id
    engine.store.set_status(token, ApprovalStatus.APPROVED)
    assert engine.authorize(WATER_HEATER, approval_token=token).status is (
        DecisionStatus.ALLOWED
    )
    replay = engine.authorize(WATER_HEATER, approval_token=token)
    assert replay.status is DecisionStatus.DENIED
    assert "consumed" in replay.reason


def test_approval_denied_by_human() -> None:
    engine = make_engine()
    pending = engine.authorize(WATER_HEATER)
    assert pending.approval is not None
    token = pending.approval.approval_id
    engine.store.set_status(token, ApprovalStatus.DENIED)
    decision = engine.authorize(WATER_HEATER, approval_token=token)
    assert decision.status is DecisionStatus.DENIED


def test_approval_expires() -> None:
    clock = FakeClock()
    engine = make_engine(clock=clock, store=InMemoryApprovalStore(clock=clock))
    pending = engine.authorize(WATER_HEATER)
    assert pending.approval is not None
    token = pending.approval.approval_id
    engine.store.set_status(token, ApprovalStatus.APPROVED)
    clock.now += 601.0
    decision = engine.authorize(WATER_HEATER, approval_token=token)
    assert decision.status is DecisionStatus.DENIED
    assert "expired" in decision.reason


def test_approval_bound_to_action() -> None:
    engine = make_engine()
    pending = engine.authorize(WATER_HEATER)
    assert pending.approval is not None
    token = pending.approval.approval_id
    engine.store.set_status(token, ApprovalStatus.APPROVED)
    other = Action(domain="water_heater", service="set_temperature")
    decision = engine.authorize(other, approval_token=token)
    assert decision.status is DecisionStatus.DENIED
    assert "another action" in decision.reason


def test_unknown_token_denied() -> None:
    decision = make_engine().authorize(WATER_HEATER, approval_token="nope")
    assert decision.status is DecisionStatus.DENIED
    assert "unknown" in decision.reason


# --- stores ------------------------------------------------------------------


def test_sqlite_store_round_trip(tmp_path: Path) -> None:
    store = SqliteApprovalStore(tmp_path / "approvals.db")
    approval = store.create(WATER_HEATER, ttl_seconds=600)
    assert store.get(approval.approval_id) == approval
    assert [a.approval_id for a in store.list_pending()] == [approval.approval_id]

    updated = store.set_status(approval.approval_id, ApprovalStatus.APPROVED)
    assert updated is not None and updated.status is ApprovalStatus.APPROVED
    assert store.list_pending() == []
    assert store.set_status("missing", ApprovalStatus.APPROVED) is None

    # Persistence survives a new connection to the same file.
    reopened = SqliteApprovalStore(tmp_path / "approvals.db")
    fetched = reopened.get(approval.approval_id)
    assert fetched is not None and fetched.status is ApprovalStatus.APPROVED


# --- audit -------------------------------------------------------------------


def test_audit_log_records_every_path(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    engine = make_engine(audit=AuditLog(audit_path))
    engine.authorize(LIGHTS)
    engine.authorize(GENERATOR)
    pending = engine.authorize(WATER_HEATER)
    assert pending.approval is not None

    lines = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert [entry["status"] for entry in lines] == [
        "allowed",
        "denied",
        "pending_approval",
    ]
    assert lines[1]["targets"] == ["switch.generator"]
    assert lines[2]["approval_id"] == pending.approval.approval_id


# --- config loading ----------------------------------------------------------


def test_from_file(tmp_path: Path) -> None:
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text(
        """
default_tier: deny
approval_ttl_seconds: 300
rules:
  - tier: control
    domain: light
    rate_limit_per_minute: 12
  - tier: guarded
    domain: climate
    service: set_temperature
"""
    )
    engine = PolicyEngine.from_file(policy_file)
    assert engine.approval_ttl_seconds == 300
    assert engine.resolve(LIGHTS) is ActionTier.CONTROL
    climate = Action(domain="climate", service="set_temperature")
    assert engine.resolve(climate) is ActionTier.GUARDED
    assert engine.resolve(GENERATOR) is ActionTier.DENY


def test_from_file_rejects_non_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "policy.yml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="mapping"):
        PolicyEngine.from_file(bad)
