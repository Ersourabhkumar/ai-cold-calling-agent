from __future__ import annotations


def _clean_api_env(monkeypatch, *, api_key: str):
    # Ensure middleware sees the key and rate limit is high enough.
    monkeypatch.setenv("API_KEY", api_key)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "10000")


def test_api_key_middleware_blocks_unauthenticated(monkeypatch):
    # App.middleware reads env at request time via app.core.config.env,
    # which calls os.getenv each time, so setting the env var works live.
    _clean_api_env(monkeypatch, api_key="sekrit")

    import app.main as main

    # Re-import config to be safe about cached module values.
    from app.core import config as cfg

    # Build a minimal test client by importing the app the way tests do.
    from fastapi.testclient import TestClient

    # NOTE: app.main already imported config; monkeypatch its env function only
    # if it captured it. To keep this robust we use a lightweight ASGI call.
    def get_config():  # pragma: no cover - helper
        pass

    client = TestClient(main.app)

    # No key -> 401
    resp = client.get("/api/leads")
    assert resp.status_code == 401

    # Wrong key -> 401
    resp = client.get("/api/leads", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

    # Correct key -> not 401 (and not an auth error)
    resp = client.get("/api/leads", headers={"X-API-Key": "sekrit"})
    assert resp.status_code != 401

    # Public endpoints stay open without a key
    resp = client.get("/health")
    assert resp.status_code == 200
