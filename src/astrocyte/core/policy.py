"""Actuation policy engine (ADR-014).

Every MCP server that exposes write tools enforces policy here: an action
resolves to a tier (``read``/``control``/``guarded``/``deny``, default deny),
``control`` actions are rate-limited, ``guarded`` actions require a two-phase
human approval, and every attempt is appended to a JSONL audit log.

The action shape is deliberately generic — for the Home Assistant MCP server
an action is a service call, but any server can express its own actions.
"""

from __future__ import annotations

import fnmatch
import json
import sqlite3
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml


class ActionTier(StrEnum):
    """Policy tiers, from harmless to forbidden (ADR-014)."""

    READ = "read"
    CONTROL = "control"
    GUARDED = "guarded"
    DENY = "deny"


class DecisionStatus(StrEnum):
    ALLOWED = "allowed"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"
    RATE_LIMITED = "rate_limited"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CONSUMED = "consumed"


@dataclass(frozen=True)
class Action:
    """A policy-relevant action, e.g. one HA service call."""

    domain: str
    service: str
    targets: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Rate-limit / audit key."""
        return f"{self.domain}.{self.service}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "service": self.service,
            "targets": list(self.targets),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Action:
        return cls(
            domain=str(data["domain"]),
            service=str(data["service"]),
            targets=tuple(str(t) for t in data.get("targets", [])),
        )


@dataclass(frozen=True)
class PolicyRule:
    """One declarative rule; first match wins (see ``PolicyEngine``).

    ``domain``/``service``/``targets`` are ``fnmatch`` glob patterns. An
    action with targets matches only if *every* target is covered by at least
    one pattern — a call touching an uncovered entity never slips through.
    A *targetless* action is unscoped (it may fan out to every entity in the
    domain), so only rules that don't restrict targets can claim it.
    """

    tier: ActionTier
    domain: str = "*"
    service: str = "*"
    targets: tuple[str, ...] = ("*",)
    rate_limit_per_minute: int | None = None

    def matches(self, action: Action) -> bool:
        if not fnmatch.fnmatchcase(action.domain, self.domain):
            return False
        if not fnmatch.fnmatchcase(action.service, self.service):
            return False
        if not action.targets:
            return self.targets == ("*",)
        return all(
            any(fnmatch.fnmatchcase(target, pattern) for pattern in self.targets)
            for target in action.targets
        )


@dataclass(frozen=True)
class PendingApproval:
    """A guarded action awaiting (or past) its human decision."""

    approval_id: str
    action: Action
    created_at: float
    expires_at: float
    status: ApprovalStatus = ApprovalStatus.PENDING


@dataclass(frozen=True)
class Decision:
    """The outcome of ``PolicyEngine.authorize``."""

    status: DecisionStatus
    tier: ActionTier
    reason: str = ""
    approval: PendingApproval | None = None


class ApprovalStore(Protocol):
    """Persistence contract for pending approvals."""

    def create(self, action: Action, ttl_seconds: float) -> PendingApproval: ...

    def get(self, approval_id: str) -> PendingApproval | None: ...

    def list_pending(self) -> list[PendingApproval]: ...

    def set_status(
        self, approval_id: str, status: ApprovalStatus
    ) -> PendingApproval | None: ...


class InMemoryApprovalStore:
    """Non-persistent store for tests and development."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._items: dict[str, PendingApproval] = {}
        self._lock = threading.Lock()

    def create(self, action: Action, ttl_seconds: float) -> PendingApproval:
        now = self._clock()
        approval = PendingApproval(
            approval_id=uuid.uuid4().hex,
            action=action,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            self._items[approval.approval_id] = approval
        return approval

    def get(self, approval_id: str) -> PendingApproval | None:
        with self._lock:
            return self._items.get(approval_id)

    def list_pending(self) -> list[PendingApproval]:
        now = self._clock()
        with self._lock:
            return [
                a
                for a in self._items.values()
                if a.status is ApprovalStatus.PENDING and a.expires_at > now
            ]

    def set_status(
        self, approval_id: str, status: ApprovalStatus
    ) -> PendingApproval | None:
        with self._lock:
            current = self._items.get(approval_id)
            if current is None:
                return None
            updated = PendingApproval(
                approval_id=current.approval_id,
                action=current.action,
                created_at=current.created_at,
                expires_at=current.expires_at,
                status=status,
            )
            self._items[approval_id] = updated
            return updated


class SqliteApprovalStore:
    """SQLite-backed store so approvals survive API restarts (ADR-014).

    Migrates to the shared PostgreSQL instance when the application DB layer
    lands; the schema is deliberately trivial to port.
    """

    def __init__(
        self, path: Path | str, clock: Callable[[], float] = time.time
    ) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                action_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _row_to_approval(row: tuple[str, str, float, float, str]) -> PendingApproval:
        approval_id, action_json, created_at, expires_at, status = row
        return PendingApproval(
            approval_id=approval_id,
            action=Action.from_dict(json.loads(action_json)),
            created_at=created_at,
            expires_at=expires_at,
            status=ApprovalStatus(status),
        )

    def create(self, action: Action, ttl_seconds: float) -> PendingApproval:
        now = self._clock()
        approval = PendingApproval(
            approval_id=uuid.uuid4().hex,
            action=action,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?)",
                (
                    approval.approval_id,
                    json.dumps(action.to_dict()),
                    approval.created_at,
                    approval.expires_at,
                    approval.status.value,
                ),
            )
            self._conn.commit()
        return approval

    def get(self, approval_id: str) -> PendingApproval | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT approval_id, action_json, created_at, expires_at, status"
                " FROM approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return self._row_to_approval(row) if row else None

    def list_pending(self) -> list[PendingApproval]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT approval_id, action_json, created_at, expires_at, status"
                " FROM approvals WHERE status = ? AND expires_at > ?",
                (ApprovalStatus.PENDING.value, self._clock()),
            ).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def set_status(
        self, approval_id: str, status: ApprovalStatus
    ) -> PendingApproval | None:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE approvals SET status = ? WHERE approval_id = ?",
                (status.value, approval_id),
            )
            self._conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get(approval_id)


class AuditLog:
    """Append-only JSONL record of every actuation attempt.

    A ``None`` path disables writing (unit tests); production always mounts a
    persistent path (backed up in phase 3).
    """

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()

    def record(
        self,
        action: Action,
        tier: ActionTier,
        status: DecisionStatus,
        *,
        approval_id: str | None = None,
        reason: str = "",
    ) -> None:
        if self._path is None:
            return
        entry: dict[str, Any] = {
            "ts": datetime.now(tz=UTC).isoformat(),
            **action.to_dict(),
            "tier": tier.value,
            "status": status.value,
        }
        if approval_id:
            entry["approval_id"] = approval_id
        if reason:
            entry["reason"] = reason
        line = json.dumps(entry, separators=(",", ":"))
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


class RateLimiter:
    """Fixed-window per-key limiter (calls per minute)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, per_minute: int) -> bool:
        now = self._clock()
        with self._lock:
            window = self._events.setdefault(key, deque())
            while window and now - window[0] >= 60.0:
                window.popleft()
            if len(window) >= per_minute:
                return False
            window.append(now)
            return True


@dataclass
class PolicyEngine:
    """Resolves actions to tiers and authorizes them (ADR-014).

    Rules are evaluated in order; the first match wins. Actions matching no
    rule get ``default_tier`` (deny unless configured otherwise — and the
    shipped configs never configure otherwise).
    """

    rules: tuple[PolicyRule, ...] = ()
    default_tier: ActionTier = ActionTier.DENY
    approval_ttl_seconds: float = 600.0
    store: ApprovalStore = field(default_factory=InMemoryApprovalStore)
    audit: AuditLog = field(default_factory=lambda: AuditLog(None))
    clock: Callable[[], float] = time.time
    _limiter: RateLimiter = field(default_factory=RateLimiter)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        store: ApprovalStore | None = None,
        audit: AuditLog | None = None,
    ) -> PolicyEngine:
        rules = tuple(
            PolicyRule(
                tier=ActionTier(str(raw["tier"])),
                domain=str(raw.get("domain", "*")),
                service=str(raw.get("service", "*")),
                targets=tuple(str(t) for t in raw.get("targets", ["*"])),
                rate_limit_per_minute=(
                    int(raw["rate_limit_per_minute"])
                    if raw.get("rate_limit_per_minute") is not None
                    else None
                ),
            )
            for raw in data.get("rules", [])
        )
        kwargs: dict[str, Any] = {
            "rules": rules,
            "default_tier": ActionTier(str(data.get("default_tier", "deny"))),
            "approval_ttl_seconds": float(data.get("approval_ttl_seconds", 600)),
        }
        if store is not None:
            kwargs["store"] = store
        if audit is not None:
            kwargs["audit"] = audit
        return cls(**kwargs)

    @classmethod
    def from_file(
        cls,
        path: Path | str,
        *,
        store: ApprovalStore | None = None,
        audit: AuditLog | None = None,
    ) -> PolicyEngine:
        with Path(path).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            msg = f"policy file must be a mapping: {path}"
            raise ValueError(msg)
        return cls.from_dict(data, store=store, audit=audit)

    def _find_rule(self, action: Action) -> PolicyRule | None:
        for rule in self.rules:
            if rule.matches(action):
                return rule
        return None

    def resolve(self, action: Action) -> ActionTier:
        rule = self._find_rule(action)
        return rule.tier if rule else self.default_tier

    def authorize(self, action: Action, approval_token: str | None = None) -> Decision:
        """Authorize one actuation attempt; every path is audited."""
        rule = self._find_rule(action)
        tier = rule.tier if rule else self.default_tier

        if tier is ActionTier.DENY:
            return self._decide(action, tier, DecisionStatus.DENIED, "policy denies")

        if tier is ActionTier.GUARDED:
            return self._authorize_guarded(action, tier, approval_token)

        # read / control
        limit = rule.rate_limit_per_minute if rule else None
        if limit is not None and not self._limiter.allow(action.key, limit):
            return self._decide(
                action,
                tier,
                DecisionStatus.RATE_LIMITED,
                f"rate limit exceeded ({limit}/min)",
            )
        return self._decide(action, tier, DecisionStatus.ALLOWED, "")

    def _authorize_guarded(
        self, action: Action, tier: ActionTier, approval_token: str | None
    ) -> Decision:
        if approval_token is None:
            created = self.store.create(action, self.approval_ttl_seconds)
            return self._decide(
                action,
                tier,
                DecisionStatus.PENDING_APPROVAL,
                "awaiting human approval",
                approval=created,
            )

        approval = self.store.get(approval_token)
        if approval is None:
            return self._decide(
                action, tier, DecisionStatus.DENIED, "unknown approval token"
            )
        if approval.action != action:
            return self._decide(
                action, tier, DecisionStatus.DENIED, "approval is for another action"
            )
        if approval.expires_at <= self.clock():
            return self._decide(
                action,
                tier,
                DecisionStatus.DENIED,
                "approval expired",
                approval=approval,
            )
        if approval.status is ApprovalStatus.PENDING:
            return self._decide(
                action,
                tier,
                DecisionStatus.PENDING_APPROVAL,
                "still awaiting human approval",
                approval=approval,
            )
        if approval.status is not ApprovalStatus.APPROVED:
            return self._decide(
                action,
                tier,
                DecisionStatus.DENIED,
                f"approval is {approval.status.value}",
                approval=approval,
            )
        consumed = self.store.set_status(approval.approval_id, ApprovalStatus.CONSUMED)
        return self._decide(
            action,
            tier,
            DecisionStatus.ALLOWED,
            "human approved",
            approval=consumed,
        )

    def _decide(
        self,
        action: Action,
        tier: ActionTier,
        status: DecisionStatus,
        reason: str,
        *,
        approval: PendingApproval | None = None,
    ) -> Decision:
        self.audit.record(
            action,
            tier,
            status,
            approval_id=approval.approval_id if approval else None,
            reason=reason,
        )
        return Decision(status=status, tier=tier, reason=reason, approval=approval)
