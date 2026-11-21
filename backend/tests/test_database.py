"""Database URL normalization for async drivers."""
from app.database import async_database_url


def test_sqlite_url_gets_aiosqlite_driver():
    assert async_database_url("sqlite:///tmp/app.db") == "sqlite+aiosqlite:///tmp/app.db"


def test_postgres_urls_get_asyncpg_driver():
    assert (
        async_database_url("postgresql://user:pass@host/db")
        == "postgresql+asyncpg://user:pass@host/db"
    )
    assert (
        async_database_url("postgresql+psycopg://user:pass@host/db")
        == "postgresql+asyncpg://user:pass@host/db"
    )


def test_async_url_is_kept_as_is():
    assert (
        async_database_url("postgresql+asyncpg://user:pass@host/db")
        == "postgresql+asyncpg://user:pass@host/db"
    )
