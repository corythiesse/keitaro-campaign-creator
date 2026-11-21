#!/usr/bin/env python
"""One-shot creation/upgrade of the local database schema.

Run this before starting several application workers (``AUTO_MIGRATE=false``),
so that DDL is not executed concurrently by every worker.

Usage (from ``backend/``):

    python -m scripts.init_db
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: F401 - register tables on Base.metadata
from app.database import Base, engine
from app.migrations import ensure_schema


async def main() -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema(engine)
    print(f"Schema is up to date: {engine.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
