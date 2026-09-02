from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.enums import CallStatus
from app.services.call_service import (
    update_call_from_provider,
)


TWILIO_STATUS_MAP = {
    "initiated": CallStatus.INITIATED,
    "ringing": CallStatus.RINGING,
    "in-progress": CallStatus.IN_PROGRESS,
    "answered": CallStatus.ANSWERED,
    "completed": CallStatus.COMPLETED,
    "busy": CallStatus.BUSY,
    "no-answer": CallStatus.NO_ANSWER,
    "failed": CallStatus.FAILED,
    "canceled": CallStatus.CANCELLED,
}


def process_twilio_webhook(
    db: Session,
    call: Call,
    call_status: str,
    duration: str | None = None,
    provider_event_id: str | None = None,
) -> Call:

    normalized_status = (
        call_status.lower().strip()
    )

    status = TWILIO_STATUS_MAP.get(
        normalized_status
    )

    if status is None:
        raise ValueError(
            f"Unsupported Twilio call status: "
            f"{call_status}"
        )

    duration_seconds = None

    if duration:
        try:
            duration_seconds = max(
                0,
                int(duration),
            )
        except (TypeError, ValueError):
            duration_seconds = None

    return update_call_from_provider(
        db=db,
        call=call,
        status=status,
        duration_seconds=duration_seconds,
        provider_event_id=provider_event_id,
    )
