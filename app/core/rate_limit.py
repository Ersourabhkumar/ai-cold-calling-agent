from __future__ import annotations

import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import env

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60


class InMemoryRateLimiter:
    """Fixed-window counter keyed by an arbitrary string.

    Intended for single-process deployments. For horizontally scaled workers
    prefer an external store; the window is intentionally small.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int = _WINDOW_SECONDS,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._buckets: dict[str, tuple[float, int]] = {}

    def _prune(self, now: float) -> None:
        if len(self._buckets) <= self.max_keys:
            return
        cutoff = now - self.window_seconds
        stale = [
            key
            for key, (window_start, _) in self._buckets.items()
            if window_start < cutoff
        ]
        for key in stale:
            self._buckets.pop(key, None)

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        self._prune(now)

        window_start, count = self._buckets.get(key, (now, 0))

        if now - window_start >= self.window_seconds:
            window_start, count = now, 0

        count += 1
        self._buckets[key] = (window_start, count)

        if count > self.limit:
            retry_in = max(1, int(self.window_seconds - (now - window_start)))
            return False, retry_in

        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit /api traffic per client IP."""

    def __init__(
        self,
        app,
        limit: int | None = None,
    ) -> None:
        super().__init__(app)
        effective_limit = limit if limit is not None else self._configured_limit()
        self._limiter = InMemoryRateLimiter(effective_limit)

    @staticmethod
    def _configured_limit() -> int:
        raw = env("RATE_LIMIT_PER_MINUTE", "120") or "120"
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning(
                "Invalid RATE_LIMIT_PER_MINUTE=%s; falling back to 120",
                raw,
            )
            return 120

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        client = forwarded.split(",")[0].strip() if forwarded else None
        return client or request.client.host if request.client else "unknown"

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        allowed, retry_in = self._limiter.allow(self._client_key(request))

        if not allowed:
            logger.warning(
                "Rate limit exceeded for %s on %s",
                self._client_key(request),
                path,
            )
            return Response(
                status_code=429,
                content='{"detail":"Rate limit exceeded"}',
                media_type="application/json",
                headers={"Retry-After": str(retry_in)},
            )

        return await call_next(request)