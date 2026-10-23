from pydantic import Field

from app.schemas.common import APIModel


class DiscoveryRunIn(APIModel):
    profile_urls: list[str] = Field(default_factory=list)
    search_query: str = ""


class DiscoveryProspectOut(APIModel):
    lead_id: str
    name: str = ""
    outcome: str = ""
    coverage_known: int = 0
    coverage_required: int = 5
    confidence: str = "none"
    response_eligible: bool = False
    next_action: str = ""
    explanation: str = ""
    owner_name: str = ""
    provider_ref: str = ""


class DiscoveryRunOut(APIModel):
    created: int
    skipped: dict[str, int]
    lead_ids: list[str]
    prospects: list[DiscoveryProspectOut] = Field(default_factory=list)
    provider: str
    is_mock: bool
    connected: bool
    reason: str
    failure_class: str = ""
    candidate_count: int
    icp_name: str


class DiscoveryHealthOut(APIModel):
    provider: str
    is_mock: bool
    connected: bool
    reason: str
    actor_id: str = ""
