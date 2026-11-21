"""Use-case orchestration for the campaign editor.

This layer knows about *what* has to happen (add offer, pin it, load the remote
snapshot, push local changes), but it delegates:

- persistence to :mod:`app.repositories`;
- Keitaro HTTP to :mod:`app.keitaro`;
- weight math to :mod:`app.weights`.

It deliberately does not build HTTP responses: the API layer maps
:class:`EditorError` and :class:`KeitaroError` to HTTP exceptions.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo
from ..changes import campaign_has_local_changes, stream_change_action
from ..config import settings
from ..errors import EditorError, RemoteChanged, RevisionConflictError
from ..keitaro import KeitaroClient, KeitaroError
from ..models import Campaign, Stream, utcnow
from ..schemas import CampaignEditorOut, OfferPatch, SyncPushOut
from ..utils import as_int
from ..weights import WeightError, distribute_shares, is_active


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #

def editor_out(campaign: Campaign, warnings: list[str] | None = None) -> CampaignEditorOut:
    """Build the full editor payload with the derived ``has_local_changes``."""
    out = CampaignEditorOut.model_validate(campaign)
    out.keitaro_campaign_url = settings.keitaro_campaign_url(campaign.keitaro_id)
    out.has_local_changes = campaign_has_local_changes(campaign)
    out.warnings = list(warnings or [])
    return out


async def _finish(
    db: AsyncSession,
    campaign: Campaign,
    warnings: list[str] | None = None,
    *,
    expected_revision: int | None = None,
    reload: bool = True,
) -> CampaignEditorOut:
    """Commit a local mutation: bump revision and return the fresh payload."""
    try:
        await repo.bump_revision(db, campaign, expected_revision)
    except RevisionConflictError as exc:
        await db.rollback()
        raise EditorError(
            409,
            "REVISION_CONFLICT",
            "Данные изменились в другой вкладке. Обновите страницу.",
        ) from exc

    campaign_id = campaign.id
    await db.commit()
    if not reload:
        # Add/patch already loaded the complete graph before the mutation.
        return editor_out(campaign, warnings)

    fresh = await repo.get_campaign(db, campaign_id, populate_existing=True)
    if fresh is None:  # pragma: no cover - defensive
        raise EditorError(404, "CAMPAIGN_NOT_FOUND", f"Кампания {campaign_id} не найдена")
    return editor_out(fresh, warnings)


async def _get_campaign_or_404(db: AsyncSession, campaign_id: int) -> Campaign:
    campaign = await repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise EditorError(404, "CAMPAIGN_NOT_FOUND", f"Кампания {campaign_id} не найдена")
    return campaign


def check_revision(campaign: Campaign, expected_revision: int | None) -> None:
    """Reject a mutation based on an outdated editor revision."""
    if expected_revision is not None and expected_revision != (campaign.revision or 0):
        raise EditorError(
            409,
            "REVISION_CONFLICT",
            "Данные изменились в другой вкладке. Обновите страницу.",
        )


# --------------------------------------------------------------------------- #
# Weight application
# --------------------------------------------------------------------------- #

def apply_shares(stream: Stream, shares: dict[int, int]) -> None:
    """Write distributed shares into the in-memory offers; never commits."""
    for offer in stream.offers:
        if offer.id in shares:
            offer.share = shares[offer.id]
        elif offer.is_pinned and is_active(offer) and offer.pinned_share is not None:
            offer.share = offer.pinned_share


def recalculate_stream(stream: Stream) -> None:
    """Validate and apply weights for one stream (raises :class:`WeightError`)."""
    shares = distribute_shares(stream.offers)
    apply_shares(stream, shares)
    repo.touch_stream(stream)


def _as_editor_error(exc: WeightError, stream: Stream | None = None) -> EditorError:
    extra = {"stream_id": stream.id} if stream is not None else {}
    return EditorError(422, exc.code, exc.message, **extra)


# --------------------------------------------------------------------------- #
# Local mutations
# --------------------------------------------------------------------------- #

async def add_offer(
    db: AsyncSession,
    api: KeitaroClient,
    stream_id: int,
    offer_id: int,
    name: str | None = None,
    *,
    expected_revision: int | None = None,
) -> CampaignEditorOut:
    """Add (or restore) an offer in a stream. Keitaro is only read for validation."""
    stream = await repo.get_stream(db, stream_id)
    if stream is None:
        raise EditorError(404, "STREAM_NOT_FOUND", f"Поток {stream_id} не найден")
    check_revision(stream.campaign, expected_revision)
    if stream.is_deleted:
        raise EditorError(409, "STREAM_DELETED", "Нельзя добавить оффер в удалённый поток")

    existing = await repo.find_offer(db, stream_id, offer_id)
    if existing is not None and not existing.is_deleted:
        raise EditorError(
            409,
            "OFFER_ALREADY_IN_STREAM",
            f"Оффер {offer_id} уже добавлен в этот поток",
        )

    remote = await api.get_offer(offer_id)
    if not isinstance(remote, dict) or str(remote.get("state", "active")).lower() != "active":
        raise EditorError(422, "OFFER_NOT_ACTIVE", "Оффер не найден или неактивен в Keitaro")
    resolved_name = name or remote.get("name")

    if existing is None:
        await repo.create_offer(db, stream, offer_id, name=resolved_name, state="active")
    else:
        existing.is_deleted = False
        existing.state = "active"
        if resolved_name:
            existing.name = resolved_name

    try:
        recalculate_stream(stream)
    except WeightError as exc:
        error = _as_editor_error(exc, stream)
        await db.rollback()
        raise error from exc

    return await _finish(
        db, stream.campaign, expected_revision=expected_revision, reload=False
    )


async def patch_offer(
    db: AsyncSession,
    offer_id: int,
    patch: OfferPatch,
    *,
    expected_revision: int | None = None,
) -> CampaignEditorOut:
    offer = await repo.get_offer(db, offer_id)
    if offer is None:
        raise EditorError(404, "OFFER_NOT_FOUND", f"Оффер {offer_id} не найден")
    stream = offer.stream
    check_revision(stream.campaign, expected_revision)

    if patch.is_deleted is not None:
        offer.is_deleted = patch.is_deleted
        if not patch.is_deleted:
            # Explicit restore also brings the offer back into rotation.
            offer.state = patch.state or "active"
    if patch.state is not None:
        offer.state = patch.state

    if patch.is_pinned is not None:
        if patch.is_pinned:
            share = patch.pinned_share if patch.pinned_share is not None else offer.share
            offer.is_pinned = True
            offer.pinned_share = 0 if share is None else int(share)
        else:
            offer.is_pinned = False
            offer.pinned_share = None
    elif patch.pinned_share is not None and offer.is_pinned:
        offer.pinned_share = patch.pinned_share

    try:
        recalculate_stream(stream)
    except WeightError as exc:
        error = _as_editor_error(exc, stream)
        await db.rollback()
        raise error from exc

    return await _finish(
        db, stream.campaign, expected_revision=expected_revision, reload=False
    )


async def discard(db: AsyncSession, campaign_id: int) -> CampaignEditorOut:
    """Revert working state to the last confirmed Keitaro version."""
    campaign = await _get_campaign_or_404(db, campaign_id)
    await repo.reset_to_baseline(db, campaign)
    return await _finish(db, campaign)


# --------------------------------------------------------------------------- #
# Payload
# --------------------------------------------------------------------------- #

def build_offers_payload(stream: Stream, shares: dict[int, int]) -> dict:
    """Payload for ``PUT /streams/{id}``.

    Locally deleted offers are excluded (that is how they are removed in
    Keitaro: ``OfferStream`` has no ``deleted`` state).
    """
    offers = []
    for offer in sorted(stream.offers, key=lambda item: item.id):
        if offer.is_deleted:
            continue
        state = offer.state or "active"
        share = shares.get(offer.id, 0) if state == "active" else 0
        offers.append({"offer_id": offer.keitaro_id, "share": share, "state": state})
    return {"offers": offers}


def _validate_before_push(streams: list[Stream]) -> None:
    """Check every changed stream before the first HTTP request to Keitaro.

    A stream with no remaining offers is valid: :func:`build_offers_payload`
    sends ``{"offers": []}``, which removes all offers from the flow in Keitaro.
    """
    errors: list[dict] = []
    for stream in streams:
        action = stream_change_action(stream)
        if action in ("none", "unsupported"):
            continue

        try:
            distribute_shares(stream.offers)
        except WeightError as exc:
            errors.append({
                "stream_id": stream.id,
                "keitaro_id": stream.keitaro_id,
                "code": exc.code,
                "message": exc.message,
            })

    if not errors:
        return

    raise EditorError(
        422,
        "WEIGHT_VALIDATION_ERROR",
        "Нельзя отправить изменения: проверьте веса потоков",
        streams=errors,
    )


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #

async def load_campaign_streams(
    db: AsyncSession,
    api: KeitaroClient,
    campaign_id: int,
    *,
    force: bool = False,
) -> CampaignEditorOut:
    """Fetch streams/offers from Keitaro and replace the local snapshot."""
    campaign = await _get_campaign_or_404(db, campaign_id)
    if campaign.keitaro_id is None:
        raise EditorError(409, "CAMPAIGN_NOT_SYNCED", "У кампании нет Keitaro ID")

    if not force and campaign_has_local_changes(campaign):
        raise EditorError(
            409,
            "LOCAL_CHANGES_PENDING",
            "Есть несинхронизированные изменения. Подтвердите загрузку, чтобы потерять их.",
            has_local_changes=True,
        )

    # All network calls happen before any local change, so a Keitaro failure
    # cannot leave the database half-updated.
    remote_streams = await api.campaign_streams(campaign.keitaro_id)
    offers = await api.offers_all()
    if not isinstance(remote_streams, list):
        raise EditorError(
            502,
            "KEITARO_INVALID_RESPONSE",
            "Keitaro вернул неожиданный формат списка потоков",
        )
    invalid_streams = [
        item for item in remote_streams
        if not isinstance(item, dict) or as_int(item.get("id")) is None
    ]
    if invalid_streams:
        raise EditorError(
            502,
            "KEITARO_INVALID_RESPONSE",
            "Keitaro вернул поток без обязательного поля id",
        )

    offer_names: dict[int, str] = {}
    for item in offers or []:
        if not isinstance(item, dict):
            continue
        offer_id = as_int(item.get("id"))
        if offer_id is None:
            continue
        offer_names[offer_id] = str(item.get("name") or "")

    if force:
        await repo.reset_to_baseline(db, campaign)
    warnings = await repo.apply_remote_snapshot(db, campaign, remote_streams, offer_names)

    campaign.last_loaded_at = utcnow()
    campaign.last_sync_error = None
    return await _finish(db, campaign, warnings)


# --------------------------------------------------------------------------- #
# Push
# --------------------------------------------------------------------------- #

async def _fresh_updated_at(api: KeitaroClient, stream: Stream, response):
    """Return a PUT response that carries a fresh ``updated_at``.

    Keitaro may answer ``PUT /streams/{id}`` with only ``{"id": ...}``. Without
    refreshing the timestamp the next push would compare against an outdated
    value and reject the stream as ``REMOTE_CHANGED`` forever.
    """
    if isinstance(response, dict) and response.get("updated_at") is not None:
        return response
    try:
        fresh = await api.get_stream(stream.keitaro_id)
    except KeitaroError:
        return response
    if isinstance(fresh, dict) and fresh.get("updated_at") is not None:
        if isinstance(response, dict):
            return {**response, "updated_at": fresh["updated_at"]}
        return {"updated_at": fresh["updated_at"]}
    return response


def _stream_result(stream_id: int, keitaro_id: int, status: str, **extra: Any) -> dict:
    return {
        "stream_id": stream_id,
        "keitaro_id": keitaro_id,
        "status": status,
        **extra,
    }


async def _push_one_stream(
    db: AsyncSession,
    api: KeitaroClient,
    stream: Stream,
    *,
    force: bool,
) -> dict:
    stream_id = stream.id
    keitaro_id = stream.keitaro_id
    action = stream_change_action(stream)
    shares = distribute_shares(stream.offers)

    try:
        if not force and stream.keitaro_updated_at:
            remote = await api.get_stream(stream.keitaro_id)
            remote_updated_at = remote.get("updated_at") if isinstance(remote, dict) else None
            if remote_updated_at is not None and str(remote_updated_at) != str(stream.keitaro_updated_at):
                raise RemoteChanged()

        apply_shares(stream, shares)
        response = await api.update_stream(
            stream.keitaro_id, build_offers_payload(stream, shares)
        )
        response = await _fresh_updated_at(api, stream, response)

        # One transaction per stream: a failure below never touches the
        # baseline of already succeeded streams, and vice versa.
        await repo.commit_stream_baseline(db, stream.campaign, stream, response)
        await db.commit()
        return _stream_result(stream_id, keitaro_id, "ok", action=action)
    except RemoteChanged:
        result = _stream_result(
            stream_id,
            keitaro_id,
            "error",
            code="REMOTE_CHANGED",
            message="Поток изменён в Keitaro после последней загрузки",
        )
        await db.rollback()
        return result
    except KeitaroError as exc:
        result = _stream_result(
            stream_id,
            keitaro_id,
            "error",
            code="KEITARO_API_ERROR",
            message=str(exc),
        )
        await db.rollback()
        return result
    except SQLAlchemyError as exc:
        result = _stream_result(
            stream_id,
            keitaro_id,
            "error",
            code="LOCAL_PERSISTENCE_ERROR",
            message=f"Не удалось сохранить результат отправки: {exc}",
        )
        await db.rollback()
        return result


async def push_campaign_changes(
    db: AsyncSession,
    api: KeitaroClient,
    campaign_id: int,
    *,
    expected_revision: int | None = None,
    force: bool = False,
) -> SyncPushOut:
    """Send local changes stream by stream; each success commits its own baseline."""
    campaign = await _get_campaign_or_404(db, campaign_id)
    if campaign.keitaro_id is None:
        raise EditorError(409, "CAMPAIGN_NOT_SYNCED", "У кампании нет Keitaro ID")
    check_revision(campaign, expected_revision)

    streams = list(campaign.streams)
    _validate_before_push(streams)

    entries = [
        (stream.id, stream.keitaro_id, stream_change_action(stream))
        for stream in streams
    ]
    changed = sum(1 for _, _, action in entries if action == "update")
    unsupported = sum(1 for _, _, action in entries if action == "unsupported")

    # Claim the revision before the first HTTP write. This turns a stale
    # revision into a 409 without sending anything to Keitaro and prevents two
    # tabs from pushing based on the same version.
    if changed:
        try:
            await repo.bump_revision(db, campaign, expected_revision)
            await db.commit()
        except RevisionConflictError as exc:
            await db.rollback()
            raise EditorError(
                409,
                "REVISION_CONFLICT",
                "Данные изменились в другой вкладке. Обновите страницу.",
            ) from exc

    results: list[dict] = []
    for stream_id, keitaro_id, action in entries:
        if action == "none":
            results.append(_stream_result(stream_id, keitaro_id, "skipped"))
        elif action == "unsupported":
            results.append(
                _stream_result(
                    stream_id,
                    keitaro_id,
                    "error",
                    code="UNSUPPORTED_STREAM",
                    message="Локально созданные потоки не поддерживаются",
                )
            )
        else:
            # A previous failed stream may have rolled the session back and
            # expired every ORM object; reload this one before touching it.
            stream = await repo.get_stream(db, stream_id)
            if stream is None:  # pragma: no cover - defensive
                results.append(
                    _stream_result(
                        stream_id,
                        keitaro_id,
                        "error",
                        code="STREAM_NOT_FOUND",
                        message="Поток исчез из локальной базы",
                    )
                )
                continue
            results.append(await _push_one_stream(db, api, stream, force=force))

    update_failed = sum(
        1
        for result in results
        if result["status"] == "error" and result.get("code") != "UNSUPPORTED_STREAM"
    )
    failed = update_failed + unsupported

    campaign = await repo.get_campaign(db, campaign_id, populate_existing=True)
    if campaign is None:  # pragma: no cover - defensive
        raise EditorError(404, "CAMPAIGN_NOT_FOUND", f"Кампания {campaign_id} не найдена")

    all_failed = changed > 0 and update_failed == changed
    if all_failed:
        campaign.last_sync_error = "Не удалось отправить изменения ни для одного потока"
        await db.commit()
        raise EditorError(
            502,
            "SYNC_FAILED",
            "Не удалось отправить изменения ни для одного потока",
            results=results,
        )

    if failed:
        campaign.last_sync_error = f"Не удалось отправить изменения для {failed} поток(ов)"
    else:
        campaign.last_sync_error = None
    await db.commit()

    return SyncPushOut(
        success=failed == 0,
        code=None if failed == 0 else "PARTIAL_SYNC",
        message=None if failed == 0 else "Часть потоков не удалось отправить",
        campaign=editor_out(campaign),
        results=results,
    )


__all__ = [
    "EditorError",
    "add_offer",
    "check_revision",
    "editor_out",
    "discard",
    "load_campaign_streams",
    "patch_offer",
    "push_campaign_changes",
    "build_offers_payload",
]
