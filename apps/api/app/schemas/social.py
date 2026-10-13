import json
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.providers.social import public_post_url
from app.schemas.common import APIModel


class SocialDraftIn(APIModel):
    channel: str


class SocialDraftOut(APIModel):
    channel: str
    body: str
    link_url: str


class SocialBriefIn(APIModel):
    headline: str = Field(min_length=1, max_length=200)
    keyword: str = Field(min_length=1, max_length=200)
    ranking_parameter: str = Field(min_length=1, max_length=500)
    snippet: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1, max_length=300)


class SocialComposeOut(APIModel):
    body: str


class SocialCreativeIn(SocialBriefIn):
    body: str = Field(min_length=1, max_length=3000)


class SocialCreativeOut(APIModel):
    url: str
    note: str = ""
    kind: str = "image"


class SocialSubmissionIn(SocialCreativeIn):
    image_url: str = ""
    video_url: str = ""
    form_key_id: UUID | None = None
    channels: list[str] = Field(min_length=1, max_length=4)


class SocialSubmissionOut(APIModel):
    approval_id: UUID
    posts: list["SocialPostOut"] = Field(default_factory=list)


class SocialExtraLink(APIModel):
    label: str = Field(default="", max_length=80)
    url: str = Field(default="", max_length=500)


class SocialPostIn(APIModel):
    channel: str
    body: str = Field(min_length=1, max_length=3000)
    link_url: str = ""
    image_url: str = ""
    form_key_id: UUID | None = None
    extra_links: list[SocialExtraLink] = Field(default_factory=list, max_length=8)


class SocialPostUpdate(APIModel):
    body: str = Field(min_length=1, max_length=3000)
    link_url: str = ""
    image_url: str = ""
    form_key_id: UUID | None = None
    extra_links: list[SocialExtraLink] = Field(default_factory=list, max_length=8)


class SocialPostOut(APIModel):
    id: UUID
    channel: str
    body: str
    headline: str = ""
    keyword: str = ""
    ranking_parameter: str = ""
    snippet: str = ""
    context: str = ""
    link_url: str
    image_url: str
    video_url: str = ""
    extra_links: list[SocialExtraLink] = Field(default_factory=list)
    form_key_id: UUID | None = None
    form_name: str = ""
    status: str
    provider: str
    external_id: str
    permalink: str = ""
    is_mock: bool
    error: str

    @field_validator("extra_links", mode="before")
    @classmethod
    def read_extra_links(cls, value: Any) -> Any:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return value

    @model_validator(mode="wrap")
    @classmethod
    def attach_permalink(cls, value: Any, handler):
        row = handler(value)
        if not row.permalink:
            row.permalink = public_post_url(row.channel, row.external_id)
        return row


class SocialChannelStatus(APIModel):
    channel: str
    mode: str
    configured: bool
    missing: list[str]


SocialSubmissionOut.model_rebuild()
