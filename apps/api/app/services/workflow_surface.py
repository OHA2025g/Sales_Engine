"""Command centre, launch readiness, identity lifecycle, and scan fairness."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.ai import AIApproval
from app.models.autonomy import AutopilotSettings, EntityAutomationState
from app.models.crm import Account, Contact, Customer, Lead
from app.models.execution import (
    AccountScanCursor,
    ActionRequest,
    AuthorizationGrant,
    CampaignPlan,
    OperationalEvidence,
    RevenueObjective,
    UserInvitation,
)
from app.models.identity import DomainEvent, RefreshToken, Role, User, UserRole
from app.models.lifecycle import Sequence
from app.services.autopilot_settings import get_or_create_settings
from app.services.journey_engine import sequence_is_runnable
from app.services.provider_resolve import resolve_channel
from app.services.revenue_ledger import retention_metrics
from app.services.scheduler_health import beat_status


def command_queue(db: Session, tenant_id: UUID) -> list[dict]:
    rows: list[dict] = []
    blocked = db.scalars(
        select(EntityAutomationState)
        .where(
            EntityAutomationState.tenant_id == tenant_id,
            EntityAutomationState.deleted_at.is_(None),
            EntityAutomationState.state.in_(["BLOCKED", "PAUSED"]),
        )
        .order_by(EntityAutomationState.updated_at.asc())
        .limit(25)
    ).all()
    for state in blocked:
        lead = db.get(Lead, UUID(state.entity_id)) if state.entity_type == "lead" else None
        account_name = ""
        if lead and lead.account_id:
            account = db.get(Account, lead.account_id)
            account_name = account.name if account else lead.company_name
        elif lead:
            account_name = lead.company_name
        rows.append(
            {
                "id": str(state.id),
                "kind": "exception",
                "account": account_name or state.entity_id,
                "reason": state.blocked_reason or state.state,
                "recommended_action": state.next_action or "Review the blocker",
                "owner": "",
                "due_at": None,
                "entity_type": state.entity_type,
                "entity_id": state.entity_id,
                "evidence": state.last_action,
            }
        )
    waiting = db.scalars(
        select(AIApproval)
        .where(
            AIApproval.tenant_id == tenant_id,
            AIApproval.deleted_at.is_(None),
            AIApproval.status == "pending",
        )
        .order_by(AIApproval.created_at.asc())
        .limit(25)
    ).all()
    for approval in waiting:
        rows.append(
            {
                "id": str(approval.id),
                "kind": "decision",
                "account": approval.entity_id,
                "reason": approval.title,
                "recommended_action": approval.action_type,
                "owner": "",
                "due_at": approval.expires_at.isoformat() if approval.expires_at else None,
                "entity_type": approval.entity_type,
                "entity_id": approval.entity_id,
                "evidence": "pending authorization",
            }
        )
    failed = db.scalars(
        select(ActionRequest)
        .where(
            ActionRequest.tenant_id == tenant_id,
            ActionRequest.deleted_at.is_(None),
            ActionRequest.status.in_(["failed", "blocked", "deferred"]),
        )
        .limit(25)
    ).all()
    for action in failed:
        rows.append(
            {
                "id": str(action.id),
                "kind": action.status,
                "account": action.recipient or action.entity_id,
                "reason": action.result or action.status,
                "recommended_action": action.action_type,
                "owner": "",
                "due_at": action.due_at.isoformat() if action.due_at else None,
                "entity_type": action.entity_type,
                "entity_id": action.entity_id,
                "evidence": action.provider_ref or action.status,
            }
        )
    return rows


def launch_checklist(db: Session, *, tenant_id: UUID, actor_id: UUID) -> dict:
    settings = get_or_create_settings(db, tenant_id=tenant_id, actor_id=actor_id)
    sequences = db.scalars(select(Sequence).where(Sequence.tenant_id == tenant_id, Sequence.deleted_at.is_(None))).all()
    runnable = [row for row in sequences if sequence_is_runnable(db, row)]
    email = resolve_channel(db, tenant_id, "email")
    objective = db.scalar(
        select(RevenueObjective).where(
            RevenueObjective.tenant_id == tenant_id,
            RevenueObjective.deleted_at.is_(None),
            RevenueObjective.status == "active",
        )
    )
    grant = db.scalar(
        select(AuthorizationGrant).where(
            AuthorizationGrant.tenant_id == tenant_id,
            AuthorizationGrant.deleted_at.is_(None),
            AuthorizationGrant.status == "active",
            AuthorizationGrant.workflow == "inbound",
        )
    )
    steps = [
        {"key": "objective", "ready": objective is not None, "detail": objective.name if objective else "No active revenue objective"},
        {"key": "journey", "ready": bool(runnable), "detail": f"{len(runnable)} activated email journey(s)"},
        {"key": "channel", "ready": email.mode in {"LIVE", "MOCK"}, "detail": email.reason},
        {"key": "policy", "ready": True, "detail": "Consent is checked before every send"},
        {"key": "grant", "ready": grant is not None or settings.email_approval_required, "detail": grant.mode if grant else "Assisted: sends wait for approval"},
        {"key": "stop", "ready": not settings.emergency_stop, "detail": "Emergency stop is clear" if not settings.emergency_stop else "Emergency stop is on"},
    ]
    inbound = all(step["ready"] for step in steps if step["key"] in {"journey", "channel", "policy", "stop"})
    return {"can_run_inbound": inbound, "steps": steps, "autonomy_mode": grant.mode if grant else ("assisted" if settings.email_approval_required else "unscoped")}


def next_scan_accounts(db: Session, *, tenant_id: UUID, actor_id: UUID, limit: int = 20) -> list[Account]:
    cursor = db.scalar(
        select(AccountScanCursor).where(AccountScanCursor.tenant_id == tenant_id, AccountScanCursor.deleted_at.is_(None))
    )
    if cursor is None:
        cursor = AccountScanCursor(tenant_id=tenant_id, created_by=actor_id, last_account_id="")
        db.add(cursor)
        db.flush()
    stmt = select(Account).where(Account.tenant_id == tenant_id, Account.deleted_at.is_(None)).order_by(Account.id.asc())
    if cursor.last_account_id:
        try:
            last = UUID(cursor.last_account_id)
        except ValueError:
            last = None
        if last is not None:
            stmt = stmt.where(Account.id > last)
    rows = list(db.scalars(stmt.limit(limit)).all())
    if not rows and cursor.last_account_id:
        cursor.last_account_id = ""
        rows = list(
            db.scalars(
                select(Account).where(Account.tenant_id == tenant_id, Account.deleted_at.is_(None)).order_by(Account.id.asc()).limit(limit)
            ).all()
        )
    if rows:
        cursor.last_account_id = str(rows[-1].id)
        cursor.next_scan_at = datetime.now(UTC) + timedelta(hours=6)
    return rows


def invite_user(db: Session, *, tenant_id: UUID, actor_id: UUID, email: str, role_name: str) -> tuple[UserInvitation, str]:
    token = uuid4().hex
    row = UserInvitation(
        tenant_id=tenant_id,
        created_by=actor_id,
        email=email.strip().lower(),
        role_name=role_name,
        status="pending",
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(row)
    db.flush()
    return row, token


def deactivate_user(db: Session, *, tenant_id: UUID, actor_id: UUID, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise ValueError("User was not found")
    user.is_active = False
    user.updated_at = datetime.now(UTC)
    tokens = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))).all()
    now = datetime.now(UTC)
    for token in tokens:
        token.revoked_at = now
    _ = actor_id
    return user


def accept_invitation(
    db: Session,
    *,
    tenant_id: UUID,
    invitation_id: UUID,
    name: str,
    password: str,
    token: str,
) -> User:
    invitation = db.get(UserInvitation, invitation_id)
    digest = hashlib.sha256(token.encode()).hexdigest()
    if invitation is None or invitation.tenant_id != tenant_id or invitation.status != "pending" or invitation.token_hash != digest:
        raise ValueError("Invitation is not pending")
    expires = invitation.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires is not None and expires < datetime.now(UTC):
        invitation.status = "expired"
        raise ValueError("Invitation expired")
    user = User(
        tenant_id=tenant_id,
        email=invitation.email,
        name=name,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == invitation.role_name))
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    invitation.status = "accepted"
    return user


def record_evidence(db: Session, *, tenant_id: UUID, actor_id: UUID, kind: str, status: str, detail: str) -> OperationalEvidence:
    row = OperationalEvidence(
        tenant_id=tenant_id,
        created_by=actor_id,
        kind=kind,
        status=status,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def latest_evidence(db: Session, tenant_id: UUID, kind: str) -> OperationalEvidence | None:
    return db.scalar(
        select(OperationalEvidence)
        .where(
            OperationalEvidence.tenant_id == tenant_id,
            OperationalEvidence.kind == kind,
            OperationalEvidence.deleted_at.is_(None),
            OperationalEvidence.status == "passed",
        )
        .order_by(OperationalEvidence.observed_at.desc())
    )


def queue_age_seconds(db: Session, tenant_id: UUID) -> int | None:
    oldest = db.scalar(
        select(func.min(DomainEvent.created_at)).where(
            DomainEvent.tenant_id == tenant_id,
            DomainEvent.processed_at.is_(None),
            DomainEvent.delivery_status.in_(["pending", "retry", "leased"]),
        )
    )
    if oldest is None:
        return 0
    stamped = oldest if oldest.tzinfo else oldest.replace(tzinfo=UTC)
    return int((datetime.now(UTC) - stamped).total_seconds())


def operating_snapshot(db: Session, *, tenant_id: UUID, settings: AutopilotSettings) -> dict:
    beat = beat_status(db)
    retention = retention_metrics(db, tenant_id)
    return {
        "scheduler": beat,
        "queue_age_seconds": queue_age_seconds(db, tenant_id),
        "retention": retention,
        "emergency_stop": settings.emergency_stop,
        "social_paused": settings.social_channel_paused,
        "sso": "not_configured",
        "whatsapp": "mock_or_not_configured",
    }


def resolve_customer_contact(db: Session, *, tenant_id: UUID, customer_id: UUID, contact_id: str | None) -> Contact | None:
    if contact_id:
        contact = db.get(Contact, UUID(str(contact_id)))
        if contact is None or contact.tenant_id != tenant_id or contact.deleted_at is not None:
            return None
        if contact.opt_out or not contact.email or not contact.consent_email:
            return None
        return contact
    customer = db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        return None
    return db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.account_id == customer.account_id,
            Contact.deleted_at.is_(None),
            Contact.opt_out.is_(False),
            Contact.consent_email.is_(True),
            Contact.email != "",
        )
    )


def create_objective(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: dict) -> RevenueObjective:
    row = RevenueObjective(
        tenant_id=tenant_id,
        created_by=actor_id,
        name=payload["name"],
        segment=payload.get("segment") or "",
        period=payload.get("period") or "",
        target_measure=payload.get("target_measure") or "qualified_pipeline",
        target_amount=payload.get("target_amount") or 0,
        offer_key=payload.get("offer_key") or "",
        status=payload.get("status") or "active",
    )
    db.add(row)
    db.flush()
    return row


def create_campaign_plan(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: dict) -> CampaignPlan:
    row = CampaignPlan(
        tenant_id=tenant_id,
        created_by=actor_id,
        objective_id=payload.get("objective_id"),
        name=payload["name"],
        audience=payload.get("audience") or "",
        channel=payload.get("channel") or "",
        offer_key=payload.get("offer_key") or "",
        product_id=payload.get("product_id"),
        budget=payload.get("budget") or 0,
        currency=payload.get("currency") or "INR",
        status=payload.get("status") or "draft",
        schedule=payload.get("schedule") or "",
    )
    db.add(row)
    db.flush()
    return row
