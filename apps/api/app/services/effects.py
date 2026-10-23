"""External effects are recorded before the provider call and reconciled before retry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessment import ExternalEffect
from app.models.autonomy import AutonomousRun, AutonomousRunStep

LEASE_MINUTES = 5
MAX_EFFECT_ATTEMPTS = 3


@dataclass(frozen=True)
class EffectAttempt:
    accepted: bool = False
    failed: bool = False
    retryable: bool = False
    provider_id: str = ""
    failure_class: str = ""
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class ReconciledEffect:
    outcome: str
    provider_id: str = ""


def build_effect_key(*, tenant_id: UUID, action: str, channel: str, target_id: str, content_version: str, grant_id: str) -> str:
    raw = "|".join([str(tenant_id), action, channel, target_id, content_version, grant_id])
    return hashlib.sha256(raw.encode()).hexdigest()


def execute_external_effect(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    run: AutonomousRun,
    action: str,
    channel: str,
    target_id: str,
    content_version: str,
    grant_id: str,
    call,
    reconcile,
) -> ExternalEffect:
    key = build_effect_key(
        tenant_id=tenant_id,
        action=action,
        channel=channel,
        target_id=target_id,
        content_version=content_version,
        grant_id=grant_id,
    )
    existing = db.scalar(
        select(ExternalEffect).where(
            ExternalEffect.tenant_id == tenant_id,
            ExternalEffect.effect_key == key,
            ExternalEffect.deleted_at.is_(None),
        )
    )
    if existing is not None and existing.outcome == "held":
        return existing
    if existing is not None and existing.outcome == "confirmed":
        return existing
    if existing is not None and existing.outcome == "confirmed_failure":
        return existing
    if existing is not None and existing.outcome == "unknown":
        resolved = reconcile(existing)
        existing.outcome = resolved.outcome
        if resolved.provider_id:
            existing.provider_ref = resolved.provider_id
        _finish_step(db, existing.step_id, existing.outcome)
        db.flush()
        return existing
    if existing is not None and existing.outcome == "retry_wait":
        if run.status in {"paused", "cancelled"} or run.cancelled_at is not None:
            return existing
        meta = _detail(existing.detail)
        if int(meta.get("attempts") or 0) >= MAX_EFFECT_ATTEMPTS:
            existing.outcome = "confirmed_failure"
            existing.detail = _dump_detail(meta, reason="retries exhausted")
            _finish_step(db, existing.step_id, existing.outcome)
            db.flush()
            return existing
        if not _retry_due(meta):
            return existing
        return _attempt_existing(db, existing, call)
    if run.status in {"paused", "cancelled"} or run.cancelled_at is not None:
        raise RuntimeError("Paused or cancelled journeys do not start a new external effect")

    now = datetime.now(UTC)
    step = AutonomousRunStep(
        tenant_id=tenant_id,
        created_by=actor_id,
        run_id=run.id,
        name=action,
        position=1,
        status="running",
        entity_type="external_effect",
        entity_id=target_id,
        started_at=now,
        finished_at=None,
        lease_owner="worker",
        lease_until=now + timedelta(minutes=LEASE_MINUTES),
        effect_key=key,
        outcome="unknown",
    )
    db.add(step)
    db.flush()
    effect = ExternalEffect(
        tenant_id=tenant_id,
        created_by=actor_id,
        effect_key=key,
        action=action,
        channel=channel,
        target_id=target_id,
        content_version=content_version,
        grant_id=grant_id,
        outcome="unknown",
        run_id=run.id,
        step_id=step.id,
    )
    db.add(effect)
    db.flush()
    return _attempt_existing(db, effect, call)


def _attempt_existing(db: Session, effect: ExternalEffect, call) -> ExternalEffect:
    try:
        attempt = call()
    except TimeoutError as exc:
        effect.detail = str(exc)[:500]
        effect.outcome = "unknown"
        db.flush()
        return effect
    effect.outcome = _outcome_for(attempt)
    effect.provider_ref = attempt.provider_id or effect.provider_ref
    if effect.outcome == "retry_wait":
        meta = _detail(effect.detail)
        attempts = int(meta.get("attempts") or 0) + 1
        delay = attempt.retry_after_seconds
        if delay is None:
            delay = 60 * (2 ** min(attempts, 6))
        if attempts >= MAX_EFFECT_ATTEMPTS:
            effect.outcome = "confirmed_failure"
            effect.detail = _dump_detail(
                {"attempts": attempts, "failure_class": attempt.failure_class or "RATE_LIMIT"},
                reason="retries exhausted",
            )
        else:
            effect.detail = _dump_detail(
                {
                    "attempts": attempts,
                    "retry_after_seconds": delay,
                    "failure_class": attempt.failure_class or "RATE_LIMIT",
                    "next_attempt_at": (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(),
                }
            )
            db.flush()
            return effect
    elif attempt.failure_class:
        effect.detail = _dump_detail(_detail(effect.detail), failure_class=attempt.failure_class)
    _finish_step(db, effect.step_id, effect.outcome)
    db.flush()
    return effect


def _detail(raw: str) -> dict:
    try:
        loaded = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _dump_detail(meta: dict, **extra: object) -> str:
    merged = dict(meta)
    merged.update(extra)
    return json.dumps(merged, default=str)[:500]


def _retry_due(meta: dict) -> bool:
    raw = str(meta.get("next_attempt_at") or "")
    if not raw:
        return True
    moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment <= datetime.now(UTC)


def _outcome_for(attempt: EffectAttempt) -> str:
    if attempt.accepted and attempt.provider_id:
        return "confirmed"
    if attempt.failed and attempt.retryable:
        return "retry_wait"
    if attempt.failed and not attempt.retryable:
        return "confirmed_failure"
    return "unknown"


def _finish_step(db: Session, step_id: UUID | None, outcome: str) -> None:
    if step_id is None or outcome == "unknown":
        return
    step = db.get(AutonomousRunStep, step_id)
    if step is None:
        return
    step.status = "completed" if outcome == "confirmed" else "blocked"
    step.outcome = outcome
    step.finished_at = datetime.now(UTC)
    step.lease_until = None
