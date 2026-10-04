"""Scoped authorization. A boolean is not a license to skip every decision."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.autonomy import AutopilotSettings
from app.models.execution import AuthorizationGrant

SENSITIVE = ("quote.discount", "ads.spend", "ads.launch", "renewal.commercial")


def _active_grant(db: Session, tenant_id: UUID, *, workflow: str, channel: str) -> AuthorizationGrant | None:
    now = datetime.now(UTC)
    rows = db.scalars(
        select(AuthorizationGrant).where(
            AuthorizationGrant.tenant_id == tenant_id,
            AuthorizationGrant.deleted_at.is_(None),
            AuthorizationGrant.status == "active",
            AuthorizationGrant.workflow == workflow,
            AuthorizationGrant.channel == channel,
        )
    ).all()
    for row in rows:
        expires = row.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires is not None and expires < now:
            continue
        return row
    return None


def send_authorization(db: Session, *, tenant_id: UUID, settings: AutopilotSettings, action_type: str) -> str:
    """Return execute, approval, or blocked.

    email_approval_required=false is not a global bypass. Predictable sends run
    only inside a bounded grant. Without that grant the journey blocks instead
    of pretending an approval is waiting.
    """
    if action_type in SENSITIVE or action_type.startswith("ads."):
        return "approval"
    channel = "email" if "email" in action_type or action_type.endswith(".send") else action_type.split(".")[0]
    grant = _active_grant(db, tenant_id, workflow="inbound", channel=channel)
    if grant is not None:
        if grant.mode == "observe":
            return "approval"
        if grant.mode == "assisted":
            return "approval"
        if grant.mode == "bounded_autopilot":
            return "execute"
        return "approval"
    if settings.email_approval_required:
        return "approval"
    return "blocked"
