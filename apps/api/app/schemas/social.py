from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class SocialPostIn(APIModel):
    channel: str
    body: str = Field(min_length=1, max_length=3000)
    link_url: str = ""
    image_url: str = ""


class SocialPostOut(APIModel):
    id: UUID
    channel: str
    body: str
    link_url: str
    image_url: str
    status: str
    provider: str
    external_id: str
    is_mock: bool
    error: str


class SocialChannelStatus(APIModel):
    channel: str
    mode: str
    configured: bool
    missing: list[str]
