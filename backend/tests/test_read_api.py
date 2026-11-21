from datetime import datetime, timedelta, timezone

import httpx

from app.models import Campaign, Offer, Stream

from .conftest import KEITARO


async def _seed_campaign(db, *, keitaro_id, name, alias=None, state="active", created_at=None):
    now = datetime.now(timezone.utc)
    campaign = Campaign(
        keitaro_id=keitaro_id,
        name=name,
        alias=alias,
        state=state,
        created_at=created_at or now,
        updated_at=created_at or now,
    )
    db.add(campaign)
    await db.flush()
    return campaign


async def _seed_stream(db, campaign, *, keitaro_id, name="Default - Offer", position=1):
    stream = Stream(
        keitaro_id=keitaro_id,
        campaign_id=campaign.id,
        name=name,
        position=position,
        schema="landings",
        type="default",
        state="active",
        action_type="http",
    )
    db.add(stream)
    await db.flush()
    return stream


async def _seed_offer(db, campaign, stream, *, keitaro_id, name="Offer A"):
    offer = Offer(
        keitaro_id=keitaro_id,
        campaign_id=campaign.id,
        stream_id=stream.id,
        name=name,
        state="active",
        share=100,
    )
    db.add(offer)
    await db.flush()
    return offer


async def test_list_campaigns_local_sorted_and_paginated(client, session):
    now = datetime.now(timezone.utc)
    await _seed_campaign(session, keitaro_id=1, name="Oldest", created_at=now - timedelta(hours=2))
    await _seed_campaign(session, keitaro_id=2, name="Middle", created_at=now - timedelta(hours=1))
    await _seed_campaign(session, keitaro_id=3, name="Newest", created_at=now)
    await session.commit()

    response = await client.get("/api/campaigns")

    assert response.status_code == 200, response.text
    assert [c["name"] for c in response.json()] == ["Newest", "Middle", "Oldest"]
    assert response.json()[0]["keitaro_id"] == 3

    page = await client.get("/api/campaigns", params={"limit": 1, "offset": 1})
    assert [c["name"] for c in page.json()] == ["Middle"]


async def test_list_campaigns_filters(client, session):
    await _seed_campaign(session, keitaro_id=1, name="Alpha campaign", alias="alpha_alias", state="active")
    await _seed_campaign(session, keitaro_id=2, name="Beta campaign", alias="beta_alias", state="disabled")
    await session.commit()

    by_name = await client.get("/api/campaigns", params={"q": "alpha"})
    assert [c["keitaro_id"] for c in by_name.json()] == [1]

    by_alias = await client.get("/api/campaigns", params={"q": "beta_alias"})
    assert [c["keitaro_id"] for c in by_alias.json()] == [2]

    by_state = await client.get("/api/campaigns", params={"state": "disabled"})
    assert [c["keitaro_id"] for c in by_state.json()] == [2]

    empty = await client.get("/api/campaigns", params={"q": "nothing-matches"})
    assert empty.json() == []


async def test_search_is_casefold_for_non_ascii(client, session):
    campaign = await _seed_campaign(session, keitaro_id=1, name="Тестовая кампания")
    stream = await _seed_stream(session, campaign, keitaro_id=901)
    await _seed_offer(session, campaign, stream, keitaro_id=11, name="Оффер Москва")
    await session.commit()

    campaigns = await client.get("/api/campaigns", params={"q": "ТЕСТОВАЯ"})
    assert [c["keitaro_id"] for c in campaigns.json()] == [1]

    offers = await client.get("/api/offers", params={"campaign_id": campaign.id, "q": "москва"})
    assert [o["keitaro_id"] for o in offers.json()] == [11]


async def test_campaign_detail_returns_streams_and_offers(client, session):
    campaign = await _seed_campaign(session, keitaro_id=123, name="Test campaign", alias="test_alias")
    await _seed_stream(session, campaign, keitaro_id=9001, name="GEO - Google", position=1)
    offer_stream = await _seed_stream(session, campaign, keitaro_id=9002, name="Default - Offer", position=2)
    await _seed_offer(session, campaign, offer_stream, keitaro_id=42, name="Offer name")
    await session.commit()

    response = await client.get(f"/api/campaigns/{campaign.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == campaign.id
    assert body["keitaro_id"] == 123
    assert body["keitaro_campaign_url"] == "https://keitaro.test/admin/#!/campaign/123/main"
    assert [s["keitaro_id"] for s in body["streams"]] == [9001, 9002]
    assert [s["name"] for s in body["streams"]] == ["GEO - Google", "Default - Offer"]
    assert body["streams"][0]["offers"] == []
    offer = body["streams"][1]["offers"][0]
    assert offer["keitaro_id"] == 42
    assert offer["name"] == "Offer name"
    assert offer["share"] == 100
    assert offer["campaign_id"] == campaign.id
    assert offer["stream_id"] == offer_stream.id
    assert offer["keitaro_stream_id"] == 9002


async def test_campaign_detail_not_found(client):
    response = await client.get("/api/campaigns/999")

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


async def test_campaign_detail_without_streams(client, session):
    campaign = await _seed_campaign(session, keitaro_id=10, name="Empty")
    await session.commit()

    response = await client.get(f"/api/campaigns/{campaign.id}")

    assert response.status_code == 200
    assert response.json()["streams"] == []


async def test_history_route_is_not_shadowed_by_campaign_id(client, session):
    await _seed_campaign(session, keitaro_id=1, name="Alpha")
    await session.commit()

    response = await client.get("/api/campaigns/history")

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_history_serializes_creation_log(client, session):
    from app.models import CampaignCreationLog

    session.add(
        CampaignCreationLog(
            campaign_name="Created",
            geo="MX",
            offer_id=42,
            status="success",
            keitaro_campaign_id=123,
        )
    )
    await session.commit()

    response = await client.get("/api/campaigns/history")

    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["campaign_name"] == "Created"
    assert row["status"] == "success"
    assert row["keitaro_campaign_id"] == 123


async def test_local_offers_requires_campaign_id(client):
    response = await client.get("/api/offers")
    assert response.status_code == 422


async def test_local_offers_are_scoped_to_campaign(client, session):
    first = await _seed_campaign(session, keitaro_id=1, name="First")
    first_stream = await _seed_stream(session, first, keitaro_id=901)
    await _seed_offer(session, first, first_stream, keitaro_id=11, name="Alpha offer")

    second = await _seed_campaign(session, keitaro_id=2, name="Second")
    second_stream = await _seed_stream(session, second, keitaro_id=902)
    await _seed_offer(session, second, second_stream, keitaro_id=22, name="Beta offer")
    await session.commit()

    response = await client.get("/api/offers", params={"campaign_id": first.id})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [o["keitaro_id"] for o in body] == [11]
    assert body[0]["campaign_id"] == first.id
    assert body[0]["stream_id"] == first_stream.id
    assert body[0]["keitaro_stream_id"] == 901


async def test_local_offers_search_by_name_and_keitaro_id(client, session):
    campaign = await _seed_campaign(session, keitaro_id=1, name="First")
    stream = await _seed_stream(session, campaign, keitaro_id=901)
    await _seed_offer(session, campaign, stream, keitaro_id=11, name="Alpha offer")
    await _seed_offer(session, campaign, stream, keitaro_id=22, name="Beta offer")
    await session.commit()

    by_name = await client.get("/api/offers", params={"campaign_id": campaign.id, "q": "beta"})
    assert [o["keitaro_id"] for o in by_name.json()] == [22]

    by_id = await client.get("/api/offers", params={"campaign_id": campaign.id, "q": "11"})
    assert [o["keitaro_id"] for o in by_id.json()] == [11]


async def test_local_offers_missing_campaign_is_404(client):
    response = await client.get("/api/offers", params={"campaign_id": 999})

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


async def test_local_offers_empty_for_campaign_without_offers(client, session):
    campaign = await _seed_campaign(session, keitaro_id=1, name="First")
    await session.commit()

    response = await client.get("/api/offers", params={"campaign_id": campaign.id})

    assert response.status_code == 200
    assert response.json() == []


async def test_offers_remote_keeps_previous_behaviour(client, respx_mock):
    respx_mock.get(f"{KEITARO}/offers").mock(
        return_value=httpx.Response(200, json=[
            {"id": 11, "name": "Alpha offer", "state": "active"},
            {"id": 22, "name": "Beta offer", "state": "active"},
            {"id": 33, "name": "Gamma offer", "state": "disabled"},
        ])
    )

    everything = await client.get("/api/offers-remote")
    assert everything.status_code == 200, everything.text
    assert everything.json() == [
        {"id": 11, "name": "Alpha offer"},
        {"id": 22, "name": "Beta offer"},
    ]

    filtered = await client.get("/api/offers-remote", params={"q": "beta"})
    assert filtered.json() == [{"id": 22, "name": "Beta offer"}]

    by_id = await client.get("/api/offers-remote", params={"q": "11"})
    assert by_id.json() == [{"id": 11, "name": "Alpha offer"}]


async def test_offers_remote_returns_keitaro_error(client, respx_mock):
    respx_mock.get(f"{KEITARO}/offers").mock(return_value=httpx.Response(500, json={"error": "boom"}))

    response = await client.get("/api/offers-remote")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "KEITARO_API_ERROR"
