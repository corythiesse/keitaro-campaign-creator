"""Unit tests for pure creation helpers."""
import re

import pytest

from app.services.creation import campaign_alias, campaign_name, find_by_name


def test_campaign_name_uses_prefix_verbatim():
    assert campaign_name("Test campaign") == "test_test-campaign"


def test_campaign_name_falls_back_for_empty_slug():
    assert campaign_name("!!!") == "test_campaign"


def test_campaign_alias_is_url_safe_and_short():
    alias = campaign_alias("Тестовая кампания")
    assert re.fullmatch(r"[a-z0-9-]+_[0-9a-f]{6}", alias)


def test_find_by_name_accepts_envelope_payload():
    payload = {"data": [{"id": 1, "name": "Example"}]}
    assert find_by_name(payload, "example", "домен")["id"] == 1


def test_find_by_name_rejects_duplicates():
    payload = [{"id": 1, "name": "Same"}, {"id": 2, "name": "same"}]
    with pytest.raises(ValueError, match="несколько"):
        find_by_name(payload, "Same", "домен")


def test_find_by_name_rejects_missing_entity():
    with pytest.raises(ValueError, match="не найден"):
        find_by_name([], "Missing", "домен")
