"""Read-only probe of the Keitaro stream endpoints (plan §2.7, stage 0).

Developer/diagnostic tool: the application never imports this module. Checks
the shape of ``GET /campaigns/{id}/streams`` and ``GET /offers`` before relying
on them. Never sends ``PUT``/``DELETE``: manual write checks (K1-K4) are
performed on a test campaign.

Run from ``backend/`` (the ``.env`` there is read by Settings):

    python -m scripts.dev.probe_keitaro_streams 456
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.keitaro import KeitaroClient


async def main(campaign_id: int) -> None:
    api = KeitaroClient()
    try:
        streams = await api.campaign_streams(campaign_id)
        print("streams:", json.dumps(streams, indent=2, ensure_ascii=False)[:4000])
        if isinstance(streams, list):
            for stream in streams:
                print(
                    "stream", stream.get("id"),
                    "state=", stream.get("state"),
                    "offers=", [
                        (offer.get("id"), offer.get("offer_id"), offer.get("share"), offer.get("state"))
                        for offer in (stream.get("offers") or [])
                    ],
                )
        offers = await api.offers_all()
        print("offers count:", len(offers) if isinstance(offers, list) else "non-list")
    finally:
        await api.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.dev.probe_keitaro_streams <campaign_id>")
    asyncio.run(main(int(sys.argv[1])))
