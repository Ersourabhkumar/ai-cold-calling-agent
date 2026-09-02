from __future__ import annotations


def _create_ready_call(client, *, max_attempts: int = 5) -> int:
    lead = client.post(
        "/api/leads",
        json={"name": "Asha Patel", "phone": "+919876543210", "source": "test"},
    )
    assert lead.status_code == 201, lead.text
    campaign = client.post(
        "/api/campaigns",
        json={"name": f"Free trial {lead.json()['id']}", "max_attempts": max_attempts},
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]
    assert client.patch(f"/api/campaigns/{campaign_id}", json={"status": "ACTIVE"}).status_code == 200
    assert client.post(f"/api/campaigns/{campaign_id}/leads/{lead.json()['id']}").status_code == 201
    call = client.post(
        "/api/calls", json={"lead_id": lead.json()["id"], "campaign_id": campaign_id}
    )
    assert call.status_code == 201, call.text
    assert call.json()["status"] == "QUEUED"
    return call.json()["id"]


def test_complete_free_trial_callback_flow(client):
    assert client.get("/health").json()["status"] == "ok"
    call_id = _create_ready_call(client)

    started = client.post(f"/api/calls/{call_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "INITIATED"
    assert started.json()["provider"] == "mock"

    simulated = client.post(
        f"/api/calls/{call_id}/simulate",
        json={"customer_text": "I am interested. Please call me tomorrow.", "complete": True},
    )
    assert simulated.status_code == 200, simulated.text
    body = simulated.json()
    assert body["call"]["status"] == "COMPLETED"
    assert body["call"]["outcome"] == "CALLBACK"
    assert body["qualification"]["callback_requested"] is True
    assert body["qualification"]["qualification_score"] >= 30
    assert "follow-up" in body["caller_text"].lower()

    messages = client.get(f"/api/calls/{call_id}/messages")
    assert messages.status_code == 200
    assert [message["speaker"] for message in messages.json()] == ["CALLER", "CUSTOMER", "CALLER"]

    summary = client.get(f"/api/calls/{call_id}/summary")
    assert summary.status_code == 200
    assert summary.json()["customer_intent"] == "callback"
    assert summary.json()["qualification"]["callback_requested"] is True
    assert client.get("/api/leads/1").json()["status"] == "CALLBACK"

    events = client.get(f"/api/calls/{call_id}/events").json()
    assert [event["event_type"] for event in events] == [
        "call.created",
        "call.initiated",
        "call.ringing",
        "call.answered",
        "call.started",
        "call.completed",
    ]
    assert client.get("/api/followups/lead/1").json()[0]["status"] == "PENDING"

    invalid = client.post(f"/api/calls/{call_id}/events", json={"status": "RINGING"})
    assert invalid.status_code == 400
    assert "Invalid call transition" in invalid.json()["detail"]


def test_terminal_scenarios_have_expected_retry_behavior(client):
    retryable = {"no_answer": "NO_ANSWER", "busy": "BUSY", "failed": "FAILED"}
    for scenario, expected_status in retryable.items():
        call_id = _create_ready_call(client)
        response = client.post(f"/api/calls/{call_id}/simulate", json={"scenario": scenario})
        assert response.status_code == 200, response.text
        call = response.json()["call"]
        assert call["status"] == expected_status
        assert call["retry_reason"]
        assert call["next_retry_at"]

    call_id = _create_ready_call(client)
    response = client.post(f"/api/calls/{call_id}/simulate", json={"scenario": "cancelled"})
    assert response.status_code == 200
    assert response.json()["call"]["status"] == "CANCELLED"
    assert response.json()["call"]["next_retry_at"] is None


def test_provider_events_are_idempotent(client):
    call_id = _create_ready_call(client)
    assert client.post(f"/api/calls/{call_id}/start").status_code == 200

    event = client.post(
        f"/api/calls/{call_id}/events",
        json={"status": "RINGING", "provider_event_id": "provider-event-123"},
    )
    assert event.status_code == 200
    duplicate = client.post(
        f"/api/calls/{call_id}/events",
        json={"status": "RINGING", "provider_event_id": "provider-event-123"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == event.json()["id"]
    assert client.get(f"/api/calls/{call_id}").json()["status"] == "RINGING"
