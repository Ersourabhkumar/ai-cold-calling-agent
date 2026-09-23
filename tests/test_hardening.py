from __future__ import annotations


def test_validate_production_config_rejects_sqlite_and_mock(monkeypatch):
    import app.core.config as cfg

    monkeypatch.setenv("CALLING_MODE", "production")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "sarvam")
    monkeypatch.setenv(
        "DATABASE_URL",
        "sqlite:///./test.db",
    )
    for key in (
        "SARVAM_API_KEY",
        "SARVAM_ORG_ID",
        "SARVAM_WORKSPACE_ID",
        "SARVAM_APP_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    health = cfg.validate_production_config()

    assert health.ok is False
    joined = " ".join(health.errors).lower()
    assert "sqlite" in joined
    assert "sarvam_api_key" in joined


def test_validate_production_config_ok_for_mock(monkeypatch):
    import app.core.config as cfg

    monkeypatch.setenv("CALLING_MODE", "mock")
    health = cfg.validate_production_config()
    assert health.ok is True


from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.rate_limit import InMemoryRateLimiter, RateLimitMiddleware


def test_in_memory_rate_limiter_fixed_window():
    limiter = InMemoryRateLimiter(limit=3, window_seconds=60)

    for _ in range(3):
        allowed, _ = limiter.allow("client-1")
        assert allowed is True

    allowed, retry_in = limiter.allow("client-1")
    assert allowed is False
    assert retry_in >= 1

    # A different client is not affected.
    assert limiter.allow("client-2") == (True, 0)


def test_rate_limit_middleware_returns_429():
    async def open_health(request):
        return JSONResponse({"ok": True})

    async def api_route(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/health", open_health),
            Route("/api/x", api_route, methods=["GET"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, limit=3)

    from fastapi.testclient import TestClient

    with TestClient(app) as tmp_client:
        for _ in range(3):
            assert tmp_client.get("/api/x").status_code == 200

        overflow = tmp_client.get("/api/x")
        assert overflow.status_code == 429
        assert overflow.headers.get("Retry-After")

        # Non-/api routes are never limited.
        assert tmp_client.get("/health").status_code == 200


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert resp.headers.get("Cache-Control") == "no-store"


def test_request_id_header_set(client):
    resp = client.get("/health", headers={"X-Request-Id": "my-trace-1"})
    assert resp.headers.get("X-Request-Id") == "my-trace-1"
    assert resp.headers.get("X-Process-Time")