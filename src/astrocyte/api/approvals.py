"""``/v1/approvals`` — the human side of guarded actuation (ADR-014).

Agents receive ``pending_approval`` from a gated write tool; a human resolves
it here (or via ``aios approve``) and the agent re-invokes the tool with the
approval id as its confirmation token.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from astrocyte.core.config import get_settings
from astrocyte.core.policy import (
    ApprovalStatus,
    ApprovalStore,
    InMemoryApprovalStore,
    PendingApproval,
    SqliteApprovalStore,
)


@lru_cache
def get_approval_store() -> ApprovalStore:
    """Process-wide approval store (SQLite when configured, ADR-014)."""
    settings = get_settings()
    if settings.approvals_db is not None:
        return SqliteApprovalStore(settings.approvals_db)
    return InMemoryApprovalStore()


def verify_api_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Interim bearer-token auth (ADR-014); disabled when no token is set."""
    token = get_settings().api_token
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
        )


router = APIRouter(
    prefix="/approvals",
    tags=["approvals"],
    dependencies=[Depends(verify_api_token)],
)


class ApprovalView(BaseModel):
    approval_id: str
    domain: str
    service: str
    targets: list[str]
    status: str
    expires_at: float

    @classmethod
    def from_approval(cls, approval: PendingApproval) -> ApprovalView:
        return cls(
            approval_id=approval.approval_id,
            domain=approval.action.domain,
            service=approval.action.service,
            targets=list(approval.action.targets),
            status=approval.status.value,
            expires_at=approval.expires_at,
        )


class ApprovalDecision(BaseModel):
    approve: bool = True


@router.get("")
def list_approvals(
    store: Annotated[ApprovalStore, Depends(get_approval_store)],
) -> list[ApprovalView]:
    """Pending (non-expired) approvals awaiting a human."""
    return [ApprovalView.from_approval(a) for a in store.list_pending()]


@router.post("/{approval_id}")
def decide_approval(
    approval_id: str,
    decision: ApprovalDecision,
    store: Annotated[ApprovalStore, Depends(get_approval_store)],
) -> ApprovalView:
    """Approve or deny one pending approval."""
    current = store.get(approval_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown approval"
        )
    if current.status is not ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"approval already {current.status.value}",
        )
    new_status = ApprovalStatus.APPROVED if decision.approve else ApprovalStatus.DENIED
    updated = store.set_status(approval_id, new_status)
    assert updated is not None  # existence checked above
    return ApprovalView.from_approval(updated)
