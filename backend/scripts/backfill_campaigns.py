#!/usr/bin/env python
"""Idempotent backfill of locally cached campaigns from Keitaro.

Reads ``campaign_creation_logs`` (statuses ``success``/``partial`` with a
``keitaro_campaign_id``) and upserts the campaign from ``GET /campaigns/{id}``
plus its streams/offers from ``GET /campaigns/{id}/streams``.

- If Keitaro returns a usable stream list, streams + offers are stored.
- If the streams endpoint fails, only the campaign is stored - the script never
  crashes on an unexpected payload.

The script is idempotent (upserts by natural keys) and is never executed on
application startup.

Usage (from ``backend/``):

    python -m scripts.backfill_campaigns --dry-run
    python -m scripts.backfill_campaigns --limit 10
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.errors import LocalPersistenceError
from app.keitaro import KeitaroClient, KeitaroError
from app.migrations import ensure_schema
from app.models import CampaignCreationLog
from app.repositories import save_campaign, save_streams_and_offers


def extract_offers(streams: list[dict]) -> list[dict]:
    """Normalize ``Stream.offers[]`` (``OfferStream``) into repository items."""
    result: list[dict] = []
    for stream in streams or []:
        if not isinstance(stream, dict):
            continue
        for item in stream.get("offers") or []:
            if not isinstance(item, dict):
                continue
            offer_id = item.get("offer_id")
            if offer_id is None:
                continue
            result.append({
                "stream": stream,
                "offer_id": offer_id,
                "share": item.get("share"),
                "state": item.get("state"),
                "id": item.get("id"),
                "snapshot": {"id": offer_id, "name": item.get("name")},
            })
    return result


async def backfill(limit: int | None, dry_run: bool) -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema(engine)

    api = KeitaroClient()
    processed = 0
    try:
        async with SessionLocal() as db:
            logs = (
                await db.scalars(
                    select(CampaignCreationLog)
                    .where(
                        CampaignCreationLog.status.in_(["success", "partial"]),
                        CampaignCreationLog.keitaro_campaign_id.is_not(None),
                    )
                    .order_by(CampaignCreationLog.id)
                )
            ).all()

            for log in logs:
                if limit is not None and processed >= limit:
                    break
                processed += 1
                keitaro_id = log.keitaro_campaign_id

                detail = None
                try:
                    detail = await api.get_campaign(keitaro_id)
                except KeitaroError as exc:
                    print(f"[{keitaro_id}] GET /campaigns/{keitaro_id} failed: {exc}")
                except Exception as exc:  # pragma: no cover - defensive
                    print(f"[{keitaro_id}] unexpected error: {exc}")

                streams: list[dict] = []
                try:
                    remote_streams = await api.campaign_streams(keitaro_id)
                    if isinstance(remote_streams, list):
                        streams = [
                            stream
                            for stream in remote_streams
                            if isinstance(stream, dict) and stream.get("id") is not None
                        ]
                except KeitaroError as exc:
                    print(f"[{keitaro_id}] GET /campaigns/{keitaro_id}/streams failed: {exc}")
                except Exception as exc:  # pragma: no cover - defensive
                    print(f"[{keitaro_id}] unexpected streams error: {exc}")

                offers = extract_offers(streams)
                campaign_data = {
                    "id": keitaro_id,
                    "name": log.campaign_name,
                    **(detail if isinstance(detail, dict) else {}),
                }

                if dry_run:
                    print(
                        f"[dry-run] campaign keitaro_id={keitaro_id} "
                        f"streams={len(streams)} offers={len(offers)}"
                    )
                    continue

                try:
                    campaign_row = await save_campaign(db, campaign_data, log_id=log.id)
                    if streams:
                        await save_streams_and_offers(db, campaign_row, streams, offers)
                    await db.commit()
                    print(
                        f"[{keitaro_id}] saved campaign, "
                        f"streams={len(streams)}, offers={len(offers)}"
                    )
                except LocalPersistenceError as exc:
                    await db.rollback()
                    print(f"[{keitaro_id}] failed to save: {exc}")

            return processed
    finally:
        await api.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill local campaigns from Keitaro")
    parser.add_argument("--limit", type=int, default=None, help="max number of log rows to process")
    parser.add_argument("--dry-run", action="store_true", help="print actions without writing to the DB")
    args = parser.parse_args()

    processed = asyncio.run(backfill(args.limit, args.dry_run))
    print(f"Processed {processed} campaign(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
