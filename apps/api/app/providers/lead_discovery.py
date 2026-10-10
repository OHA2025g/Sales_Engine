from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.provider_ops import classify_http
from app.services.provider_resolve import resolve_channel


def normalize_actor_id(actor_id: str) -> str:
    return actor_id.strip().replace("/", "~")


SEARCH_EMAIL_MODE = "Full + email search"
PROFILE_EMAIL_MODE = "Profile details + email search ($10 per 1k)"
HARVEST_MAX_ITEMS = 30
DISCOVERY_DAILY_LIMIT = 50
HARVEST_LIMIT_MARKERS = ("run limit", "free user", "upgrade to a paid")


def _text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("email") or value.get("value") or value.get("address")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
            if isinstance(first, dict):
                nested = first.get("email") or first.get("value") or first.get("address") or first.get("id")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return ""


@dataclass(frozen=True)
class DiscoveredLead:
    first_name: str
    last_name: str
    email: str
    title: str
    company_name: str
    linkedin_url: str
    raw_keys: tuple[str, ...] = field(default_factory=tuple)
    provider_ref: str = ""
    confidence: int = 0
    source_url: str = ""
    company_website: str = ""


@dataclass(frozen=True)
class DiscoveryQuery:
    industries: str = ""
    geographies: str = ""
    search_query: str = ""
    profile_urls: tuple[str, ...] = ()
    max_items: int = 10
    process_token: str = ""
    job_titles: tuple[str, ...] = ()
    seniorities: tuple[str, ...] = ()
    target_companies: tuple[str, ...] = ()
    keywords: str = ""
    min_employees: int | None = None
    max_employees: int | None = None
    industry_ids: tuple[str, ...] = ()
    seniority_ids: tuple[str, ...] = ()
    company_headcount: tuple[str, ...] = ()
    function_ids: tuple[str, ...] = ()
    location_names: tuple[str, ...] = ()
    actor_search_query: str = ""

    @property
    def has_icp(self) -> bool:
        return bool(
            self.industries.strip()
            or self.geographies.strip()
            or self.search_query.strip()
            or self.actor_search_query.strip()
            or self.profile_urls
            or self.job_titles
            or self.target_companies
            or self.keywords.strip()
            or self.location_names
        )


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[DiscoveredLead]
    provider: str
    is_mock: bool
    connected: bool
    reason: str = ""
    failure_class: str = ""
    status_code: int = 0


def harvest_limit_reached(message: str) -> bool:
    text = (message or "").lower()
    return any(marker in text for marker in HARVEST_LIMIT_MARKERS)


def empty_dataset_reason(message: str = "", row_error: str = "") -> str:
    if harvest_limit_reached(message) or harvest_limit_reached(row_error):
        return (
            "HarvestAPI blocked this Apify free-plan run. "
            "Upgrade the Apify account to a paid plan, then run discovery again. "
            "No invented people were stored."
        )
    detail = (row_error or message or "").strip()
    if detail:
        return f"Apify returned 0 profiles. {detail}"
    return (
        "Apify returned 0 profiles for this ICP. "
        "The LinkedIn filters may be too tight, or the vendor returned an empty dataset."
    )


def _status_message(payload: dict[str, Any]) -> str:
    return str(payload.get("statusMessage") or payload.get("status_message") or "").strip()


def _row_error(rows: list[Any]) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("error", "errorDescription", "errorCode", "message"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


class LeadDiscoveryProvider(Protocol):
    def health(self) -> dict[str, Any]: ...

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult: ...


class MockLeadDiscoveryProvider:
    def health(self) -> dict[str, Any]:
        return {
            "provider": "mock-discovery",
            "is_mock": True,
            "connected": False,
            "reason": "DISCOVERY_PROVIDER is mock. Discovery will not invent people.",
        }

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        if not query.has_icp:
            return DiscoveryResult(
                candidates=[],
                provider="mock-discovery",
                is_mock=True,
                connected=False,
                reason="No ICP or profile URLs. Labeled mock returns no people.",
            )
        return DiscoveryResult(
            candidates=[],
            provider="mock-discovery",
            is_mock=True,
            connected=False,
            reason="Labeled mock. No live vendor. No invented prospects.",
        )


class NotConfiguredDiscoveryProvider:
    def health(self) -> dict[str, Any]:
        return {
            "provider": "apify",
            "is_mock": False,
            "connected": False,
            "reason": "DISCOVERY_PROVIDER is apify but APIFY_API_TOKEN or APIFY_ACTOR_ID is missing.",
        }

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        _ = query
        return DiscoveryResult(
            candidates=[],
            provider="apify",
            is_mock=False,
            connected=False,
            reason="Apify is not configured. No invented people.",
            failure_class="CONFIGURATION",
        )


class ApifyLeadDiscoveryProvider:
    def __init__(
        self,
        *,
        token: str,
        actor_id: str,
        max_items: int,
        process_token: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._actor_id = normalize_actor_id(actor_id)
        self._max_items = max(1, min(max_items, HARVEST_MAX_ITEMS))
        self._process_token = process_token
        self._client = client

    def health(self) -> dict[str, Any]:
        return {
            "provider": "apify",
            "is_mock": False,
            "connected": True,
            "actor_id": self._actor_id.replace("~", "/"),
            "reason": "Apify token and actor are configured. People are persisted only from dataset items.",
        }

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=90.0)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _actor_input(self, query: DiscoveryQuery) -> dict[str, Any]:
        max_items = min(query.max_items or self._max_items, self._max_items)
        actor = self._actor_id.lower()
        payload: dict[str, Any] = {}
        if "profile-search" in actor:
            payload = {
                "maxItems": max_items,
                "profileScraperMode": SEARCH_EMAIL_MODE,
                "startPage": 1,
                "takePages": 1,
            }
            search = query.actor_search_query.strip()
            if not search and not query.job_titles:
                search = query.search_query or ", ".join(
                    part for part in (query.keywords, query.industries, query.geographies) if part
                )
            if search:
                payload["searchQuery"] = search
            locations = list(query.location_names) or [
                item.strip() for item in query.geographies.split(",") if item.strip()
            ]
            if locations:
                payload["locations"] = locations
            if query.job_titles:
                payload["currentJobTitles"] = list(query.job_titles)[:20]
            if query.seniority_ids:
                payload["seniorityLevelIds"] = list(query.seniority_ids)
            if query.industry_ids:
                payload["industryIds"] = list(query.industry_ids)
            if query.function_ids:
                payload["functionIds"] = list(query.function_ids)
            if query.company_headcount:
                payload["companyHeadcount"] = list(query.company_headcount)
            if query.target_companies:
                payload["currentCompanies"] = list(query.target_companies)
        else:
            urls = [url.strip() for url in query.profile_urls if url.strip()]
            payload = {
                "profileScraperMode": PROFILE_EMAIL_MODE,
                "queries": urls,
            }
        if query.process_token or self._process_token:
            payload["token"] = query.process_token or self._process_token
        return payload

    def _failed(self, *, reason: str, status_code: int = 0, timeout: bool = False) -> DiscoveryResult:
        return DiscoveryResult(
            candidates=[],
            provider="apify",
            is_mock=False,
            connected=False,
            reason=reason,
            failure_class=classify_http(status_code, timeout=timeout) or "TRANSIENT",
            status_code=status_code,
        )

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        actor = self._actor_id.lower()
        urls = [url.strip() for url in query.profile_urls if url.strip()]
        if "profile-search" not in actor and not urls:
            return DiscoveryResult(
                candidates=[],
                provider="apify",
                is_mock=False,
                connected=True,
                reason=(
                    "Configured actor scrapes LinkedIn profile URLs only. "
                    "Pass profile URLs or set APIFY_ACTOR_ID to a search actor such as harvestapi/linkedin-profile-search."
                ),
                failure_class="CONFIGURATION",
            )
        owns_client = self._client is None
        client = self._http()
        try:
            start = client.post(
                f"https://api.apify.com/v2/acts/{self._actor_id}/runs",
                headers=self._headers(),
                json=self._actor_input(query),
                params={"waitForFinish": 60},
            )
            if start.status_code >= 400:
                return self._failed(
                    reason=f"Apify run refused ({start.status_code}). Falling back without inventing people.",
                    status_code=start.status_code,
                )
            body = start.json().get("data") or {}
            run_id = body.get("id")
            dataset_id = body.get("defaultDatasetId")
            status = body.get("status")
            message = _status_message(body)
            if status not in {"SUCCEEDED", "READY"} or not dataset_id:
                wait = client.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers=self._headers(),
                    params={"waitForFinish": 60},
                )
                if wait.status_code >= 400:
                    return self._failed(reason="Apify wait failed. No invented people.", status_code=wait.status_code)
                waited = wait.json().get("data") or {}
                dataset_id = waited.get("defaultDatasetId")
                status = waited.get("status")
                message = _status_message(waited) or message
            if status != "SUCCEEDED" or not dataset_id:
                ended = f"Apify run ended {status or 'unknown'}."
                detail = f" {message}" if message else " Dataset empty."
                return self._failed(reason=ended + detail)
            items = client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                headers=self._headers(),
                params={"limit": self._max_items},
            )
            if items.status_code >= 400:
                return self._failed(reason="Apify dataset read failed.", status_code=items.status_code)
            rows = items.json()
            if not isinstance(rows, list):
                return DiscoveryResult(
                    candidates=[],
                    provider="apify",
                    is_mock=False,
                    connected=True,
                    reason="Apify dataset was not a list.",
                )
            mapped = map_dataset_items(rows)[: self._max_items]
            if mapped:
                return DiscoveryResult(
                    candidates=mapped,
                    provider="apify",
                    is_mock=False,
                    connected=True,
                    reason="",
                )
            if not message and run_id:
                detail = client.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers=self._headers(),
                )
                if detail.status_code < 400:
                    payload = detail.json()
                    data = payload.get("data") if isinstance(payload, dict) else None
                    if isinstance(data, dict):
                        message = _status_message(data) or message
            row_error = _row_error(rows)
            limited = harvest_limit_reached(message) or harvest_limit_reached(row_error)
            return DiscoveryResult(
                candidates=[],
                provider="apify",
                is_mock=False,
                connected=not limited,
                reason=empty_dataset_reason(message, row_error),
                failure_class="RATE_LIMIT" if limited else "",
            )
        except httpx.TimeoutException:
            return self._failed(reason="Apify timeout. No invented people.", timeout=True)
        except httpx.HTTPError:
            return self._failed(reason="Apify network error. No invented people.", timeout=True)
        finally:
            if owns_client:
                client.close()


def _current_positions(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("currentPosition", "currentPositions"):
        value = row.get(key)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _website_value(value: str) -> str:
    text = value.strip()
    if text and "linkedin.com" not in text.lower():
        return text
    return ""


def _company_website(row: dict[str, Any]) -> str:
    sites = row.get("companyWebsites")
    if isinstance(sites, list):
        for site in sites:
            if isinstance(site, str):
                found = _website_value(site)
            elif isinstance(site, dict):
                found = _website_value(_text(site, "url", "domain"))
            else:
                found = ""
            if found:
                return found
    for key in ("companyWebsite", "website", "companyUrl", "websiteUrl", "company_website"):
        found = _website_value(_text(row, key))
        if found:
            return found
    company = row.get("company")
    if isinstance(company, dict):
        found = _website_value(_text(company, "website", "url", "companyWebsite"))
        if found:
            return found
    for position in _current_positions(row):
        found = _website_value(_text(position, "companyWebsite", "website", "companyUrl"))
        if not found and isinstance(position.get("company"), dict):
            found = _website_value(_text(position["company"], "website", "url", "companyWebsite"))
        if found:
            return found
    return ""


def map_dataset_items(rows: list[Any]) -> list[DiscoveredLead]:
    mapped: list[DiscoveredLead] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        first = _text(row, "firstName", "first_name", "firstname")
        last = _text(row, "lastName", "last_name", "lastname")
        if not first and not last:
            full = _text(row, "fullName", "name", "full_name")
            parts = full.split(None, 1)
            if parts:
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""
        email = _text(row, "email", "emails", "workEmail", "verifiedEmail", "primaryEmail")
        title = _text(row, "title", "jobTitle", "headline", "occupation")
        company = _text(row, "companyName", "company", "company_name", "currentCompany")
        positions = _current_positions(row)
        if positions:
            company = company or _text(positions[0], "companyName", "company")
            title = _text(positions[0], "position", "title") or title
        linkedin = _text(row, "linkedinUrl", "linkedin_url", "profileUrl", "url", "profile_url", "linkedinProfileUrl")
        website = _company_website(row)
        provider_ref = _text(row, "id", "profileId", "linkedinId", "publicIdentifier", "urn")
        if not first or not last:
            continue
        mapped.append(
            DiscoveredLead(
                first_name=first[:80],
                last_name=last[:80],
                email=email[:255],
                title=title[:120],
                company_name=company[:200],
                linkedin_url=linkedin[:255],
                raw_keys=tuple(sorted(row.keys())),
                provider_ref=provider_ref[:200],
                confidence=70 if email or linkedin else 40,
                source_url=linkedin[:255],
                company_website=website[:255],
            )
        )
    return mapped


def get_lead_discovery_provider(db: Session | None = None, tenant_id: UUID | None = None) -> LeadDiscoveryProvider:
    settings = get_settings()
    if db is not None and tenant_id is not None:
        resolved = resolve_channel(db, tenant_id, "discovery")
        if resolved.mode == "LIVE":
            token = resolved.secrets.get("access_token") or ""
            actor_id = resolved.secrets.get("actor_id") or settings.apify_actor_id
            if token and actor_id:
                return ApifyLeadDiscoveryProvider(
                    token=token,
                    actor_id=actor_id,
                    max_items=settings.apify_max_items,
                    process_token=resolved.secrets.get("process_token") or settings.apify_linkedin_process_token,
                )
            return NotConfiguredDiscoveryProvider()
        if resolved.mode == "MOCK":
            return MockLeadDiscoveryProvider()
        return NotConfiguredDiscoveryProvider()
    mode = (settings.discovery_provider or "mock").strip().lower()
    if mode == "apify":
        if settings.apify_configured:
            return ApifyLeadDiscoveryProvider(
                token=settings.resolved_apify_token,
                actor_id=settings.apify_actor_id,
                max_items=settings.apify_max_items,
                process_token=settings.apify_linkedin_process_token,
            )
        return NotConfiguredDiscoveryProvider()
    return MockLeadDiscoveryProvider()
