"""Health and Keitaro introspection endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from ..deps import KeitaroClientDep
from ..schemas import HealthOut

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(ok=True)


@router.get("/admin/stream-actions")
async def stream_actions(api: KeitaroClientDep):
    return await api.stream_actions()
