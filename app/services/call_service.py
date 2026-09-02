from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.campaign import Campaign
from app.models.campaign_lead import CampaignLead
from app.models.enums import CallStatus, LeadStatus
from app.models.lead import Lead
from app.schemas.call import CallCreate, CallUpdate
from app.services.call_lifecycle import record_event, transition_call
from app.services.queue_service import enqueue_call


def create_call(db: Session, data: CallCreate) -> Call:
    lead = db.get(Lead, data.lead_id)
    if lead is None:
        raise ValueError("Lead not found")
    campaign = db.get(Campaign, data.campaign_id)
    if campaign is None:
        raise ValueError("Campaign not found")
    if campaign.status.value != "ACTIVE":
        raise ValueError("Campaign is not active")

    campaign_lead = db.scalar(
        select(CampaignLead).where(
            CampaignLead.campaign_id == data.campaign_id,
            CampaignLead.lead_id == data.lead_id,
        )
    )
    if campaign_lead is None:
        raise ValueError("Lead is not assigned to this campaign")
    if campaign_lead.attempt_count >= campaign.max_attempts:
        raise ValueError("Maximum call attempts reached")
    if lead.status == LeadStatus.DO_NOT_CALL:
        raise ValueError("Lead is marked as DO_NOT_CALL")

    attempt_number = campaign_lead.attempt_count + 1
    call = Call(
        lead_id=lead.id,
        campaign_id=campaign.id,
        phone_number=lead.phone,
        status=CallStatus.QUEUED,
        attempt_number=attempt_number,
        max_attempts=campaign.max_attempts,
    )
    db.add(call)
    campaign_lead.attempt_count = attempt_number
    lead.attempt_count += 1
    lead.status = LeadStatus.QUEUED
    db.flush()
    record_event(db, call, "call.created", None, CallStatus.QUEUED)
    db.commit()
    db.refresh(call)

    # Redis is optional in the free trial; persisted status is the source of truth.
    enqueue_call(call)
    return call


def get_call(db: Session, call_id: int) -> Call | None:
    return db.get(Call, call_id)


def get_calls(db: Session, skip: int = 0, limit: int = 50) -> list[Call]:
    return list(
        db.scalars(select(Call).order_by(Call.id.desc()).offset(skip).limit(limit)).all()
    )


def get_lead_calls(db: Session, lead_id: int) -> list[Call]:
    return list(
        db.scalars(
            select(Call).where(Call.lead_id == lead_id).order_by(Call.id.desc())
        ).all()
    )


def update_call(db: Session, call: Call, data: CallUpdate) -> Call:
    """Backward-compatible PATCH handler; lifecycle changes remain validated."""
    update_data = data.model_dump(exclude_unset=True)
    status = update_data.pop("status", None)
    outcome = update_data.pop("outcome", None)
    duration_seconds = update_data.pop("duration_seconds", None)
    if status is not None:
        call, _ = transition_call(
            db,
            call,
            status,
            outcome=outcome,
            duration_seconds=duration_seconds,
            provider=update_data.pop("provider", None),
            provider_call_id=update_data.pop("provider_call_id", None),
        )
    elif outcome is not None:
        raise ValueError("An outcome can only be applied when completing a call")

    for field, value in update_data.items():
        setattr(call, field, value)
    if update_data:
        db.commit()
        db.refresh(call)
    return call


def update_call_from_provider(
    db: Session,
    call: Call,
    status: CallStatus,
    duration_seconds: int | None = None,
    provider_event_id: str | None = None,
) -> Call:
    updated_call, _ = transition_call(
        db,
        call,
        status,
        duration_seconds=duration_seconds,
        provider_event_id=provider_event_id,
        payload={"source": "provider"},
    )
    return updated_call
