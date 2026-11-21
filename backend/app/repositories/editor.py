"""Editor working-state, baseline and revision operations."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..changes import campaign_has_local_changes as _campaign_has_local_changes
from ..errors import RevisionConflictError
from ..models import Campaign, Offer, Stream, ORIGIN_KEITARO, ORIGIN_LOCAL
from ..utils import as_int, as_str
from .campaigns import get_campaign
from .mapping import apply_offer_snapshot, apply_stream_snapshot, now


async def find_offer(db: AsyncSession, stream_id: int, keitaro_id: int) -> Offer | None:
    """Find an offer row in a stream, including softly deleted ones."""
    return (
        await db.scalars(
            select(Offer).where(
                Offer.stream_id == stream_id,
                Offer.keitaro_id == keitaro_id,
            )
        )
    ).one_or_none()


async def create_offer(
    db: AsyncSession,
    stream: Stream,
    keitaro_id: int,
    *,
    name: str | None = None,
    state: str = "active",
    share: int | None = None,
) -> Offer:
    """Insert a locally added offer (``origin='local'``) and flush."""
    row = Offer(
        keitaro_id=keitaro_id,
        stream_id=stream.id,
        campaign_id=stream.campaign_id,
        name=name,
        state=state,
        share=share,
        origin=ORIGIN_LOCAL,
        is_deleted=False,
        is_pinned=False,
        base_share=None,
        base_state=None,
        base_is_deleted=False,
    )
    row.stream = stream
    db.add(row)
    await db.flush()
    return row


def touch_stream(stream: Stream) -> None:
    stream.updated_at = now()


def _iter_remote_offers(remote: dict) -> tuple[list[dict], bool]:
    """Return ``(valid_offers, offers_known)`` for one remote stream payload.

    A missing/non-list ``offers`` key, or a list with malformed rows, means the
    payload is partial. In that case offers must not be soft-deleted as missing.
    """
    raw = remote.get("offers")
    if not isinstance(raw, list):
        return [], False
    valid = [
        item
        for item in raw
        if isinstance(item, dict) and as_int(item.get("offer_id")) is not None
    ]
    return valid, len(valid) == len(raw)


async def _reload_campaign_graph(db: AsyncSession, campaign: Campaign) -> Campaign:
    """Return a campaign with streams/offers eagerly loaded (safe for async)."""
    fresh = await get_campaign(db, campaign.id, populate_existing=True)
    return fresh or campaign


async def apply_remote_snapshot(
    db: AsyncSession,
    campaign: Campaign,
    remote_streams: list[dict],
    offer_names: dict[int, str] | None = None,
) -> list[str]:
    """Apply a Keitaro snapshot: upsert, refresh baseline, soft delete missing rows.

    Rows that vanished from the snapshot are never deleted physically: they are
    marked ``is_deleted`` and ``base_is_deleted`` so the change is visible and
    revertible. Locally added rows (``origin='local'``) are left untouched.
    """
    warnings: list[str] = []
    offer_names = offer_names or {}
    campaign = await _reload_campaign_graph(db, campaign)

    existing = {stream.keitaro_id: stream for stream in campaign.streams}
    offers_by_stream: dict[int, dict[int, Offer]] = {
        stream.id: {offer.keitaro_id: offer for offer in stream.offers}
        for stream in campaign.streams
    }
    seen_streams: set[int] = set()

    for remote in remote_streams or []:
        if not isinstance(remote, dict):
            continue
        sid = as_int(remote.get("id"))
        if sid is None:
            continue

        stream = existing.get(sid)
        if stream is None:
            stream = Stream(
                keitaro_id=sid,
                campaign_id=campaign.id,
                name=f"Stream {sid}",
                origin=ORIGIN_KEITARO,
            )
            stream.campaign = campaign
            apply_stream_snapshot(stream, remote)
            db.add(stream)
            await db.flush()
            existing[sid] = stream
            offers_by_stream[stream.id] = {}
        else:
            apply_stream_snapshot(stream, remote)

        seen_streams.add(sid)

        remote_offers, offers_known = _iter_remote_offers(remote)
        if not offers_known:
            warnings.append(
                f"Keitaro не вернул полный список офферов для потока {sid}; "
                "офферы оставлены без изменений"
            )

        known_offers = offers_by_stream.setdefault(stream.id, {})
        seen_offers: set[int] = set()
        for remote_offer in remote_offers:
            oid = as_int(remote_offer.get("offer_id"))
            if oid is None:
                continue

            offer = known_offers.get(oid)
            if offer is None:
                offer = Offer(
                    keitaro_id=oid,
                    stream_id=stream.id,
                    campaign_id=campaign.id,
                    origin=ORIGIN_KEITARO,
                )
                offer.stream = stream
                db.add(offer)
                known_offers[oid] = offer

            apply_offer_snapshot(
                offer,
                share=as_int(remote_offer.get("share")),
                state=as_str(remote_offer.get("state"), 20),
                keitaro_offer_stream_id=as_int(remote_offer.get("id")),
                name=offer_names.get(oid) or offer.name or f"Offer #{oid}",
                raw=remote_offer,
            )
            seen_offers.add(oid)

        if offers_known:
            for offer in known_offers.values():
                if offer.keitaro_id not in seen_offers and offer.origin == ORIGIN_KEITARO:
                    offer.is_deleted = True
                    offer.base_is_deleted = True
                    offer.share = None
                    offer.base_share = None

    for stream in campaign.streams:
        if stream.keitaro_id not in seen_streams and stream.origin == ORIGIN_KEITARO:
            stream.is_deleted = True
            stream.state = "deleted"
            stream.base_state = "deleted"
            stream.base_is_deleted = True
            for offer in stream.offers:
                offer.is_deleted = True
                offer.base_is_deleted = True

    if not remote_streams:
        warnings.append("Keitaro не вернул ни одного потока для этой кампании")

    await db.flush()
    return warnings


async def reset_to_baseline(db: AsyncSession, campaign: Campaign) -> None:
    """Restore the working state from ``base_*`` columns.

    Locally added offers that never reached Keitaro are deleted physically;
    every other row is only reset (soft delete is never undone by deletion).
    """
    campaign = await _reload_campaign_graph(db, campaign)
    for stream in campaign.streams:
        stream.is_deleted = bool(stream.base_is_deleted)
        stream.state = stream.base_state
        stream.updated_at = now()

        for offer in list(stream.offers):
            if offer.origin == ORIGIN_LOCAL and offer.keitaro_offer_stream_id is None:
                stream.offers.remove(offer)
                await db.delete(offer)
                continue
            offer.is_deleted = bool(offer.base_is_deleted)
            offer.state = offer.base_state
            offer.share = offer.base_share
            offer.is_pinned = False
            offer.pinned_share = None
            offer.updated_at = now()

    await db.flush()


async def commit_stream_baseline(
    db: AsyncSession,
    campaign: Campaign,
    stream: Stream,
    response: dict | None,
) -> None:
    """After a successful Keitaro call: baseline for exactly one stream."""
    response = response if isinstance(response, dict) else {}
    remote_offers: dict[int, dict] = {}
    for item in response.get("offers") or []:
        if not isinstance(item, dict):
            continue
        oid = as_int(item.get("offer_id"))
        if oid is not None:
            remote_offers[oid] = item

    remote_state = as_str(response.get("state"), 20)
    if remote_state:
        stream.state = remote_state
    # Keep the freshness marker in sync with the response. When Keitaro omits
    # ``updated_at`` the caller is expected to fetch it; if it is still missing,
    # storing ``None`` disables the REMOTE_CHANGED check instead of comparing
    # against an outdated timestamp forever.
    stream.keitaro_updated_at = as_str(response.get("updated_at"), 32)
    stream.base_state = stream.state
    stream.base_is_deleted = bool(stream.is_deleted)
    stream.origin = ORIGIN_KEITARO
    stream.updated_at = now()

    for offer in stream.offers:
        remote = remote_offers.get(offer.keitaro_id)
        if remote is not None and not offer.is_deleted:
            remote_offer_stream_id = as_int(remote.get("id"))
            if remote_offer_stream_id is not None:
                offer.keitaro_offer_stream_id = remote_offer_stream_id
            remote_share = as_int(remote.get("share"))
            if remote_share is not None:
                offer.share = remote_share
            remote_offer_state = as_str(remote.get("state"), 20)
            if remote_offer_state:
                offer.state = remote_offer_state
        offer.base_share = offer.share
        offer.base_state = offer.state
        offer.base_is_deleted = bool(offer.is_deleted)
        offer.origin = ORIGIN_KEITARO

    campaign.last_pushed_at = now()
    await db.flush()


def campaign_has_local_changes(campaign: Campaign) -> bool:
    """Derived dirty flag: never stored, so it cannot get stuck after errors."""
    return _campaign_has_local_changes(campaign)


async def bump_revision(
    db: AsyncSession,
    campaign: Campaign,
    expected_revision: int | None = None,
) -> None:
    """Increment ``campaign.revision`` using a compare-and-swap when requested."""
    current = campaign.revision or 0
    if expected_revision is None:
        campaign.revision = current + 1
        await db.flush()
        return

    result = await db.execute(
        update(Campaign)
        .where(Campaign.id == campaign.id, Campaign.revision == expected_revision)
        .values(revision=Campaign.revision + 1)
    )
    if result.rowcount != 1:
        raise RevisionConflictError()
    campaign.revision = expected_revision + 1


async def get_stream(db: AsyncSession, stream_id: int) -> Stream | None:
    stmt = (
        select(Stream)
        .where(Stream.id == stream_id)
        .options(
            joinedload(Stream.campaign)
            .selectinload(Campaign.streams)
            .selectinload(Stream.offers),
        )
    )
    return (await db.scalars(stmt)).unique().one_or_none()


async def get_offer(db: AsyncSession, offer_id: int) -> Offer | None:
    stmt = (
        select(Offer)
        .where(Offer.id == offer_id)
        .options(
            joinedload(Offer.stream)
            .joinedload(Stream.campaign)
            .selectinload(Campaign.streams)
            .selectinload(Stream.offers),
        )
    )
    return (await db.scalars(stmt)).unique().one_or_none()
