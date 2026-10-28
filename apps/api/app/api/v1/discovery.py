from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.providers.lead_discovery import get_lead_discovery_provider
from app.schemas.common import Envelope
from app.schemas.discovery import DiscoveryHealthOut, DiscoveryRunIn, DiscoveryRunOut
from app.services.discovery import annotate_prospects, run_discovery
from app.services.orchestrator import process_pending_events

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/health", response_model=Envelope[DiscoveryHealthOut])
def discovery_health(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("leads.read"))],
) -> Envelope[DiscoveryHealthOut]:
    return Envelope(data=DiscoveryHealthOut.model_validate(get_lead_discovery_provider(db, ctx.tenant_id).health()))


@router.post("/run", response_model=Envelope[DiscoveryRunOut])
def discover_leads(
    body: DiscoveryRunIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("leads.write"))],
) -> Envelope[DiscoveryRunOut]:
    result = run_discovery(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        profile_urls=body.profile_urls,
        search_query=body.search_query,
        correlation_id=ctx.correlation_id,
        operating_plan_id=body.operating_plan_id,
        icp_id=body.icp_id,
    )
    if not result.get("execution_blocked") and result.get("next_action") not in {"choose_operating_plan", "choose_icp"}:
        process_pending_events(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id)
        result = annotate_prospects(db, ctx.tenant_id, result)
    db.commit()
    return Envelope(data=DiscoveryRunOut.model_validate(result))
