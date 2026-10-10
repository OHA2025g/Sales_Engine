from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class ChannelSearchIn(APIModel):
    query: str = Field(min_length=2, max_length=300)

    @field_validator("query")
    @classmethod
    def collapse_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Enter at least two characters.")
        return cleaned


class ChannelHitOut(APIModel):
    rank: int
    title: str
    url: str
    snippet: str


class ChannelBucketOut(APIModel):
    channel: str
    mode: str
    provider: str
    reason: str
    hits: list[ChannelHitOut]


class ChannelSearchOut(APIModel):
    id: UUID
    query: str
    status: str
    provider: str
    created_at: datetime
    channels: list[ChannelBucketOut]


class ChannelSearchStatusOut(APIModel):
    provider: str
    configured: bool
    detail: str
