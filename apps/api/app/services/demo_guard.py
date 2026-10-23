"""A prepared demonstration blocks unrelated external work until it is authorized."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.integrations import ProviderAction
from app.models.operating_plan import DemoScope
from app.services.external_hold import external_action

PREPARED_BLOCK = "The controlled demonstration is prepared and has not been authorized to execute."


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def open_demo_scope(db: Session, tenant_id: UUID) -> DemoScope | None:
    return db.scalar(
        select(DemoScope)
        .where(
            DemoScope.tenant_id == tenant_id,
            DemoScope.deleted_at.is_(None),
            DemoScope.status.in_(["prepared", "authorized"]),
        )
        .order_by(DemoScope.created_at.desc())
    )


def external_execution_block(
    db: Session,
    *,
    tenant_id: UUID,
    action: str,
    recipient: str = "",
    target_id: str = "",
    channel: str = "",
) -> str:
    if not external_action(action):
        return ""
    scope = open_demo_scope(db, tenant_id)
    if scope is None:
        return ""
    if scope.status == "prepared":
        return PREPARED_BLOCK
    if action.startswith("ads.") or action.startswith("voice."):
        return "Ads and voice stay outside this demonstration. No activation or dial was sent."
    expires = _aware(scope.expires_at)
    if expires is not None and expires < datetime.now(UTC):
        return "The demonstration scope has expired. Nothing was sent."
    used = int(
        db.scalar(
            select(func.count())
            .select_from(ProviderAction)
            .where(
                ProviderAction.tenant_id == tenant_id,
                ProviderAction.deleted_at.is_(None),
                ProviderAction.status == "CONFIRMED",
                ProviderAction.created_at >= scope.created_at,
            )
        )
        or 0
    )
    if used >= scope.action_limit:
        return "The demonstration action limit is reached. Nothing was sent."
    buyer = (scope.buyer_email or "").strip().casefold()
    if action.startswith("social"):
        if scope.version_id is None or not target_id or target_id != str(scope.version_id):
            return "That creative version is outside the controlled demonstration."
        if scope.channel and channel and channel != scope.channel:
            return "That social channel is outside the controlled demonstration."
        return ""
    if not buyer or recipient.strip().casefold() != buyer:
        return "The recipient is outside the controlled demonstration."
    return ""
