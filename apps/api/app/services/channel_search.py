import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.channel_search import ChannelSearch, ChannelSearchHit
from app.providers.channel_search import (
    CHANNELS,
    NO_MATCH_REASON,
    NOT_CONFIGURED_DETAIL,
    ChannelHit,
    ChannelSearchOutcome,
    get_channel_search_provider,
    normalize_channels,
    overall_status,
    relevant_hits,
)
from app.services.audit import write_audit


def channel_search_status() -> dict[str, str | bool]:
    settings = get_settings()
    kind = settings.resolved_channel_search_provider
    if kind == "google_cse":
        detail = "Results come from Google Programmable Search. Rank is the Google result position. A result is shown only when its title or text matches the keyword."
    elif kind == "apify":
        detail = "Results come from Google result pages. Rank is the Google result position. A result is shown only when its title or text matches the keyword."
    elif kind == "gemini":
        detail = "Results are the public sources Google Search returned. Rank is that order. A result is shown only when its title or text matches the keyword."
    else:
        kind = "not_configured"
        detail = NOT_CONFIGURED_DETAIL
    return {"provider": kind, "configured": kind != "not_configured", "detail": detail}


def run_channel_search(db: Session, *, tenant_id: UUID, actor_id: UUID, query: str) -> ChannelSearch:
    outcome = get_channel_search_provider().search(query)
    outcome = ChannelSearchOutcome(
        provider=outcome.provider,
        channels=normalize_channels(outcome.channels, provider=outcome.provider),
    )
    status = overall_status(outcome.channels)
    row = ChannelSearch(
        tenant_id=tenant_id,
        created_by=actor_id,
        updated_by=actor_id,
        query=query,
        status=status,
        provider=outcome.provider,
        channels_json=json.dumps(
            [
                {"channel": channel.channel, "mode": channel.mode, "provider": channel.provider, "reason": channel.reason}
                for channel in outcome.channels
            ]
        ),
    )
    db.add(row)
    db.flush()
    hit_count = 0
    for channel in outcome.channels:
        for hit in channel.hits:
            hit_count += 1
            db.add(
                ChannelSearchHit(
                    tenant_id=tenant_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                    search_id=row.id,
                    channel=channel.channel,
                    rank=hit.rank,
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                )
            )
    write_audit(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="channel_search.create",
        entity_type="channel_search",
        entity_id=str(row.id),
        after={"query": query, "provider": outcome.provider, "status": status, "hit_count": hit_count},
    )
    return row


def hits_for_search(db: Session, tenant_id: UUID, search_id: UUID) -> list[ChannelSearchHit]:
    return list(
        db.scalars(
            select(ChannelSearchHit).where(
                ChannelSearchHit.tenant_id == tenant_id,
                ChannelSearchHit.search_id == search_id,
                ChannelSearchHit.deleted_at.is_(None),
            )
        ).all()
    )


def list_channel_searches(db: Session, tenant_id: UUID, *, limit: int = 10) -> list[dict]:
    bounded = max(1, min(limit, 20))
    rows = list(
        db.scalars(
            select(ChannelSearch)
            .where(ChannelSearch.tenant_id == tenant_id, ChannelSearch.deleted_at.is_(None))
            .order_by(ChannelSearch.created_at.desc())
            .limit(bounded)
        ).all()
    )
    if not rows:
        return []
    hits = list(
        db.scalars(
            select(ChannelSearchHit).where(
                ChannelSearchHit.tenant_id == tenant_id,
                ChannelSearchHit.search_id.in_([row.id for row in rows]),
                ChannelSearchHit.deleted_at.is_(None),
            )
        ).all()
    )
    return [present_search(row, [hit for hit in hits if hit.search_id == row.id]) for row in rows]


def present_search(row: ChannelSearch, hits: list[ChannelSearchHit]) -> dict:
    raw = json.loads(row.channels_json or "[]")
    meta = {item.get("channel"): item for item in raw if isinstance(item, dict)}
    grouped: dict[str, list[ChannelSearchHit]] = {name: [] for name in CHANNELS}
    for hit in hits:
        if hit.channel in grouped:
            grouped[hit.channel].append(hit)
    channels = []
    for name in CHANNELS:
        info = meta.get(name) or {}
        ordered = sorted(grouped[name], key=lambda item: item.rank)
        matched = relevant_hits(
            row.query,
            [ChannelHit(rank=hit.rank, title=hit.title, url=hit.url, snippet=hit.snippet) for hit in ordered],
        )
        reason = str(info.get("reason") or "")
        mode = str(info.get("mode") or "")
        if mode == "live" and not matched:
            reason = NO_MATCH_REASON
        channels.append(
            {
                "channel": name,
                "mode": mode,
                "provider": str(info.get("provider") or ""),
                "reason": reason,
                "hits": [{"rank": hit.rank, "title": hit.title, "url": hit.url, "snippet": hit.snippet} for hit in matched],
            }
        )
    return {
        "id": row.id,
        "query": row.query,
        "status": row.status,
        "provider": row.provider,
        "created_at": row.created_at,
        "channels": channels,
    }
