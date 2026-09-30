from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class SellerProfileIn(APIModel):
    company_name: str = Field(default="", max_length=200)
    summary: str = ""
    audience: str = ""
    website: str = ""
    proof: str = ""
    capture_url: str = ""


class SellerProfileOut(SellerProfileIn):
    id: UUID | None = None


class ContentProductIn(APIModel):
    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    kind: str = "subscription"
    list_price: Decimal = Decimal("0")
    currency: str = "INR"


class ContentProductOut(APIModel):
    id: UUID
    sku: str
    name: str
    kind: str
    list_price: Decimal
    currency: str
    description: str


class ContentProductPatch(APIModel):
    description: str = Field(min_length=1)


class GenerateContentIn(APIModel):
    product_id: UUID
    ad_channel: str = "linkedin"
    brief: str = Field(default="", max_length=2000)


class ContentDraftPatch(APIModel):
    headline: str = ""
    body: str = ""
    cta: str = ""
    image_url: str = ""


class ContentDraftOut(APIModel):
    id: UUID
    product_id: UUID | None
    channel: str
    kind: str
    headline: str
    body: str
    cta: str
    brief: str
    destination_url: str
    image_url: str
    status: str
    provider: str
    external_id: str
    social_post_id: UUID | None
    campaign_id: UUID | None
    is_mock: bool
    error: str
