"""Pure rules that decide whether a campaign has unsynchronised changes."""
from __future__ import annotations

from .models import ORIGIN_LOCAL, Campaign, Offer, Stream


def offer_has_local_changes(offer: Offer) -> bool:
    if offer.origin == ORIGIN_LOCAL:
        return True
    if bool(offer.is_deleted) != bool(offer.base_is_deleted):
        return True
    if (offer.state or "active") != (offer.base_state or "active"):
        return True
    if not offer.is_deleted and offer.share != offer.base_share:
        return True
    return False


def stream_change_action(stream: Stream) -> str:
    """``update`` | ``none`` | ``unsupported``.

    Only offers are editable: streams themselves can never be deleted or
    restored from the editor.
    """
    if stream.origin == ORIGIN_LOCAL:
        return "unsupported"
    if any(offer_has_local_changes(offer) for offer in stream.offers):
        return "update"
    return "none"


def campaign_has_local_changes(campaign: Campaign) -> bool:
    return any(
        offer_has_local_changes(offer)
        for stream in campaign.streams
        for offer in stream.offers
    )
