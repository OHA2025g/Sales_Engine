from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class AssessmentEvidence(Base, TenantOwnedMixin):
    __tablename__ = "assessment_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "person_id",
            "kind",
            "source",
            "content_hash",
            name="uq_assessment_evidence",
        ),
    )

    person_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), default="neutral", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)


class AssessmentDecision(Base, TenantOwnedMixin):
    __tablename__ = "assessment_decisions"

    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), index=True, nullable=False)
    identity: Mapped[str] = mapped_column(String(20), default="resolved", nullable=False)
    fit_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    coverage_known: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coverage_required: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    response_eligible: Mapped[bool] = mapped_column(default=False, nullable=False)
    outbound_eligible: Mapped[bool] = mapped_column(default=False, nullable=False)
    meeting_eligible: Mapped[bool] = mapped_column(default=False, nullable=False)
    sales_qualified: Mapped[bool] = mapped_column(default=False, nullable=False)
    not_a_fit: Mapped[bool] = mapped_column(default=False, nullable=False)
    next_action: Mapped[str] = mapped_column(String(40), default="wait", nullable=False)
    rules_version: Mapped[str] = mapped_column(String(40), default="heuristics-v2", nullable=False)


class ExternalEffect(Base, TenantOwnedMixin):
    __tablename__ = "external_effects"
    __table_args__ = (UniqueConstraint("tenant_id", "effect_key", name="uq_external_effect_key"),)

    effect_key: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    content_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    grant_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    provider_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("autonomous_runs.id"), nullable=True)
    step_id: Mapped[UUID | None] = mapped_column(ForeignKey("autonomous_run_steps.id"), nullable=True)
