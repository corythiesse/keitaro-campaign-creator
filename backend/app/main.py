"""FastAPI application assembly."""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api_errors import register_exception_handlers
from .config import settings
from .database import Base, engine
from .errors import LocalPersistenceError
from .migrations import ensure_schema
from .routers import campaigns, editor, health, offers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Running DDL at import time made every import (scripts, tests) touch the
    # configured database and raced between uvicorn workers. Initialise the
    # schema once per process here; multi-worker deployments can disable this
    # with AUTO_MIGRATE=false and run ``python -m scripts.init_db`` first.
    settings.require_keitaro()
    if settings.auto_migrate:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_schema(engine)
    if not settings.api_auth_token:
        logger.warning("API_AUTH_TOKEN is empty: the HTTP API is open")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Keitaro Campaign Creator",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        """Protect the API when ``API_AUTH_TOKEN`` is configured."""
        token = settings.api_auth_token
        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        if token and is_api and path != "/api/health":
            provided = request.headers.get("x-api-token")
            if not provided:
                authorization = request.headers.get("authorization", "")
                scheme, _, value = authorization.partition(" ")
                if scheme.lower() == "bearer":
                    provided = value.strip()
            if not provided or not secrets.compare_digest(provided, token):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "code": "UNAUTHORIZED",
                            "message": "Не указан или неверный API-токен",
                        }
                    },
                )
        return await call_next(request)

    # Added last so CORS becomes the outermost middleware and 401 responses
    # still carry the CORS headers required by the browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(campaigns.router)
    app.include_router(offers.router)
    app.include_router(editor.router)
    return app


app = create_app()

__all__ = ["app", "create_app", "LocalPersistenceError"]
