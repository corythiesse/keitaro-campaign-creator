"""Offer search and local offer listing endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import repositories as repo
from ..deps import DbSession, KeitaroClientDep
from ..errors import EditorError
from ..schemas import OfferOut, OfferSearchOut

router = APIRouter(prefix="/api", tags=["offers"])


@router.get("/offers-remote", response_model=list[OfferSearchOut])
async def search_offers_remote(
    api: KeitaroClientDep,
    q: str = Query(default="", max_length=150),
):
    """Active offers from Keitaro (autocomplete for campaign creation)."""
    offers = await api.offers()
    q_lower = q.casefold().strip()
    filtered = [
        offer
        for offer in offers
        if q_lower in str(offer.get("name", "")).casefold()
        or q_lower in str(offer.get("id", ""))
    ]
    result: list[OfferSearchOut] = []
    for offer in filtered[:50]:
        try:
            offer_id = int(offer["id"])
        except (KeyError, TypeError, ValueError):
            continue
        result.append(OfferSearchOut(id=offer_id, name=str(offer.get("name", ""))))
    return result


@router.get("/offers", response_model=list[OfferOut])
async def campaign_offers(
    db: DbSession,
    campaign_id: int = Query(..., gt=0),
    q: str = Query(default="", max_length=150),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    if not await repo.campaign_exists(db, campaign_id):
        raise EditorError(404, "CAMPAIGN_NOT_FOUND", f"Кампания {campaign_id} не найдена")
    return await repo.list_offers(db, campaign_id=campaign_id, q=q, limit=limit, offset=offset)
