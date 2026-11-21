"""Validation tests for request schemas."""
import pycountry
import pytest
from pydantic import ValidationError

from app.schemas import CampaignCreate


def test_geo_is_normalized_and_deduplicated():
    payload = CampaignCreate(name="Test", geo="mx au, RO, mx", offer_id=1)
    assert payload.geo == "MX, AU, RO"


def test_geo_rejects_invalid_iso_codes():
    with pytest.raises(ValidationError, match="ZH"):
        CampaignCreate(name="Test", geo="MX, ZH", offer_id=1)


def test_geo_rejects_normalized_value_over_column_limit():
    # 80 valid two-letter codes fit the input limit, but normalize to >255 chars.
    codes = [country.alpha_2 for country in list(pycountry.countries)[:80]]
    raw = " ".join(codes)
    assert len(raw) <= 255

    with pytest.raises(ValidationError, match="255"):
        CampaignCreate(name="Test", geo=raw, offer_id=1)
