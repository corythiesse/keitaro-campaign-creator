"""Application-level errors shared by services, repositories and API handlers."""
from __future__ import annotations

from typing import Any


class EditorError(Exception):
    """A business error with an HTTP status and a stable ``code``."""

    def __init__(self, status_code: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


class LocalPersistenceError(Exception):
    """Raised when a snapshot could not be written to the local database.

    ``campaign`` is the optional Keitaro campaign dict, so the caller can still
    record ``keitaro_campaign_id`` in the operation log.
    """

    def __init__(self, message: str, campaign: dict | None = None):
        super().__init__(message)
        self.campaign = campaign


class RevisionConflictError(Exception):
    """A compare-and-swap on ``campaigns.revision`` found a stale value."""


class RemoteChanged(Exception):
    """The stream was modified in Keitaro after the last load/push."""
