import json
import time
from typing import Any

import httpx

from .config import settings

_DETAILS_LIMIT = 1500


def _details_text(details: Any) -> str:
    """Convert a Keitaro error body into a short, readable message suffix."""
    if details is None:
        return ""
    if isinstance(details, str):
        return details.strip()[:_DETAILS_LIMIT]
    try:
        text = json.dumps(details, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(details)
    return text[:_DETAILS_LIMIT]


def _request_label(method: str, path: str) -> str:
    return f"{method.upper()} {path}"

# Process-wide offer catalogue cache. Keitaro has no search endpoint used by the
# app, so both autocomplete and snapshot loading would otherwise page through
# every offer in the tracker on each request.
_OFFERS_CACHE: dict[str, tuple[float, list[dict]]] = {}


class KeitaroError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: Any = None,
        *,
        method: str | None = None,
        path: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.details = details
        self.method = method
        self.path = path

    @property
    def request_label(self) -> str | None:
        if self.method and self.path:
            return _request_label(self.method, self.path)
        return None


class KeitaroClient:
    def __init__(self):
        settings.require_keitaro()
        self.base = settings.keitaro_base_url.rstrip("/") + "/admin_api/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base,
            headers={"Api-Key": settings.keitaro_api_key, "Content-Type": "application/json"},
            timeout=settings.keitaro_timeout,
        )

    async def close(self):
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs):
        label = _request_label(method, path)
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(
                f"Не удалось связаться с Keitaro ({label}): {exc}",
                method=method,
                path=path,
            ) from exc
        if response.is_error:
            try:
                details = response.json()
            except ValueError:
                details = response.text
            detail_text = _details_text(details) or "пустой ответ Keitaro"
            raise KeitaroError(
                f"Keitaro вернул HTTP {response.status_code} ({label}): {detail_text}",
                response.status_code,
                details,
                method=method,
                path=path,
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def list_all(self, path: str, page_size: int = 500):
        results = []
        offset = 0
        while True:
            data = await self.request("GET", path, params={"offset": offset, "limit": page_size})
            if not isinstance(data, list):
                return data
            results.extend(data)
            if len(data) < page_size:
                break
            offset += page_size
        return results

    async def _offer_catalogue(self) -> list[dict]:
        """Return the full offer catalogue, cached for ``KEITARO_OFFERS_CACHE_TTL``."""
        ttl = settings.keitaro_offers_cache_ttl
        now = time.monotonic()
        if ttl > 0:
            cached = _OFFERS_CACHE.get(self.base)
            if cached is not None and now - cached[0] < ttl:
                return cached[1]

        data = await self.list_all("/offers")
        # Be defensive about unexpected payloads (dict envelope, non-dict rows).
        if isinstance(data, dict):
            data = data.get("data") or data.get("items") or []
        items = [item for item in (data or []) if isinstance(item, dict)]
        if ttl > 0:
            _OFFERS_CACHE[self.base] = (now, items)
        return items

    async def offers(self):
        # API supports offset/limit. Active filtering is done locally for consistency.
        items = await self._offer_catalogue()
        return [x for x in items if str(x.get("state", "active")).lower() == "active"]

    async def get_offer(self, offer_id: int):
        return await self.request("GET", f"/offers/{offer_id}")

    async def get_campaign(self, campaign_id: int):
        return await self.request("GET", f"/campaigns/{campaign_id}")

    async def domains(self):
        return await self.list_all("/domains")

    async def groups(self):
        return await self.request("GET", "/groups", params={"type": "campaigns"})

    async def traffic_sources(self):
        return await self.request("GET", "/traffic_sources")

    async def stream_actions(self):
        return await self.request("GET", "/streams_actions")

    async def create_campaign(self, payload: dict):
        return await self.request("POST", "/campaigns", json=payload)

    async def create_stream(self, payload: dict):
        return await self.request("POST", "/streams", json=payload)

    async def campaign_streams(self, campaign_id: int):
        return await self.request("GET", f"/campaigns/{campaign_id}/streams")

    async def get_stream(self, stream_id: int):
        return await self.request("GET", f"/streams/{stream_id}")

    async def update_stream(self, stream_id: int, payload: dict):
        return await self.request("PUT", f"/streams/{stream_id}", json=payload)

    async def offers_all(self):
        """All offers without the ``active`` filter (used for the id -> name map)."""
        return list(await self._offer_catalogue())
