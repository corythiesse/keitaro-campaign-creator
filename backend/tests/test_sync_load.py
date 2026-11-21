"""Keitaro -> local load tests (plan §10.4)."""
import httpx
from sqlalchemy import select

from app.models import Offer, Stream

from .conftest import KEITARO
from .editor_helpers import remote_offer, remote_stream, seed_campaign, seed_offer, seed_stream


def _mock_load(respx_mock, campaign_keitaro_id, streams, offers=None):
    respx_mock.get(f"{KEITARO}/campaigns/{campaign_keitaro_id}/streams").mock(
        return_value=httpx.Response(200, json=streams)
    )
    respx_mock.get(f"{KEITARO}/offers").mock(
        return_value=httpx.Response(200, json=offers if offers is not None else [])
    )


async def _load(client, campaign_id, force=None):
    payload = {} if force is None else {"force": force}
    return await client.post(f"/api/campaigns/{campaign_id}/sync/load", json=payload)


async def test_load_creates_streams_and_offers(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(42, offer_stream_id=555)])],
        [{"id": 42, "name": "Offer A", "state": "active"}],
    )

    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_local_changes"] is False
    assert body["last_loaded_at"] is not None
    assert body["revision"] == 1
    assert [s["keitaro_id"] for s in body["streams"]] == [9001]
    offer = body["streams"][0]["offers"][0]
    assert offer["name"] == "Offer A"
    assert offer["share"] == 100
    assert offer["keitaro_offer_stream_id"] == 555
    assert offer["origin"] == "keitaro"


async def test_load_updates_stream_fields(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await seed_stream(session, campaign, keitaro_id=9001, name="Old name")
    await session.commit()
    remote = remote_stream(9001)
    remote["comments"] = "main flow"
    _mock_load(respx_mock, campaign.keitaro_id, [remote])

    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    stream = response.json()["streams"][0]
    assert stream["name"] == "Default - Offer"
    assert stream["comments"] == "main flow"


async def test_load_adds_new_offer(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(41, share=60), remote_offer(42, share=40)])],
        [{"id": 42, "name": "Offer B"}],
    )

    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    offers = {o["keitaro_id"]: o for o in response.json()["streams"][0]["offers"]}
    assert set(offers) == {41, 42}
    assert offers[42]["name"] == "Offer B"
    assert offers[42]["share"] == 40


async def test_load_updates_share_and_state(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(41, share=100, state="disabled")])],
    )

    response = await _load(client, campaign.id)

    offer = response.json()["streams"][0]["offers"][0]
    assert offer["state"] == "disabled"
    assert response.json()["has_local_changes"] is False


async def test_load_soft_deletes_missing_stream(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await seed_stream(session, campaign, keitaro_id=9001)
    await seed_stream(session, campaign, keitaro_id=9002)
    await session.commit()
    _mock_load(respx_mock, campaign.keitaro_id, [remote_stream(9001)])

    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    streams = {s["keitaro_id"]: s for s in response.json()["streams"]}
    assert streams[9002]["is_deleted"] is True
    assert len((await session.scalars(select(Stream))).all()) == 2


async def test_load_soft_deletes_missing_offer(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=41)
    await seed_offer(session, campaign, stream, keitaro_id=42)
    await session.commit()
    _mock_load(
        respx_mock, campaign.keitaro_id, [remote_stream(9001, offers=[remote_offer(41)])]
    )

    response = await _load(client, campaign.id)

    offers = {o["keitaro_id"]: o for o in response.json()["streams"][0]["offers"]}
    assert offers[42]["is_deleted"] is True
    assert len((await session.scalars(select(Offer))).all()) == 2


async def test_load_empty_response_marks_all_deleted_with_warning(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await seed_stream(session, campaign, keitaro_id=9001)
    await session.commit()
    _mock_load(respx_mock, campaign.keitaro_id, [])

    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["warnings"]
    assert body["streams"][0]["is_deleted"] is True


async def test_load_is_idempotent(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(42)])],
        [{"id": 42, "name": "Offer A"}],
    )

    await _load(client, campaign.id)
    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    assert len((await session.scalars(select(Stream))).all()) == 1
    assert len((await session.scalars(select(Offer))).all()) == 1
    assert response.json()["revision"] == 2


async def test_load_with_local_changes_requires_force(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    offer = await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()
    offer.share = 30
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(41, share=100)])],
    )

    response = await _load(client, campaign.id)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "LOCAL_CHANGES_PENDING"
    assert respx_mock.calls.call_count == 0

    session.expire_all()
    assert (await session.scalars(select(Offer))).one().share == 30


async def test_load_with_force_replaces_local_changes(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    offer = await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()
    offer.share = 30
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(41, share=100)])],
    )

    response = await _load(client, campaign.id, force=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_local_changes"] is False
    assert body["streams"][0]["offers"][0]["share"] == 100


async def test_load_keitaro_failure_does_not_touch_db(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001, name="Original")
    await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()

    respx_mock.get(f"{KEITARO}/campaigns/{campaign.keitaro_id}/streams").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    response = await _load(client, campaign.id)

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "KEITARO_API_ERROR"

    session.expire_all()
    assert (await session.scalars(select(Stream))).one().name == "Original"
    assert (await session.scalars(select(Offer))).one().share == 100


async def test_load_offer_names_failure_does_not_touch_db(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await seed_stream(session, campaign, keitaro_id=9001, name="Original")
    await session.commit()
    respx_mock.get(f"{KEITARO}/campaigns/{campaign.keitaro_id}/streams").mock(
        return_value=httpx.Response(200, json=[remote_stream(9001)])
    )
    respx_mock.get(f"{KEITARO}/offers").mock(return_value=httpx.Response(500, json={"error": "boom"}))

    response = await _load(client, campaign.id)

    assert response.status_code == 502
    session.expire_all()
    assert (await session.scalars(select(Stream))).one().name == "Original"


async def test_load_non_list_streams_is_rejected_without_changes(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await seed_stream(session, campaign, keitaro_id=9001, name="Original")
    await session.commit()

    respx_mock.get(f"{KEITARO}/campaigns/{campaign.keitaro_id}/streams").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx_mock.get(f"{KEITARO}/offers").mock(return_value=httpx.Response(200, json=[]))

    response = await _load(client, campaign.id)

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "KEITARO_INVALID_RESPONSE"
    session.expire_all()
    assert (await session.scalars(select(Stream))).one().is_deleted is False


async def test_load_stream_without_id_is_rejected(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await seed_stream(session, campaign, keitaro_id=9001, name="Original")
    await session.commit()

    respx_mock.get(f"{KEITARO}/campaigns/{campaign.keitaro_id}/streams").mock(
        return_value=httpx.Response(200, json=[{"name": "No id"}])
    )
    respx_mock.get(f"{KEITARO}/offers").mock(return_value=httpx.Response(200, json=[]))

    response = await _load(client, campaign.id)

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "KEITARO_INVALID_RESPONSE"
    session.expire_all()
    assert (await session.scalars(select(Stream))).one().is_deleted is False


async def test_load_unknown_offer_gets_fallback_name(client, session, respx_mock):
    campaign = await seed_campaign(session)
    await session.commit()
    _mock_load(
        respx_mock,
        campaign.keitaro_id,
        [remote_stream(9001, offers=[remote_offer(99)])],
        [],
    )

    response = await _load(client, campaign.id)

    assert response.status_code == 200, response.text
    assert response.json()["streams"][0]["offers"][0]["name"] == "Offer #99"
