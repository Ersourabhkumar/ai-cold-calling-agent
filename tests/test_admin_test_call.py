import pytest


def test_admin_test_call_dispatches_one_call(client):
    resp = client.post(
        "/api/admin/test-call",
        json={"phone": "+917665035514", "lead_name": "Demo Customer"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["call"]["status"] == "INITIATED"
    assert body["call"]["provider"] == "mock"
    assert body["call"]["id"] > 0
    assert body["diagnostics"]["Provider"] == "mock"
    assert body["diagnostics"]["Destination"] == "+********5514"
    assert "7660" not in " ".join(map(str, body["diagnostics"].values()))


def test_admin_test_call_rejects_invalid_phone(client):
    resp = client.post(
        "/api/admin/test-call",
        json={"phone": "12345"},
    )
    assert resp.status_code == 422


def test_admin_test_call_rejects_local_number(client):
    resp = client.post(
        "/api/admin/test-call",
        json={"phone": "7665035514"},
    )
    assert resp.status_code == 422


def test_admin_test_call_rejects_duplicate_campaign(client):
    first = client.post(
        "/api/admin/test-call",
        json={"phone": "+917665035514"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/admin/test-call",
        json={"phone": "+917665035515", "campaign_name": "AI Real Estate Demo"},
    )
    assert second.status_code == 409


def test_admin_test_call_status(client):
    created = client.post(
        "/api/admin/test-call",
        json={"phone": "+917665035514"},
    ).json()
    call_id = created["call"]["id"]

    resp = client.post(
        f"/api/admin/test-call/status?call_id={call_id}", json={}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["call"]["id"] == call_id
    assert body["diagnostics"]["Internal Call ID"] == call_id
    assert body["lead"]["id"] > 0