from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class FactOut(APIModel):
    facet: str
    fact_class: str
    value: str = ""
    relation: str = "unknown"
    source: str = ""
    excerpt: str = ""


class AssessmentOut(APIModel):
    lead_id: UUID
    identity: str
    facts: list[FactOut]
    coverage_known: int
    coverage_required: int
    confidence: str
    response_eligible: bool
    outbound_eligible: bool = False
    meeting_eligible: bool
    sales_qualified: bool
    not_a_fit: bool
    next_action: str
    rules_version: str
    evidence_ids: list[UUID] = Field(default_factory=list)


class FactIn(APIModel):
    facet: str
    fact_class: str
    value: str = ""
    relation: str = "unknown"
    source: str = "operator"
    excerpt: str = ""


class SalesQualificationIn(APIModel):
    facts: list[FactIn]


class SalesQualificationOut(APIModel):
    sales_qualified: bool
    opportunity_id: UUID | None = None
    next_action: str


class JourneyControlOut(APIModel):
    journey_id: UUID
    job_id: str
    status: str


class DiscoveryBookingIn(APIModel):
    start_at: str
    end_at: str
    timezone: str = "UTC"


class DiscoveryBookingOut(APIModel):
    status: str
    detail: str = ""
    meeting_id: str = ""
    provider_event_id: str = ""


class NextActionOut(APIModel):
    journey_id: UUID
    job_id: str
    state: str
    next_action: str
    waiting_reason: str = ""
    coverage_known: int = 0
    coverage_required: int = 0
    confidence: str = "none"
    meeting_eligible: bool = False
    sales_qualified: bool = False


class JourneyContinueOut(APIModel):
    journey_id: UUID
    job_id: str
    status: str
    detail: str = ""
