import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AIApproval
from app.models.autonomy import AutonomousRun
from app.models.crm import Lead
from app.models.integrations import EmailMessage
from app.models.lifecycle import Conversation, Sequence, SequenceEnrollment, SequenceStep
from app.providers.email import get_email_provider
from app.services.audit import emit_event
from app.services.automation_state import is_entity_paused, upsert_state
from app.services.autopilot_settings import get_or_create_settings, in_quiet_hours
from app.services.consent import assert_can_email, email_block_reason
from app.services.crm import add_activity
from app.services.demo_guard import external_execution_block
from app.services.external_hold import hold_stale_external_work
from app.services.idempotency import claim_daily_slot, claim_key, remember_result
from app.services.lifecycle import enroll_sequence
from app.services.mail_origin import response_block
from app.services.outreach_limits import outreach_limit_reason
from app.services.policy_versions import current_policy_version
from app.services.provider_ops import begin_action, confirm_action, fail_action


def _payload(row: AIApproval) -> dict:
    try:
        data = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def advance_enrollment(db: Session, enrollment: SequenceEnrollment) -> None:
    nxt = db.scalar(
        select(SequenceStep)
        .where(
            SequenceStep.sequence_id == enrollment.sequence_id,
            SequenceStep.deleted_at.is_(None),
            SequenceStep.position > enrollment.current_step,
        )
        .order_by(SequenceStep.position.asc())
    )
    if nxt is None:
        enrollment.status = "completed"
        enrollment.next_run_at = None
        return
    enrollment.current_step = nxt.position
    enrollment.next_run_at = datetime.now(UTC) + timedelta(days=max(nxt.delay_days, 0))


def find_or_create_thread(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    subject: str,
    provider: str,
    is_mock: bool,
    thread_id: str,
) -> Conversation:
    conversation = None
    if thread_id:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.provider_thread_id == thread_id,
                Conversation.deleted_at.is_(None),
            )
        )
    if conversation is None:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.lead_id == lead.id,
                Conversation.channel == "email",
                Conversation.deleted_at.is_(None),
            )
        )
    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant_id,
            created_by=actor_id,
            channel="email",
            account_id=lead.account_id,
            contact_id=lead.contact_id,
            lead_id=lead.id,
            subject=subject,
            status="open",
            outcome="",
            consent=True,
            provider=provider,
            is_mock=is_mock,
            transcript="",
            summary="",
            provider_thread_id=thread_id,
        )
        db.add(conversation)
        db.flush()
        return conversation
    if thread_id and not conversation.provider_thread_id:
        conversation.provider_thread_id = thread_id
    conversation.lead_id = conversation.lead_id or lead.id
    return conversation


def persisted_send_for_approval(db: Session, tenant_id: UUID, approval_id: UUID) -> EmailMessage | None:
    return db.scalar(
        select(EmailMessage).where(
            EmailMessage.tenant_id == tenant_id,
            EmailMessage.approval_id == approval_id,
            EmailMessage.deleted_at.is_(None),
        )
    )


def execute_email_send(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    approval: AIApproval,
    payload_patch: dict | None = None,
) -> str:
    payload = _payload(approval)
    if payload_patch:
        if payload_patch.get("subject"):
            payload["subject"] = payload_patch["subject"]
        if payload_patch.get("body"):
            payload["body"] = payload_patch["body"]
        approval.payload_json = json.dumps(payload, default=str)
    existing = persisted_send_for_approval(db, tenant_id, approval.id)
    if existing is not None and existing.status == "SENT":
        return f"Provider {existing.provider} recorded send {existing.provider_message_id}."
    if existing is not None and existing.status == "SENDING":
        return "Send outcome is unknown. Reconcile before another attempt."
    if existing is not None and existing.status == "FAILED":
        return existing.last_error or "Send failed and will not be retried until the failure is corrected."
    if existing is not None and existing.status == "RETRYING" and existing.next_retry_at is not None:
        due = existing.next_retry_at if existing.next_retry_at.tzinfo else existing.next_retry_at.replace(tzinfo=UTC)
        if due > datetime.now(UTC):
            return f"Retry scheduled after {due.isoformat()}."
        if existing.attempt >= 3:
            existing.status = "FAILED"
            existing.last_error = "Retry limit reached."
            return existing.last_error
    lead_id = payload.get("lead_id") or approval.entity_id
    if not lead_id:
        return "Send was not executed: lead_id is missing from the approval payload."
    lead = db.scalar(select(Lead).where(Lead.tenant_id == tenant_id, Lead.id == UUID(str(lead_id)), Lead.deleted_at.is_(None)))
    enrollment_id = payload.get("enrollment_id")
    enrollment = None
    if enrollment_id:
        enrollment = db.scalar(
            select(SequenceEnrollment).where(
                SequenceEnrollment.tenant_id == tenant_id,
                SequenceEnrollment.id == UUID(str(enrollment_id)),
                SequenceEnrollment.deleted_at.is_(None),
            )
        )
        if enrollment is not None and lead is None:
            lead = db.scalar(select(Lead).where(Lead.tenant_id == tenant_id, Lead.id == enrollment.lead_id))
    if lead is None:
        return "Send was not executed: lead is missing from the approval payload."
    try:
        assert_can_email(lead)
    except HTTPException:
        reason = email_block_reason(lead) or "consent or suppression blocked the message"
        return f"Send was not executed: {reason}."
    if is_entity_paused(db, tenant_id=tenant_id, entity_type="lead", entity_id=str(lead.id)):
        return "Send was not executed: automation is paused for this lead."
    if approval.status == "held":
        return "Held for review. It was not executed."
    expires = approval.expires_at
    if expires is not None and (expires if expires.tzinfo else expires.replace(tzinfo=UTC)) < datetime.now(UTC):
        approval.status = "held"
        return "Approval expired before execution."
    scope_block = external_execution_block(db, tenant_id=tenant_id, action=approval.action_type or "email.send", recipient=lead.email or "")
    if scope_block:
        return scope_block
    thread_block = response_block(db, tenant_id=tenant_id, thread_id=str(payload.get("thread_id") or ""))
    if thread_block:
        return thread_block
    subject = str(payload.get("subject") or "Follow-up")
    body = str(payload.get("body") or payload.get("template") or "")
    version = hashlib.sha256(f"{subject}|{body}".encode()).hexdigest()
    stored_copy = str(payload.get("copy_hash") or "")
    if stored_copy and stored_copy != version:
        return "Send was not executed: the content version does not match the authorized copy."
    if not stored_copy:
        payload["copy_hash"] = version
        approval.payload_json = json.dumps(payload, default=str)
    settings = get_or_create_settings(db, tenant_id=tenant_id, actor_id=actor_id)
    if in_quiet_hours(settings):
        return "Send deferred: quiet hours."
    limit = outreach_limit_reason(db, settings, lead.id)
    if limit:
        return f"Send was not executed: {limit}."
    provider = get_email_provider(db, tenant_id)
    health = provider.health()
    if not health.connected:
        upsert_state(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            entity_type="lead",
            entity_id=str(lead.id),
            state="BLOCKED",
            last_action="email_blocked_config",
            next_action="connect_gmail",
            blocked_reason="BLOCKED BY CONFIGURATION",
            run_id=approval.run_id,
        )
        return "BLOCKED BY CONFIGURATION"
    if enrollment is None and payload.get("sequence_id"):
        sequence = db.scalar(
            select(Sequence).where(
                Sequence.tenant_id == tenant_id,
                Sequence.id == UUID(str(payload["sequence_id"])),
                Sequence.deleted_at.is_(None),
            )
        )
        if sequence is not None:
            enrollment = enroll_sequence(
                db,
                tenant_id=tenant_id,
                actor_id=actor_id,
                sequence=sequence,
                lead=lead,
                run_id=approval.run_id,
                actor_type="ai",
            )
            payload["enrollment_id"] = str(enrollment.id)
            approval.payload_json = json.dumps(payload, default=str)
    send_key = f"email.send:{tenant_id}:{approval.id}"
    claimed, key_row = claim_key(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        key=send_key,
        workflow="email_send",
        entity_id=str(lead.id),
        action_type="email.send",
    )
    action = begin_action(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="email.send",
        idempotency_key=send_key,
        provider=health.provider,
        approval_id=approval.id,
        entity_type="lead",
        entity_id=str(lead.id),
        request_summary=f"send:{lead.email}",
    )
    action.policy_version = current_policy_version(db, tenant_id)
    action.provider_mode = "MOCK" if health.is_mock else "LIVE"
    if action.status == "CONFIRMED" and action.external_id:
        return f"Provider {action.provider} recorded send {action.external_id}."
    replay = persisted_send_for_approval(db, tenant_id, approval.id)
    if replay is not None and replay.status == "SENT":
        confirm_action(action, provider=replay.provider, external_id=replay.provider_message_id, response_summary="replay")
        return f"Provider {replay.provider} recorded send {replay.provider_message_id}."
    if not claimed:
        if key_row.result_ref and replay is not None:
            confirm_action(action, provider=replay.provider, external_id=replay.provider_message_id, response_summary="replay")
            return f"Provider {replay.provider} recorded send {replay.provider_message_id}."
        return "Send already in progress for this approval."
    if not claim_daily_slot(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        kind="email",
        limit=settings.max_emails_per_day,
    ):
        return "Send was not executed: Daily email cap reached."
    pending_id = f"pending-{uuid4()}"
    conversation = find_or_create_thread(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        lead=lead,
        subject=subject,
        provider=health.provider,
        is_mock=health.is_mock,
        thread_id=str(payload.get("thread_id") or ""),
    )
    message = existing or EmailMessage(
        tenant_id=tenant_id,
        created_by=actor_id,
        conversation_id=conversation.id,
        direction="outbound",
        from_addr="",
        to_addrs=json.dumps([lead.email]),
        subject=subject,
        body_text=body,
        provider=health.provider,
        provider_message_id=pending_id,
        provider_thread_id=conversation.provider_thread_id,
        status="SENDING",
        approval_id=approval.id,
        lead_id=lead.id,
        attempt=(existing.attempt + 1) if existing else 1,
    )
    if existing is None:
        db.add(message)
        db.flush()
    else:
        message.attempt = (message.attempt or 1) + 1
        message.status = "SENDING"
        message.subject = subject
        message.body_text = body
    result = provider.send(to=lead.email, subject=subject, body=body, thread_id=conversation.provider_thread_id)
    if not result.ok:
        retryable = bool(result.retryable) and message.attempt < 3
        failure_class = "RATE_LIMIT" if result.retryable and result.retry_after_seconds is not None else ("TRANSIENT" if result.retryable else "PERMANENT")
        if result.reason == "BLOCKED BY CONFIGURATION":
            failure_class = "CONFIGURATION"
            retryable = False
        fail_action(action, failure_class=failure_class, error=result.reason, retryable=retryable)
        message.status = "RETRYING" if retryable else "FAILED"
        message.last_error = "Retry limit reached. " + result.reason if result.retryable and not retryable else result.reason
        if retryable:
            delay = result.retry_after_seconds
            message.next_retry_at = (
                datetime.now(UTC) + timedelta(seconds=max(int(delay), 0))
                if delay is not None
                else datetime.now(UTC) + timedelta(minutes=2 ** min(message.attempt, 6))
            )
        else:
            message.next_retry_at = None
        if not result.retryable:
            upsert_state(
                db,
                tenant_id=tenant_id,
                actor_id=actor_id,
                entity_type="lead",
                entity_id=str(lead.id),
                state="BLOCKED",
                last_action="email_failed",
                next_action="retry_send",
                blocked_reason=result.reason or "BLOCKED BY CONFIGURATION",
                run_id=approval.run_id,
            )
        return result.reason or "Send failed."
    confirm_action(action, provider=result.provider, external_id=result.provider_message_id, response_summary=result.reason)
    message.status = "SENT"
    message.provider = result.provider
    message.provider_message_id = result.provider_message_id
    message.provider_thread_id = result.thread_id
    message.sent_at = datetime.now(UTC)
    message.last_error = ""
    conversation.provider_thread_id = result.thread_id
    conversation.provider = result.provider
    conversation.is_mock = result.is_mock
    conversation.status = "sent"
    conversation.outcome = "sent"
    conversation.transcript = ((conversation.transcript or "") + f"\n\nOutbound: {body}").strip()
    conversation.summary = f"Last outbound via {result.provider}"
    add_activity(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        activity_type="email",
        title=f"Email sent through {result.provider}",
        body=f"{result.reason} id={result.provider_message_id}",
        actor_type="ai",
    )
    upsert_state(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        state="CONTACTED",
        last_action="email_sent",
        next_action="wait_for_reply",
        blocked_reason="",
        run_id=approval.run_id,
    )
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="email.sent",
        entity_type="lead",
        entity_id=str(lead.id),
        payload={
            "approval_id": str(approval.id),
            "message_id": str(message.id),
            "provider_message_id": result.provider_message_id,
            "provider": result.provider,
            "is_mock": result.is_mock,
        },
    )
    if str(payload.get("purpose") or "") == "acknowledgement":
        _record_acknowledgement(db, tenant_id=tenant_id, actor_id=actor_id, lead_id=str(lead.id), message_id=str(message.id), provider_message_id=result.provider_message_id, correlation_id="")
    if enrollment is not None:
        advance_enrollment(db, enrollment)
    if approval.run_id:
        run = db.get(AutonomousRun, approval.run_id)
        if run is not None and run.tenant_id == tenant_id:
            run.status = "completed"
            run.summary = (run.summary + f" Email send executed via {result.provider}.").strip()
    remember_result(key_row, str(message.id))
    return f"Provider {result.provider} recorded send {result.provider_message_id}."


def _record_acknowledgement(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead_id: str,
    message_id: str,
    provider_message_id: str,
    correlation_id: str,
) -> None:
    from app.models.execution import JourneyLink
    from app.models.identity import DomainEvent

    already = db.scalar(
        select(DomainEvent.id).where(
            DomainEvent.tenant_id == tenant_id,
            DomainEvent.event_type == "response.sent",
            DomainEvent.entity_id == lead_id,
        )
    )
    if already is None:
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="response.sent",
            entity_type="lead",
            entity_id=lead_id,
            payload={"message_id": message_id, "provider_message_id": provider_message_id},
            correlation_id=correlation_id,
        )
    journey_key = f"lead:{lead_id}"
    linked = db.scalar(
        select(JourneyLink.id).where(
            JourneyLink.tenant_id == tenant_id,
            JourneyLink.journey_key == journey_key,
            JourneyLink.entity_type == "email_message",
            JourneyLink.entity_id == message_id,
            JourneyLink.deleted_at.is_(None),
        )
    )
    if linked is None:
        db.add(
            JourneyLink(
                tenant_id=tenant_id,
                created_by=actor_id,
                journey_key=journey_key,
                entity_type="email_message",
                entity_id=message_id,
                role="acknowledgement",
            )
        )


def retry_retrying_sends(db: Session, *, tenant_id: UUID | None = None, limit: int = 25) -> int:
    hold_stale_external_work(db, tenant_id=tenant_id)
    db.flush()
    now = datetime.now(UTC)
    stmt = select(EmailMessage).where(
        EmailMessage.deleted_at.is_(None),
        EmailMessage.status == "RETRYING",
        EmailMessage.approval_id.is_not(None),
        EmailMessage.next_retry_at.is_not(None),
        EmailMessage.next_retry_at <= now,
    )
    if tenant_id is not None:
        stmt = stmt.where(EmailMessage.tenant_id == tenant_id)
    rows = db.scalars(stmt.limit(limit)).all()
    count = 0
    for row in rows:
        approval = db.get(AIApproval, row.approval_id)
        if approval is None or approval.tenant_id != row.tenant_id:
            continue
        execute_email_send(db, tenant_id=row.tenant_id, actor_id=row.created_by or approval.created_by, approval=approval)
        count += 1
    return count
