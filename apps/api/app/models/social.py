from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class SocialPost(Base, TenantOwnedMixin):
    __tablename__ = "social_posts"

    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="failed", nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    external_id: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
