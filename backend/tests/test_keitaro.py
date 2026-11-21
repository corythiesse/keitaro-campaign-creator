"""Keitaro client behaviour that is easy to get wrong: payload shape and caching."""
import asyncio

import httpx
import pytest

from app import keitaro as keitaro_module
from app.keitaro import KeitaroClient, KeitaroError

from .conftest import KEITARO

OFFERS = [
    {"id": 11, "name": "Alpha", "state": "active"},
    {"id": 22, "name": "Beta", "state": "disabled"},
]


def _collect_offers():
    async def run():
        api = KeitaroClient()
        try:
            active = await api.offers()
            every = await api.offers_all()
        finally:
            await api.close()
        return active, every

    return asyncio.run(run())


def test_offer_catalogue_is_cached(respx_mock, monkeypatch):
    monkeypatch.setattr(keitaro_module.settings, "keitaro_offers_cache_ttl", 60)
    keitaro_module._OFFERS_CACHE.clear()
    route = respx_mock.get(f"{KEITARO}/offers").mock(
        return_value=httpx.Response(200, json=OFFERS)
    )

    active, every = _collect_offers()

    assert route.call_count == 1
    assert [offer["id"] for offer in active] == [11]
    assert [offer["id"] for offer in every] == [11, 22]


def test_offer_catalogue_cache_can_be_disabled(respx_mock, monkeypatch):
    monkeypatch.setattr(keitaro_module.settings, "keitaro_offers_cache_ttl", 0)
    keitaro_module._OFFERS_CACHE.clear()
    route = respx_mock.get(f"{KEITARO}/offers").mock(
        return_value=httpx.Response(200, json=OFFERS)
    )

    _collect_offers()

    assert route.call_count == 2


async def test_error_message_contains_status_request_and_text_body(respx_mock):
    respx_mock.post(f"{KEITARO}/campaigns").mock(
        return_value=httpx.Response(408, text="upstream timeout")
    )
    api = KeitaroClient()
    try:
        with pytest.raises(KeitaroError) as caught:
            await api.create_campaign({"name": "Test"})
    finally:
        await api.close()

    message = str(caught.value)
    assert "HTTP 408" in message
    assert "POST /campaigns" in message
    assert "upstream timeout" in message
    assert caught.value.details == "upstream timeout"
    assert caught.value.request_label == "POST /campaigns"


async def test_error_message_contains_json_details(respx_mock):
    respx_mock.post(f"{KEITARO}/campaigns").mock(
        return_value=httpx.Response(400, json={"error": "invalid alias", "code": 12})
    )
    api = KeitaroClient()
    try:
        with pytest.raises(KeitaroError) as caught:
            await api.create_campaign({"name": "Test"})
    finally:
        await api.close()

    assert "invalid alias" in str(caught.value)
    assert caught.value.details == {"error": "invalid alias", "code": 12}


async def test_error_message_mentions_empty_response(respx_mock):
    respx_mock.get(f"{KEITARO}/domains").mock(return_value=httpx.Response(408))
    api = KeitaroClient()
    try:
        with pytest.raises(KeitaroError) as caught:
            await api.domains()
    finally:
        await api.close()

    assert "пустой ответ Keitaro" in str(caught.value)


def test_offer_catalogue_ignores_unexpected_payload(respx_mock, monkeypatch):
    monkeypatch.setattr(keitaro_module.settings, "keitaro_offers_cache_ttl", 0)
    keitaro_module._OFFERS_CACHE.clear()
    respx_mock.get(f"{KEITARO}/offers").mock(
        return_value=httpx.Response(200, json={"data": OFFERS})
    )

    active, every = _collect_offers()

    assert [offer["id"] for offer in active] == [11]
    assert [offer["id"] for offer in every] == [11, 22]
