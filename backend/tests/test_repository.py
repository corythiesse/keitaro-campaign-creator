import datetime as dt

import pytest
from sqlalchemy import select

from app.models import Campaign, Offer, Stream
from app.errors import LocalPersistenceError
from app.repositories import save_campaign, save_streams_and_offers

CAMPAIGN = {
    "id": 123,
    "name": "Test campaign",
    "alias": "test_alias",
    "type": "position",
    "state": "active",
    "domain_id": 5,
    "group_id": "7",
}
STREAMS = [
    {"id": 9001, "name": "GEO - Google", "type": "regular", "schema": "redirect", "position": 1},
    {"id": 9002, "name": "Default - Offer", "type": "default", "schema": "landings", "position": 2},
]
OFFERS = [
    {
        "stream": STREAMS[1],
        "offer_id": 42,
        "share": 100,
        "state": "active",
        "snapshot": {"id": 42, "name": "Offer A", "state": "active"},
    }
]


async def test_save_campaign_is_idempotent(session):
    first = await save_campaign(session, CAMPAIGN, log_id=None)
    await session.commit()
    first_id = first.id
    first_updated_at = first.updated_at

    second = await save_campaign(session, {**CAMPAIGN, "name": "Renamed"}, log_id=None)
    await session.commit()

    campaigns = (await session.scalars(select(Campaign))).all()
    assert len(campaigns) == 1
    assert second.id == first_id
    assert second.name == "Renamed"
    assert second.updated_at >= first_updated_at


async def test_save_streams_and_offers_is_idempotent(session):
    campaign = await save_campaign(session, CAMPAIGN, log_id=None)
    await session.flush()

    await save_streams_and_offers(session, campaign, STREAMS, OFFERS)
    await session.commit()

    await save_streams_and_offers(session, campaign, STREAMS, OFFERS)
    await session.commit()

    streams = (await session.scalars(select(Stream))).all()
    offers = (await session.scalars(select(Offer))).all()
    assert sorted(s.keitaro_id for s in streams) == [9001, 9002]
    assert len(offers) == 1


async def test_offer_campaign_id_comes_from_stream_only(session):
    campaign = await save_campaign(session, CAMPAIGN, log_id=None)
    await session.flush()

    other_campaign = await save_campaign(session, {**CAMPAIGN, "id": 999}, log_id=None)
    await session.flush()

    tampered = [
        {
            "stream": {**STREAMS[1], "campaign_id": other_campaign.keitaro_id},
            "offer_id": 42,
            "share": 100,
            "state": "active",
            "campaign_id": other_campaign.keitaro_id,
            "snapshot": {"id": 42, "name": "Offer A", "campaign_id": other_campaign.keitaro_id},
        }
    ]

    await save_streams_and_offers(session, campaign, [STREAMS[1]], tampered)
    await session.commit()

    offer = (await session.scalars(select(Offer))).one()
    local_stream = (await session.scalars(select(Stream))).one()
    assert offer.campaign_id == campaign.id
    assert offer.stream_id == local_stream.id
    assert offer.campaign_id != other_campaign.id


async def test_raw_is_null_when_not_json_serializable(session):
    campaign = await save_campaign(
        session,
        {**CAMPAIGN, "payload": dt.datetime(2026, 1, 1)},
        log_id=None,
    )
    await session.commit()

    assert campaign.raw is None


async def test_missing_keitaro_id_raises_local_persistence_error(session):
    with pytest.raises(LocalPersistenceError):
        await save_campaign(session, {"name": "No id"}, log_id=None)


async def test_stream_is_required_for_offer(session):
    campaign = await save_campaign(session, CAMPAIGN, log_id=None)
    await session.flush()

    with pytest.raises(LocalPersistenceError):
        await save_streams_and_offers(session, campaign, [], OFFERS)
