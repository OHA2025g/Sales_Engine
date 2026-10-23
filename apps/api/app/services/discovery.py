import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers import get_llm_provider
from app.core.config import get_settings
from app.models.autonomy import AutopilotSettings
from app.models.crm import ICP, Account, Contact, Lead, Task
from app.models.identity import DomainEvent
from app.models.integrations import ProviderAction
from app.providers.lead_discovery import (
    DISCOVERY_DAILY_LIMIT,
    HARVEST_MAX_ITEMS,
    DiscoveredLead,
    DiscoveryResult,
    get_lead_discovery_provider,
    search_public_profiles,
)
from app.services.assessment import Fact, assess_and_store
from app.services.audit import emit_event, write_audit
from app.services.autopilot_settings import discovered_today, get_or_create_settings
from app.services.crm import add_activity, assign_lead, list_lead_assignees
from app.services.discovery_query import build_discovery_query
from app.services.idempotency import claim_daily_slot
from app.services.provider_metrics import DISCOVERY_CANDIDATES, DISCOVERY_CREATED, DISCOVERY_DUPLICATES
from app.services.provider_ops import (
    begin_action,
    block_action,
    confirm_action,
    fail_action,
    get_health_state,
    is_circuit_open,
    record_provider_result,
)
from app.services.scoring import score_lead


def _normalize_email(email: str) -> str:
    return email.strip().lower()


_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_FREE_OR_SOCIAL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
}


def clean_domain(value: str) -> str:
    text = (value or "").strip().lower().strip("`").strip(".,)")
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.split("/")[0].split("?")[0].split()[0] if text else ""
    if text.startswith("www."):
        text = text[4:]
    if "@" in text:
        text = text.split("@", 1)[1]
    if not _DOMAIN_RE.match(text) or text in _FREE_OR_SOCIAL_DOMAINS:
        return ""
    return text[:255]


def infer_company_domain(candidate: DiscoveredLead, *, db: Session | None = None, tenant_id: UUID | None = None) -> str:
    scraped = clean_domain(candidate.company_website)
    if scraped:
        return scraped
    email_domain = clean_domain(candidate.email.split("@", 1)[1] if "@" in candidate.email else "")
    if email_domain:
        return email_domain
    if not candidate.company_name.strip():
        return ""
    result = get_llm_provider(db, tenant_id).complete(
        (
            f"Company name: {candidate.company_name}\n"
            f"Job title: {candidate.title}\n"
            f"LinkedIn: {candidate.linkedin_url}\n"
            f"Website text from the scrape: {candidate.company_website or 'none'}"
        ),
        system=(
            "Read the scraped profile and identify the company's public website domain. "
            "Reply with only the domain, such as example.com. "
            "If the company is ambiguous or you are not sure, reply UNKNOWN. "
            "Do not explain."
        ),
    )
    if result.is_mock or "NOT_CONFIGURED" in result.text:
        return ""
    first_line = result.text.strip().splitlines()[0] if result.text.strip() else ""
    if first_line.strip().upper() == "UNKNOWN":
        return ""
    match = re.search(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", first_line.lower())
    return clean_domain(match.group(0) if match else first_line)


def _normalize_url(url: str) -> str:
    value = (url or "").strip().lower().rstrip("/")
    return value.split("?")[0]


def default_icp(db: Session, tenant_id: UUID) -> ICP | None:
    rows = db.scalars(select(ICP).where(ICP.tenant_id == tenant_id, ICP.deleted_at.is_(None))).all()
    return next((row for row in rows if row.is_default), rows[0] if rows else None)


def _find_account(db: Session, tenant_id: UUID, company_name: str, email: str) -> Account | None:
    if company_name:
        account = db.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.deleted_at.is_(None),
                func.lower(Account.name) == company_name.lower(),
            )
        )
        if account:
            return account
    domain = email.split("@", 1)[1].lower() if "@" in email else ""
    if domain:
        return db.scalar(
            select(Account).where(Account.tenant_id == tenant_id, Account.domain == domain, Account.deleted_at.is_(None))
        )
    return None


def persist_discovered_lead(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    candidate: DiscoveredLead,
    provider: str = "apify",
) -> tuple[str, Lead | None]:
    email = _normalize_email(candidate.email)
    linkedin = _normalize_url(candidate.linkedin_url)
    if email:
        contact = db.scalar(
            select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email, Contact.deleted_at.is_(None))
        )
        if contact and contact.opt_out:
            return "opt_out", None
        existing = db.scalar(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.email == email, Lead.deleted_at.is_(None))
        )
        if existing:
            return "duplicate_email", existing

    if linkedin:
        url_match = db.scalar(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.deleted_at.is_(None),
                func.lower(Lead.linkedin_url) == linkedin,
            )
        )
        if url_match:
            return "duplicate_linkedin", url_match

    if candidate.provider_ref:
        ref_match = db.scalar(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.deleted_at.is_(None),
                Lead.provider_ref == candidate.provider_ref,
            )
        )
        if ref_match:
            return "duplicate_provider_ref", ref_match

    person_match = db.scalar(
        select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.deleted_at.is_(None),
            func.lower(Lead.first_name) == candidate.first_name.lower(),
            func.lower(Lead.last_name) == candidate.last_name.lower(),
            func.lower(Lead.company_name) == (candidate.company_name or "").lower(),
        )
    )
    if person_match:
        return "duplicate_person", person_match

    account = _find_account(db, tenant_id, candidate.company_name, email)
    domain = infer_company_domain(candidate, db=db, tenant_id=tenant_id)
    if account is None and domain:
        account = db.scalar(
            select(Account).where(Account.tenant_id == tenant_id, Account.domain == domain, Account.deleted_at.is_(None))
        )
    if account is not None and domain and not account.domain:
        account.domain = domain
        if not account.website:
            account.website = f"https://{domain}"
    if account is None and candidate.company_name:
        account = Account(
            tenant_id=tenant_id,
            created_by=actor_id,
            name=candidate.company_name,
            domain=domain,
            website=f"https://{domain}" if domain else "",
            ownership="prospect",
            notes="Created by AI discovery. Review before outreach.",
        )
        db.add(account)
        db.flush()

    contact_id = None
    if email:
        contact = db.scalar(
            select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email, Contact.deleted_at.is_(None))
        )
        if contact is None:
            contact = Contact(
                tenant_id=tenant_id,
                created_by=actor_id,
                account_id=account.id if account else None,
                first_name=candidate.first_name,
                last_name=candidate.last_name,
                email=email,
                title=candidate.title,
                consent_email=False,
                opt_out=False,
                linkedin_url=(linkedin or candidate.linkedin_url)[:255],
                preferred_channel="EMAIL",
                consent_voice=False,
            )
            db.add(contact)
            db.flush()
        contact_id = contact.id

    notes = f"LinkedIn: {candidate.linkedin_url}" if candidate.linkedin_url else ""
    lead = Lead(
        tenant_id=tenant_id,
        created_by=actor_id,
        account_id=account.id if account else None,
        contact_id=contact_id,
        first_name=candidate.first_name,
        last_name=candidate.last_name,
        email=email,
        company_name=candidate.company_name or (account.name if account else ""),
        title=candidate.title,
        source="ai_discovery",
        channel="ai_discovery",
        status="new",
        consent_email=False,
        opt_out=False,
        notes=notes,
        linkedin_url=(linkedin or candidate.linkedin_url)[:255],
        provider_ref=candidate.provider_ref[:200],
        discovery_provider=provider,
        retrieved_at=datetime.now(UTC),
        discovery_confidence=candidate.confidence,
    )
    db.add(lead)
    db.flush()
    score_lead(db, lead, emit=False)
    add_activity(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type="lead",
        entity_id=str(lead.id),
        activity_type="discovery",
        title="Lead discovered",
        body="Source is AI discovery. Consent is false until a human records it.",
        actor_type="ai",
    )
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="lead.created",
        entity_type="lead",
        entity_id=str(lead.id),
    )
    return "created", lead


def _day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def discovery_runs_today(db: Session, tenant_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProviderAction)
            .where(
                ProviderAction.tenant_id == tenant_id,
                ProviderAction.deleted_at.is_(None),
                ProviderAction.action_type == "discovery.search",
                ProviderAction.created_at >= _day_start(),
            )
        )
        or 0
    )


def candidates_today(db: Session, tenant_id: UUID) -> int:
    events = db.scalars(
        select(DomainEvent).where(
            DomainEvent.tenant_id == tenant_id,
            DomainEvent.event_type == "discovery.ran",
            DomainEvent.created_at >= _day_start(),
        )
    ).all()
    total = 0
    for event in events:
        try:
            payload = json.loads(event.payload_json or "{}")
        except (ValueError, TypeError):
            payload = {}
        total += int(payload.get("candidate_count") or 0)
    return total


def _labeled_mock(provider: object) -> bool:
    health = getattr(provider, "health", None)
    if not callable(health):
        return False
    report = health()
    if isinstance(report, dict):
        return bool(report.get("is_mock"))
    return bool(getattr(report, "is_mock", False))


def _discover_people(db: Session, tenant_id: UUID, query, provider) -> DiscoveryResult:
    if _labeled_mock(provider):
        return provider.discover(query)
    settings = get_settings()
    if is_circuit_open(db, tenant_id=tenant_id, provider="apify"):
        fallback = search_public_profiles(
            query,
            token=settings.resolved_apify_token,
            actor_id=settings.channel_search_apify_actor,
        )
        if fallback.candidates:
            return fallback
        health_state = get_health_state(db, tenant_id=tenant_id, provider="apify")
        reason = health_state.last_error_summary if health_state and health_state.last_error_summary else "Blocked by provider"
        return DiscoveryResult(
            candidates=[],
            provider="apify",
            is_mock=False,
            connected=False,
            reason=reason,
            failure_class="RATE_LIMIT",
        )
    result = provider.discover(query)
    if result.failure_class == "RATE_LIMIT" and not result.candidates:
        fallback = search_public_profiles(
            query,
            token=settings.resolved_apify_token,
            actor_id=settings.channel_search_apify_actor,
        )
        if fallback.candidates:
            return fallback
    return result


def remaining_candidate_budget(db: Session, settings: AutopilotSettings) -> int:
    per_run = HARVEST_MAX_ITEMS
    per_day = DISCOVERY_DAILY_LIMIT
    leftover = max(per_day - candidates_today(db, settings.tenant_id), 0)
    leftover_leads = max(per_day - discovered_today(db, settings.tenant_id), 0)
    return max(0, min(per_run, leftover, leftover_leads))


def _assign_discovered(db: Session, *, tenant_id: UUID, actor_id: UUID, lead: Lead, correlation_id: str) -> str:
    people = list_lead_assignees(db, tenant_id)
    if not people:
        return ""
    counts: dict[UUID, int] = {}
    for person in people:
        owner_id = person["id"]
        if not isinstance(owner_id, UUID):
            continue
        counts[owner_id] = int(
            db.scalar(
                select(func.count()).select_from(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.owner_id == owner_id,
                    Lead.deleted_at.is_(None),
                )
            )
            or 0
        )
    ranked = [person for person in people if isinstance(person["id"], UUID)]
    if not ranked:
        return ""
    chosen = min(ranked, key=lambda person: (counts.get(person["id"], 0), str(person["name"]).casefold()))
    owner_id = chosen["id"]
    if isinstance(owner_id, UUID):
        try:
            assign_lead(db, tenant_id=tenant_id, actor_id=actor_id, lead=lead, owner_id=owner_id, correlation_id=correlation_id)
        except ValueError:
            return ""
        return str(chosen["name"])
    return ""


def _next_action_text(decision: dict, *, has_email: bool) -> str:
    if decision.get("not_a_fit"):
        return "Stop. Verified facts show this person is not a fit."
    if decision.get("identity") == "suppressed":
        return "Do not contact. The person is suppressed."
    if not has_email:
        return "Complete the missing email before any outreach."
    if not decision.get("response_eligible"):
        return "Record channel permission before any email. Discovery did not create consent or buying intent."
    return "Wait. Unknown facts stay unknown."


def _remember_next_action(db: Session, *, tenant_id: UUID, actor_id: UUID, lead: Lead, title: str) -> None:
    existing = db.scalar(
        select(Task).where(
            Task.tenant_id == tenant_id,
            Task.entity_type == "lead",
            Task.entity_id == str(lead.id),
            Task.title == title[:200],
            Task.status == "open",
            Task.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return
    db.add(
        Task(
            tenant_id=tenant_id,
            created_by=actor_id,
            title=title[:200],
            description="Created from discovery. This is not a send and it does not grant consent.",
            status="open",
            source="ai",
            owner_id=lead.owner_id,
            entity_type="lead",
            entity_id=str(lead.id),
        )
    )


def _place_discovered(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    lead: Lead,
    candidate: DiscoveredLead,
    provider: str,
    correlation_id: str,
) -> dict:
    excerpt = " ".join(
        part
        for part in (candidate.title.strip(), provider, candidate.provider_ref, candidate.source_url or candidate.linkedin_url)
        if part
    ).strip()
    overrides: list[Fact] = []
    if candidate.title.strip():
        overrides.append(Fact("persona", "inferred", candidate.title.strip(), "present", provider, excerpt[:500]))
    decision = assess_and_store(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        lead=lead,
        overrides=overrides,
        correlation_id=correlation_id,
    )
    owner_name = ""
    if decision.get("identity") != "suppressed":
        owner_name = _assign_discovered(db, tenant_id=tenant_id, actor_id=actor_id, lead=lead, correlation_id=correlation_id)
    action = _next_action_text(decision, has_email=bool(lead.email))
    if not decision.get("response_eligible"):
        _remember_next_action(db, tenant_id=tenant_id, actor_id=actor_id, lead=lead, title=action)
    return {
        "lead_id": str(lead.id),
        "name": f"{lead.first_name} {lead.last_name}".strip(),
        "outcome": "created",
        "coverage_known": int(decision.get("coverage_known") or 0),
        "coverage_required": int(decision.get("coverage_required") or 5),
        "confidence": str(decision.get("confidence") or "none"),
        "response_eligible": bool(decision.get("response_eligible")),
        "next_action": action,
        "explanation": (
            f"Coverage {decision.get('coverage_known')}/{decision.get('coverage_required')}. "
            f"Confidence {decision.get('confidence')}. "
            + "; ".join(str(item) for item in decision.get("reasons") or [])
            + ". Unknown facts stay unknown. No buying intent was added."
        ),
        "owner_name": owner_name,
        "provider_ref": candidate.provider_ref,
    }


def discovery_board(db: Session, tenant_id: UUID) -> dict:
    event = db.scalar(
        select(DomainEvent)
        .where(DomainEvent.tenant_id == tenant_id, DomainEvent.event_type == "discovery.ran")
        .order_by(DomainEvent.created_at.desc())
    )
    if event is None:
        return {"status": "idle", "reason": "", "created": 0, "failures": "", "prospects": []}
    try:
        payload = json.loads(event.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    failure = str(payload.get("failure_class") or "")
    return {
        "status": "failed" if failure else "recorded",
        "reason": str(payload.get("reason") or ""),
        "created": int(payload.get("created") or 0),
        "failures": failure,
        "prospects": payload.get("prospects") if isinstance(payload.get("prospects"), list) else [],
    }


def run_discovery(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    profile_urls: list[str] | None = None,
    search_query: str = "",
    correlation_id: str = "",
    provider=None,
    enforce_budget: bool = True,
) -> dict:
    icp = default_icp(db, tenant_id)
    settings = get_or_create_settings(db, tenant_id=tenant_id, actor_id=actor_id)
    env = get_settings()
    empty = {
        "created": 0,
        "skipped": {},
        "lead_ids": [],
        "provider": "skipped",
        "is_mock": True,
        "connected": False,
        "reason": "",
        "candidate_count": 0,
        "icp_name": icp.name if icp else "",
        "prospects": [],
        "failure_class": "",
    }
    if enforce_budget and settings.max_discovery_runs_per_day > 0 and discovery_runs_today(db, tenant_id) >= settings.max_discovery_runs_per_day:
        empty["reason"] = "Daily discovery run cap reached"
        return empty
    if enforce_budget and not claim_daily_slot(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        kind="discovery",
        limit=settings.max_discovery_runs_per_day,
    ):
        empty["reason"] = "Daily discovery run cap reached"
        return empty
    if enforce_budget and discovered_today(db, tenant_id) >= DISCOVERY_DAILY_LIMIT:
        empty["reason"] = "Daily discovered-lead cap reached"
        return empty
    max_items = remaining_candidate_budget(db, settings) if enforce_budget else min(env.apify_max_items, HARVEST_MAX_ITEMS)
    max_items = min(max_items, HARVEST_MAX_ITEMS)
    if enforce_budget and max_items <= 0:
        empty["reason"] = "Daily candidate cap reached"
        return empty
    query = build_discovery_query(
        icp,
        search_query=search_query,
        profile_urls=profile_urls,
        max_items=max_items,
        process_token=env.apify_linkedin_process_token,
    )
    used = provider or get_lead_discovery_provider(db, tenant_id)
    health = used.health() if hasattr(used, "health") else {"provider": "discovery"}
    action = begin_action(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_type="discovery.search",
        idempotency_key=f"discovery.search:{tenant_id}:{uuid4()}",
        provider=str(health.get("provider") if isinstance(health, dict) else "discovery"),
        request_summary=f"max_items={query.max_items}",
    )
    result = _discover_people(db, tenant_id, query, used)
    action.provider = result.provider
    created = 0
    skipped: dict[str, int] = {}
    lead_ids: list[str] = []
    prospects: list[dict] = []
    for candidate in result.candidates[:max_items]:
        reason, lead = persist_discovered_lead(
            db, tenant_id=tenant_id, actor_id=actor_id, candidate=candidate, provider=result.provider
        )
        if reason == "created" and lead is not None:
            created += 1
            lead_ids.append(str(lead.id))
            prospects.append(
                _place_discovered(
                    db,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    lead=lead,
                    candidate=candidate,
                    provider=result.provider,
                    correlation_id=correlation_id,
                )
            )
        else:
            skipped[reason] = skipped.get(reason, 0) + 1
            if lead is not None:
                prospects.append(
                    {
                        "lead_id": str(lead.id),
                        "name": f"{lead.first_name} {lead.last_name}".strip(),
                        "outcome": reason,
                        "coverage_known": 0,
                        "coverage_required": 5,
                        "confidence": "none",
                        "response_eligible": False,
                        "next_action": "Already on file. No second person was created.",
                        "explanation": f"Matched an existing person by {reason.replace('_', ' ')}.",
                        "owner_name": "",
                        "provider_ref": candidate.provider_ref,
                    }
                )
    prospects.sort(key=lambda item: (-int(item["coverage_known"]), str(item["name"])))
    DISCOVERY_CANDIDATES.labels(provider=result.provider[:40]).inc(len(result.candidates))
    DISCOVERY_CREATED.labels(provider=result.provider[:40]).inc(created)
    DISCOVERY_DUPLICATES.labels(provider=result.provider[:40]).inc(sum(skipped.values()))
    record_provider_result(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        provider=result.provider,
        action="discovery.search",
        ok=result.failure_class == "" and (result.connected or result.is_mock),
        failure_class=result.failure_class,
        error=result.reason,
    )
    if result.failure_class:
        fail_action(
            action,
            failure_class=result.failure_class,
            error=result.reason,
            retryable=result.failure_class in {"TRANSIENT", "RATE_LIMIT"},
        )
    elif not result.connected and not result.is_mock:
        block_action(action, reason=result.reason or "Discovery provider unavailable")
    else:
        confirm_action(action, provider=result.provider, external_id="", response_summary=f"created={created}")
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="discovery.run",
        entity_type="lead",
        after={
            "created": created,
            "skipped": skipped,
            "provider": result.provider,
            "is_mock": result.is_mock,
        },
        correlation_id=correlation_id,
        actor_type="ai",
    )
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="discovery.ran",
        entity_type="icp",
        entity_id=str(icp.id) if icp else "",
        payload={
            "candidate_count": len(result.candidates),
            "created": created,
            "provider": result.provider,
            "reason": result.reason,
            "failure_class": result.failure_class,
            "prospects": prospects,
        },
    )
    return {
        "created": created,
        "skipped": skipped,
        "lead_ids": lead_ids,
        "prospects": prospects,
        "provider": result.provider,
        "is_mock": result.is_mock,
        "connected": result.connected,
        "reason": result.reason,
        "failure_class": result.failure_class,
        "candidate_count": len(result.candidates),
        "icp_name": icp.name if icp else "",
    }
