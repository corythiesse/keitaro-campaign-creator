"""Small, dependency-free coercion helpers shared by services and repositories."""
from __future__ import annotations

import json
from typing import Any


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_str(value: Any, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if limit is not None:
        text = text[:limit]
    return text


def as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def json_safe(value: Any) -> Any:
    """Return ``value`` only if it is JSON-serializable, otherwise ``None``."""
    if value is None:
        return None
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return None
    return value


def as_list(value: Any) -> list:
    """Normalize a Keitaro collection response (list or ``{"data": [...]}``)."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "result"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def merge_snapshot(payload: dict, response: Any) -> dict:
    """Keitaro may return only ``{"id": ...}``, so the snapshot is payload + response."""
    if isinstance(response, dict):
        return {**payload, **response}
    return {**payload}
