"""Tests for Sarvam enrichment service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.call import Call
from app.models.call_message import CallMessage
from app.models.enums import CallStatus, LeadStatus
from app.models.lead import Lead
from app.services.sarvam_enrichment import (
    _flatten_agent_variables,
    _infer_outcome,
    _parse_budget,
    _parse_timeline,
    apply_sarvam_enrichment,
)


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
def completed_lead_and_call(db_session):
    lead = Lead(
        id=100,
        name="Rahul",
        phone="+917665035514",
        city="Mumbai",
        status=LeadStatus.CONNECTED,
    )
    db_session.add(lead)
    db_session.flush()

    call = Call(
        id=200,
        lead_id=100,
        campaign_id=1,
        phone_number="+917665035514",
        status=CallStatus.COMPLETED,
        provider="sarvam",
        provider_call_id="att-test",
        attempt_number=1,
        max_attempts=3,
    )
    db_session.add(call)
    db_session.commit()
    db_session.refresh(lead)
    db_session.refresh(call)
    return lead, call


class TestParseBudget:
    def test_parse_lakh(self):
        assert _parse_budget("50 lakh") == 5_000_000

    def test_parse_crore(self):
        assert _parse_budget("1.5 crore") == 15_000_000

    def test_parse_raw_number(self):
        assert _parse_budget("5000000") == 5_000_000

    def test_parse_none(self):
        assert _parse_budget(None) is None

    def test_parse_empty(self):
        assert _parse_budget("") is None

    def test_parse_bool(self):
        assert _parse_budget(True) is None


class TestParseTimeline:
    def test_parse_months(self):
        assert _parse_timeline("3 months") == "3 months"

    def test_parse_immediately(self):
        assert _parse_timeline("immediately") == "immediately"

    def test_parse_none(self):
        assert _parse_timeline(None) is None

    def test_parse_weeks(self):
        assert _parse_timeline("2 weeks") == "2 weeks"


class TestInferOutcome:
    def test_callback(self):
        assert _infer_outcome({"callback_requested": True}) == "CALLBACK"

    def test_appointment(self):
        assert _infer_outcome({"appointment_requested": True}) == "APPOINTMENT_BOOKED"

    def test_interested(self):
        assert _infer_outcome({"interested": True}) == "INTERESTED"

    def test_do_not_contact(self):
        assert _infer_outcome({"qualification_status": "DO_NOT_CONTACT"}) == "DO_NOT_CALL"

    def test_unqualified(self):
        assert _infer_outcome({"qualification_status": "UNQUALIFIED"}) == "NOT_INTERESTED"

    def test_unknown(self):
        assert _infer_outcome({}) is None


class TestFlattenAgentVariables:
    def test_flat(self):
        assert _flatten_agent_variables({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_nested(self):
        result = _flatten_agent_variables({"inner": {"x": 1, "y": 2}})
        assert result == {"x": 1, "y": 2}

    def test_mixed(self):
        result = _flatten_agent_variables({"a": 1, "inner": {"x": 2}})
        assert result == {"a": 1, "x": 2}


class TestApplySarvamEnrichment:
    def test_enriches_lead_and_summary(self, db_session, completed_lead_and_call):
        lead, call = completed_lead_and_call
        agent_vars = {
            "customer_name": "Rahul",
            "interested": True,
            "budget": "75 lakh",
            "timeline": "3 months",
            "location": "Andheri West",
            "property_type": "flat",
            "bhk": "2 BHK",
        }
        transcript = [
            {"role": "agent", "en_text": "Hello Rahul"},
            {"role": "user", "en_text": "Hi, yes speaking"},
        ]

        result = apply_sarvam_enrichment(
            db_session,
            call,
            final_agent_variables=agent_vars,
            interaction_transcript=transcript,
        )

        assert result["enriched"] is True
        assert result["outcome"] == "INTERESTED"
        assert result["qualification_status"] == "QUALIFIED"

        db_session.refresh(call)
        assert call.outcome == "INTERESTED"
        assert "Hello Rahul" in call.transcript

        db_session.refresh(lead)
        assert str(lead.budget) == "7500000"
        assert lead.timeline == "3 months"
        assert lead.city == "Andheri West"
        assert lead.status == LeadStatus.INTERESTED

        summary = call.summary
        assert summary is not None
        assert summary.qualification_status == "QUALIFIED"
        assert summary.qualification.get("source") == "sarvam"

    def test_callback_requested(self, db_session, completed_lead_and_call):
        lead, call = completed_lead_and_call
        agent_vars = {
            "callback_requested": True,
            "interested": False,
        }

        result = apply_sarvam_enrichment(
            db_session,
            call,
            final_agent_variables=agent_vars,
            interaction_transcript=[],
        )

        assert result["enriched"] is True
        assert result["outcome"] == "CALLBACK"
        db_session.refresh(lead)
        assert lead.status == LeadStatus.CALLBACK
        assert call.summary.followup_at is not None

    def test_not_enriched_if_not_completed(self, db_session):
        lead = Lead(id=300, name="Test", phone="+911234567890", status=LeadStatus.CALLING)
        db_session.add(lead)
        db_session.flush()
        call = Call(
            id=400, lead_id=300, campaign_id=1, phone_number="+911234567890",
            status=CallStatus.INITIATED, provider="sarvam",
        )
        db_session.add(call)
        db_session.commit()

        result = apply_sarvam_enrichment(db_session, call, final_agent_variables={})
        assert result["enriched"] is False
        assert "COMPLETED" in result["message"]

    def test_idempotent_enrichment(self, db_session, completed_lead_and_call):
        lead, call = completed_lead_and_call
        agent_vars = {"interested": True}

        apply_sarvam_enrichment(
            db_session, call,
            final_agent_variables=agent_vars,
            interaction_transcript=[],
        )

        result2 = apply_sarvam_enrichment(
            db_session, call,
            final_agent_variables=agent_vars,
            interaction_transcript=[],
        )
        assert result2["enriched"] is False
        assert result2["message"] == "already enriched"

    def test_transcript_creates_call_messages(self, db_session, completed_lead_and_call):
        lead, call = completed_lead_and_call
        transcript = [
            {"role": "agent", "en_text": "Hello"},
            {"role": "user", "en_text": "Hi there"},
            {"role": "agent", "en_text": "How can I help?"},
        ]

        apply_sarvam_enrichment(
            db_session, call,
            final_agent_variables={},
            interaction_transcript=transcript,
        )

        messages = db_session.query(CallMessage).filter(
            CallMessage.call_id == call.id
        ).order_by(CallMessage.sequence).all()
        assert len(messages) == 3
        assert messages[0].speaker == "CALLER"
        assert messages[0].text == "Hello"
        assert messages[1].speaker == "CUSTOMER"
        assert messages[1].text == "Hi there"
