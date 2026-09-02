from __future__ import annotations

import contextvars
import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import env

logger = logging.getLogger(__name__)

request_id_var = contextvars.ContextVar(
    "request_id",
    default=None,
)


class RequestIdFilter(logging.Filter):
    """Attach the active request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure a single root handler with request-id aware formatting."""
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] "
        "request_id=%(request_id)s %(message)s"
    )

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        # Logger-level filters are not applied to propagated records, so the
        # request-id filter must live on the handler itself.
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            if not isinstance(handler, logging.StreamHandler):
                continue
            handler.setFormatter(formatter)
            if not any(
                isinstance(existing, RequestIdFilter)
                for existing in handler.filters
            ):
                handler.addFilter(RequestIdFilter())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, time the request, and emit an access log line."""

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        request_id = request.headers.get(
            "X-Request-Id",
            uuid.uuid4().hex[:24],
        )
        request_id_var.set(request_id)

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "%s %s failed",
                request.method,
                request.url.path,
            )
            raise
        finally:
            request_id_var.set(None)

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        logger.info(
            "%s %s -> %d (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response