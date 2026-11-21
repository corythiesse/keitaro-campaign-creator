"""FastAPI dependencies shared by routers."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .keitaro import KeitaroClient


async def get_keitaro_client() -> AsyncGenerator[KeitaroClient, None]:
    client = KeitaroClient()
    try:
        yield client
    finally:
        await client.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]
KeitaroClientDep = Annotated[KeitaroClient, Depends(get_keitaro_client)]
