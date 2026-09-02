import pytest

from app.database.connection import SessionLocal
from app.models.call import Call
from app.models.call_summary import CallSummary
from app.models.campaign import Campaign
from app.models.enums import CallStatus, CampaignStatus, LeadStatus
from app.models.lead import Lead
from app.services.tabby_enrichment import apply_tabby_enrichment


@pytest.fixture
def completed_call():
    db = SessionLocal()
    lead = Lead(name="Demo Customer", phone="+917665035514", status=LeadStatus.NEW)
    db.add(lead)
    db.flush()
    campaign = Campaign(name="Enrich Test", status=CampaignStatus.ACTIVE, max_attempts=1)
    db.add(campaign)
    db.flush()
    call = Call(
        lead_id=lead.id,
        campaign_id=campaign.id,
        phone_number="+917665035514",
        status=CallStatus.COMPLETED,
        provider="tabbly",
        provider_call_id="4242",
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    yield call
    db.close()


def _payload():
    return {
        "call_status": "completed",
        "call_duration": "95",
        "call_transcript": (
            "AI: Hello, are you looking for a property?\n"
            "Customer: Yes, a 2 BHK flat.\n"
            "AI: What is your budget?\n"
            "Customer: Around 50 lakh.\n"
            "AI: When do you plan to buy?\n"
            "Customer: Within two months.\n"
        ),
        "call_json_output": (
            '{"property_type": "flat", "bhk": "2", "location": "Pune", '
            '"budget": "50 lakh", "timeline": "two months", '
            '"purpose": "self use", "interested": true, '
            '"appointment_requested": true, "callback_requested": false}'
        ),
        "call_summary": "Customer wants a 2 BHK flat near Pune.",
        "call_recording": "https://example.com/rec.mp3",
        "record_id": "log-999",
        "called_time": "2026-09-01 20:00:00",
    }


def test_enrichment_populates_crm(completed_call):
    db = SessionLocal()
    call = db.get(Call, completed_call.id)
    result = apply_tabby_enrichment(db, call, _payload())

    assert result["enriched"] is True
    db.refresh(call)

    assert call.status == CallStatus.COMPLETED
    assert call.outcome is not None
    assert call.outcome.value == "APPOINTMENT_BOOKED"
    assert call.transcript and "2 BHK" in call.transcript

    assert call.messages
    assert call.messages[0].speaker == "CALLER"
    assert any(m.speaker == "CUSTOMER" and "2 BHK" in m.text for m in call.messages)

    summary = db.get(CallSummary, call.summary.id)
    assert summary.qualification_status == "QUALIFIED"
    assert summary.qualification["source"] == "tabbly"
    assert summary.qualification["interested"] is True
    assert summary.qualification["appointment_requested"] is True
    assert summary.qualification["budget"] == 5000000
    assert summary.qualification["timeline"] == "2 months"
    assert summary.qualification["requirement"] == "flat 2 Pune"

    db.refresh(call.lead)
    assert call.lead.status == LeadStatus.QUALIFIED
    assert call.lead.requirement == "flat 2 Pune"
    assert call.lead.budget == "5000000"
    assert call.lead.timeline == "2 months"
    db.close()


def test_enrichment_is_idempotent(completed_call):
    db = SessionLocal()
    call = db.get(Call, completed_call.id)
    apply_tabby_enrichment(db, call, _payload())
    messages_count = len(call.messages)

    second = apply_tabby_enrichment(db, call, _payload())
    assert second["enriched"] is False
    assert len(call.messages) == messages_count
    db.close()


def test_enrichment_skips_non_completed(completed_call):
    db = SessionLocal()
    call = db.get(Call, completed_call.id)
    call.status = CallStatus.INITIATED
    db.commit()

    result = apply_tabby_enrichment(db, call, _payload())
    assert result["enriched"] is False
    db.close()