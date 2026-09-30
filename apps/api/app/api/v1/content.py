from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_permission
from app.db.session import get_db
from app.schemas.common import Envelope, Meta
from app.schemas.content import (
    ContentDraftOut,
    ContentDraftPatch,
    ContentProductIn,
    ContentProductOut,
    ContentProductPatch,
    GenerateContentIn,
    SellerProfileIn,
    SellerProfileOut,
)
from app.services.content import (
    create_catalog_product,
    generate_drafts,
    get_profile,
    list_drafts,
    list_products,
    publish_draft,
    save_profile,
    update_draft,
    update_product_description,
)

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/profile", response_model=Envelope[SellerProfileOut])
def read_profile(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[SellerProfileOut]:
    row = get_profile(db, ctx.tenant_id)
    if row is None:
        return Envelope(data=SellerProfileOut())
    return Envelope(data=SellerProfileOut.model_validate(row))


@router.put("/profile", response_model=Envelope[SellerProfileOut])
def write_profile(
    body: SellerProfileIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[SellerProfileOut]:
    row = save_profile(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, **body.model_dump())
    db.commit()
    db.refresh(row)
    return Envelope(data=SellerProfileOut.model_validate(row))


@router.get("/products", response_model=Envelope[list[ContentProductOut]])
def content_products(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[list[ContentProductOut]]:
    rows = [ContentProductOut.model_validate(row) for row in list_products(db, ctx.tenant_id)]
    return Envelope(data=rows, meta=Meta(total=len(rows)))


@router.post("/products", response_model=Envelope[ContentProductOut])
def add_content_product(
    body: ContentProductIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[ContentProductOut]:
    row = create_catalog_product(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, **body.model_dump())
    db.commit()
    db.refresh(row)
    return Envelope(data=ContentProductOut.model_validate(row))


@router.patch("/products/{product_id}", response_model=Envelope[ContentProductOut])
def patch_content_product(
    product_id: UUID,
    body: ContentProductPatch,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[ContentProductOut]:
    row = update_product_description(db, tenant_id=ctx.tenant_id, product_id=product_id, description=body.description)
    db.commit()
    db.refresh(row)
    return Envelope(data=ContentProductOut.model_validate(row))


@router.get("/drafts", response_model=Envelope[list[ContentDraftOut]])
def content_drafts(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.read"))],
) -> Envelope[list[ContentDraftOut]]:
    rows = [ContentDraftOut.model_validate(row) for row in list_drafts(db, ctx.tenant_id)]
    return Envelope(data=rows, meta=Meta(total=len(rows)))


@router.post("/generate", response_model=Envelope[list[ContentDraftOut]])
def generate_content(
    body: GenerateContentIn,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[list[ContentDraftOut]]:
    rows = generate_drafts(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        product_id=body.product_id,
        ad_channel=body.ad_channel,
        brief=body.brief,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return Envelope(data=[ContentDraftOut.model_validate(row) for row in rows], meta=Meta(total=len(rows)))


@router.patch("/drafts/{draft_id}", response_model=Envelope[ContentDraftOut])
def patch_draft(
    draft_id: UUID,
    body: ContentDraftPatch,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[ContentDraftOut]:
    row = update_draft(db, tenant_id=ctx.tenant_id, draft_id=draft_id, **body.model_dump())
    db.commit()
    db.refresh(row)
    return Envelope(data=ContentDraftOut.model_validate(row))


@router.post("/drafts/{draft_id}/publish", response_model=Envelope[ContentDraftOut])
def publish_content_draft(
    draft_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_permission("campaigns.write"))],
) -> Envelope[ContentDraftOut]:
    row = publish_draft(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, draft_id=draft_id)
    db.commit()
    db.refresh(row)
    return Envelope(data=ContentDraftOut.model_validate(row))
