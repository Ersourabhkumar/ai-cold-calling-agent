from __future__ import annotations

import hmac

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import env

_OPEN_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/health",
}


def _is_open_path(path: str) -> bool:
    if path in _OPEN_PATHS:
        return True
    return any(
        path == prefix or path.startswith(prefix + "/") or path.startswith(prefix)
        for prefix in ("/health", "/webhooks")
    )


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require an API key for /api routes when API_KEY is configured."""

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        api_key = env("API_KEY")

        if api_key and request.url.path.startswith("/api/"):
            presented = request.headers.get("X-API-Key", "")
            if not presented or not hmac.compare_digest(presented, api_key):
                return Response(
                    status_code=401,
                    content='{"detail":"Invalid or missing API key"}',
                    media_type="application/json",
                    headers={"WWW-Authenticate": "ApiKey"},
                )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline hardening headers to every response."""

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )

        return response