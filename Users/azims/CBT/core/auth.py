"""
API Key Authentication for FastAPI

Provides a reusable dependency that validates API keys from:
  - Authorization: Bearer <key> header
  - X-API-Key: <key> header

When API_KEY env var is not set, all requests pass through (backward compatible).
When API_KEY is set, sensitive endpoints require a matching key.
"""

import os
import hmac
from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY", "")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _extract_api_key(request: Request, x_api_key: str | None) -> str | None:
    """Extract API key from Authorization header or X-API-Key header."""
    # Check Authorization: Bearer <key>
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    # Check X-API-Key header
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()

    return None


async def require_api_key(
    request: Request,
    x_api_key: str | None = Depends(_api_key_header),
) -> None:
    """
    FastAPI dependency that enforces API key authentication.

    Usage:
        @app.post("/api/sensitive", dependencies=[Depends(require_api_key)])
        async def sensitive_endpoint(): ...

    When API_KEY is not configured, all requests pass through (dev-friendly).
    """
    env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    if not API_KEY:
        if env == "production":
            raise HTTPException(
                status_code=500,
                detail={"error": "Production Security Misconfiguration: API_KEY must be configured in production."},
            )
        return  # No key configured in dev/test — backward compatible passthrough

    provided_key = _extract_api_key(request, x_api_key)

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Authentication required",
                "message": "Provide API key via Authorization: Bearer <key> or X-API-Key header",
            },
        )

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_key.encode(), API_KEY.encode()):
        raise HTTPException(
            status_code=403,
            detail={"error": "Invalid API key"},
        )
