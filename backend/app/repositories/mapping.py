"""Shared ORM field mapping for Keitaro snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Offer, Stream, ORIGIN_KEITARO
from ..utils import as_float, as_int, as_str, as_text, json_safe


def now() -> datetime:
    return datetime.now(timezone.utc)


def apply_stream_snapshot(row: Stream, data: dict) -> None:
    row.name = as_str(data.get("name"), 255) or f"Stream {row.keitaro_id}"
    row.type = as_str(data.get("type"), 32)
    row.schema = as_str(data.get("schema"), 32)
    row.position = as_int(data.get("position"))
    row.state = as_str(data.get("state"), 20)
    row.action_type = as_str(data.get("action_type"), 64)
    row.action_payload = as_text(data.get("action_payload"))
    row.comments = as_str(data.get("comments"))
    row.weight = as_float(data.get("weight"))
    row.keitaro_updated_at = as_str(data.get("updated_at"), 32)
    row.raw = json_safe(data)
    row.updated_at = now()

    # A freshly observed Keitaro snapshot is the baseline: no local changes yet.
    row.origin = ORIGIN_KEITARO
    row.is_deleted = row.state == "deleted"
    row.base_state = row.state
    row.base_is_deleted = row.is_deleted


def apply_offer_snapshot(
    row: Offer,
    *,
    share: int | None,
    state: str | None,
    keitaro_offer_stream_id: int | None,
    name: str | None,
    raw: Any,
) -> None:
    row.name = as_str(name, 255)
    row.state = state or "active"
    row.share = share
    row.keitaro_offer_stream_id = keitaro_offer_stream_id
    row.raw = json_safe(raw)
    row.updated_at = now()

    row.origin = ORIGIN_KEITARO
    row.is_deleted = False
    row.is_pinned = False
    row.pinned_share = None
    row.base_share = row.share
    row.base_state = row.state
    row.base_is_deleted = False
