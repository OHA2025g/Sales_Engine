"""Confirm website signals, read public pages, and query a cohort.

This does not start discovery, enroll a sequence, or send mail. It only
stores facts a person asked for and the sentence those facts support.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import Account
from app.models.site_signals import SiteObservation, SiteProfileCheck, SiteProfileRun, SiteSignalChoice
from app.services.audit import write_audit
from app.services.site_profiler import RawObservation, analyze_pages
from app.services.site_signal_catalog import (
    BY_CODE,
    CATALOG,
    DECISIONS,
    OPENING_ORDER,
    STALE_DAYS,
    opening_line,
)
from app.services.snippet_expand import SnippetUnavailable, assert_public_url

PAGE_LIMIT = 400_000
CANDIDATE_LIMIT = 200
TEAM_PATHS = ("/team", "/about", "/about-us", "/our-team", "/staff")
CAREERS_PATHS = ("/careers", "/jobs", "/join-us")
CONTACT_PATHS = ("/contact", "/contact-us")


class SiteSignalError(ValueError):
    """The request names a signal or a decision the catalog does not have."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _positive(value_num: int | None, value_text: str) -> bool:
    if value_num is None:
        return bool(value_text.strip())
    return value_num != 0


def ensure_choices(db: Session, tenant_id: UUID, actor_id: UUID | None) -> list[SiteSignalChoice]:
    rows = list(
        db.scalars(
            select(SiteSignalChoice).where(
                SiteSignalChoice.tenant_id == tenant_id,
                SiteSignalChoice.deleted_at.is_(None),
            )
        ).all()
    )
    known = {row.code: row for row in rows}
    for spec in CATALOG:
        if spec.code in known:
            continue
        row = SiteSignalChoice(
            tenant_id=tenant_id,
            created_by=actor_id,
            updated_by=actor_id,
            code=spec.code,
            status="proposed",
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def set_signal_status(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    codes: list[str],
    status: str,
) -> list[SiteSignalChoice]:
    if status not in DECISIONS:
        raise SiteSignalError("Choose confirmed, skipped, or rejected.")
    unknown = [code for code in codes if code not in BY_CODE]
    if unknown:
        raise SiteSignalError(f"Unknown signal: {unknown[0]}.")
    if not codes:
        raise SiteSignalError("Choose at least one signal.")
    rows = ensure_choices(db, tenant_id, actor_id)
    chosen = [row for row in rows if row.code in set(codes)]
    before = {row.code: row.status for row in chosen}
    for row in chosen:
        row.status = status
        row.updated_by = actor_id
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="site_signal.status",
        entity_type="site_signal_choice",
        entity_id=",".join(codes),
        before=before,
        after={code: status for code in codes},
    )
    db.flush()
    return chosen


def _latest(db: Session, tenant_id: UUID) -> dict[tuple[UUID, str], SiteObservation]:
    rows = db.scalars(
        select(SiteObservation)
        .where(SiteObservation.tenant_id == tenant_id, SiteObservation.deleted_at.is_(None))
        .order_by(SiteObservation.observed_at.desc(), SiteObservation.created_at.desc())
    ).all()
    latest: dict[tuple[UUID, str], SiteObservation] = {}
    for row in rows:
        key = (row.account_id, row.signal_code)
        if key not in latest:
            latest[key] = row
    return latest


def catalog_view(db: Session, tenant_id: UUID, actor_id: UUID | None) -> dict:
    choices = ensure_choices(db, tenant_id, actor_id)
    by_code = {row.code: row.status for row in choices}
    latest = _latest(db, tenant_id)
    counts: dict[str, int] = {}
    for (_account_id, code), row in latest.items():
        if _positive(row.value_num, row.value_text):
            counts[code] = counts.get(code, 0) + 1
    signals = [
        {
            "code": spec.code,
            "label": spec.label,
            "description": spec.description,
            "category": spec.category,
            "value_type": spec.value_type,
            "cost_note": spec.cost_note,
            "collectable": spec.collectable,
            "status": by_code.get(spec.code, "proposed"),
            "accounts": counts.get(spec.code, 0),
        }
        for spec in CATALOG
    ]
    recent_rows = db.scalars(
        select(SiteObservation)
        .where(SiteObservation.tenant_id == tenant_id, SiteObservation.deleted_at.is_(None))
        .order_by(SiteObservation.observed_at.desc())
        .limit(12)
    ).all()
    accounts = {
        row.id: row
        for row in db.scalars(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.id.in_({item.account_id for item in recent_rows} or {UUID(int=0)}),
                Account.deleted_at.is_(None),
            )
        ).all()
    }
    recent = [_present_observation(row, accounts.get(row.account_id)) for row in recent_rows]
    last = db.scalar(
        select(SiteProfileRun)
        .where(SiteProfileRun.tenant_id == tenant_id, SiteProfileRun.deleted_at.is_(None))
        .order_by(SiteProfileRun.created_at.desc())
    )
    return {"signals": signals, "recent": recent, "last_run": _present_run(last)}


def _present_run(row: SiteProfileRun | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "status": row.status,
        "accounts_read": row.accounts_read,
        "observations": row.observations,
        "skipped": row.skipped,
        "note": row.note,
    }


def _present_observation(row: SiteObservation, account: Account | None) -> dict:
    spec = BY_CODE.get(row.signal_code)
    return {
        "id": str(row.id),
        "account_id": str(row.account_id),
        "account_name": account.name if account else "",
        "signal_code": row.signal_code,
        "label": spec.label if spec else row.signal_code,
        "value_num": row.value_num,
        "value_text": row.value_text,
        "confidence": row.confidence,
        "evidence_url": row.evidence_url,
        "opening": opening_line(row.signal_code, row.value_text, row.value_num) if _positive(row.value_num, row.value_text) else "",
    }


def cohort(db: Session, tenant_id: UUID, require: list[str], exclude: list[str]) -> dict:
    unknown = [code for code in [*require, *exclude] if code not in BY_CODE]
    if unknown:
        raise SiteSignalError(f"Unknown signal: {unknown[0]}.")
    if not require and not exclude:
        raise SiteSignalError("Choose at least one signal the cohort must have or must not have.")
    latest = _latest(db, tenant_id)
    by_account: dict[UUID, dict[str, SiteObservation]] = {}
    for (account_id, code), row in latest.items():
        if _positive(row.value_num, row.value_text):
            by_account.setdefault(account_id, {})[code] = row
    matched = []
    for account_id, facts in by_account.items():
        if require and any(code not in facts for code in require):
            continue
        if any(code in facts for code in exclude):
            continue
        if not require and not exclude:
            continue
        matched.append(account_id)
    # Accounts with no positive facts still fail a require list. An exclude-only
    # cohort is everyone who does not carry the excluded signal, including
    # accounts we have never read. That would look like the whole book. An
    # exclude-only query therefore stays inside accounts that have any fact.
    if not require:
        matched = [account_id for account_id in matched if by_account.get(account_id)]
    accounts = list(
        db.scalars(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.id.in_(matched or [UUID(int=0)]),
                Account.deleted_at.is_(None),
            )
        ).all()
    )
    presented = []
    for account in accounts:
        facts = by_account.get(account.id, {})
        line = ""
        for code in OPENING_ORDER:
            fact = facts.get(code)
            if fact is None:
                continue
            line = opening_line(code, fact.value_text, fact.value_num)
            if line:
                break
        presented.append(
            {
                "account_id": str(account.id),
                "name": account.name,
                "website": account.website,
                "opening": line,
                "signals": [
                    {"code": code, "label": BY_CODE[code].label, "value_text": fact.value_text, "value_num": fact.value_num}
                    for code, fact in facts.items()
                    if code in BY_CODE
                ],
            }
        )
    presented.sort(key=lambda item: item["name"].lower())
    return {"count": len(presented), "accounts": presented}


def fetch_public_text(url: str) -> str:
    """GET one public page. A private, local, or unreachable address returns empty."""
    try:
        with httpx.Client(timeout=12.0, trust_env=False, follow_redirects=False) as client:
            current = url
            for _ in range(4):
                current = assert_public_url(current)
                response = client.get(
                    current,
                    headers={"User-Agent": "SalesEngineSiteSignals/1.0", "Accept": "text/html,application/xml,text/plain"},
                )
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location") or ""
                    if not location:
                        return ""
                    current = str(httpx.URL(current).join(location))
                    continue
                if response.status_code >= 400:
                    return ""
                content_type = (response.headers.get("content-type") or "").lower()
                if content_type and not any(token in content_type for token in ("html", "xml", "plain", "text")):
                    return ""
                return response.text[:PAGE_LIMIT]
    except (SnippetUnavailable, httpx.HTTPError, ValueError):
        return ""
    return ""


def _site(account: Account) -> tuple[str, str]:
    raw = (account.website or "").strip()
    if not raw and account.domain:
        raw = f"https://{account.domain.strip()}"
    if not raw:
        return "", ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or not host:
        return "", ""
    return f"{parsed.scheme}://{parsed.netloc}", host


def _first_page(base: str, paths: tuple[str, ...], fetcher) -> tuple[str, str]:
    for path in paths:
        url = f"{base}{path}"
        body = fetcher(url)
        if body and len(body) > 80:
            return url, body
    return "", ""


def _recently_checked(db: Session, tenant_id: UUID, account_id: UUID, force: bool) -> bool:
    if force:
        return False
    row = db.scalar(
        select(SiteProfileCheck)
        .where(
            SiteProfileCheck.tenant_id == tenant_id,
            SiteProfileCheck.account_id == account_id,
            SiteProfileCheck.deleted_at.is_(None),
        )
        .order_by(SiteProfileCheck.checked_at.desc())
    )
    checked = _aware(row.checked_at) if row else None
    if checked is None:
        return False
    return checked >= _now() - timedelta(days=STALE_DAYS)


def profile_accounts(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    limit: int = 10,
    force: bool = False,
    fetcher=None,
) -> dict:
    fetch = fetcher if fetcher is not None else fetch_public_text
    choices = ensure_choices(db, tenant_id, actor_id)
    wanted = {row.code for row in choices if row.status == "confirmed" and BY_CODE[row.code].collectable}
    if not wanted:
        return {
            "accounts_read": 0,
            "observations": 0,
            "skipped": 0,
            "note": "Confirm at least one free signal before reading websites.",
        }
    bounded = max(1, min(limit, 25))
    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.tenant_id == tenant_id, Account.deleted_at.is_(None))
            .limit(CANDIDATE_LIMIT)
        ).all()
    )
    run = SiteProfileRun(
        tenant_id=tenant_id,
        created_by=actor_id,
        updated_by=actor_id,
        status="completed",
        note="",
    )
    db.add(run)
    db.flush()
    read = 0
    stored = 0
    skipped = 0
    unreachable = 0
    now = _now()
    needs_home = bool(wanted - {"NO_WEBSITE"})
    for account in accounts:
        if read >= bounded:
            break
        if _recently_checked(db, tenant_id, account.id, force):
            skipped += 1
            continue
        base, domain = _site(account)
        observations: list[RawObservation] = []
        reachable = False
        if "NO_WEBSITE" in wanted:
            observations.append(RawObservation("NO_WEBSITE", 0 if base else 1, "", 100, base))
        if base and needs_home:
            home = fetch(base if base.endswith("/") else f"{base}/")
            home_url = base
            if not home:
                unreachable += 1
            else:
                reachable = True
                robots = robots_url = sitemap = sitemap_url = ""
                team = team_url = careers = careers_url = contact = contact_url = ""
                if {"BLOCKS_AI_CRAWLERS"} & wanted:
                    robots_url = f"{base}/robots.txt"
                    robots = fetch(robots_url)
                if {"SITE_PAGE_COUNT", "BLOG_STALE"} & wanted:
                    sitemap_url = f"{base}/sitemap.xml"
                    sitemap = fetch(sitemap_url)
                if {"CONTACT_FOUND", "DECISION_MAKER_TITLE"} & wanted:
                    team_url, team = _first_page(base, TEAM_PATHS, fetch)
                if "HIRING_ROLE" in wanted:
                    careers_url, careers = _first_page(base, CAREERS_PATHS, fetch)
                if "CONTACT_FORM_URL" in wanted:
                    contact_url, contact = _first_page(base, CONTACT_PATHS, fetch)
                observations.extend(
                    analyze_pages(
                        domain=domain,
                        home_url=home_url,
                        home=home,
                        robots=robots,
                        robots_url=robots_url,
                        sitemap=sitemap,
                        sitemap_url=sitemap_url,
                        team=team,
                        team_url=team_url,
                        careers=careers,
                        careers_url=careers_url,
                        contact=contact,
                        contact_url=contact_url,
                        wanted=wanted,
                        today=now.date(),
                    )
                )
        elif not base:
            reachable = False
        for item in observations:
            db.add(
                SiteObservation(
                    tenant_id=tenant_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                    account_id=account.id,
                    run_id=run.id,
                    signal_code=item.code,
                    value_num=item.value_num,
                    value_text=item.value_text[:400],
                    confidence=item.confidence,
                    evidence_url=item.evidence_url[:1000],
                    observed_at=now,
                )
            )
            stored += 1
        db.add(
            SiteProfileCheck(
                tenant_id=tenant_id,
                created_by=actor_id,
                updated_by=actor_id,
                account_id=account.id,
                run_id=run.id,
                reachable=reachable,
                checked_at=now,
            )
        )
        read += 1
    note = ""
    if unreachable:
        note = f"{unreachable} website{'s' if unreachable != 1 else ''} could not be read. Nothing was invented for them."
    run.accounts_read = read
    run.observations = stored
    run.skipped = skipped
    run.note = note
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="site_signal.profile",
        entity_type="site_profile_run",
        entity_id=str(run.id),
        after={"accounts_read": read, "observations": stored, "skipped": skipped},
    )
    db.flush()
    return _present_run(run) or {}
