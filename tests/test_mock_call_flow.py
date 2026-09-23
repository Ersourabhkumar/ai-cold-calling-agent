"""PHASE A: Complete mock Sarvam call flow verification.

Tests the full end-to-end flow in mock mode:
  Lead -> Campaign -> Call -> Dispatch -> MockProvider -> Simulated Sarvam webhook
  -> Webhook processing -> Transcript storage -> Enrichment -> Lead update -> Database

No real calls are placed. No real provider is used.
The Sarvam webhook path (/webhooks/sarvam/status) is exercised via
the simulate endpoint's new sarvam scenario and via the HTTP webhook endpoint.
"""
from __future__ import annotations


def _create_ready_call(client, *, max_attempts: int = 5) -> dict:
    """Create lead + campaign + assign + call. Returns call JSON."""
    lead = client.post(
        "/api/leads",
        json={"name": "Test Lead", "phone": "+919876543210", "source": "test"},
    )
    assert lead.status_code == 201, lead.text
    lead_data = lead.json()

    campaign = client.post(
        "/api/campaigns",
        json={"name": f"Campaign for {lead_data['id']}", "max_attempts": max_attempts},
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]

    assert client.patch(f"/api/campaigns/{campaign_id}", json={"status": "ACTIVE"}).status_code == 200
    assert client.post(f"/api/campaigns/{campaign_id}/leads/{lead_data['id']}").status_code == 201

    call = client.post(
        "/api/calls", json={"lead_id": lead_data["id"], "campaign_id": campaign_id}
    )
    assert call.status_code == 201, call.text
    assert call.json()["status"] == "QUEUED"
    return call.json()


def _dispatch_call(client, call_id: int) -> str:
    """Dispatch a call and return provider_call_id."""
    resp = client.post(f"/api/calls/{call_id}/start")
    assert resp.status_code == 200, resp.text
    return resp.json()["provider_call_id"]


def _send_sarvam_webhook(client, provider_call_id: str, status: str, *, call_id: int | None = None,
                          duration: int | None = None, transcript: list | None = None,
                          agent_variables: dict | None = None, interaction_id: str | None = None) -> dict:
    """Send a Sarvam webhook via the HTTP endpoint."""
    payload = {
        "attempt_id": provider_call_id,
        "status": status,
        "duration": duration,
        "interaction_id": interaction_id,
        "failure_reason": None,
        "final_agent_variables": agent_variables,
        "interaction_transcript": transcript,
        "webhook_config": {"metadata": {"call_id": str(call_id)} if call_id else {}},
    }
    resp = client.post("/webhooks/sarvam/status", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ============================================================
# PHASE A: Core mock call flow — connected scenarios
# ============================================================


def test_sarvam_connected_qualified_lead(client):
    """Full happy path: qualified lead with budget, timeline, site visit."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={"scenario": "sarvam"},
    )
    assert result.status_code == 200, result.text
    body = result.json()

    assert body["success"] is True
    assert body["handled"] is True
    assert body["enriched"] is True

    call_resp = body["call"]
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["outcome"] == "APPOINTMENT_BOOKED"
    assert call_resp["provider"] == "mock"
    assert call_resp["duration_seconds"] == 120
    assert call_resp["transcript"] is not None
    assert "Hello" in call_resp["transcript"]

    messages = client.get(f"/api/calls/{call_id}/messages").json()
    assert len(messages) >= 2
    speakers = [m["speaker"] for m in messages]
    assert "CALLER" in speakers
    assert "CUSTOMER" in speakers

    summary_resp = client.get(f"/api/calls/{call_id}/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["qualification"]["interested"] is True
    assert summary["qualification"]["appointment_requested"] is True
    assert summary["qualification_status"] == "QUALIFIED"

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "APPOINTMENT_BOOKED"

    events = client.get(f"/api/calls/{call_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "call.completed" in event_types


def test_sarvam_connected_interested_no_appointment(client):
    """Interested lead but no appointment requested."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "property_type": "apartment",
                "bhk": "2",
                "location": "Mumbai",
                "budget": "1 crore",
                "budget_amount": 10000000,
                "timeline": "6 months",
                "interested": True,
                "appointment_requested": False,
                "callback_requested": False,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()

    assert body["success"] is True
    assert body["enriched"] is True

    call_resp = body["call"]
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["outcome"] == "INTERESTED"

    summary_resp = client.get(f"/api/calls/{call_id}/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["qualification"]["interested"] is True
    assert summary["qualification"]["appointment_requested"] is False

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "INTERESTED"


def test_sarvam_connected_callback_requested(client):
    """Callback requested creates followup."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "property_type": "villa",
                "bhk": "3",
                "location": "Pune",
                "budget": "80 lakh",
                "budget_amount": 8000000,
                "timeline": "2 months",
                "interested": True,
                "callback_requested": True,
                "appointment_requested": False,
                "qualification_status": "QUALIFIED",
            },
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello!"},
                {"role": "user", "en_text": "I am interested but call me back tomorrow."},
                {"role": "agent", "en_text": "Sure, I will arrange a follow-up."},
            ],
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["enriched"] is True

    call_resp = body["call"]
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["outcome"] == "CALLBACK"

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "CALLBACK"

    followups = client.get(f"/api/followups/lead/{lead_id}").json()
    assert len(followups) >= 1
    assert followups[0]["status"] == "PENDING"


def test_sarvam_connected_not_interested(client):
    """Not interested lead."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "interested": False,
                "qualification_status": "UNQUALIFIED",
                "disposition": "not_interested",
            },
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello!"},
                {"role": "user", "en_text": "I am not interested. Please do not call again."},
            ],
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["enriched"] is True

    call_resp = body["call"]
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["outcome"] == "NOT_INTERESTED"

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "NOT_INTERESTED"


def test_sarvam_connected_do_not_call(client):
    """DND request sets DO_NOT_CALL."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "interested": False,
                "qualification_status": "DO_NOT_CONTACT",
                "disposition": "dnd",
            },
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello!"},
                {"role": "user", "en_text": "Do not call me again. Remove my number."},
            ],
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["enriched"] is True

    call_resp = body["call"]
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["outcome"] == "DO_NOT_CALL"

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "DO_NOT_CALL"


def test_sarvam_wrong_number(client):
    """Wrong number outcome."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "interested": False,
                "qualification_status": "UNQUALIFIED",
                "disposition": "wrong_number",
            },
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello, am I speaking with the property owner?"},
                {"role": "user", "en_text": "You have the wrong number."},
            ],
        },
    )
    assert result.status_code == 200, result.text

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] in {"NOT_INTERESTED", "FAILED"}


def test_sarvam_incomplete_conversation(client):
    """Incomplete conversation with no qualification data."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "interested": False,
                "qualification_status": "UNKNOWN",
            },
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello!"},
                {"role": "user", "en_text": "Hello"},
            ],
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()

    call_resp = body["call"]
    assert call_resp["status"] == "COMPLETED"

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "COMPLETED"


# ============================================================
# PHASE A: Terminal scenarios via webhook
# ============================================================


def test_sarvam_no_answer(client):
    """Sarvam reports no_answer via HTTP webhook."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    provider_call_id = _dispatch_call(client, call_id)

    body = _send_sarvam_webhook(client, provider_call_id, "no_answer", call_id=call_id)
    assert body["handled"] is True

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "NO_ANSWER"
    assert call_resp["retry_reason"] is not None

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "FAILED"


def test_sarvam_busy(client):
    """Sarvam reports busy via HTTP webhook."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    body = _send_sarvam_webhook(client, provider_call_id, "busy", call_id=call_id)
    assert body["handled"] is True

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "BUSY"


def test_sarvam_failed(client):
    """Sarvam reports failed via HTTP webhook."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    body = _send_sarvam_webhook(client, provider_call_id, "failed", call_id=call_id,
                                 duration=5, interaction_id="fail-int-001")
    assert body["handled"] is True

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "FAILED"


# ============================================================
# PHASE A: Transcript and language scenarios
# ============================================================


def test_sarvam_hindi_transcript(client):
    """Hindi transcript is stored correctly."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_transcript": [
                {"role": "agent", "en_text": "namaste, main AI sahayak bol raha hoon."},
                {"role": "user", "en_text": "haan, bataiye."},
                {"role": "agent", "en_text": "aap kis tarah ki property dhoond rahe hain?"},
                {"role": "user", "en_text": "mujhe 2 BHK apartment chahiye."},
                {"role": "agent", "en_text": "aapka budget kya hai?"},
                {"role": "user", "en_text": "50 lakh ke aaspaas."},
            ],
            "sarvam_agent_variables": {
                "property_type": "apartment",
                "bhk": "2",
                "location": "Delhi",
                "budget": "50 lakh",
                "budget_amount": 5000000,
                "interested": True,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["enriched"] is True

    messages = client.get(f"/api/calls/{call_id}/messages").json()
    assert len(messages) >= 2


def test_sarvam_english_transcript(client):
    """English transcript is stored correctly."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello, this is the AI assistant."},
                {"role": "user", "en_text": "Hi, I am looking for a flat."},
                {"role": "agent", "en_text": "What is your budget?"},
                {"role": "user", "en_text": "Around 75 lakh."},
            ],
            "sarvam_agent_variables": {
                "property_type": "flat",
                "budget": "75 lakh",
                "budget_amount": 7500000,
                "interested": True,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["enriched"] is True


def test_sarvam_hinglish_transcript(client):
    """Hinglish transcript is stored correctly."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello, main AI assistant bol raha hoon."},
                {"role": "user", "en_text": "Haan batao."},
                {"role": "agent", "en_text": "Aap kya dhoond rahe hain?"},
                {"role": "user", "en_text": "Mujhe 2 BHK chahiye, budget around 50 lakh."},
            ],
            "sarvam_agent_variables": {
                "property_type": "apartment",
                "bhk": "2",
                "budget": "50 lakh",
                "budget_amount": 5000000,
                "interested": True,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["enriched"] is True


# ============================================================
# PHASE A: Edge cases
# ============================================================


def test_sarvam_empty_transcript(client):
    """Missing transcript does not break the flow."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_transcript": None,
            "sarvam_agent_variables": {
                "interested": True,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["enriched"] is True

    call_resp = result.json()["call"]
    assert call_resp["status"] == "COMPLETED"


def test_sarvam_empty_agent_variables(client):
    """Missing agent variables does not break the flow."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {},
            "sarvam_transcript": [
                {"role": "agent", "en_text": "Hello"},
                {"role": "user", "en_text": "Hello"},
            ],
        },
    )
    assert result.status_code == 200, result.text

    call_resp = result.json()["call"]
    assert call_resp["status"] == "COMPLETED"


def test_sarvam_recording_url_set(client):
    """Recording URL is constructed from interaction_id."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={"scenario": "sarvam"},
    )
    assert result.status_code == 200, result.text

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["recording_url"] is not None
    assert "recordings/" in call_resp["recording_url"]
    assert "simulated-int-" in call_resp["recording_url"]


def test_sarvam_lead_fields_updated(client):
    """Lead fields are updated from agent variables."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "property_type": "villa",
                "bhk": "4",
                "location": "Goa",
                "budget": "2 crore",
                "budget_amount": 20000000,
                "timeline": "1 year",
                "interested": True,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["budget"] == "20000000"
    assert lead["timeline"] in {"1 year", "1 years"}
    assert lead["city"] == "Goa"


def test_sarvam_site_visit_requested(client):
    """Site visit / appointment requested flow."""
    call = _create_ready_call(client)
    call_id = call["id"]
    lead_id = call["lead_id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "property_type": "apartment",
                "bhk": "3",
                "location": "Noida",
                "budget": "1.5 crore",
                "budget_amount": 15000000,
                "timeline": "within 2 months",
                "purpose": "investment",
                "interested": True,
                "appointment_requested": True,
                "qualification_status": "QUALIFIED",
            },
        },
    )
    assert result.status_code == 200
    body = result.json()

    assert body["call"]["outcome"] == "APPOINTMENT_BOOKED"

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["status"] == "APPOINTMENT_BOOKED"


# ============================================================
# PHASE A: HTTP webhook endpoint tests
# ============================================================


def test_sarvam_webhook_via_http_endpoint(client):
    """Test the actual /webhooks/sarvam/status HTTP endpoint."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    body = _send_sarvam_webhook(
        client, provider_call_id, "connected", call_id=call_id,
        duration=95, interaction_id="http-test-int-001",
        transcript=[
            {"role": "agent", "en_text": "Hello!"},
            {"role": "user", "en_text": "I am looking for 2 BHK in Chennai."},
            {"role": "agent", "en_text": "What is your budget?"},
            {"role": "user", "en_text": "40 lakh."},
            {"role": "agent", "en_text": "When do you need it?"},
            {"role": "user", "en_text": "Within 1 month."},
        ],
        agent_variables={
            "property_type": "apartment",
            "bhk": "2",
            "location": "Chennai",
            "budget": "40 lakh",
            "budget_amount": 4000000,
            "timeline": "within 1 month",
            "interested": True,
            "qualification_status": "QUALIFIED",
        },
    )
    assert body["success"] is True
    assert body["handled"] is True
    assert body["enriched"] is True
    assert body["call_id"] == call_id

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["transcript"] is not None
    assert call_resp["duration_seconds"] == 95

    summary = client.get(f"/api/calls/{call_id}/summary").json()
    assert summary["qualification"]["interested"] is True
    assert summary["qualification_status"] == "QUALIFIED"

    lead = client.get(f"/api/leads/{call['lead_id']}").json()
    assert lead["status"] == "INTERESTED"


def test_sarvam_no_answer_via_http_endpoint(client):
    """Test no_answer via actual /webhooks/sarvam/status HTTP endpoint."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    body = _send_sarvam_webhook(client, provider_call_id, "no_answer", call_id=call_id)
    assert body["success"] is True
    assert body["handled"] is True

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "NO_ANSWER"


def test_sarvam_duplicate_webhook_idempotent(client):
    """Sending the same Sarvam webhook twice is idempotent."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    transcript = [
        {"role": "agent", "en_text": "Hello!"},
        {"role": "user", "en_text": "Hi there."},
    ]
    body1 = _send_sarvam_webhook(client, provider_call_id, "connected", call_id=call_id,
                                  duration=60, interaction_id="dup-int-001",
                                  transcript=transcript,
                                  agent_variables={"interested": True, "qualification_status": "QUALIFIED"})
    assert body1["handled"] is True
    assert body1.get("duplicate") is False

    body2 = _send_sarvam_webhook(client, provider_call_id, "connected", call_id=call_id,
                                  duration=60, interaction_id="dup-int-001",
                                  transcript=transcript)
    assert body2["handled"] is True
    assert body2.get("duplicate") is True

    messages = client.get(f"/api/calls/{call_id}/messages").json()
    assert len(messages) >= 2


def test_dispatch_then_sarvam_webhook_full_flow(client):
    """Complete flow: create -> dispatch -> webhook -> verify all DB tables."""
    lead = client.post(
        "/api/leads",
        json={
            "name": "Full Flow Lead",
            "phone": "+919876543211",
            "city": "Mumbai",
            "requirement": "3 BHK",
            "budget": "1 crore",
            "timeline": "3 months",
            "source": "test",
        },
    )
    assert lead.status_code == 201
    lead_data = lead.json()

    campaign = client.post(
        "/api/campaigns",
        json={"name": "Full Flow Campaign", "max_attempts": 3},
    )
    assert campaign.status_code == 201
    campaign_id = campaign.json()["id"]
    client.patch(f"/api/campaigns/{campaign_id}", json={"status": "ACTIVE"})
    client.post(f"/api/campaigns/{campaign_id}/leads/{lead_data['id']}")

    call = client.post(
        "/api/calls",
        json={"lead_id": lead_data["id"], "campaign_id": campaign_id},
    )
    assert call.status_code == 201
    call_id = call.json()["id"]

    provider_call_id = _dispatch_call(client, call_id)

    body = _send_sarvam_webhook(
        client, provider_call_id, "connected", call_id=call_id,
        duration=180, interaction_id="full-flow-int-001",
        transcript=[
            {"role": "agent", "en_text": "Hello, this is the AI assistant."},
            {"role": "user", "en_text": "Hi, I am looking for a 3 BHK in Mumbai."},
            {"role": "agent", "en_text": "What is your budget?"},
            {"role": "user", "en_text": "Around 1.2 crore."},
            {"role": "agent", "en_text": "When do you need it?"},
            {"role": "user", "en_text": "Within 3 months."},
            {"role": "agent", "en_text": "Would you like to schedule a visit?"},
            {"role": "user", "en_text": "Call me back tomorrow, I am busy now."},
        ],
        agent_variables={
            "property_type": "apartment",
            "bhk": "3",
            "location": "Mumbai",
            "budget": "1.2 crore",
            "budget_amount": 12000000,
            "timeline": "3 months",
            "purpose": "self-use",
            "interested": True,
            "callback_requested": True,
            "appointment_requested": False,
            "qualification_status": "QUALIFIED",
        },
    )
    assert body["success"] is True
    assert body["enriched"] is True

    # Verify Call
    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "COMPLETED"
    assert call_resp["outcome"] == "CALLBACK"
    assert call_resp["duration_seconds"] == 180
    assert call_resp["transcript"] is not None
    assert call_resp["recording_url"] is not None

    # Verify CallMessages
    messages = client.get(f"/api/calls/{call_id}/messages").json()
    assert len(messages) == 8
    assert messages[0]["speaker"] == "CALLER"
    assert messages[1]["speaker"] == "CUSTOMER"

    # Verify CallSummary
    summary = client.get(f"/api/calls/{call_id}/summary").json()
    assert summary["qualification_status"] == "QUALIFIED"
    assert summary["qualification"]["callback_requested"] is True

    # Verify CallEvents
    events = client.get(f"/api/calls/{call_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "call.completed" in event_types

    # Verify Lead
    lead_resp = client.get(f"/api/leads/{lead_data['id']}").json()
    assert lead_resp["status"] == "CALLBACK"
    assert lead_resp["budget"] == "12000000"
    assert lead_resp["city"] == "Mumbai"

    # Verify Followup
    followups = client.get(f"/api/followups/lead/{lead_data['id']}").json()
    assert len(followups) >= 1
    assert followups[0]["status"] == "PENDING"


# ============================================================
# PHASE B: Edge case scenarios
# ============================================================


def test_sarvam_late_webhook_after_terminal(client):
    """Webhook arrives after call already terminal is handled as ignored/duplicate."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    body1 = _send_sarvam_webhook(client, provider_call_id, "failed", call_id=call_id)
    assert body1["handled"] is True

    body2 = _send_sarvam_webhook(client, provider_call_id, "connected", call_id=call_id,
                                  duration=60, interaction_id="late-int-001")
    assert body2["success"] is True

    call_resp = client.get(f"/api/calls/{call_id}").json()
    assert call_resp["status"] == "FAILED"


def test_sarvam_provider_failure_returns_not_handled(client):
    """Webhook for unknown call_id returns not_handled."""
    body = _send_sarvam_webhook(client, "unknown-attempt-id", "connected", call_id=None)
    assert body["handled"] is False
    assert body["success"] is False


def test_sarvam_webhook_missing_attempt_id(client):
    """Webhook with missing attempt_id returns error."""
    resp = client.post("/webhooks/sarvam/status", json={
        "attempt_id": "",
        "status": "connected",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["handled"] is False


def test_sarvam_webhook_missing_status(client):
    """Webhook with missing status returns error."""
    resp = client.post("/webhooks/sarvam/status", json={
        "attempt_id": "some-id",
        "status": "",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["handled"] is False


def test_sarvam_webhook_unknown_status(client):
    """Webhook with unknown status returns unsupported."""
    call = _create_ready_call(client)
    call_id = call["id"]
    provider_call_id = _dispatch_call(client, call_id)

    resp = client.post("/webhooks/sarvam/status", json={
        "attempt_id": provider_call_id,
        "status": "unknown_status",
        "webhook_config": {"metadata": {"call_id": str(call_id)}},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["handled"] is False


def test_sarvam_empty_webhook_body(client):
    """Empty webhook body returns error."""
    resp = client.post("/webhooks/sarvam/status", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["handled"] is False


def test_sarvam_nested_agent_variables(client):
    """Nested agent variables are flattened correctly."""
    call = _create_ready_call(client)
    call_id = call["id"]

    result = client.post(
        f"/api/calls/{call_id}/simulate",
        json={
            "scenario": "sarvam",
            "sarvam_agent_variables": {
                "qualification": {
                    "status": "QUALIFIED",
                    "score": 85,
                },
                "property": {
                    "type": "apartment",
                    "bhk": "3",
                },
                "budget": "1 crore",
                "budget_amount": 10000000,
                "interested": True,
            },
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["enriched"] is True

    summary = client.get(f"/api/calls/{call_id}/summary").json()
    assert summary["qualification"]["budget"] == 10000000
    assert summary["qualification"]["interested"] is True


def test_sarvam_list_webhooks_batch(client):
    """Batch webhook delivery (list of payloads) is handled."""
    call = _create_ready_call(client)
    call_id = call["id"]

    provider_call_id = _dispatch_call(client, call_id)

    resp = client.post("/webhooks/sarvam/status", json=[
        {
            "attempt_id": provider_call_id,
            "status": "connected",
            "duration": 45,
            "interaction_id": "batch-int-001",
            "final_agent_variables": {"interested": True, "qualification_status": "QUALIFIED"},
            "interaction_transcript": [
                {"role": "agent", "en_text": "Hello!"},
                {"role": "user", "en_text": "Hi!"},
            ],
            "webhook_config": {"metadata": {"call_id": str(call_id)}},
        }
    ])
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["handled_count"] == 1
