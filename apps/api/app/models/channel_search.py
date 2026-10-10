from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class ChannelSearch(Base, TenantOwnedMixin):
    __tablename__ = "channel_searches"

    query: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    channels_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class ChannelSearchHit(Base, TenantOwnedMixin):
    __tablename__ = "channel_search_hits"

    search_id: Mapped[UUID] = mapped_column(ForeignKey("channel_searches.id"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
