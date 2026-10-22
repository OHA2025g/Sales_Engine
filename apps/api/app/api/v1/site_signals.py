from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.schemas.common import Envelope
from app.schemas.site_signals import (
    CohortIn,
    CohortOut,
    SiteProfileIn,
    SiteProfileRunOut,
    SiteSignalBoardOut,
    SiteSignalStatusIn,
)
from app.services.site_signals import SiteSignalError, catalog_view, cohort, profile_accounts, set_signal_status

router = APIRouter(prefix="/site-signals", tags=["site-signals"])


@router.get("", response_model=Envelope[SiteSignalBoardOut])
def read_site_signals(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("signals.read"))],
) -> Envelope[SiteSignalBoardOut]:
    board = catalog_view(db, ctx.tenant_id, ctx.user.id)
    db.commit()
    return Envelope(data=SiteSignalBoardOut.model_validate(board))


@router.post("/status", response_model=Envelope[SiteSignalBoardOut])
def update_site_signal_status(
    body: SiteSignalStatusIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("signals.write"))],
) -> Envelope[SiteSignalBoardOut]:
    try:
        set_signal_status(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, codes=body.codes, status=body.status)
        board = catalog_view(db, ctx.tenant_id, ctx.user.id)
    except SiteSignalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return Envelope(data=SiteSignalBoardOut.model_validate(board))


@router.post("/profile", response_model=Envelope[SiteProfileRunOut])
def read_account_websites(
    body: SiteProfileIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("signals.write"))],
) -> Envelope[SiteProfileRunOut]:
    result = profile_accounts(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        limit=body.limit,
        force=body.force,
    )
    db.commit()
    return Envelope(data=SiteProfileRunOut.model_validate(result))


@router.post("/cohort", response_model=Envelope[CohortOut])
def read_site_signal_cohort(
    body: CohortIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("signals.read"))],
) -> Envelope[CohortOut]:
    try:
        result = cohort(db, ctx.tenant_id, body.require, body.exclude)
    except SiteSignalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Envelope(data=CohortOut.model_validate(result))
