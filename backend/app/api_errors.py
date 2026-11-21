"""Domain exception -> HTTP response mapping."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .errors import EditorError, LocalPersistenceError, RevisionConflictError
from .keitaro import KeitaroError
from .services.creation import PartialCreationError
from .utils import as_int

logger = logging.getLogger(__name__)


def _response(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message, **extra}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EditorError)
    async def editor_error_handler(request: Request, exc: EditorError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail()})

    @app.exception_handler(KeitaroError)
    async def keitaro_error_handler(request: Request, exc: KeitaroError) -> JSONResponse:
        return _response(
            502,
            "KEITARO_API_ERROR",
            str(exc),
            keitaro_status=exc.status_code,
            keitaro_method=exc.method,
            keitaro_path=exc.path,
            details=exc.details,
        )

    @app.exception_handler(LocalPersistenceError)
    async def local_persistence_handler(
        request: Request, exc: LocalPersistenceError
    ) -> JSONResponse:
        return _response(500, "LOCAL_PERSISTENCE_ERROR", str(exc))

    @app.exception_handler(RevisionConflictError)
    async def revision_conflict_handler(
        request: Request, exc: RevisionConflictError
    ) -> JSONResponse:
        return _response(
            409,
            "REVISION_CONFLICT",
            "Данные изменились в другой вкладке. Обновите страницу.",
        )

    @app.exception_handler(PartialCreationError)
    async def partial_creation_handler(
        request: Request, exc: PartialCreationError
    ) -> JSONResponse:
        return _response(
            502,
            "PARTIAL_CREATION",
            str(exc),
            campaign_id=as_int((exc.campaign or {}).get("id")),
            google_stream_id=as_int((exc.google_stream or {}).get("id")),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Unhandled database error")
        return _response(
            500,
            "LOCAL_PERSISTENCE_ERROR",
            "Не удалось сохранить данные локально",
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        return _response(500, "INTERNAL_ERROR", "Внутренняя ошибка сервера")
