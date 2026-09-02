from __future__ import annotations

from app.services.calling.tabbly_provider import TabblyCallingProvider


def test_webhook_payload_maps_call_log_row():
    log = {
        "id": "abc123",
        "called_to": "+919871234560",
        "campaign_id": "45123",
        "call_duration": "95",
        "call_recording": "https://tabbly.test/rec.mp3",
        "call_transcript": "agent: Hi\ncustomer: interested",
        "call_status": "completed",
        "custom_identifiers": "call_id=7,lead_id=3,campaign_id=2",
    }

    payload = TabblyCallingProvider.webhook_payload(log)

    assert payload is not None
    assert payload["call_status"] == "completed"
    assert payload["call_duration"] == "95"
    assert payload["call_recording"] == "https://tabbly.test/rec.mp3"
    assert payload["call_transcript"] == "agent: Hi\ncustomer: interested"
    assert payload["custom_identifiers"] == "call_id=7,lead_id=3,campaign_id=2"
    assert payload["record_id"] == "abc123"


def test_webhook_payload_none_for_parked_contact():
    # A campaign whose contact was added but never dialled carries no status.
    assert TabblyCallingProvider.webhook_payload({"campaign_id": "45123"}) is None


def test_webhook_payload_falls_back_to_campaign_id():
    log = {
        "id": "x",
        "call_status": "no answer",
        "campaign_id": "45123",
    }
    payload = TabblyCallingProvider.webhook_payload(log)
    assert payload is not None
    assert payload["campaign_id"] == "45123"
    assert "custom_identifiers" not in payload
