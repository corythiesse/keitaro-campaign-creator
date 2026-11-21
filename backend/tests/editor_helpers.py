"""Shared builders for editor tests.

Rows are created so that baseline equals working state (a "clean" campaign),
mirroring what ``save_streams_and_offers`` / ``apply_remote_snapshot`` do.
"""
from app.models import Campaign, Offer, Stream


async def seed_campaign(db, *, keitaro_id=123, name="Test campaign", state="active", revision=0):
    campaign = Campaign(keitaro_id=keitaro_id, name=name, state=state, revision=revision)
    db.add(campaign)
    await db.flush()
    return campaign


async def seed_stream(
    db,
    campaign,
    *,
    keitaro_id,
    name="Default - Offer",
    state="active",
    is_deleted=False,
    updated_at="2026-01-01T00:00:00Z",
    origin="keitaro",
):
    stream = Stream(
        keitaro_id=keitaro_id,
        campaign_id=campaign.id,
        name=name,
        type="default",
        schema="landings",
        position=1,
        state=state,
        action_type="http",
        keitaro_updated_at=updated_at,
        origin=origin,
        is_deleted=is_deleted,
        base_state=state,
        base_is_deleted=is_deleted,
    )
    db.add(stream)
    await db.flush()
    return stream


async def seed_offer(
    db,
    campaign,
    stream,
    *,
    keitaro_id,
    name="Offer A",
    share=100,
    state="active",
    is_deleted=False,
    is_pinned=False,
    pinned_share=None,
    origin="keitaro",
    keitaro_offer_stream_id=None,
):
    offer = Offer(
        keitaro_id=keitaro_id,
        campaign_id=campaign.id,
        stream_id=stream.id,
        name=name,
        state=state,
        share=share,
        keitaro_offer_stream_id=keitaro_offer_stream_id,
        origin=origin,
        is_deleted=is_deleted,
        is_pinned=is_pinned,
        pinned_share=pinned_share,
        base_share=share,
        base_state=state,
        base_is_deleted=is_deleted,
    )
    db.add(offer)
    await db.flush()
    return offer


def remote_stream(keitaro_id, *, name="Default - Offer", offers=None, state="active"):
    return {
        "id": keitaro_id,
        "name": name,
        "type": "default",
        "schema": "landings",
        "position": 1,
        "state": state,
        "action_type": "http",
        "updated_at": "2026-02-01T00:00:00Z",
        "offers": offers or [],
    }


def remote_offer(offer_id, *, offer_stream_id=5000, share=100, state="active"):
    return {
        "id": offer_stream_id,
        "offer_id": offer_id,
        "share": share,
        "state": state,
    }
