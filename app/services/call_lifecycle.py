from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.enums import CallOutcome, CallStatus, LeadStatus
from app.services.retry_service import create_callback_followup, create_retry_followup


TERMINAL_STATUSES = {
    CallStatus.COMPLETED,
    CallStatus.NO_ANSWER,
    CallStatus.BUSY,
    CallStatus.FAILED,
    CallStatus.CANCELLED,
}

VALID_TRANSITIONS: dict[CallStatus, set[CallStatus]] = {
    CallStatus.QUEUED: {CallStatus.INITIATED, CallStatus.CANCELLED},
    CallStatus.INITIATED: {
        CallStatus.RINGING,
        CallStatus.ANSWERED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.FAILED,
        CallStatus.CANCELLED,
    },
    CallStatus.RINGING: {
        CallStatus.ANSWERED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.FAILED,
        CallStatus.CANCELLED,
    },
    CallStatus.ANSWERED: {
        CallStatus.IN_PROGRESS,
        CallStatus.COMPLETED,
        CallStatus.FAILED,
        CallStatus.CANCELLED,
    },
    CallStatus.IN_PROGRESS: {
        CallStatus.COMPLETED,
        CallStatus.FAILED,
        CallStatus.CANCELLED,
    },
    **{status: set() for status in TERMINAL_STATUSES},
}

EVENT_TYPE_BY_STATUS = {
    CallStatus.INITIATED: "call.initiated",
    CallStatus.RINGING: "call.ringing",
    CallStatus.ANSWERED: "call.answered",
    CallStatus.IN_PROGRESS: "call.started",
    CallStatus.COMPLETED: "call.completed",
    CallStatus.NO_ANSWER: "call.no_answer",
    CallStatus.BUSY: "call.busy",
    CallStatus.FAILED: "call.failed",
    CallStatus.CANCELLED: "call.cancelled",
}


def get_event_by_provider_id(
    db: Session, provider_event_id: str | None
) -> CallEvent | None:
    if not provider_event_id:
        return None
    return db.scalar(
        select(CallEvent).where(CallEvent.provider_event_id == provider_event_id)
    )


def record_event(
    db: Session,
    call: Call,
    event_type: str,
    previous_status: CallStatus | None,
    new_status: CallStatus | None,
    provider_event_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> CallEvent:
    event = CallEvent(
        call_id=call.id,
        event_type=event_type,
        previous_status=previous_status.value if previous_status else None,
        new_status=new_status.value if new_status else None,
        provider_event_id=provider_event_id,
        payload=payload,
    )
    db.add(event)
    return event


def _apply_outcome(
    db: Session,
    call: Call,
    outcome: CallOutcome,
) -> None:
    call.outcome = outcome
    lead = call.lead
    outcome_statuses = {
        CallOutcome.INTERESTED: LeadStatus.INTERESTED,
        CallOutcome.NOT_INTERESTED: LeadStatus.NOT_INTERESTED,
        CallOutcome.CALLBACK: LeadStatus.CALLBACK,
        CallOutcome.APPOINTMENT_BOOKED: LeadStatus.APPOINTMENT_BOOKED,
        CallOutcome.DO_NOT_CALL: LeadStatus.DO_NOT_CALL,
        CallOutcome.WRONG_NUMBER: LeadStatus.FAILED,
        CallOutcome.NO_RESPONSE: LeadStatus.FAILED,
    }
    lead.status = outcome_statuses[outcome]

    if outcome == CallOutcome.CALLBACK:
        followup_at = call.summary.followup_at if call.summary else None
        followup = create_callback_followup(
            db, lead, notes=call.transcript, scheduled_at=followup_at, commit=False
        )
        call.next_retry_at = followup.scheduled_at
    elif outcome == CallOutcome.NO_RESPONSE:
        _schedule_retry(db, call, "Retry after no response")


def _schedule_retry(db: Session, call: Call, reason: str) -> None:
    followup = create_retry_followup(
        db,
        call.lead,
        reason=reason,
        max_attempts=call.max_attempts,
        commit=False,
    )
    call.retry_reason = reason
    call.next_retry_at = followup.scheduled_at if followup else None


def _apply_status_side_effects(
    db: Session,
    call: Call,
    status: CallStatus,
    outcome: CallOutcome | None,
    duration_seconds: int | None,
) -> None:
    now = datetime.utcnow()
    if status in {CallStatus.INITIATED, CallStatus.RINGING}:
        call.started_at = call.started_at or now
        call.lead.status = LeadStatus.CALLING
    elif status == CallStatus.ANSWERED:
        call.started_at = call.started_at or now
        call.answered_at = call.answered_at or now
        call.lead.status = LeadStatus.CONNECTED
    elif status == CallStatus.IN_PROGRESS:
        call.started_at = call.started_at or now
        call.answered_at = call.answered_at or now
        call.lead.status = LeadStatus.CONNECTED
    elif status == CallStatus.COMPLETED:
        call.ended_at = call.ended_at or now
        if duration_seconds is not None:
            call.duration_seconds = duration_seconds
        elif call.answered_at and call.duration_seconds is None:
            call.duration_seconds = max(0, int((call.ended_at - call.answered_at).total_seconds()))
        if outcome is not None:
            _apply_outcome(db, call, outcome)
        else:
            call.lead.status = LeadStatus.COMPLETED
    elif status in {CallStatus.NO_ANSWER, CallStatus.BUSY, CallStatus.FAILED}:
        call.ended_at = call.ended_at or now
        call.lead.status = LeadStatus.FAILED
        _schedule_retry(db, call, f"Retry after {status.value.lower().replace('_', ' ')}")
    elif status == CallStatus.CANCELLED:
        call.ended_at = call.ended_at or now
        call.lead.status = LeadStatus.NEW


def transition_call(
    db: Session,
    call: Call,
    new_status: CallStatus,
    *,
    outcome: CallOutcome | None = None,
    duration_seconds: int | None = None,
    provider: str | None = None,
    provider_call_id: str | None = None,
    provider_event_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[Call, CallEvent | None]:
    """Apply one validated call-state transition and persist an auditable event."""
    duplicate = get_event_by_provider_id(db, provider_event_id)
    if duplicate is not None:
        return call, duplicate

    previous_status = call.status
    if previous_status == new_status:
        return call, None
    if new_status not in VALID_TRANSITIONS[previous_status]:
        raise ValueError(
            f"Invalid call transition: {previous_status.value} -> {new_status.value}"
        )

    call.status = new_status
    if provider is not None:
        call.provider = provider
    if provider_call_id is not None:
        call.provider_call_id = provider_call_id
    _apply_status_side_effects(db, call, new_status, outcome, duration_seconds)
    event = record_event(
        db,
        call,
        EVENT_TYPE_BY_STATUS[new_status],
        previous_status,
        new_status,
        provider_event_id=provider_event_id,
        payload=payload,
    )
    db.commit()
    db.refresh(call)
    db.refresh(event)
    return call, event
