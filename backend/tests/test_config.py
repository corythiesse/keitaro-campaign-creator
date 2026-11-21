"""Settings validation for DB-only versus Keitaro-facing commands."""
import pytest

from app.config import Settings


def test_keitaro_settings_are_not_required_for_db_only_startup(monkeypatch):
    for name in (
        "KEITARO_BASE_URL",
        "KEITARO_API_KEY",
        "KEITARO_DOMAIN_NAME",
        "KEITARO_GROUP_NAME",
        "KEITARO_TRAFFIC_SOURCE_NAME",
        "KEITARO_STREAM_ACTION_TYPE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url


def test_require_keitaro_reports_missing_variables(monkeypatch):
    for name in (
        "KEITARO_BASE_URL",
        "KEITARO_API_KEY",
        "KEITARO_DOMAIN_NAME",
        "KEITARO_GROUP_NAME",
        "KEITARO_TRAFFIC_SOURCE_NAME",
        "KEITARO_STREAM_ACTION_TYPE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    with pytest.raises(RuntimeError, match="KEITARO_BASE_URL"):
        settings.require_keitaro()
