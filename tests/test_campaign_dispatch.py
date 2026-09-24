"""Tests for bulk campaign dispatch (dry-run preview + live mock dialing)."""

from __future__ import annotations


def _make_lead(client, name, phone):
    r = client.post(
        "/api/leads",
        json={"name": name, "phone": phone, "city": "Jaipur"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _make_campaign(client, name, max_attempts=1):
    r = client.post(
        "/api/campaigns",
        json={"name": name, "max_attempts": max_attempts},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client, campaign_id, lead_id):
    r = client.post(f"/api/campaigns/{campaign_id}/leads/{lead_id}")
    assert r.status_code in (200, 201), r.text


def _setup_campaign(client, name="Bulk-Sep", max_attempts=1):
    lead1 = _make_lead(client, "Bulk One", "+919000000031")
    lead2 = _make_lead(client, "Bulk Two", "+919000000032")
    campaign = _make_campaign(client, name, max_attempts=max_attempts)
    r = client.patch(f"/api/campaigns/{campaign['id']}", json={"status": "ACTIVE"})
    assert r.status_code == 200, r.text
    _assign(client, campaign["id"], lead1["id"])
    _assign(client, campaign["id"], lead2["id"])
    return campaign, lead1, lead2


def _call_count(client):
    r = client.get("/api/calls")
    assert r.status_code == 200
    body = r.json()
    if isinstance(body, dict):
        return body.get("Count", len(body.get("value", [])))
    return len(body)


def test_dispatch_dry_run_creates_nothing(client):
    campaign, _, _ = _setup_campaign(client)
    before = _call_count(client)

    r = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch",
        json={"dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["eligible"] == 2
    assert body["dispatched"] == []
    assert _call_count(client) == before


def test_dispatch_live_dials_through_mock_provider(client):
    campaign, _, _ = _setup_campaign(client, name="Bulk-Live")

    r = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch",
        json={"dry_run": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is False
    assert len(body["dispatched"]) == 2
    assert all(d["call_id"] for d in body["dispatched"])


def test_dispatch_second_run_skips_exhausted_attempts(client):
    campaign, _, _ = _setup_campaign(client, name="Bulk-Exhaust")

    first = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch",
        json={"dry_run": False},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch",
        json={"dry_run": False},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["dispatched"] == []
    assert len(body["skipped"]) == 2
    assert all(s["reason"] == "max attempts reached" for s in body["skipped"])


def test_dispatch_skips_dnd_leads(client):
    campaign, lead1, lead2 = _setup_campaign(client, name="Bulk-DND")

    r = client.patch(f"/api/leads/{lead1['id']}", json={"status": "DO_NOT_CALL"})
    assert r.status_code == 200, r.text

    r = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch",
        json={"dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eligible"] == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["lead_id"] == lead1["id"]
    assert body["skipped"][0]["reason"] == "DO_NOT_CALL"
    assert lead2["id"] not in {s["lead_id"] for s in body["skipped"]}


def test_dispatch_respects_max_calls_cap(client):
    campaign, _, _ = _setup_campaign(client, name="Bulk-Cap", max_attempts=3)

    r = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch",
        json={"dry_run": False, "max_calls": 1},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["dispatched"]) == 1


def test_dispatch_missing_and_inactive_campaign(client):
    r = client.post("/api/campaigns/99999/dispatch", json={"dry_run": True})
    assert r.status_code == 404

    campaign, _, _ = _setup_campaign(client, name="Bulk-Closed")
    r = client.patch(
        f"/api/campaigns/{campaign['id']}", json={"status": "COMPLETED"}
    )
    assert r.status_code == 200, r.text

    r = client.post(
        f"/api/campaigns/{campaign['id']}/dispatch", json={"dry_run": True}
    )
    assert r.status_code == 409
