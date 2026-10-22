from pydantic import Field

from app.schemas.common import APIModel


class SiteSignalOut(APIModel):
    code: str
    label: str
    description: str
    category: str
    value_type: str
    cost_note: str
    collectable: bool
    status: str
    accounts: int


class SiteObservationOut(APIModel):
    id: str
    account_id: str
    account_name: str
    signal_code: str
    label: str
    value_num: int | None
    value_text: str
    confidence: int
    evidence_url: str
    opening: str


class SiteProfileRunOut(APIModel):
    id: str = ""
    status: str = ""
    accounts_read: int = 0
    observations: int = 0
    skipped: int = 0
    note: str = ""


class SiteSignalBoardOut(APIModel):
    signals: list[SiteSignalOut]
    recent: list[SiteObservationOut]
    last_run: SiteProfileRunOut | None = None


class SiteSignalStatusIn(APIModel):
    codes: list[str] = Field(min_length=1, max_length=23)
    status: str


class SiteProfileIn(APIModel):
    limit: int = Field(default=10, ge=1, le=25)
    force: bool = False


class CohortIn(APIModel):
    require: list[str] = Field(default_factory=list, max_length=23)
    exclude: list[str] = Field(default_factory=list, max_length=23)


class CohortSignalOut(APIModel):
    code: str
    label: str
    value_text: str
    value_num: int | None


class CohortAccountOut(APIModel):
    account_id: str
    name: str
    website: str
    opening: str
    signals: list[CohortSignalOut]


class CohortOut(APIModel):
    count: int
    accounts: list[CohortAccountOut]
