from __future__ import annotations

from app.services.calling.provider import CallRequest


def _create_ready_call(client, *, max_attempts: int = 5) -> tuple[int, int, int]:
    lead = client.post(
        "/api/leads",
        json={"name": "Raj Sharma", "phone": "+919871234560", "source": "test"},
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]
    campaign = client.post(
        "/api/campaigns",
        json={"name": f"Tabbly test {lead_id}", "max_attempts": max_attempts},
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]
    assert client.patch(f"/api/campaigns/{campaign_id}", json={"status": "ACTIVE"}).status_code == 200
    assert client.post(f"/api/campaigns/{campaign_id}/leads/{lead_id}").status_code == 201
    call = client.post(
        "/api/calls", json={"lead_id": lead_id, "campaign_id": campaign_id}
    )
    assert call.status_code == 201, call.text
    assert call.json()["status"] == "QUEUED"
    return call.json()["id"], lead_id, campaign_id


def _make_tabby_provider():
    import app.services.calling.tabbly_provider as tp

    provider = tp.TabblyCallingProvider.__new__(tp.TabblyCallingProvider)
    provider.api_key = "test-key"
    provider.agent_id = "7174"
    provider.expected_phone = None
    provider.organization_id = None
    provider._validated = True
    return provider


def test_tabby_provider_uses_documented_campaign_api():
    provider = _make_tabby_provider()

    requests = []

    def fake_request(url, payload, method="POST"):
        requests.append((url, payload, method))
        if url.endswith("/create-campaign"):
            return {"status": "success", "data": {"campaign_id": "45123"}}
        if url.endswith("/add-campaign-contacts"):
            return {"status": "success", "id": "90001", "custom_identifier": "call_id=7"}
        raise AssertionError(f"Unexpected URL: {url}")

    provider._request = fake_request

    result = provider.start_call(
        CallRequest(
            phone_number="+919871234560",
            call_id=7,
            lead_id=3,
            campaign_id=2,
            webhook_url="http://localhost:8000",
        )
    )

    assert result.provider == "tabbly"
    assert result.provider_call_id == "45123"
    assert result.status == "INITIATED"
    assert result.metadata["tabbly_contact_id"] == "90001"
    assert result.metadata["tabbly_campaign_id"] == "45123"

    create_url, create_payload, _ = requests[0]
    assert create_url.endswith("/create-campaign")
    assert create_payload["campaign_name"] == "call-7"
    assert create_payload["agent_id"] == 7174
    assert create_payload["time_zone"] == "IST"
    assert create_payload["start_time"]
    assert create_payload["end_time"]

    add_url, add_payload, _ = requests[1]
    assert add_url.endswith("/add-campaign-contacts")
    assert add_payload["phone_number"] == "+919871234560"
    assert add_payload["campaign_id"] == 45123
    assert add_payload["use_agent_id"] == 7174
    assert "call_id=7" in add_payload["custom_identifiers"]
    assert "lead_id=3" in add_payload["custom_identifiers"]


def test_tabby_provider_embeds_lead_context_in_script():
    provider = _make_tabby_provider()
    requests = []

    def fake_request(url, payload, method="POST"):
        requests.append((url, payload, method))
        if url.endswith("/create-campaign"):
            return {"status": "success", "data": {"campaign_id": "45124"}}
        if url.endswith("/add-campaign-contacts"):
            return {"status": "success", "id": "90002"}
        raise AssertionError(f"Unexpected URL: {url}")

    provider._request = fake_request

    provider.start_call(
        CallRequest(
            phone_number="+919871234560",
            call_id=8,
            lead_id=4,
            campaign_id=3,
            webhook_url="http://localhost:8000",
            lead_context={
                "name": "Raj Sharma",
                "city": "Jaipur",
                "requirement": "3 BHK residential",
                "budget": "7500000",
                "timeline": "1-3 months",
            },
        )
    )

    create_payload = requests[0][1]
    add_payload = requests[1][1]

    assert "Raj Sharma" in create_payload["custom_first_line"]
    assert "3 bhk residential" in create_payload["custom_first_line"]
    assert "3 BHK residential" in add_payload["custom_instruction"]
    assert "7500000" in add_payload["custom_instruction"]
    assert "1-3 months" in add_payload["custom_instruction"]
    assert "Jaipur" in add_payload["custom_instruction"]


def test_tabby_provider_validates_agent_configuration(monkeypatch):
    import app.services.calling.tabbly_provider as tp

    provider = _make_tabby_provider()
    provider.expected_phone = "+918035736739"

    provider._get_agents = lambda: [
        {"id": 7174, "agent_name": "ritesh", "phone_number": "+918035736739"}
    ]
    provider.validate_config()
    assert provider._validated is True

    provider._validated = False
    provider._get_agents = lambda: [
        {"id": 7174, "agent_name": "ritesh", "phone_number": "+15551234567"}
    ]

    import pytest

    with pytest.raises(RuntimeError, match="phone mismatch"):
        provider.validate_config()


def test_dispatcher_provider_failure_leaves_failed_call(client, monkeypatch):
    call_id, _, _ = _create_ready_call(client)

    from app.services import call_dispatcher

    class FailProvider:
        provider = "tabbly"

        def start_call(self, request):
            raise RuntimeError("provider rejected dispatch")

        def hangup_call(self, provider_call_id):
            pass

    monkeypatch.setattr(call_dispatcher, "get_calling_provider", lambda: FailProvider())

    response = client.post(f"/api/calls/{call_id}/start")
    assert response.status_code == 502
    assert "provider rejected dispatch" in response.json()["detail"]

    call = client.get(f"/api/calls/{call_id}").json()
    assert call["status"] == "FAILED"
    assert call["retry_reason"]
    assert call["next_retry_at"]


def test_tabby_webhook_applies_lifecycle_and_transcript(client):
    call_id, _, _ = _create_ready_call(client)
    assert client.post(f"/api/calls/{call_id}/start").status_code == 200

    assert client.post(
        "/webhooks/tabbly/status",
        json={"event_type": "call.ringing", "status": "ringing"},
    ).status_code == 200

    assert client.post(
        "/webhooks/tabbly/status",
        json={"event_type": "call.answered", "call_status": "call answered"},
    ).status_code == 200

    completed = client.post(
        "/webhooks/tabbly/status",
        json={
            "event_type": "call.completed",
            "call_status": "completed",
            "call_duration": "95",
            "call_recording": "https://tabbly.test/recording.mp3",
            "call_transcript": "agent: Hello.\ncustomer: I am interested.",
            "custom_identifiers": f"call_id={call_id}",
        },
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["success"] is True
    assert body["handled"] is True
    assert body["status"] == "COMPLETED"

    call = client.get(f"/api/calls/{call_id}").json()
    assert call["status"] == "COMPLETED"
    assert call["duration_seconds"] == 95
    assert call["recording_url"] == "https://tabbly.test/recording.mp3"
    assert "I am interested" in call["transcript"]


def test_tabby_webhook_resolves_call_by_destination_fallback(client):
    call_id, _, _ = _create_ready_call(client)

    lead = client.get(f"/api/calls/{call_id}").json()
    assert lead["status"] == "QUEUED"

    assert (
        client.post(
            f"/api/calls/{call_id}/start",
        ).status_code
        == 200
    )

    call = client.get(f"/api/calls/{call_id}").json()
    assert call["status"] == "INITIATED"
    assert call["provider"] in ("tabbly", "mock")
    destination = call["phone_number"]

    payload = {
        "call_status": "completed",
        "called_to": destination,
        "called_time": "2026-09-02 10:00:00",
        "call_duration": "45",
        "call_transcript": "agent: Hello.\ncustomer: I want a 3 BHK flat.",
        "call_json_output": '{"property_type":"flat","bhk":3,"interested":true}',
        "call_summary": "Customer wants a 3 BHK flat in Jaipur.",
    }

    response = client.post("/webhooks/tabbly/status", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["handled"] is True
    assert body["call_id"] == call_id
    assert body["status"] == "COMPLETED"
    assert body["enriched"] is True

    synced = client.get(f"/api/calls/{call_id}").json()
    assert synced["status"] == "COMPLETED"
    assert synced["transcript"]
    assert synced["duration_seconds"] == 45

    summary = client.get(f"/api/calls/{call_id}/summary").json()
    assert summary.get("customer_intent") == "interested"


def test_answered_call_with_conversation_completes_and_enriches(client):
    call_id, _, _ = _create_ready_call(client)
    assert client.post(f"/api/calls/{call_id}/start").status_code == 200

    payload = {
        "call_status": "call answered",
        "called_to": "+919871234560",
        "called_time": "2026-09-02 10:00:00",
        "call_duration": "28",
        "call_transcript": (
            "AI: Hello, I see you enquired about a 3 BHK flat.\n"
            "Customer: Yes, I want a 3 BHK flat in Jaipur.\n"
            "AI: What is your budget?\n"
            "Customer: Around 75 lakh.\n"
            "AI: And when do you plan to buy?\n"
            "Customer: Within three months.\n"
        ),
        "call_json_output": (
            '{"property_type":"flat","bhk":3,"location":"Jaipur",'
            '"budget":"75 lakh","timeline":"three months",'
            '"interested":true,"appointment_requested":false,'
            '"callback_requested":false}'
        ),
        "call_summary": "Customer wants a 3 BHK flat in Jaipur in 3 months.",
    }

    response = client.post("/webhooks/tabbly/status", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["handled"] is True
    assert body["call_id"] == call_id
    assert body["status"] == "COMPLETED"
    assert body["enriched"] is True

    call = client.get(f"/api/calls/{call_id}").json()
    assert call["status"] == "COMPLETED"
    assert call["duration_seconds"] == 28
    assert "3 BHK flat" in call["transcript"]

    summary = client.get(f"/api/calls/{call_id}/summary").json()
    assert summary["qualification_status"] == "QUALIFIED"
    assert summary["qualification"]["source"] == "tabbly"
    assert summary["qualification"]["budget"] == 7500000
    assert summary["customer_intent"] == "interested"


def test_answered_conversation_after_no_answer_reopens_to_completed(client):
    call_id, _, _ = _create_ready_call(client)
    assert client.post(f"/api/calls/{call_id}/start").status_code == 200

    call = client.get(f"/api/calls/{call_id}").json()
    provider_call_id = call["provider_call_id"]
    destination = call["phone_number"]

    no_answer = client.post(
        "/webhooks/tabbly/status",
        json={
            "call_status": "not answered",
            "campaign_id": provider_call_id,
            "called_to": destination,
            "called_time": "2026-09-02 10:00:00",
            "call_duration": "12",
            "call_transcript": "no answer",
        },
    )
    assert no_answer.status_code == 200
    assert no_answer.json()["status"] == "NO_ANSWER"

    answered = client.post(
        "/webhooks/tabbly/status",
        json={
            "call_status": "call answered",
            "campaign_id": provider_call_id,
            "called_to": destination,
            "called_time": "2026-09-02 10:00:05",
            "call_duration": "106",
            "call_transcript": (
                "AI: Hello, I see you are looking for a 3 BHK villa.\n"
                "Customer: Yes, near Gopalpura.\n"
                "AI: And your budget?\n"
                "Customer: Around 1.2 crore.\n"
                "AI: When do you plan to buy?\n"
                "Customer: Within three months.\n"
            ),
            "call_json_output": (
                '{"property_type":"villa","bhk":3,'
                '"location":"Gopalpura, Jaipur","budget":"1.2 crore",'
                '"timeline":"three months","interested":true,'
                '"appointment_requested":false,"callback_requested":false}'
            ),
            "call_summary": "Customer wants a 3 BHK villa near Gopalpura.",
        },
    )
    assert answered.status_code == 200
    body = answered.json()
    assert body["status"] == "COMPLETED"
    assert body["enriched"] is True

    call = client.get(f"/api/calls/{call_id}").json()
    assert call["status"] == "COMPLETED"
    assert call["duration_seconds"] == 106
    assert "Gopalpura" in call["transcript"]

    summary = client.get(f"/api/calls/{call_id}/summary").json()
    assert summary["qualification_status"] == "QUALIFIED"
    assert summary["qualification"]["source"] == "tabbly"
    assert summary["qualification"]["budget"] == 12000000


def test_tabby_webhook_is_idempotent_and_tolerates_unknown(client):
    call_id, _, _ = _create_ready_call(client)
    assert client.post(f"/api/calls/{call_id}/start").status_code == 200

    payload = {
        "call_status": "completed",
        "custom_identifiers": f"call_id={call_id}",
        "webhook_id": "fixed-id-1",
    }

    first = client.post("/webhooks/tabbly/status", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "COMPLETED"

    second = client.post("/webhooks/tabbly/status", json=payload)
    assert second.status_code == 200
    assert second.json()["handled"] is True
    assert second.json()["status"] == "COMPLETED"

    current = client.get(f"/api/calls/{call_id}").json()
    assert current["status"] == "COMPLETED"

    unknown = client.post(
        "/webhooks/tabbly/status",
        json={"call_status": "completed", "custom_identifiers": "call_id=99999999"},
    )
    assert unknown.status_code == 200
    assert unknown.json()["success"] is False
    assert unknown.json()["message"] == "unknown call"


def test_factory_refuses_mock_in_production(monkeypatch):
    from app.services.calling.factory import get_calling_provider

    import pytest

    monkeypatch.setenv("CALLING_MODE", "production")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "mock")

    with pytest.raises(ValueError, match="production"):
        get_calling_provider()