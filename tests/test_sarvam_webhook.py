"""Tests for Sarvam webhook handler."""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.call import Call
from app.models.enums import CallStatus, LeadStatus
from app.models.lead import Lead
from app.services.sarvam_webhook_service import process_sarvam_webhook


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def lead_and_call(db_session):
    lead = Lead(
        id=100,
        name="Rahul",
        phone="+917665035514",
        city="Mumbai",
        status=LeadStatus.CALLING,
    )
    db_session.add(lead)
    db_session.flush()

    call = Call(
        id=200,
        lead_id=100,
        campaign_id=1,
        phone_number="+917665035514",
        status=CallStatus.INITIATED,
        provider="sarvam",
        provider_call_id="att-webhook-test",
        attempt_number=1,
        max_attempts=3,
    )
    db_session.add(call)
    db_session.commit()
    db_session.refresh(lead)
    db_session.refresh(call)
    return lead, call


class TestResolveCall:
    def test_resolves_by_metadata_call_id(self, db_session, lead_and_call):
        from app.services.sarvam_webhook_service import _resolve_call

        payload = {
            "attempt_id": "att-webhook-test",
            "webhook_config": {
                "metadata": {"call_id": "200"},
            },
        }
        call = _resolve_call(db_session, payload)
        assert call is not None
        assert call.id == 200

    def test_resolves_by_attempt_id(self, db_session, lead_and_call):
        from app.services.sarvam_webhook_service import _resolve_call

        payload = {
            "attempt_id": "att-webhook-test",
            "webhook_config": {},
        }
        call = _resolve_call(db_session, payload)
        assert call is not None
        assert call.id == 200

    def test_returns_none_for_unknown(self, db_session, lead_and_call):
        from app.services.sarvam_webhook_service import _resolve_call

        payload = {
            "attempt_id": "att-nonexistent",
            "webhook_config": {},
        }
        call = _resolve_call(db_session, payload)
        assert call is None


class TestProcessSarvamWebhook:
    def test_connected_call_transitions_to_completed(self, db_session, lead_and_call):
        lead, call = lead_and_call
        payload = {
            "attempt_id": "att-webhook-test",
            "status": "connected",
            "duration": 42.5,
            "interaction_id": "20250920/abc123",
            "failure_reason": None,
            "final_agent_variables": {
                "customer_name": "Rahul",
                "disposition": "interested",
            },
            "webhook_config": {
                "metadata": {"call_id": "200"},
            },
            "interaction_transcript": [
                {"role": "agent", "en_text": "Hello, am I speaking with Rahul?"},
                {"role": "user", "en_text": "Yes, this is Rahul."},
            ],
        }
        result = process_sarvam_webhook(db_session, payload)

        assert result["success"] is True
        assert result["handled"] is True
        assert result["call_id"] == 200
        db_session.refresh(call)
        assert call.status == CallStatus.COMPLETED
        assert call.duration_seconds == 42
        assert call.transcript is not None
        assert "Hello, am I speaking with Rahul?" in call.transcript

    def test_no_answer_transitions_to_no_answer(self, db_session, lead_and_call):
        lead, call = lead_and_call
        payload = {
            "attempt_id": "att-webhook-test",
            "status": "no_answer",
            "duration": None,
            "interaction_id": None,
            "failure_reason": None,
            "final_agent_variables": None,
            "webhook_config": {
                "metadata": {"call_id": "200"},
            },
            "interaction_transcript": None,
        }
        result = process_sarvam_webhook(db_session, payload)

        assert result["success"] is True
        assert result["handled"] is True
        db_session.refresh(call)
        assert call.status == CallStatus.NO_ANSWER

    def test_busy_transitions_to_busy(self, db_session, lead_and_call):
        lead, call = lead_and_call
        payload = {
            "attempt_id": "att-webhook-test",
            "status": "busy",
            "duration": None,
            "interaction_id": None,
            "failure_reason": None,
            "final_agent_variables": None,
            "webhook_config": {
                "metadata": {"call_id": "200"},
            },
            "interaction_transcript": None,
        }
        result = process_sarvam_webhook(db_session, payload)

        assert result["success"] is True
        db_session.refresh(call)
        assert call.status == CallStatus.BUSY

    def test_failed_transitions_to_failed(self, db_session, lead_and_call):
        lead, call = lead_and_call
        payload = {
            "attempt_id": "att-webhook-test",
            "status": "failed",
            "duration": None,
            "interaction_id": None,
            "failure_reason": "exotel: Phone number is registered under TRAI NDNC",
            "final_agent_variables": None,
            "webhook_config": {
                "metadata": {"call_id": "200"},
            },
            "interaction_transcript": None,
        }
        result = process_sarvam_webhook(db_session, payload)

        assert result["success"] is True
        db_session.refresh(call)
        assert call.status == CallStatus.FAILED

    def test_unknown_call_returns_not_handled(self, db_session):
        payload = {
            "attempt_id": "att-nonexistent",
            "status": "connected",
            "duration": 10,
            "interaction_id": None,
            "failure_reason": None,
            "final_agent_variables": None,
            "webhook_config": {},
            "interaction_transcript": None,
        }
        result = process_sarvam_webhook(db_session, payload)

        assert result["success"] is False
        assert result["handled"] is False
        assert result["message"] == "unknown call"

    def test_missing_attempt_id_returns_error(self, db_session):
        result = process_sarvam_webhook(db_session, {"status": "connected"})
        assert result["success"] is False
        assert "missing" in result["message"]

    def test_missing_status_returns_error(self, db_session):
        result = process_sarvam_webhook(db_session, {"attempt_id": "att-1"})
        assert result["success"] is False
        assert "missing" in result["message"]

    def test_duplicate_webhook_is_idempotent(self, db_session, lead_and_call):
        lead, call = lead_and_call
        payload = {
            "attempt_id": "att-webhook-test",
            "status": "connected",
            "duration": 10,
            "interaction_id": "int-1",
            "failure_reason": None,
            "final_agent_variables": {},
            "webhook_config": {"metadata": {"call_id": "200"}},
            "interaction_transcript": None,
        }
        result1 = process_sarvam_webhook(db_session, payload)
        assert result1["success"] is True

        result2 = process_sarvam_webhook(db_session, payload)
        assert result2["success"] is True
        assert result2.get("duplicate") is True

    def test_bridges_from_initiated_to_completed(self, db_session, lead_and_call):
        lead, call = lead_and_call
        assert call.status == CallStatus.INITIATED

        payload = {
            "attempt_id": "att-webhook-test",
            "status": "connected",
            "duration": 30,
            "interaction_id": "int-bridge",
            "failure_reason": None,
            "final_agent_variables": {"interested": True},
            "webhook_config": {"metadata": {"call_id": "200"}},
            "interaction_transcript": [
                {"role": "agent", "en_text": "Hello"},
                {"role": "user", "en_text": "Hi"},
            ],
        }
        result = process_sarvam_webhook(db_session, payload)

        assert result["success"] is True
        db_session.refresh(call)
        assert call.status == CallStatus.COMPLETED
