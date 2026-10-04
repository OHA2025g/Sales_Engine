"""Separate an approval decision from the external effect it authorizes."""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AIApproval
from app.models.execution import ActionRequest


def _now() -> datetime:
    return datetime.now(UTC)


def classify_execution(message: str) -> str:
    text = (message or "").strip().lower()
    if not text:
        return "failed"
    if "not executable" in text or text.startswith("action type"):
        return "failed"
    if "deferred" in text or "quiet hours" in text:
        return "deferred"
    if any(token in text for token in ("not executed", "blocked", "refused", "suspended", "missing", "stale", "expired", "paused", "stop", "cancelled")):
        return "blocked"
    if text.startswith("failed") or "was not" in text:
        return "failed"
    return "delivered"


def upsert_action_request(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID | None,
    approval: AIApproval | None,
    action_type: str,
    status: str,
    result: str,
    channel: str = "",
    recipient: str = "",
    entity_type: str = "",
    entity_id: str = "",
    dedupe_key: str = "",
    payload: dict | None = None,
    version_key: str = "",
    provider: str = "",
    provider_ref: str = "",
) -> ActionRequest:
    key = dedupe_key or (approval.idempotency_key if approval and approval.idempotency_key else f"{action_type}:{entity_id}:{version_key}")
    if not key:
        key = f"{action_type}:{entity_type}:{entity_id}:{_now().timestamp()}"
    row = db.scalar(
        select(ActionRequest).where(
            ActionRequest.tenant_id == tenant_id,
            ActionRequest.dedupe_key == key,
            ActionRequest.deleted_at.is_(None),
        )
    )
    body = json.dumps(payload or {}, default=str)
    if row is None:
        row = ActionRequest(
            tenant_id=tenant_id,
            created_by=actor_id,
            approval_id=approval.id if approval else None,
            action_type=action_type,
            channel=channel,
            entity_type=entity_type or (approval.entity_type if approval else ""),
            entity_id=entity_id or (approval.entity_id if approval else ""),
            recipient=recipient,
            payload_json=body,
            dedupe_key=key[:200],
            status=status,
            result=result[:2000],
            version_key=version_key,
            provider=provider,
            provider_ref=provider_ref,
            due_at=_now() if status == "deferred" else None,
        )
        db.add(row)
    else:
        row.status = status
        row.result = result[:2000]
        row.provider = provider or row.provider
        row.provider_ref = provider_ref or row.provider_ref
        row.version_key = version_key or row.version_key
        if recipient:
            row.recipient = recipient
        if status == "deferred" and row.due_at is None:
            row.due_at = _now()
        row.updated_by = actor_id
    db.flush()
    return row
