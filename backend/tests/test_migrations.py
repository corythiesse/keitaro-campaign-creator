"""Idempotent schema top-up tests (plan §4.5)."""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base
from app.migrations import _ddl_for, ensure_schema
from app.models import Campaign, Offer, Stream  # noqa: F401 - register tables on Base.metadata


class _PostgresEngine:
    class dialect:
        name = "postgresql"


class _SqliteEngine:
    class dialect:
        name = "sqlite"


def test_ddl_is_translated_only_for_boolean_columns():
    assert _ddl_for(_SqliteEngine(), "BOOLEAN NOT NULL DEFAULT 0") == "BOOLEAN NOT NULL DEFAULT 0"
    assert (
        _ddl_for(_PostgresEngine(), "BOOLEAN NOT NULL DEFAULT 0")
        == "BOOLEAN NOT NULL DEFAULT FALSE"
    )
    # ``revision`` is an integer and must keep its numeric default.
    assert (
        _ddl_for(_PostgresEngine(), "INTEGER NOT NULL DEFAULT 0")
        == "INTEGER NOT NULL DEFAULT 0"
    )
    assert _ddl_for(_PostgresEngine(), "DATETIME") == "TIMESTAMP"


async def _create_legacy_schema(engine):
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE campaigns ("
            "id INTEGER PRIMARY KEY, keitaro_id INTEGER, name VARCHAR(255))"
        ))
        await conn.execute(text(
            "CREATE TABLE streams ("
            "id INTEGER PRIMARY KEY, campaign_id INTEGER, keitaro_id INTEGER, "
            "name VARCHAR(255), state VARCHAR(20))"
        ))
        await conn.execute(text(
            "CREATE TABLE offers ("
            "id INTEGER PRIMARY KEY, stream_id INTEGER, campaign_id INTEGER, "
            "keitaro_id INTEGER, name VARCHAR(255), state VARCHAR(20), share INTEGER)"
        ))
        await conn.execute(text("INSERT INTO campaigns (keitaro_id, name) VALUES (1, 'Legacy')"))
        await conn.execute(text(
            "INSERT INTO streams (campaign_id, keitaro_id, name, state) "
            "VALUES (1, 9001, 'Default - Offer', 'active')"
        ))
        await conn.execute(text(
            "INSERT INTO offers (stream_id, campaign_id, keitaro_id, name, state, share) "
            "VALUES (1, 1, 42, 'Offer A', 'active', 100)"
        ))


async def test_ensure_schema_adds_columns_and_backfills(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    await _create_legacy_schema(engine)

    await ensure_schema(engine)
    await ensure_schema(engine)  # idempotent: must not fail or duplicate

    async with engine.connect() as conn:
        offer_columns = await conn.run_sync(
            lambda c: {column["name"] for column in inspect(c).get_columns("offers")}
        )
        stream_columns = await conn.run_sync(
            lambda c: {column["name"] for column in inspect(c).get_columns("streams")}
        )
        campaign_columns = await conn.run_sync(
            lambda c: {column["name"] for column in inspect(c).get_columns("campaigns")}
        )

    assert {
        "keitaro_offer_stream_id",
        "is_deleted",
        "is_pinned",
        "pinned_share",
        "origin",
        "base_share",
        "base_state",
        "base_is_deleted",
    } <= offer_columns
    assert {
        "comments",
        "weight",
        "keitaro_updated_at",
        "is_deleted",
        "origin",
        "base_state",
        "base_is_deleted",
    } <= stream_columns
    assert {"last_loaded_at", "last_pushed_at", "last_sync_error", "revision"} <= campaign_columns

    async with engine.connect() as conn:
        offer = (await conn.execute(text(
            "SELECT base_share, base_state, base_is_deleted, origin, is_deleted "
            "FROM offers WHERE id = 1"
        ))).one()
        stream = (await conn.execute(text(
            "SELECT base_state, base_is_deleted, origin FROM streams WHERE id = 1"
        ))).one()
        revision = (await conn.execute(text("SELECT revision FROM campaigns WHERE id = 1"))).scalar()

    assert tuple(offer) == (100, "active", 0, "keitaro", 0)
    assert tuple(stream) == ("active", 0, "keitaro")
    assert revision == 0
    await engine.dispose()


async def test_ensure_schema_does_not_wipe_pending_local_edits(tmp_path):
    """Restarting the app must not turn a local soft delete into a synced state."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'current.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "INSERT INTO campaigns (id, keitaro_id, name, revision, created_at, updated_at) "
            "VALUES (1, 1, 'Campaign', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        await conn.execute(text(
            "INSERT INTO streams (id, campaign_id, keitaro_id, name, state, origin, "
            "is_deleted, base_state, base_is_deleted, created_at, updated_at) "
            "VALUES (1, 1, 9001, 'Stream', 'active', 'keitaro', 0, 'active', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        await conn.execute(text(
            "INSERT INTO offers (id, campaign_id, stream_id, keitaro_id, name, state, share, "
            "origin, is_deleted, base_share, base_state, base_is_deleted, created_at, updated_at) "
            "VALUES (1, 1, 1, 42, 'Offer', 'active', 100, 'keitaro', 1, 100, 'active', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))

    await ensure_schema(engine)
    await ensure_schema(engine)

    async with engine.connect() as conn:
        offer = (await conn.execute(text(
            "SELECT is_deleted, base_is_deleted, base_share FROM offers WHERE id = 1"
        ))).one()

    assert tuple(offer) == (1, 0, 100)
    await engine.dispose()
