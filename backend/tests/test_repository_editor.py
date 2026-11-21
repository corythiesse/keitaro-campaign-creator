"""Repository/editor persistence tests (plan §10.2, §10.6)."""
import pytest
from sqlalchemy import select

from app import repositories as repo
from app.errors import RevisionConflictError
from app.models import Offer, Stream

from .editor_helpers import (
    remote_offer,
    remote_stream,
    seed_campaign,
    seed_offer,
    seed_stream,
)


async def _fresh(db, campaign):
    await db.commit()
    return await repo.get_campaign(db, campaign.id)


async def test_create_offer_and_find_including_deleted(session):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)

    created = await repo.create_offer(session, stream, 42, name="New offer", state="active")
    await session.commit()

    assert created.origin == "local"
    assert created.base_share is None
    assert (await repo.find_offer(session, stream.id, 42)).id == created.id

    created.is_deleted = True
    await session.commit()
    assert (await repo.find_offer(session, stream.id, 42)).id == created.id
    assert (await session.scalars(select(Offer))).all() != []


async def test_apply_remote_snapshot_creates_rows_and_baseline(session):
    campaign = await seed_campaign(session)
    warnings = await repo.apply_remote_snapshot(
        session,
        campaign,
        [remote_stream(9001, offers=[remote_offer(42, offer_stream_id=555)])],
        {42: "Offer A"},
    )
    await session.commit()

    fresh = await _fresh(session, campaign)
    assert warnings == []
    assert len(fresh.streams) == 1
    stream = fresh.streams[0]
    assert stream.origin == "keitaro"
    assert stream.keitaro_updated_at == "2026-02-01T00:00:00Z"
    assert stream.base_state == stream.state == "active"

    offer = stream.offers[0]
    assert offer.origin == "keitaro"
    assert offer.name == "Offer A"
    assert offer.share == offer.base_share == 100
    assert offer.base_state == offer.state == "active"
    assert offer.keitaro_offer_stream_id == 555
    assert repo.campaign_has_local_changes(fresh) is False


async def test_apply_remote_snapshot_is_idempotent(session):
    campaign = await seed_campaign(session)
    snapshot = [remote_stream(9001, offers=[remote_offer(42)])]

    await repo.apply_remote_snapshot(session, campaign, snapshot, {42: "Offer A"})
    await session.commit()
    await repo.apply_remote_snapshot(session, campaign, snapshot, {42: "Offer A"})
    await session.commit()

    assert len((await session.scalars(select(Stream))).all()) == 1
    assert len((await session.scalars(select(Offer))).all()) == 1


async def test_apply_remote_snapshot_updates_existing_fields(session):
    campaign = await seed_campaign(session)
    await repo.apply_remote_snapshot(
        session, campaign, [remote_stream(9001, offers=[remote_offer(42, share=100)])], {42: "Old"}
    )
    await session.commit()

    await repo.apply_remote_snapshot(
        session,
        campaign,
        [remote_stream(9001, name="Renamed", offers=[remote_offer(42, share=70)])],
        {42: "New name"},
    )
    await session.commit()

    fresh = await _fresh(session, campaign)
    stream = fresh.streams[0]
    offer = stream.offers[0]
    assert stream.name == "Renamed"
    assert offer.name == "New name"
    assert offer.share == offer.base_share == 70
    assert repo.campaign_has_local_changes(fresh) is False


async def test_apply_remote_snapshot_soft_deletes_missing_stream(session):
    campaign = await seed_campaign(session)
    await repo.apply_remote_snapshot(
        session, campaign, [remote_stream(9001, offers=[remote_offer(42)])], {42: "Offer A"}
    )
    await session.commit()

    await repo.apply_remote_snapshot(session, campaign, [], {})
    await session.commit()

    fresh = await _fresh(session, campaign)
    stream = (await session.scalars(select(Stream))).one()
    assert stream.is_deleted is True
    assert stream.state == "deleted"
    assert stream.base_is_deleted is True
    assert stream.base_state == "deleted"
    assert len(stream.offers) == 1
    assert stream.offers[0].is_deleted is True
    assert stream.offers[0].base_is_deleted is True
    assert fresh.streams[0].id == stream.id


async def test_apply_remote_snapshot_soft_deletes_missing_offer(session):
    campaign = await seed_campaign(session)
    await repo.apply_remote_snapshot(
        session, campaign, [remote_stream(9001, offers=[remote_offer(42), remote_offer(43)])], {}
    )
    await session.commit()

    await repo.apply_remote_snapshot(session, campaign, [remote_stream(9001, offers=[remote_offer(42)])], {})
    await session.commit()

    offers = {offer.keitaro_id: offer for offer in (await session.scalars(select(Offer))).all()}
    assert set(offers) == {42, 43}
    assert offers[43].is_deleted is True
    assert offers[43].base_is_deleted is True
    assert offers[42].is_deleted is False


async def test_apply_remote_snapshot_missing_offers_key_keeps_offers(session):
    """A partial stream payload must not be read as "the stream has no offers"."""
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=42, share=100)
    await session.commit()

    partial_stream = remote_stream(9001)
    partial_stream.pop("offers")
    warnings = await repo.apply_remote_snapshot(session, campaign, [partial_stream], {})
    await session.commit()

    fresh = await _fresh(session, campaign)
    assert fresh.streams[0].offers[0].is_deleted is False
    assert fresh.streams[0].offers[0].base_is_deleted is False
    assert any("оффер" in warning.lower() for warning in warnings)


async def test_apply_remote_snapshot_empty_returns_warning(session):
    campaign = await seed_campaign(session)
    warnings = await repo.apply_remote_snapshot(session, campaign, [], {})

    assert warnings
    await session.commit()


async def test_reset_to_baseline_restores_state_and_removes_local_rows(session):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    kept = await seed_offer(session, campaign, stream, keitaro_id=42, share=100)
    local = await seed_offer(
        session,
        campaign,
        stream,
        keitaro_id=43,
        share=0,
        origin="local",
        keitaro_offer_stream_id=None,
    )
    local.base_share = None
    local.base_state = None

    # Local edits:
    kept.share = 30
    kept.is_deleted = True
    kept.is_pinned = True
    kept.pinned_share = 30
    stream.is_deleted = True
    await session.commit()

    loaded = await _fresh(session, campaign)
    assert repo.campaign_has_local_changes(loaded) is True

    await repo.reset_to_baseline(session, loaded)
    await session.commit()

    fresh = await _fresh(session, campaign)
    fresh_stream = fresh.streams[0]
    offers = {offer.keitaro_id: offer for offer in fresh_stream.offers}
    assert set(offers) == {42}
    assert offers[42].share == 100
    assert offers[42].is_deleted is False
    assert offers[42].is_pinned is False
    assert offers[42].pinned_share is None
    assert fresh_stream.is_deleted is False
    assert repo.campaign_has_local_changes(fresh) is False


async def test_has_local_changes_tracks_share_and_state(session):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    offer = await seed_offer(session, campaign, stream, keitaro_id=42, share=100)
    await session.commit()

    fresh = await _fresh(session, campaign)
    assert repo.campaign_has_local_changes(fresh) is False

    offer.share = 50
    await session.commit()
    assert repo.campaign_has_local_changes(await _fresh(session, campaign)) is True

    offer.share = 100
    offer.state = "disabled"
    await session.commit()
    assert repo.campaign_has_local_changes(await _fresh(session, campaign)) is True


async def test_commit_stream_baseline_sets_baseline_and_offer_stream_id(session):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    offer = await seed_offer(
        session, campaign, stream, keitaro_id=42, share=60, origin="local", keitaro_offer_stream_id=None
    )
    offer.base_share = None
    offer.base_state = None
    await session.commit()

    loaded = await _fresh(session, campaign)
    loaded_stream = loaded.streams[0]
    await repo.commit_stream_baseline(
        session,
        loaded,
        loaded_stream,
        {
            "id": 9001,
            "state": "active",
            "updated_at": "2026-03-01T00:00:00Z",
            "offers": [{"id": 777, "offer_id": 42, "share": 60, "state": "active"}],
        },
    )
    await session.commit()

    fresh = await _fresh(session, campaign)
    assert fresh.last_pushed_at is not None
    fresh_stream = fresh.streams[0]
    assert fresh_stream.keitaro_updated_at == "2026-03-01T00:00:00Z"
    assert fresh_stream.base_state == fresh_stream.state == "active"
    fresh_offer = fresh_stream.offers[0]
    assert fresh_offer.origin == "keitaro"
    assert fresh_offer.keitaro_offer_stream_id == 777
    assert fresh_offer.base_share == fresh_offer.share == 60
    assert repo.campaign_has_local_changes(fresh) is False


async def test_stream_level_drift_is_not_a_local_change(session):
    """Streams are not editable: only offers make a campaign dirty."""
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=42)
    await session.commit()

    loaded = await _fresh(session, campaign)
    loaded.streams[0].is_deleted = True
    loaded.streams[0].state = "deleted"
    await session.commit()

    assert repo.campaign_has_local_changes(await _fresh(session, campaign)) is False


async def test_bump_revision_is_compare_and_swap(session):
    campaign = await seed_campaign(session, revision=0)
    await session.commit()

    await repo.bump_revision(session, campaign, 0)
    await session.commit()
    assert campaign.revision == 1

    with pytest.raises(RevisionConflictError):
        await repo.bump_revision(session, campaign, 0)


async def test_soft_deleted_stream_keeps_offers(session):
    campaign = await seed_campaign(session)
    stream = await seed_stream(session, campaign, keitaro_id=9001)
    await seed_offer(session, campaign, stream, keitaro_id=42)
    await session.commit()

    loaded = await _fresh(session, campaign)
    loaded.streams[0].is_deleted = True
    await session.commit()

    assert len((await session.scalars(select(Offer))).all()) == 1
    assert (await session.scalars(select(Stream))).one().is_deleted is True
