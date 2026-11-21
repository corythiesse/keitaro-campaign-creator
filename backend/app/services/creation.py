"""Business logic for creating a Keitaro campaign and its two streams."""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field

from slugify import slugify
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo
from ..config import settings
from ..errors import LocalPersistenceError
from ..keitaro import KeitaroClient, KeitaroError
from ..models import Campaign, CampaignCreationLog
from ..utils import as_int, as_list, merge_snapshot

logger = logging.getLogger(__name__)

STATUS_STARTED = "started"
STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"


class PartialCreationError(Exception):
    """Keitaro created part of the campaign, but a later step failed."""

    def __init__(
        self,
        message: str,
        campaign: dict,
        google_stream: dict | None = None,
        *,
        streams: list[dict] | None = None,
        offers: list[dict] | None = None,
    ):
        super().__init__(message)
        self.campaign = campaign
        self.google_stream = google_stream
        if streams is None:
            streams = [google_stream] if google_stream else []
        self.streams = list(streams)
        self.offers = list(offers or [])


@dataclass
class CampaignContext:
    countries: list[str]
    offer_id: int
    offer: dict
    action_key: str


@dataclass
class CreatedCampaign:
    campaign: dict
    context: CampaignContext


@dataclass
class CreatedStreams:
    streams: list[dict] = field(default_factory=list)
    offers: list[dict] = field(default_factory=list)


def find_by_name(items, expected: str, entity: str) -> dict:
    matches = [
        item
        for item in as_list(items)
        if isinstance(item, dict) and str(item.get("name", "")).casefold() == expected.casefold()
    ]
    if not matches:
        raise ValueError(f'{entity} "{expected}" не найден в Keitaro')
    if len(matches) > 1:
        raise ValueError(
            f'В Keitaro найдено несколько сущностей "{expected}" ({entity}); '
            "требуется устранить неоднозначность"
        )
    return matches[0]


def campaign_name(name: str) -> str:
    base = slugify(name, max_length=45) or "campaign"
    return f"{settings.campaign_name_prefix}{base}"


def campaign_alias(name: str) -> str:
    # Keitaro aliases are used in tracking URLs: keep them URL-safe and short
    # enough for the local ``campaigns.alias`` column (VARCHAR(64)).
    base = slugify(name, max_length=45) or "campaign"
    return f"{base}_{secrets.token_hex(3)}"


def _require_int_field(data: dict, field_name: str, entity: str) -> int:
    value = as_int((data or {}).get(field_name))
    if value is None:
        raise ValueError(f'У сущности Keitaro "{entity}" отсутствует поле {field_name}')
    return value


def _campaign_snapshot(payload: dict, response) -> dict:
    snapshot = merge_snapshot(payload, response)
    if snapshot.get("id") is None:
        raise ValueError("Keitaro не вернул ID созданной кампании")
    return snapshot


def _stream_snapshot(payload: dict, response, label: str) -> dict:
    snapshot = merge_snapshot(payload, response)
    if snapshot.get("id") is None:
        raise ValueError(f"Keitaro не вернул ID созданного потока ({label})")
    return snapshot


async def create_campaign(
    api: KeitaroClient,
    name: str,
    geo: str,
    offer_id: int,
) -> CreatedCampaign:
    """Validate the context and create the campaign in Keitaro.

    Nothing is persisted here: any error means no local entities may exist.
    """
    countries = [x.strip() for x in geo.split(",") if x.strip()]

    offer = await api.get_offer(offer_id)
    if not isinstance(offer, dict) or str(offer.get("state", "active")).lower() != "active":
        raise ValueError("Оффер не найден или неактивен")

    domains, groups, sources, actions = await asyncio.gather(
        api.domains(),
        api.groups(),
        api.traffic_sources(),
        api.stream_actions(),
    )

    domain = find_by_name(domains, settings.keitaro_domain_name, "домен")
    group = find_by_name(groups, settings.keitaro_group_name, "группа кампаний")
    source = find_by_name(sources, settings.keitaro_traffic_source_name, "источник трафика")

    action_key = settings.keitaro_stream_action_type.strip()
    if not action_key or action_key == "replace_with_action_key":
        raise ValueError(
            "Не задан KEITARO_STREAM_ACTION_TYPE. Получите точный key через "
            "GET /streams_actions и укажите его в .env"
        )
    action_keys = {
        str(item["key"])
        for item in as_list(actions)
        if isinstance(item, dict) and item.get("key") is not None
    }
    if action_key not in action_keys:
        raise ValueError(
            f"KEITARO_STREAM_ACTION_TYPE={action_key!r} отсутствует в GET /streams_actions. "
            f"Доступные keys: {', '.join(sorted(action_keys))}"
        )

    payload = {
        "name": campaign_name(name),
        "alias": campaign_alias(name),
        "type": "position",
        "state": "active",
        "domain_id": _require_int_field(domain, "id", "домен"),
        "group_id": str(_require_int_field(group, "id", "группа кампаний")),
        "traffic_source_id": _require_int_field(source, "id", "источник трафика"),
    }
    campaign = await api.create_campaign(payload)

    return CreatedCampaign(
        campaign=_campaign_snapshot(payload, campaign),
        context=CampaignContext(
            countries=countries,
            offer_id=offer_id,
            offer=offer,
            action_key=action_key,
        ),
    )


async def create_campaign_streams(
    api: KeitaroClient,
    created: CreatedCampaign,
) -> CreatedStreams:
    """Create both streams for an already created campaign.

    Any expected failure is wrapped into ``PartialCreationError`` carrying
    everything that was actually created, so the caller can persist what exists.
    """
    context = created.context
    campaign = created.campaign
    campaign_id = _require_int_field(campaign, "id", "кампания")
    streams: list[dict] = []

    geo_payload = {
        "campaign_id": campaign_id,
        "schema": "redirect",
        "type": "regular",
        "name": "GEO - Google",
        "position": 1,
        "state": "active",
        "action_type": context.action_key,
        "action_payload": "https://www.google.com/",
        "collect_clicks": True,
        "filter_or": False,
        # Keitaro Country filter accepts a space-separated list of ISO country codes.
        "filters": [{
            "name": "country",
            "mode": "accept",
            "payload": " ".join(context.countries),
        }],
    }
    try:
        geo_response = await api.create_stream(geo_payload)
        geo_stream = _stream_snapshot(geo_payload, geo_response, "GEO - Google")
    except (KeitaroError, ValueError) as exc:
        raise PartialCreationError(
            f"Кампания создана (ID {campaign_id}), но не удалось создать GEO-поток: {exc}",
            campaign,
            streams=[],
            offers=[],
        ) from exc
    streams.append(geo_stream)

    offer_payload = {
        "campaign_id": campaign_id,
        "schema": "landings",
        "type": "default",
        "name": "Default - Offer",
        "position": 2,
        "state": "active",
        "action_type": context.action_key,
        "collect_clicks": True,
        "offers": [
            {
                "offer_id": context.offer_id,
                "share": 100,
                "state": "active",
            }
        ],
        "offer_selection": "before_click",
    }
    try:
        offer_response = await api.create_stream(offer_payload)
        offer_stream = _stream_snapshot(offer_payload, offer_response, "Default - Offer")
    except (KeitaroError, ValueError) as exc:
        raise PartialCreationError(
            f"Кампания и GEO-поток созданы, но не удалось создать поток оффера: {exc}",
            campaign,
            geo_stream,
            streams=list(streams),
            offers=[],
        ) from exc
    streams.append(offer_stream)

    offers = [{
        "stream": offer_stream,
        "offer_id": context.offer_id,
        "share": 100,
        "state": "active",
        "snapshot": context.offer,
    }]

    return CreatedStreams(streams=streams, offers=offers)


# --------------------------------------------------------------------------- #
# Persistence orchestration
# --------------------------------------------------------------------------- #

@dataclass
class CampaignCreationResult:
    campaign: dict
    streams: list[dict]


def _keitaro_id(data: dict | None) -> int | None:
    if not isinstance(data, dict):
        return None
    return as_int(data.get("id"))


def _persistence_error(exc: Exception, campaign: dict | None = None) -> LocalPersistenceError:
    """Normalize repository/commit failures to a single error type."""
    if isinstance(exc, LocalPersistenceError):
        return exc
    return LocalPersistenceError(
        f"Не удалось сохранить данные локально: {exc}",
        campaign=campaign,
    )


async def _apply_log(
    db: AsyncSession,
    log: CampaignCreationLog,
    *,
    status: str,
    message: str | None = None,
    **fields,
) -> None:
    """Best-effort log update: must never mask the original error."""
    try:
        await db.rollback()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to roll back before updating campaign creation log")
    try:
        for name, value in fields.items():
            setattr(log, name, value)
        log.status = status
        if message is not None:
            log.error_message = message
        await db.commit()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to update campaign creation log")
        try:
            await db.rollback()
        except Exception:
            logger.exception("Failed to roll back campaign creation log update")


async def _local_campaign(db: AsyncSession, campaign: dict) -> Campaign:
    keitaro_id = _keitaro_id(campaign)
    if keitaro_id is None:
        raise LocalPersistenceError("Не удалось определить ID кампании Keitaro", campaign=campaign)
    row = await repo.get_campaign_by_keitaro_id(db, keitaro_id)
    if row is None:
        raise LocalPersistenceError("Локальная кампания не найдена после сохранения", campaign=campaign)
    return row


async def create_campaign_with_persistence(
    db: AsyncSession,
    api: KeitaroClient,
    *,
    name: str,
    geo: str,
    offer_id: int,
) -> CampaignCreationResult:
    """Create the campaign in Keitaro and persist every successful step locally.

    Commit boundaries are intentional:
    1. the ``started`` log entry;
    2. the campaign immediately after ``POST /campaigns``;
    3. streams/offers together with the final log status.
    """
    log = CampaignCreationLog(
        campaign_name=name,
        geo=geo,
        offer_id=offer_id,
        status=STATUS_STARTED,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    created_keitaro_id: int | None = None
    try:
        try:
            created = await create_campaign(api, name, geo, offer_id)
        except KeitaroError as exc:
            await _apply_log(db, log, status=STATUS_FAILED, message=str(exc))
            raise
        except ValueError as exc:
            await _apply_log(db, log, status=STATUS_FAILED, message=str(exc))
            raise
        except Exception as exc:
            await _apply_log(db, log, status=STATUS_FAILED, message=str(exc))
            raise

        # Persist the campaign before creating streams so a stream failure
        # cannot lose an existing Keitaro campaign.
        try:
            await repo.save_campaign(db, created.campaign, log_id=log.id)
            await db.commit()
            created_keitaro_id = _keitaro_id(created.campaign)
        except (LocalPersistenceError, SQLAlchemyError) as exc:
            persist_exc = _persistence_error(exc, created.campaign)
            await _apply_log(
                db,
                log,
                status=STATUS_PARTIAL,
                message=f"LOCAL_PERSISTENCE_ERROR: {persist_exc}",
                keitaro_campaign_id=_keitaro_id(created.campaign),
            )
            raise persist_exc from exc

        try:
            result = await create_campaign_streams(api, created)
        except PartialCreationError as exc:
            try:
                campaign_row = await _local_campaign(db, exc.campaign)
                await repo.save_streams_and_offers(db, campaign_row, exc.streams, exc.offers)
                log.keitaro_campaign_id = _keitaro_id(exc.campaign)
                log.google_stream_id = _keitaro_id(exc.google_stream)
                log.status = STATUS_PARTIAL
                log.error_message = str(exc)
                await db.commit()
            except (LocalPersistenceError, SQLAlchemyError) as persist_error:
                persist_exc = _persistence_error(persist_error, exc.campaign)
                await _apply_log(
                    db,
                    log,
                    status=STATUS_PARTIAL,
                    message=f"PARTIAL_CREATION: {exc} | LOCAL_PERSISTENCE_ERROR: {persist_exc}",
                    keitaro_campaign_id=_keitaro_id(exc.campaign),
                    google_stream_id=_keitaro_id(exc.google_stream),
                )
                raise persist_exc from persist_error
            raise

        try:
            campaign_row = await _local_campaign(db, created.campaign)
            await repo.save_streams_and_offers(db, campaign_row, result.streams, result.offers)
            log.keitaro_campaign_id = _keitaro_id(created.campaign)
            log.google_stream_id = _keitaro_id(result.streams[0]) if result.streams else None
            log.offer_stream_id = _keitaro_id(result.streams[1]) if len(result.streams) > 1 else None
            log.status = STATUS_SUCCESS
            await db.commit()
        except (LocalPersistenceError, SQLAlchemyError) as exc:
            persist_exc = _persistence_error(exc, created.campaign)
            await _apply_log(
                db,
                log,
                status=STATUS_PARTIAL,
                message=f"LOCAL_PERSISTENCE_ERROR: {persist_exc}",
                keitaro_campaign_id=_keitaro_id(created.campaign),
            )
            raise persist_exc from exc

        return CampaignCreationResult(
            campaign={
                "id": created.campaign.get("id"),
                "name": created.campaign.get("name"),
                "alias": created.campaign.get("alias"),
            },
            streams=result.streams,
        )
    except Exception as exc:
        # Defensive fallback: never leave the log in "started".
        if log.status == STATUS_STARTED:
            await _apply_log(
                db,
                log,
                status=STATUS_PARTIAL if created_keitaro_id is not None else STATUS_FAILED,
                message=str(exc),
                keitaro_campaign_id=created_keitaro_id,
            )
        raise
