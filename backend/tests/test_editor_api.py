"""Editor API tests for local mutations (plan §10.3, §10.6)."""
import httpx
from sqlalchemy import event, select

from app.database import engine
from app.models import Offer

from .conftest import KEITARO
from .editor_helpers import seed_campaign, seed_offer, seed_stream


async def _seed_three_offers(db):
    campaign = await seed_campaign(db)
    stream = await seed_stream(db, campaign, keitaro_id=9001)
    first = await seed_offer(db, campaign, stream, keitaro_id=41, name="A", share=33)
    second = await seed_offer(db, campaign, stream, keitaro_id=42, name="B", share=33)
    third = await seed_offer(db, campaign, stream, keitaro_id=43, name="C", share=34)
    await db.commit()
    return campaign, stream, first, second, third


async def _offers_by_keitaro_id(db):
    return {
        offer.keitaro_id: offer
        for offer in (
            await db.scalars(select(Offer).execution_options(populate_existing=True))
        ).all()
    }


async def test_detail_contains_editor_fields(client, session):
    campaign, stream, first, *_ = await _seed_three_offers(session)

    response = await client.get(f"/api/campaigns/{campaign.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_local_changes"] is False
    assert body["revision"] == 0
    assert body["last_loaded_at"] is None
    assert body["warnings"] == []
    assert body["streams"][0]["is_deleted"] is False
    assert body["streams"][0]["origin"] == "keitaro"
    offer = body["streams"][0]["offers"][0]
    assert offer["is_pinned"] is False
    assert offer["is_deleted"] is False
    assert offer["origin"] == "keitaro"


async def test_detail_not_found(client):
    response = await client.get("/api/campaigns/999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


async def test_add_offer_recalculates_weights(client, session, respx_mock):
    campaign, stream, *_ = await _seed_three_offers(session)
    respx_mock.get(f"{KEITARO}/offers/44").mock(
        return_value=httpx.Response(200, json={"id": 44, "name": "Offer D", "state": "active"})
    )

    response = await client.post(f"/api/streams/{stream.id}/offers", json={"offer_id": 44})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_local_changes"] is True
    assert body["revision"] == 1
    offers = {o["keitaro_id"]: o for o in body["streams"][0]["offers"]}
    assert set(offers) == {41, 42, 43, 44}
    assert offers[44]["name"] == "Offer D"
    assert offers[44]["origin"] == "local"
    assert sum(o["share"] for o in offers.values()) == 100


async def test_add_duplicate_offer_is_conflict(client, session, respx_mock):
    campaign, stream, *_ = await _seed_three_offers(session)

    response = await client.post(f"/api/streams/{stream.id}/offers", json={"offer_id": 41})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "OFFER_ALREADY_IN_STREAM"
    assert respx_mock.calls.call_count == 0


async def test_add_offer_to_deleted_stream_is_conflict(client, session):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001, is_deleted=True)
    await session.commit()

    response = await client.post(f"/api/streams/{stream.id}/offers", json={"offer_id": 44})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STREAM_DELETED"


async def test_add_inactive_offer_is_rejected(client, session, respx_mock):
    campaign, stream, *_ = await _seed_three_offers(session)
    respx_mock.get(f"{KEITARO}/offers/44").mock(
        return_value=httpx.Response(200, json={"id": 44, "name": "Offer D", "state": "disabled"})
    )

    response = await client.post(f"/api/streams/{stream.id}/offers", json={"offer_id": 44})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "OFFER_NOT_ACTIVE"
    assert 44 not in (await _offers_by_keitaro_id(session))


async def test_add_missing_stream_is_404(client):
    response = await client.post("/api/streams/999/offers", json={"offer_id": 44})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "STREAM_NOT_FOUND"


async def test_patch_offer_soft_delete_distributes_remaining_weight(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)

    response = await client.patch(f"/api/offers/{first.id}", json={"is_deleted": True})

    assert response.status_code == 200, response.text
    body = response.json()
    offers = {o["keitaro_id"]: o for o in body["streams"][0]["offers"]}
    assert offers[41]["is_deleted"] is True
    assert offers[42]["share"] == 50
    assert offers[43]["share"] == 50
    assert sum(o["share"] for o in offers.values() if not o["is_deleted"]) == 100


async def test_patch_offer_restore_returns_to_distribution(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)
    await client.patch(f"/api/offers/{first.id}", json={"is_deleted": True})

    response = await client.patch(f"/api/offers/{first.id}", json={"is_deleted": False})

    assert response.status_code == 200, response.text
    offers = {o["keitaro_id"]: o for o in response.json()["streams"][0]["offers"]}
    assert offers[41]["is_deleted"] is False
    assert offers[41]["state"] == "active"
    assert sum(o["share"] for o in offers.values()) == 100


async def test_patch_offer_pin(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)

    response = await client.patch(
        f"/api/offers/{first.id}", json={"is_pinned": True, "pinned_share": 50}
    )

    assert response.status_code == 200, response.text
    offers = {o["keitaro_id"]: o for o in response.json()["streams"][0]["offers"]}
    assert offers[41]["is_pinned"] is True
    assert offers[41]["pinned_share"] == 50
    assert offers[41]["share"] == 50
    assert offers[42]["share"] == 25
    assert offers[43]["share"] == 25


async def test_patch_offer_pin_overflow_does_not_change_db(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)
    await client.patch(f"/api/offers/{first.id}", json={"is_pinned": True, "pinned_share": 50})

    response = await client.patch(
        f"/api/offers/{second.id}", json={"is_pinned": True, "pinned_share": 60}
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PINNED_SHARE_OVERFLOW"

    offers = await _offers_by_keitaro_id(session)
    assert offers[42].is_pinned is False
    assert offers[42].pinned_share is None
    assert offers[42].share == 25


async def test_patch_offer_unpin_rebalances(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)
    await client.patch(f"/api/offers/{first.id}", json={"is_pinned": True, "pinned_share": 50})

    response = await client.patch(f"/api/offers/{first.id}", json={"is_pinned": False})

    assert response.status_code == 200, response.text
    offers = {o["keitaro_id"]: o for o in response.json()["streams"][0]["offers"]}
    assert offers[41]["is_pinned"] is False
    assert offers[41]["pinned_share"] is None
    assert [offers[key]["share"] for key in (41, 42, 43)] == [33, 33, 34]


async def test_patch_offer_does_not_reload_the_whole_campaign(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)
    selects: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = await client.patch(f"/api/offers/{first.id}", json={"is_deleted": True})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    assert response.status_code == 200, response.text
    # get_offer + campaign/streams/offers graph; no per-stream lazy loads.
    assert len(selects) <= 4, selects


async def test_patch_missing_offer_is_404(client):
    response = await client.patch("/api/offers/999", json={"is_deleted": True})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "OFFER_NOT_FOUND"


async def test_stream_deletion_endpoint_is_removed(client, session):
    campaign, stream, *_ = await _seed_three_offers(session)
    stream_id = stream.id
    stream_type = type(stream)

    response = await client.patch(f"/api/streams/{stream_id}", json={"is_deleted": True})

    assert response.status_code in (404, 405), response.text
    session.expire_all()
    assert (await session.get(stream_type, stream_id)).is_deleted is False


async def test_discard_restores_baseline(client, session):
    campaign, stream, first, second, third = await _seed_three_offers(session)
    await client.patch(f"/api/offers/{first.id}", json={"is_deleted": True})
    await client.patch(f"/api/offers/{second.id}", json={"is_pinned": True, "pinned_share": 30})

    response = await client.post(f"/api/campaigns/{campaign.id}/sync/discard")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_local_changes"] is False
    offers = {o["keitaro_id"]: o for o in body["streams"][0]["offers"]}
    assert offers[41]["is_deleted"] is False
    assert offers[41]["share"] == 33
    assert offers[42]["is_pinned"] is False
    assert offers[42]["share"] == 33
    assert offers[43]["share"] == 34


async def test_patch_offer_rejects_stale_revision(client, session, respx_mock):
    campaign, stream, first, *_ = await _seed_three_offers(session)

    response = await client.patch(
        f"/api/offers/{first.id}",
        json={"is_deleted": True, "expected_revision": 99},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert (await _offers_by_keitaro_id(session))[41].is_deleted is False
    assert respx_mock.calls.call_count == 0


async def test_patch_offer_accepts_current_revision(client, session):
    campaign, stream, first, *_ = await _seed_three_offers(session)

    response = await client.patch(
        f"/api/offers/{first.id}",
        json={"is_deleted": True, "expected_revision": campaign.revision},
    )

    assert response.status_code == 200, response.text
    assert response.json()["revision"] == campaign.revision + 1


async def test_add_offer_rejects_stale_revision(client, session, respx_mock):
    campaign, stream, *_ = await _seed_three_offers(session)

    response = await client.post(
        f"/api/streams/{stream.id}/offers",
        json={"offer_id": 44, "expected_revision": 99},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert 44 not in (await _offers_by_keitaro_id(session))
    assert respx_mock.calls.call_count == 0
