from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class SiteSignalChoice(Base, TenantOwnedMixin):
    """A tenant's decision on one catalog signal. Proposed until a person chooses."""

    __tablename__ = "site_signal_choices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_site_signal_choice"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)


class SiteObservation(Base, TenantOwnedMixin):
    """One observed fact. History stays; a cohort reads the newest row per account and code."""

    __tablename__ = "site_observations"
    __table_args__ = (
        Index("ix_site_observations_lookup", "tenant_id", "account_id", "signal_code", "observed_at"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("site_profile_runs.id"), nullable=True)
    signal_code: Mapped[str] = mapped_column(String(40), nullable=False)
    value_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_text: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    evidence_url: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SiteProfileRun(Base, TenantOwnedMixin):
    __tablename__ = "site_profile_runs"

    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    accounts_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    observations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SiteProfileCheck(Base, TenantOwnedMixin):
    """Marks an account as read so an unreachable site is not retried every click."""

    __tablename__ = "site_profile_checks"
    __table_args__ = (
        Index("ix_site_profile_checks_account", "tenant_id", "account_id", "checked_at"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("site_profile_runs.id"), nullable=True)
    reachable: Mapped[bool] = mapped_column(default=False, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
