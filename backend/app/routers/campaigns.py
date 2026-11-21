"""Campaign listing, detail, history and creation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import repositories as repo
from ..deps import DbSession, KeitaroClientDep
from ..services.editor import editor_out
from ..errors import EditorError
from ..schemas import (
    CampaignCreate,
    CampaignCreatedOut,
    CampaignEditorOut,
    CampaignHistoryOut,
    CampaignOut,
    CreatedCampaignOut,
    CreatedStreamOut,
)
from ..services.creation import create_campaign_with_persistence
from ..utils import as_int

router = APIRouter(prefix="/api", tags=["campaigns"])


@router.post("/campaigns/create", response_model=CampaignCreatedOut)
async def create_campaign_endpoint(
    data: CampaignCreate,
    db: DbSession,
    api: KeitaroClientDep,
):
    try:
        result = await create_campaign_with_persistence(
            db,
            api,
            name=data.name,
            geo=data.geo,
            offer_id=data.offer_id,
        )
    except ValueError as exc:
        raise EditorError(400, "CAMPAIGN_CREATION_ERROR", str(exc)) from exc

    return CampaignCreatedOut(
        success=True,
        campaign=CreatedCampaignOut(
            id=as_int(result.campaign.get("id")),
            name=result.campaign.get("name"),
            alias=result.campaign.get("alias"),
        ),
        streams=[
            CreatedStreamOut(id=as_int(item.get("id")), name=str(item.get("name") or ""))
            for item in result.streams
        ],
    )


@router.get("/campaigns", response_model=list[CampaignOut])
async def campaigns_list(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=150),
    state: str | None = Query(default=None, max_length=20),
):
    return await repo.list_campaigns(db, limit=limit, offset=offset, q=q, state=state)


@router.get("/campaigns/history", response_model=list[CampaignHistoryOut])
async def campaign_history(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
):
    return await repo.list_creation_logs(db, limit=limit)


@router.get("/campaigns/{campaign_id}", response_model=CampaignEditorOut)
async def campaign_detail(campaign_id: int, db: DbSession):
    row = await repo.get_campaign(db, campaign_id)
    if row is None:
        raise EditorError(404, "CAMPAIGN_NOT_FOUND", f"Кампания {campaign_id} не найдена")
    return editor_out(row)
