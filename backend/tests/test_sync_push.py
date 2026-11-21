"""Push tests: local -> Keitaro, partial success (plan §10.5)."""
import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.services import editor as editor_service
from app.models import Offer, Stream

from .conftest import KEITARO
from .editor_helpers import seed_campaign, seed_offer, seed_stream

UPDATED_AT = "2026-01-01T00:00:00Z"


def _mock_stream_get(respx_mock, stream_id, updated_at=UPDATED_AT):
    return respx_mock.get(f"{KEITARO}/streams/{stream_id}").mock(
        return_value=httpx.Response(200, json={"id": stream_id, "updated_at": updated_at})
    )


async def _push(client, campaign_id, **payload):
    return await client.post(f"/api/campaigns/{campaign_id}/sync/push", json=payload)


async def _dirty_two_offer_stream(db):
    """A clean stream with two offers, then one is soft-deleted locally."""
    campaign = await seed_campaign(db)
    stream = await seed_stream(db, campaign, keitaro_id=9001)
    first = await seed_offer(db, campaign, stream, keitaro_id=41, share=50, keitaro_offer_stream_id=5001)
    second = await seed_offer(db, campaign, stream, keitaro_id=42, share=50, keitaro_offer_stream_id=5002)
    return campaign, stream, first, second


async def _offers(db):
    return {
        offer.keitaro_id: offer
        for offer in (
            await db.scalars(select(Offer).execution_options(populate_existing=True))
        ).all()
    }


async def test_push_sends_payload_and_updates_baseline(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    put_route = respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={
            "id": 9001,
            "state": "active",
            "updated_at": "2026-04-01T00:00:00Z",
            "offers": [{"id": 5001, "offer_id": 41, "share": 100, "state": "active"}],
        })
    )

    response = await _push(client, campaign.id, expected_revision=1)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["results"][0]["status"] == "ok"
    assert body["results"][0]["action"] == "update"
    assert body["campaign"]["has_local_changes"] is False

    import json
    payload = json.loads(put_route.calls[0].request.content)
    assert payload == {"offers": [{"offer_id": 41, "share": 100, "state": "active"}]}

    offers = await _offers(session)
    assert offers[41].base_share == offers[41].share == 100
    assert offers[42].is_deleted is True
    assert offers[42].base_is_deleted is True


async def test_push_two_streams_both_succeed(client, session, respx_mock):
    campaign = await seed_campaign(session)
    first_stream = await seed_stream(session, campaign, keitaro_id=9001)
    second_stream = await seed_stream(session, campaign, keitaro_id=9002, name="Other")
    await seed_offer(session, campaign, first_stream, keitaro_id=41, share=50)
    await seed_offer(session, campaign, first_stream, keitaro_id=42, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=51, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=52, share=50)
    await session.commit()
    await client.patch(f"/api/offers/{await seed_offer_id(session, 42)}", json={"is_deleted": True})
    await client.patch(f"/api/offers/{await seed_offer_id(session, 52)}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    _mock_stream_get(respx_mock, 9002)
    put_first = respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "state": "active", "offers": []})
    )
    put_second = respx_mock.put(f"{KEITARO}/streams/9002").mock(
        return_value=httpx.Response(200, json={"id": 9002, "state": "active", "offers": []})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert [r["status"] for r in body["results"]] == ["ok", "ok"]
    assert put_first.called and put_second.called
    assert body["campaign"]["has_local_changes"] is False


async def test_push_partial_success_keeps_failed_stream_dirty(client, session, respx_mock):
    campaign = await seed_campaign(session)
    first_stream = await seed_stream(session, campaign, keitaro_id=9001)
    second_stream = await seed_stream(session, campaign, keitaro_id=9002, name="Other")
    await seed_offer(session, campaign, first_stream, keitaro_id=41, share=50)
    await seed_offer(session, campaign, first_stream, keitaro_id=42, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=51, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=52, share=50)
    await session.commit()
    await client.patch(f"/api/offers/{await seed_offer_id(session, 42)}", json={"is_deleted": True})
    await client.patch(f"/api/offers/{await seed_offer_id(session, 52)}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    _mock_stream_get(respx_mock, 9002)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "state": "active", "offers": []})
    )
    respx_mock.put(f"{KEITARO}/streams/9002").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is False
    assert body["code"] == "PARTIAL_SYNC"
    assert [r["status"] for r in body["results"]] == ["ok", "error"]
    assert body["results"][1]["code"] == "KEITARO_API_ERROR"
    assert body["campaign"]["has_local_changes"] is True

    offers = await _offers(session)
    assert offers[42].base_is_deleted is True
    assert offers[52].base_is_deleted is False


async def test_push_failure_first_still_processes_next_stream(client, session, respx_mock):
    campaign = await seed_campaign(session)
    first_stream = await seed_stream(session, campaign, keitaro_id=9001)
    second_stream = await seed_stream(session, campaign, keitaro_id=9002, name="Other")
    await seed_offer(session, campaign, first_stream, keitaro_id=41, share=50)
    await seed_offer(session, campaign, first_stream, keitaro_id=42, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=51, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=52, share=50)
    await session.commit()
    await client.patch(f"/api/offers/{await seed_offer_id(session, 42)}", json={"is_deleted": True})
    await client.patch(f"/api/offers/{await seed_offer_id(session, 52)}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    _mock_stream_get(respx_mock, 9002)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    respx_mock.put(f"{KEITARO}/streams/9002").mock(
        return_value=httpx.Response(200, json={"id": 9002, "state": "active", "offers": []})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is False
    assert [result["status"] for result in body["results"]] == ["error", "ok"]
    assert body["results"][0]["code"] == "KEITARO_API_ERROR"


async def test_push_all_failed_returns_502_and_keeps_baseline(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "SYNC_FAILED"
    assert detail["results"][0]["code"] == "KEITARO_API_ERROR"

    offers = await _offers(session)
    assert offers[42].base_is_deleted is False


async def test_push_retry_skips_successful_streams(client, session, respx_mock):
    campaign = await seed_campaign(session)
    first_stream = await seed_stream(session, campaign, keitaro_id=9001)
    second_stream = await seed_stream(session, campaign, keitaro_id=9002, name="Other")
    await seed_offer(session, campaign, first_stream, keitaro_id=41, share=50)
    await seed_offer(session, campaign, first_stream, keitaro_id=42, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=51, share=50)
    await seed_offer(session, campaign, second_stream, keitaro_id=52, share=50)
    await session.commit()
    await client.patch(f"/api/offers/{await seed_offer_id(session, 42)}", json={"is_deleted": True})
    await client.patch(f"/api/offers/{await seed_offer_id(session, 52)}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    _mock_stream_get(respx_mock, 9002)
    first_put = respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "state": "active", "offers": []})
    )
    second_put = respx_mock.put(f"{KEITARO}/streams/9002").mock(
        side_effect=[
            httpx.Response(500, json={"error": "boom"}),
            httpx.Response(200, json={"id": 9002, "state": "active", "offers": []}),
        ]
    )

    first = await _push(client, campaign.id)
    assert first.status_code == 200
    assert first.json()["success"] is False

    second = await _push(client, campaign.id)

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["success"] is True
    assert [r["status"] for r in body["results"]] == ["skipped", "ok"]
    assert first_put.call_count == 1
    assert second_put.call_count == 2
    assert body["campaign"]["has_local_changes"] is False


async def test_push_includes_restored_offer(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    restored = await seed_offer(
        session, campaign, stream, keitaro_id=42, share=None, is_deleted=True
    )
    restored.base_is_deleted = True
    restored.base_share = None
    await session.commit()

    await client.patch(f"/api/offers/{restored.id}", json={"is_deleted": False})

    _mock_stream_get(respx_mock, 9001)
    put_route = respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "state": "active", "offers": []})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    import json
    payload = json.loads(put_route.calls[0].request.content)
    assert {item["offer_id"] for item in payload["offers"]} == {41, 42}


async def test_push_remote_changed_is_not_sent(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001, updated_at="2026-09-09T09:09:09Z")
    put_route = respx_mock.put(f"{KEITARO}/streams/9001")

    response = await _push(client, campaign.id)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "SYNC_FAILED"
    assert detail["results"][0]["code"] == "REMOTE_CHANGED"
    assert not put_route.called


async def test_push_updates_offer_stream_id_from_response(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    first.keitaro_offer_stream_id = None
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={
            "id": 9001,
            "state": "active",
            "offers": [{"id": 7777, "offer_id": 41, "share": 100, "state": "active"}],
        })
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    assert (await _offers(session))[41].keitaro_offer_stream_id == 7777


async def test_push_baseline_from_response_share(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={
            "id": 9001,
            "state": "active",
            "offers": [{"id": 5001, "offer_id": 41, "share": 87, "state": "active"}],
        })
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    offer = (await _offers(session))[41]
    assert offer.share == 87
    assert offer.base_share == 87
    assert response.json()["campaign"]["has_local_changes"] is False


async def test_push_db_failure_after_put_keeps_local_changes(client, session, respx_mock, monkeypatch):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "state": "active", "offers": []})
    )

    async def boom(*args, **kwargs):
        raise SQLAlchemyError("db is down")

    monkeypatch.setattr(editor_service.repo, "commit_stream_baseline", boom)

    response = await _push(client, campaign.id)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["results"][0]["code"] == "LOCAL_PERSISTENCE_ERROR"
    assert (await _offers(session))[42].base_is_deleted is False


async def test_push_empty_stream_sends_empty_offers(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    only = await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()
    await client.patch(f"/api/offers/{only.id}", json={"is_deleted": True})

    _mock_stream_get(respx_mock, 9001)
    put_route = respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={
            "id": 9001,
            "state": "active",
            "updated_at": "2026-04-01T00:00:00Z",
            "offers": [],
        })
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["results"][0]["action"] == "update"
    assert body["campaign"]["has_local_changes"] is False

    import json
    payload = json.loads(put_route.calls[0].request.content)
    assert payload == {"offers": []}

    offer = (await _offers(session))[41]
    assert offer.is_deleted is True
    assert offer.base_is_deleted is True


async def test_push_weight_validation_happens_before_http(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    first = await seed_offer(session, campaign, stream, keitaro_id=41, share=60, origin="local")
    second = await seed_offer(session, campaign, stream, keitaro_id=42, share=50, origin="local")
    first.is_pinned = True
    first.pinned_share = 60
    second.is_pinned = True
    second.pinned_share = 50
    await session.commit()

    response = await _push(client, campaign.id)

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "WEIGHT_VALIDATION_ERROR"
    assert detail["streams"][0]["code"] == "PINNED_SHARE_OVERFLOW"
    assert respx_mock.calls.call_count == 0


async def test_push_revision_conflict(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()

    response = await _push(client, campaign.id, expected_revision=99)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert respx_mock.calls.call_count == 0


async def test_push_without_changes_skips_everything(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["results"] == [
        {"stream_id": stream.id, "keitaro_id": 9001, "status": "skipped", "action": None,
         "code": None, "message": None}
    ]
    assert respx_mock.calls.call_count == 0


async def test_push_missing_campaign_is_404(client):
    response = await _push(client, 999)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


async def test_push_increments_revision_and_invalidates_other_tabs(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    patched = await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})
    revision_before_push = patched.json()["revision"]

    _mock_stream_get(respx_mock, 9001)
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "state": "active", "offers": []})
    )

    response = await _push(client, campaign.id, expected_revision=revision_before_push)

    assert response.status_code == 200, response.text
    assert response.json()["campaign"]["revision"] == revision_before_push + 1

    stale = await _push(client, campaign.id, expected_revision=revision_before_push)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"


async def test_push_refreshes_updated_at_when_put_response_is_minimal(client, session, respx_mock):
    campaign, stream, first, second = await _dirty_two_offer_stream(session)
    await session.commit()
    await client.patch(f"/api/offers/{second.id}", json={"is_deleted": True})

    respx_mock.get(f"{KEITARO}/streams/9001").mock(side_effect=[
        httpx.Response(200, json={"id": 9001, "updated_at": UPDATED_AT}),
        httpx.Response(200, json={"id": 9001, "updated_at": "2026-09-09T09:09:09Z"}),
    ])
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    assert (await _offers(session))[42].base_is_deleted is True
    session.expire_all()
    assert (await session.scalars(select(Stream).where(Stream.keitaro_id == 9001))).one().keitaro_updated_at == (
        "2026-09-09T09:09:09Z"
    )


async def test_push_without_baseline_timestamp_stores_fresh_one(client, session, respx_mock):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001, updated_at=None)
    await seed_offer(session, campaign, stream, keitaro_id=41, share=100)
    await session.commit()
    await client.patch(
        f"/api/offers/{await seed_offer_id(session, 41)}",
        json={"is_deleted": True},
    )

    respx_mock.get(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001, "updated_at": "2026-09-09T09:09:09Z"})
    )
    respx_mock.put(f"{KEITARO}/streams/9001").mock(
        return_value=httpx.Response(200, json={"id": 9001})
    )

    response = await _push(client, campaign.id)

    assert response.status_code == 200, response.text
    session.expire_all()
    assert (await session.scalars(select(Stream).where(Stream.keitaro_id == 9001))).one().keitaro_updated_at == (
        "2026-09-09T09:09:09Z"
    )


async def seed_offer_id(db, keitaro_id):
    """Find a seeded offer id by Keitaro offer id."""
    return (
        await db.scalars(
            select(Offer)
            .where(Offer.keitaro_id == keitaro_id)
            .execution_options(populate_existing=True)
        )
    ).one().id
