"""Campaign editor: local mutations and synchronisation."""
from __future__ import annotations

from fastapi import APIRouter

from ..deps import DbSession, KeitaroClientDep
from ..services.editor import (
    add_offer,
    discard,
    load_campaign_streams,
    patch_offer,
    push_campaign_changes,
)
from ..schemas import (
    AddOfferRequest,
    CampaignEditorOut,
    OfferPatch,
    SyncLoadRequest,
    SyncPushOut,
    SyncPushRequest,
)

router = APIRouter(prefix="/api", tags=["editor"])


@router.post("/campaigns/{campaign_id}/sync/load", response_model=CampaignEditorOut)
async def campaign_sync_load(
    campaign_id: int,
    db: DbSession,
    api: KeitaroClientDep,
    data: SyncLoadRequest | None = None,
):
    return await load_campaign_streams(
        db,
        api,
        campaign_id,
        force=bool(data and data.force),
    )


@router.post("/campaigns/{campaign_id}/sync/push", response_model=SyncPushOut)
async def campaign_sync_push(
    campaign_id: int,
    db: DbSession,
    api: KeitaroClientDep,
    data: SyncPushRequest | None = None,
):
    return await push_campaign_changes(
        db,
        api,
        campaign_id,
        expected_revision=data.expected_revision if data else None,
        force=bool(data and data.force),
    )


@router.post("/campaigns/{campaign_id}/sync/discard", response_model=CampaignEditorOut)
async def campaign_sync_discard(campaign_id: int, db: DbSession):
    return await discard(db, campaign_id)


@router.post("/streams/{stream_id}/offers", response_model=CampaignEditorOut)
async def add_stream_offer(
    stream_id: int,
    data: AddOfferRequest,
    db: DbSession,
    api: KeitaroClientDep,
):
    return await add_offer(
        db,
        api,
        stream_id,
        data.offer_id,
        data.name,
        expected_revision=data.expected_revision,
    )


@router.patch("/offers/{offer_id}", response_model=CampaignEditorOut)
async def patch_offer_endpoint(offer_id: int, data: OfferPatch, db: DbSession):
    return await patch_offer(
        db,
        offer_id,
        data,
        expected_revision=data.expected_revision,
    )
