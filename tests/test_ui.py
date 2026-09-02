from __future__ import annotations


def test_ui_dashboard_renders(client):
    r = client.get("/ui")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_ui_pages_render(client):
    for path, needle in [
        ("/ui/leads", "Leads / CRM"),
        ("/ui/calls", "All Calls"),
        ("/ui/followups", "Follow-ups"),
        ("/ui/new-call", "Fire a Live Call"),
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert needle in r.text, path


def test_root_redirects_to_ui(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"].endswith("/ui")


def test_ui_create_lead(client):
    r = client.post(
        "/ui/api/leads",
        json={"name": "UI Lead", "phone": "+919876543210", "city": "Delhi"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "UI Lead"

    page = client.get("/ui/leads")
    assert "UI Lead" in page.text


def test_ui_lead_detail_renders(client):
    r = client.post(
        "/ui/api/leads",
        json={"name": "Detail Lead", "phone": "+919876543210", "city": "Pune"},
    )
    lead_id = r.json()["id"]
    page = client.get(f"/ui/leads/{lead_id}")
    assert page.status_code == 200
    assert "Detail Lead" in page.text

    missing = client.get("/ui/leads/99999")
    assert missing.status_code == 404


def test_ui_fire_call_endpoint(client):
    r = client.post(
        "/ui/api/test-call",
        json={
            "phone": "+919876543210",
            "lead_name": "UI Fire",
            "city": "Pune",
            "campaign_name": "UI-Smoke-Test",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["call"]["id"] > 0

    status = client.post(f"/ui/api/test-call/status?call_id={body['call']['id']}")
    assert status.status_code == 200
    assert status.json()["call"]["id"] == body["call"]["id"]
