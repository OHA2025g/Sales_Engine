from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class SellerProfile(Base, TenantOwnedMixin):
    __tablename__ = "seller_profiles"

    company_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    proof: Mapped[str] = mapped_column(Text, default="", nullable=False)
    capture_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class ContentDraft(Base, TenantOwnedMixin):
    __tablename__ = "content_drafts"

    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    headline: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cta: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    destination_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    brief: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    external_id: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    social_post_id: Mapped[UUID | None] = mapped_column(nullable=True)
    campaign_id: Mapped[UUID | None] = mapped_column(nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
