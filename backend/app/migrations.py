"""Idempotent schema top-up for the local cache database.

``Base.metadata.create_all`` only creates missing tables; it never adds columns
to an existing table. Alembic is intentionally not used: the project has a
single SQLite database and the changes below are additive only.

``ensure_schema`` is safe to call more than once. The baseline backfill is a
**one-time** operation: it runs only for the columns that were actually added by
this call. Re-running the migrations on every start must never rewrite the
``base_*`` columns of an already upgraded database, otherwise unsynchronised
local edits (for example a soft-deleted offer) would silently become part of the
baseline.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

# name -> DDL used for SQLite. Boolean defaults are translated for PostgreSQL
# in :func:`_ddl_for`; other columns are dialect-neutral.
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "campaigns": [
        ("last_loaded_at", "DATETIME"),
        ("last_pushed_at", "DATETIME"),
        ("last_sync_error", "TEXT"),
        ("revision", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "streams": [
        ("comments", "TEXT"),
        ("weight", "FLOAT"),
        ("keitaro_updated_at", "VARCHAR(32)"),
        ("is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
        ("origin", "VARCHAR(16) NOT NULL DEFAULT 'keitaro'"),
        ("base_state", "VARCHAR(20)"),
        ("base_is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
    "offers": [
        ("keitaro_offer_stream_id", "INTEGER"),
        ("is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
        ("is_pinned", "BOOLEAN NOT NULL DEFAULT 0"),
        ("pinned_share", "INTEGER"),
        ("origin", "VARCHAR(16) NOT NULL DEFAULT 'keitaro'"),
        ("base_share", "INTEGER"),
        ("base_state", "VARCHAR(20)"),
        ("base_is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
}


def _ddl_for(engine: Engine, ddl: str) -> str:
    """Translate the SQLite-oriented DDL for the current dialect."""
    if engine.dialect.name == "sqlite":
        return ddl
    ddl = ddl.replace("DATETIME", "TIMESTAMP")
    if ddl.startswith("BOOLEAN"):
        # Only boolean columns use "DEFAULT 0"; integer columns such as
        # ``revision`` must keep their numeric default.
        ddl = ddl.replace("DEFAULT 0", "DEFAULT FALSE").replace("DEFAULT 1", "DEFAULT TRUE")
    return ddl


def _existing_columns(connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


async def ensure_schema(engine: AsyncEngine) -> None:
    """Add missing columns and backfill the baseline for legacy rows once."""
    added: dict[str, set[str]] = {}
    async with engine.begin() as conn:
        existing_tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))

        for table, columns in COLUMNS.items():
            if table not in existing_tables:
                continue
            existing_columns = await conn.run_sync(lambda c, t=table: _existing_columns(c, t))
            for name, ddl in columns:
                if name in existing_columns:
                    continue
                await conn.execute(
                    text(f'ALTER TABLE {table} ADD COLUMN "{name}" {_ddl_for(engine, ddl)}')
                )
                added.setdefault(table, set()).add(name)

    await _backfill_baseline(engine, added)


async def _backfill_baseline(
    engine: AsyncEngine,
    added: dict[str, set[str]],
) -> None:
    """Make legacy rows look "clean": baseline == current working state.

    Statements are emitted only for columns added during this run. On an
    already upgraded database ``added`` is empty, so pending local edits are
    never overwritten by a restart.
    """
    statements: list[str] = []
    offer_columns = added.get("offers", set())
    if offer_columns:
        if "base_share" in offer_columns:
            statements.append("UPDATE offers SET base_share = share WHERE base_share IS NULL")
        if "base_state" in offer_columns:
            statements.append("UPDATE offers SET base_state = state WHERE base_state IS NULL")
        if "base_is_deleted" in offer_columns:
            statements.append("UPDATE offers SET base_is_deleted = is_deleted WHERE is_deleted")
        if "origin" in offer_columns:
            statements.append("UPDATE offers SET origin = 'keitaro' WHERE origin IS NULL")

    stream_columns = added.get("streams", set())
    if stream_columns:
        if "base_state" in stream_columns:
            statements.append("UPDATE streams SET base_state = state WHERE base_state IS NULL")
        if "base_is_deleted" in stream_columns:
            statements.append("UPDATE streams SET base_is_deleted = is_deleted WHERE is_deleted")
        if "origin" in stream_columns:
            statements.append("UPDATE streams SET origin = 'keitaro' WHERE origin IS NULL")

    if not statements:
        return
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
