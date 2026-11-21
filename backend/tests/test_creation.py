import re
import sqlite3

import httpx
from sqlalchemy import select

from app.services import creation as service_module
from app.database import SessionLocal
from app.main import app
from app.models import Campaign, CampaignCreationLog, Offer, Stream

from .conftest import KEITARO, TEST_DB_PATH, mock_keitaro_context

CREATE_PAYLOAD = {"name": "Test campaign", "geo": "MX, AU, RO", "offer_id": 42}


def _streams_route(respx_mock, handler):
    return respx_mock.post(f"{KEITARO}/streams").mock(side_effect=handler)


async def test_create_campaign_persists_campaign_streams_and_offer(client, respx_mock):
    mock_keitaro_context(respx_mock)
    ids = iter([9001, 9002])
    _streams_route(respx_mock, lambda request: httpx.Response(200, json={"id": next(ids)}))

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["campaign"]["id"] == 123
    assert body["campaign"]["name"] == "test_test-campaign"
    assert body["streams"] == [
        {"id": 9001, "name": "GEO - Google"},
        {"id": 9002, "name": "Default - Offer"},
    ]

    async with SessionLocal() as db:
        campaigns = (await db.scalars(select(Campaign))).all()
        streams = (await db.scalars(select(Stream))).all()
        offers = (await db.scalars(select(Offer))).all()
        log = (await db.scalars(select(CampaignCreationLog))).one()

    assert len(campaigns) == 1
    campaign = campaigns[0]
    assert campaign.keitaro_id == 123
    assert campaign.name == "test_test-campaign"
    assert re.fullmatch(r"test-campaign_[0-9a-f]{6}", campaign.alias)
    assert campaign.traffic_source_id == 8
    assert campaign.campaign_creation_log_id == log.id

    assert len(streams) == 2
    geo_stream = next(s for s in streams if s.keitaro_id == 9001)
    offer_stream = next(s for s in streams if s.keitaro_id == 9002)
    assert geo_stream.type == "regular"
    assert geo_stream.schema == "redirect"
    assert offer_stream.type == "default"
    assert offer_stream.schema == "landings"
    assert geo_stream.campaign_id == campaign.id
    assert offer_stream.campaign_id == campaign.id

    assert len(offers) == 1
    offer = offers[0]
    assert offer.keitaro_id == 42
    assert offer.name == "Offer A"
    assert offer.share == 100
    assert offer.state == "active"
    assert offer.campaign_id == campaign.id
    assert offer.stream_id == offer_stream.id

    assert log.status == "success"
    assert log.keitaro_campaign_id == 123
    assert log.google_stream_id == 9001
    assert log.offer_stream_id == 9002


async def test_create_campaign_reports_invalid_geo_in_russian(client):
    response = await client.post(
        "/api/campaigns/create",
        json={**CREATE_PAYLOAD, "geo": "MX, ZH"},
    )

    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "geo"]
    assert error["msg"] == "Некорректные ISO-коды стран: ZH"


async def test_campaign_is_committed_before_streams_are_created(client, respx_mock):
    mock_keitaro_context(respx_mock)
    seen = {}
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            # A separate connection must already see the committed campaign.
            with sqlite3.connect(TEST_DB_PATH) as conn:
                seen["campaigns"] = [
                    row[0] for row in conn.execute("SELECT keitaro_id FROM campaigns")
                ]
                seen["streams"] = conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0]
        return httpx.Response(200, json={"id": 9000 + calls["n"]})

    _streams_route(respx_mock, handler)

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 200, response.text
    assert seen["campaigns"] == [123]
    assert seen["streams"] == 0


async def test_partial_when_offer_stream_fails(client, respx_mock):
    mock_keitaro_context(respx_mock)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"id": 9001})
        return httpx.Response(500, json={"error": "boom"})

    _streams_route(respx_mock, handler)

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 502, response.text
    body = response.json()["detail"]
    assert body["code"] == "PARTIAL_CREATION"
    assert body["campaign_id"] == 123
    assert body["google_stream_id"] == 9001

    async with SessionLocal() as db:
        campaigns = (await db.scalars(select(Campaign))).all()
        streams = (await db.scalars(select(Stream))).all()
        offers = (await db.scalars(select(Offer))).all()
        log = (await db.scalars(select(CampaignCreationLog))).one()

    assert [c.keitaro_id for c in campaigns] == [123]
    assert [s.keitaro_id for s in streams] == [9001]
    assert offers == []
    assert log.status == "partial"
    assert log.keitaro_campaign_id == 123


async def test_partial_when_geo_stream_fails(client, respx_mock):
    mock_keitaro_context(respx_mock)
    _streams_route(respx_mock, lambda request: httpx.Response(500, json={"error": "boom"}))

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "PARTIAL_CREATION"

    async with SessionLocal() as db:
        campaigns = (await db.scalars(select(Campaign))).all()
        streams = (await db.scalars(select(Stream))).all()
        offers = (await db.scalars(select(Offer))).all()
        log = (await db.scalars(select(CampaignCreationLog))).one()

    assert [c.keitaro_id for c in campaigns] == [123]
    assert streams == []
    assert offers == []
    assert log.status == "partial"


async def test_keitaro_error_before_campaign_creates_nothing(client, respx_mock):
    respx_mock.get(f"{KEITARO}/offers/42").mock(return_value=httpx.Response(500, json={"error": "boom"}))

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "KEITARO_API_ERROR"

    async with SessionLocal() as db:
        assert (await db.scalars(select(Campaign))).all() == []
        assert (await db.scalars(select(Stream))).all() == []
        log = (await db.scalars(select(CampaignCreationLog))).one()
    assert log.status == "failed"
    assert log.keitaro_campaign_id is None


async def test_keitaro_error_response_contains_underlying_text(client, respx_mock):
    respx_mock.get(f"{KEITARO}/offers/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "Offer A", "state": "active"})
    )
    respx_mock.get(f"{KEITARO}/domains").mock(
        return_value=httpx.Response(200, json=[{"id": 5, "name": "example.com"}])
    )
    respx_mock.get(f"{KEITARO}/groups").mock(
        return_value=httpx.Response(200, json=[{"id": 7, "name": "FORTESTS"}])
    )
    respx_mock.get(f"{KEITARO}/traffic_sources").mock(
        return_value=httpx.Response(200, json=[{"id": 8, "name": "FORTESTS"}])
    )
    respx_mock.get(f"{KEITARO}/streams_actions").mock(
        return_value=httpx.Response(200, json=[{"key": "http"}])
    )
    respx_mock.post(f"{KEITARO}/campaigns").mock(
        return_value=httpx.Response(408, text="upstream timeout")
    )

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 502, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "KEITARO_API_ERROR"
    assert "HTTP 408" in detail["message"]
    assert "POST /campaigns" in detail["message"]
    assert "upstream timeout" in detail["message"]
    assert detail["keitaro_status"] == 408
    assert detail["keitaro_method"] == "POST"
    assert detail["keitaro_path"] == "/campaigns"
    assert detail["details"] == "upstream timeout"


async def test_validation_error_from_service_creates_nothing(client, respx_mock):
    respx_mock.get(f"{KEITARO}/offers/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "Offer A", "state": "inactive"})
    )

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "CAMPAIGN_CREATION_ERROR"

    async with SessionLocal() as db:
        assert (await db.scalars(select(Campaign))).all() == []
        log = (await db.scalars(select(CampaignCreationLog))).one()
    assert log.status == "failed"


async def test_unexpected_creation_error_is_500_and_logged(
    client, monkeypatch, main_app
):
    async def boom(*args, **kwargs):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr(service_module, "create_campaign", boom)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local_client:
        response = await local_client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 500, response.text
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"

    async with SessionLocal() as db:
        log = (await db.scalars(select(CampaignCreationLog))).one()
    assert log.status == "failed"
    assert "unexpected boom" in log.error_message


async def test_local_persistence_error_on_campaign_skips_streams(client, respx_mock, monkeypatch, main_app):
    mock_keitaro_context(respx_mock)
    stream_calls = {"n": 0}

    def handler(request):
        stream_calls["n"] += 1
        return httpx.Response(200, json={"id": 9001})

    _streams_route(respx_mock, handler)

    async def boom(*args, **kwargs):
        raise main_app.LocalPersistenceError("db is down", campaign={"id": 123})

    monkeypatch.setattr(service_module.repo, "save_campaign", boom)

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 500, response.text
    assert response.json()["detail"]["code"] == "LOCAL_PERSISTENCE_ERROR"
    assert stream_calls["n"] == 0

    async with SessionLocal() as db:
        assert (await db.scalars(select(Campaign))).all() == []
        log = (await db.scalars(select(CampaignCreationLog))).one()
    assert log.status == "partial"
    assert log.keitaro_campaign_id == 123
    assert "LOCAL_PERSISTENCE_ERROR" in log.error_message


async def test_local_persistence_error_on_streams_keeps_campaign(client, respx_mock, monkeypatch, main_app):
    mock_keitaro_context(respx_mock)
    ids = iter([9001, 9002])
    _streams_route(respx_mock, lambda request: httpx.Response(200, json={"id": next(ids)}))

    async def boom(*args, **kwargs):
        raise main_app.LocalPersistenceError("db is down")

    monkeypatch.setattr(service_module.repo, "save_streams_and_offers", boom)

    response = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)

    assert response.status_code == 500, response.text
    assert response.json()["detail"]["code"] == "LOCAL_PERSISTENCE_ERROR"

    async with SessionLocal() as db:
        campaigns = (await db.scalars(select(Campaign))).all()
        streams = (await db.scalars(select(Stream))).all()
        log = (await db.scalars(select(CampaignCreationLog))).one()

    assert [c.keitaro_id for c in campaigns] == [123]
    assert streams == []
    assert log.status == "partial"
    assert log.keitaro_campaign_id == 123


async def test_repeated_same_response_does_not_duplicate(client, respx_mock):
    mock_keitaro_context(respx_mock)
    ids = iter([9001, 9002, 9001, 9002])
    _streams_route(respx_mock, lambda request: httpx.Response(200, json={"id": next(ids)}))

    first_create = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)
    assert first_create.status_code == 200
    async with SessionLocal() as db:
        first_updated_at = (await db.scalars(select(Campaign))).one().updated_at

    second_create = await client.post("/api/campaigns/create", json=CREATE_PAYLOAD)
    assert second_create.status_code == 200

    async with SessionLocal() as db:
        campaign = (await db.scalars(select(Campaign))).one()
        streams = (await db.scalars(select(Stream))).all()
        offers = (await db.scalars(select(Offer))).all()
        second_updated_at = campaign.updated_at

    assert len(streams) == 2
    assert len(offers) == 1
    assert second_updated_at > first_updated_at
