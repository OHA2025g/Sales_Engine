"""Durable workflow contracts added by the revenue redesign.

These records sit beside CRM objects. They do not replace accounts, leads,
opportunities, contracts, or customers.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class EventDeliveryAttempt(Base, TenantOwnedMixin):
    __tablename__ = "event_delivery_attempts"

    event_id: Mapped[UUID] = mapped_column(ForeignKey("domain_events.id"), index=True, nullable=False)
    consumer: Mapped[str] = mapped_column(String(40), default="orchestrator", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionRequest(Base, TenantOwnedMixin):
    __tablename__ = "action_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "dedupe_key", name="uq_action_request_dedupe"),)

    approval_id: Mapped[UUID | None] = mapped_column(ForeignKey("ai_approvals.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    provider_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version_key: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class AuthorizationGrant(Base, TenantOwnedMixin):
    __tablename__ = "authorization_grants"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="assisted", nullable=False)
    workflow: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    segment: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    template_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    volume_cap: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cap: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RevenueObjective(Base, TenantOwnedMixin):
    __tablename__ = "revenue_objectives"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    segment: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    target_measure: Mapped[str] = mapped_column(String(40), default="qualified_pipeline", nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    offer_key: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)


class CampaignPlan(Base, TenantOwnedMixin):
    __tablename__ = "campaign_plans"

    objective_id: Mapped[UUID | None] = mapped_column(ForeignKey("revenue_objectives.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    offer_key: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    budget: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    schedule: Mapped[str] = mapped_column(String(80), default="", nullable=False)


class StageEvidence(Base, TenantOwnedMixin):
    __tablename__ = "stage_evidence"

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="human", nullable=False)


class EligibilityEvidence(Base, TenantOwnedMixin):
    __tablename__ = "eligibility_evidence"

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    basis: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    scope: Mapped[str] = mapped_column(String(40), default="email", nullable=False)
    fresh: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SlaClock(Base, TenantOwnedMixin):
    __tablename__ = "sla_clocks"

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transition: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    pause_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class JourneyLink(Base, TenantOwnedMixin):
    __tablename__ = "journey_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "journey_key", "entity_type", "entity_id", name="uq_journey_link"),
    )

    journey_key: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="", nullable=False)


class AccountScanCursor(Base, TenantOwnedMixin):
    __tablename__ = "account_scan_cursors"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_account_scan_cursor"),)

    last_account_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RevenueCohortSnapshot(Base, TenantOwnedMixin):
    __tablename__ = "revenue_cohort_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_revenue_cohort_period"),)

    period: Mapped[str] = mapped_column(String(20), nullable=False)
    opening_arr: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    churn_arr: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    contraction_arr: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    expansion_arr: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)


class UserInvitation(Base, TenantOwnedMixin):
    __tablename__ = "user_invitations"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role_name: Mapped[str] = mapped_column(String(80), default="Sales Rep", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationalEvidence(Base, TenantOwnedMixin):
    __tablename__ = "operational_evidence"

    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="recorded", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
