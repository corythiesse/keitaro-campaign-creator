"""Campaign/stream snapshot upserts and read queries."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from ..errors import LocalPersistenceError
from ..models import Campaign, CampaignCreationLog, Offer, Stream
from ..utils import as_int, as_str, json_safe
from .mapping import apply_offer_snapshot, apply_stream_snapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_keitaro_id(data: dict) -> int:
    keitaro_id = as_int((data or {}).get("id"))
    if keitaro_id is None:
        raise LocalPersistenceError("В ответе Keitaro отсутствует обязательное поле id", campaign=data)
    return keitaro_id


def _require_stream_id(stream_data: dict) -> int:
    keitaro_id = as_int((stream_data or {}).get("id"))
    if keitaro_id is None:
        raise LocalPersistenceError("В ответе Keitaro отсутствует обязательное поле id потока", campaign=stream_data)
    return keitaro_id


async def save_campaign(
    db: AsyncSession,
    data: dict,
    *,
    log_id: int | None = None,
) -> Campaign:
    """Upsert a campaign by ``keitaro_id`` (flush only, caller commits)."""
    data = data or {}
    try:
        keitaro_id = _require_keitaro_id(data)
        row = (
            await db.scalars(select(Campaign).where(Campaign.keitaro_id == keitaro_id))
        ).one_or_none()
        if row is None:
            row = Campaign(keitaro_id=keitaro_id)
            db.add(row)

        row.name = as_str(data.get("name"), 255) or f"Campaign {keitaro_id}"
        row.alias = as_str(data.get("alias"), 64)
        row.type = as_str(data.get("type"), 32)
        row.state = as_str(data.get("state"), 20)
        row.domain_id = as_int(data.get("domain_id"))
        row.group_id = as_str(data.get("group_id"), 64)
        row.traffic_source_id = as_int(data.get("traffic_source_id"))
        if log_id is not None:
            row.campaign_creation_log_id = log_id
        row.raw = json_safe(data)
        row.updated_at = _now()

        await db.flush()
        return row
    except LocalPersistenceError:
        raise
    except SQLAlchemyError as exc:
        raise LocalPersistenceError(f"Не удалось сохранить кампанию: {exc}", campaign=data) from exc


async def upsert_stream(db: AsyncSession, campaign: Campaign, data: dict) -> Stream:
    """Upsert a stream by ``(campaign_id, keitaro_id)`` and refresh its baseline."""
    data = data or {}
    keitaro_id = _require_stream_id(data)
    row = (
        await db.scalars(
            select(Stream).where(
                Stream.campaign_id == campaign.id,
                Stream.keitaro_id == keitaro_id,
            )
        )
    ).one_or_none()
    if row is None:
        row = Stream(keitaro_id=keitaro_id, campaign_id=campaign.id, name=f"Stream {keitaro_id}")
        db.add(row)

    apply_stream_snapshot(row, data)
    await db.flush()
    return row


async def upsert_stream_offers(
    db: AsyncSession,
    campaign: Campaign,
    stream: Stream,
    offers: list[dict],
) -> None:
    """Upsert offers by ``(stream_id, keitaro_id)``; ``campaign_id`` comes from the stream."""
    for item in offers or []:
        item = item or {}
        keitaro_id = as_int(item.get("offer_id"))
        if keitaro_id is None:
            raise LocalPersistenceError(
                "В снимке оффера отсутствует обязательное поле offer_id",
                campaign=item,
            )

        snapshot = item.get("snapshot") or {}
        row = (
            await db.scalars(
                select(Offer).where(
                    Offer.stream_id == stream.id,
                    Offer.keitaro_id == keitaro_id,
                )
            )
        ).one_or_none()
        if row is None:
            row = Offer(keitaro_id=keitaro_id, stream_id=stream.id, campaign_id=stream.campaign_id)
            db.add(row)

        apply_offer_snapshot(
            row,
            share=as_int(item.get("share")),
            state=as_str(item.get("state") or snapshot.get("state"), 20),
            keitaro_offer_stream_id=as_int(item.get("id")),
            name=snapshot.get("name") or item.get("name"),
            raw=snapshot or item,
        )
        # Always derive campaign ownership from the stream, never from external data.
        row.campaign_id = stream.campaign_id

    await db.flush()


async def save_streams_and_offers(
    db: AsyncSession,
    campaign: Campaign,
    streams: list[dict],
    offers: list[dict],
) -> None:
    """Upsert streams and their offers. No commit: the caller owns the transaction."""
    try:
        saved: dict[int, Stream] = {}
        for data in streams or []:
            stream = await upsert_stream(db, campaign, data)
            saved[stream.keitaro_id] = stream

        for item in offers or []:
            stream_data = (item or {}).get("stream") or {}
            keitaro_stream_id = _require_stream_id(stream_data)
            stream = saved.get(keitaro_stream_id)
            if stream is None:
                stream = (
                    await db.scalars(
                        select(Stream).where(
                            Stream.campaign_id == campaign.id,
                            Stream.keitaro_id == keitaro_stream_id,
                        )
                    )
                ).one_or_none()
            if stream is None:
                raise LocalPersistenceError(
                    f"Поток Keitaro {keitaro_stream_id} не найден среди сохраняемых потоков кампании",
                    campaign={"id": campaign.keitaro_id},
                )
            await upsert_stream_offers(db, campaign, stream, [item])
    except LocalPersistenceError:
        raise
    except SQLAlchemyError as exc:
        raise LocalPersistenceError(f"Не удалось сохранить потоки и офферы: {exc}") from exc


async def get_campaign_by_keitaro_id(db: AsyncSession, keitaro_id: int) -> Campaign | None:
    return (
        await db.scalars(select(Campaign).where(Campaign.keitaro_id == keitaro_id))
    ).one_or_none()


async def get_campaign(
    db: AsyncSession,
    campaign_id: int,
    *,
    populate_existing: bool = False,
) -> Campaign | None:
    stmt = (
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.streams).selectinload(Stream.offers))
    )
    if populate_existing:
        stmt = stmt.execution_options(populate_existing=True)
    return (await db.scalars(stmt)).one_or_none()


async def campaign_exists(db: AsyncSession, campaign_id: int) -> bool:
    return (
        await db.scalars(select(Campaign.id).where(Campaign.id == campaign_id))
    ).one_or_none() is not None


async def list_campaigns(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    state: str | None = None,
) -> list[Campaign]:
    stmt = select(Campaign)
    if state:
        stmt = stmt.where(Campaign.state == state)
    stmt = stmt.order_by(Campaign.created_at.desc(), Campaign.id.desc())

    query = (q or "").strip().casefold()
    if not query:
        return list((await db.scalars(stmt.limit(limit).offset(offset))).all())

    # ``casefold`` is done in Python to keep the previous search semantics for
    # non-ASCII names (SQLite ``lower()`` only handles ASCII). The local table is
    # small, so filtering in memory is acceptable for this MVP.
    rows = [
        row
        for row in (await db.scalars(stmt)).all()
        if query in (row.name or "").casefold() or query in (row.alias or "").casefold()
    ]
    return rows[offset : offset + limit]


async def list_offers(
    db: AsyncSession,
    *,
    campaign_id: int,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Offer]:
    stmt = (
        select(Offer)
        .join(Stream, Offer.stream_id == Stream.id)
        .where(Stream.campaign_id == campaign_id)
        .options(joinedload(Offer.stream))
        .order_by(Offer.id)
    )

    query = (q or "").strip().casefold()
    if not query:
        return list((await db.scalars(stmt.limit(limit).offset(offset))).unique().all())

    rows = [
        row
        for row in (await db.scalars(stmt)).unique().all()
        if query in (row.name or "").casefold() or query in str(row.keitaro_id)
    ]
    return rows[offset : offset + limit]


async def list_creation_logs(
    db: AsyncSession, *, limit: int = 50
) -> list[CampaignCreationLog]:
    return list(
        (
            await db.scalars(
                select(CampaignCreationLog)
                .order_by(CampaignCreationLog.id.desc())
                .limit(limit)
            )
        ).all()
    )
