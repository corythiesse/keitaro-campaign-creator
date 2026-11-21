from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to ``backend/``: the default SQLite file and .env must not
# depend on the process working directory.
BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # Keitaro fields are optional at import time so DB-only commands such as
    # ``scripts.init_db`` work without tracker credentials. The application and
    # KeitaroClient call ``require_keitaro()`` before doing any real work.
    keitaro_base_url: str = ""
    keitaro_api_key: str = ""
    keitaro_timeout: float = 20
    keitaro_domain_name: str = ""
    keitaro_group_name: str = ""
    keitaro_traffic_source_name: str = ""
    keitaro_stream_action_type: str = ""
    # Keitaro has no server-side offer search used by the app, so the offer
    # catalogue is cached process-wide for this many seconds (0 disables it).
    keitaro_offers_cache_ttl: float = 30
    database_url: str = f"sqlite:///{BASE_DIR / 'campaign_creator.db'}"
    cors_origins: str = "http://localhost:5173"
    # Optional shared secret for the HTTP API. When set, every /api route
    # except /api/health requires it (X-API-Token or Authorization: Bearer).
    api_auth_token: str = ""
    # When false, schema creation/migrations are skipped on startup; run
    # ``python -m scripts.init_db`` once instead (multi-worker deployments).
    auto_migrate: bool = True
    # Prefix of the generated Keitaro campaign name. It is used verbatim, so
    # include the separator if one is needed (the documented default is "test_").
    campaign_name_prefix: str = "test_"

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", ".env"),
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def keitaro_campaign_url(self, keitaro_id: int) -> str | None:
        """Public Keitaro admin URL of a campaign, or None when no host is set."""
        base = self.keitaro_base_url.strip().rstrip("/")
        if not base:
            return None
        return f"{base}/admin/#!/campaign/{keitaro_id}/main"

    def require_keitaro(self) -> None:
        """Fail fast when a component that talks to Keitaro is used."""
        required = {
            "KEITARO_BASE_URL": self.keitaro_base_url,
            "KEITARO_API_KEY": self.keitaro_api_key,
            "KEITARO_DOMAIN_NAME": self.keitaro_domain_name,
            "KEITARO_GROUP_NAME": self.keitaro_group_name,
            "KEITARO_TRAFFIC_SOURCE_NAME": self.keitaro_traffic_source_name,
            "KEITARO_STREAM_ACTION_TYPE": self.keitaro_stream_action_type,
        }
        missing = sorted(name for name, value in required.items() if not value.strip())
        if missing:
            raise RuntimeError(
                "Не заданы обязательные переменные Keitaro: " + ", ".join(missing)
            )


settings = Settings()
