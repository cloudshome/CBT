"""
core/correlation_context.py
===========================
Institutional Request Traceability & Correlation Context Engine.
Provides asynchronous, thread-safe request correlation ID propagation across
all quantitative, execution, sizing, and audit subsystems via contextvars.
"""

from __future__ import annotations

import contextvars
import re
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Institutional Context Variable holding the active correlation identifier
_CORRELATION_ID_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Strict regex matching allowed correlation IDs: alphanumeric, hyphen, underscore, dot, colon
_CORRELATION_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.:]{8,64}$")


def generate_correlation_id(prefix: str = "CID") -> str:
    """Generates an institutional monotonic timestamp-prefixed correlation ID."""
    now_ms = int(time.time() * 1000)
    rand_hex = uuid.uuid4().hex[:8]
    return f"{prefix}-{now_ms}-{rand_hex}"


def sanitize_correlation_id(raw_id: Any, prefix: str = "CID") -> str:
    """
    Validates and sanitizes incoming correlation identifiers.
    Rejects malformed, control, space, or script characters to prevent telemetry injection.
    Falls back to a newly generated ID if validation fails.
    """
    if isinstance(raw_id, str):
        cleaned = raw_id.strip()
        if _CORRELATION_ID_REGEX.match(cleaned):
            return cleaned

    return generate_correlation_id(prefix=prefix)


def get_correlation_id() -> str | None:
    """Retrieves the active correlation ID from the current async/thread context."""
    return _CORRELATION_ID_VAR.get()


def set_correlation_id(cid: str | None) -> contextvars.Token:
    """Sets the active correlation ID in the current context."""
    return _CORRELATION_ID_VAR.set(cid)


def reset_correlation_id(token: contextvars.Token) -> None:
    """Resets the context variable to its prior state."""
    _CORRELATION_ID_VAR.reset(token)


@contextmanager
def correlation_scope(cid: str | None = None, prefix: str = "CID") -> Generator[str, None, None]:
    """
    Context manager that binds a correlation ID for a synchronous or asynchronous code block.
    If no ID is supplied, a new sanitized ID is created.
    """
    resolved = (
        sanitize_correlation_id(cid, prefix=prefix)
        if cid
        else generate_correlation_id(prefix=prefix)
    )
    token = set_correlation_id(resolved)
    try:
        yield resolved
    finally:
        reset_correlation_id(token)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Starlette/FastAPI middleware that binds, validates, and echoes request correlation IDs.
    """

    HEADER_NAME = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_header = request.headers.get(self.HEADER_NAME)
        cid = sanitize_correlation_id(raw_header)

        # Bind to request state
        request.state.correlation_id = cid

        # Bind to contextvar for downstream components (Orchestrator, Sizer, Audit Bus)
        token = set_correlation_id(cid)
        try:
            response = await call_next(request)
            response.headers[self.HEADER_NAME] = cid
            return response
        finally:
            reset_correlation_id(token)
