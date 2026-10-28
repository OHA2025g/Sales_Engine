"""Scoped authorization. A boolean is not a license to skip every decision."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai import AIApproval
from app.models.autonomy import AutopilotSettings
from app.models.execution import AuthorizationGrant
from app.models.integrations import ProviderAction

SENSITIVE = ("quote.discount", "ads.spend", "ads.launch", "renewal.commercial")


def _unexpired(row: AuthorizationGrant, now: datetime) -> bool:
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires is None or expires >= now


def _active_grant(db: Session, tenant_id: UUID, *, workflow: str, channel: str, action_type: str = "") -> AuthorizationGrant | None:
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
    specific: list[AuthorizationGrant] = []
    general: list[AuthorizationGrant] = []
    for row in rows:
        if not _unexpired(row, now):
            continue
        if row.template_version and row.template_version != action_type:
            continue
        if row.template_version:
            specific.append(row)
        else:
            general.append(row)
    if specific:
        return specific[0]
    return general[0] if general else None


def _grant_uses(db: Session, grant: AuthorizationGrant, action_type: str) -> int:
    created = grant.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    stmt = (
        select(func.count())
        .select_from(ProviderAction)
        .join(AIApproval, AIApproval.id == ProviderAction.approval_id)
        .where(
            ProviderAction.tenant_id == grant.tenant_id,
            ProviderAction.deleted_at.is_(None),
            ProviderAction.status == "CONFIRMED",
            AIApproval.action_type == action_type,
        )
    )
    if created is not None:
        stmt = stmt.where(ProviderAction.created_at >= created)
    return int(db.scalar(stmt) or 0)


def send_authorization(db: Session, *, tenant_id: UUID, settings: AutopilotSettings, action_type: str) -> str:
    """Return execute, approval, or blocked.

    email_approval_required=false is not a global bypass. Predictable sends run
    only inside a bounded grant. Without that grant the journey blocks instead
    of pretending an approval is waiting.
    """
    if action_type in SENSITIVE or action_type.startswith("ads."):
        return "approval"
    channel = "email" if "email" in action_type or action_type.endswith(".send") else action_type.split(".")[0]
    grant = _active_grant(db, tenant_id, workflow="inbound", channel=channel, action_type=action_type)
    if grant is not None:
        if grant.mode == "observe":
            return "approval"
        if grant.mode == "assisted":
            return "approval"
        if grant.mode == "bounded_autopilot":
            if grant.volume_cap > 0 and _grant_uses(db, grant, action_type) >= grant.volume_cap:
                return "approval"
            return "execute"
        return "approval"
    if settings.email_approval_required:
        return "approval"
    return "blocked"
