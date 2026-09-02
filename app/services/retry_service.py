from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.call_config import (
    CALLBACK_DELAY_MINUTES,
    MAX_CALL_ATTEMPTS,
    RETRY_DELAY_MINUTES,
)
from app.models.enums import FollowupStatus, LeadStatus
from app.models.followup import Followup
from app.models.lead import Lead


def _next_followup_time(minutes: int) -> datetime:
    """
    Return next follow-up time in UTC.

    Database currently uses timezone-naive DateTime,
    so UTC timezone information is removed before saving.
    """
    return (
        datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(minutes=minutes)
    )


def create_callback_followup(
    db: Session,
    lead: Lead,
    notes: str | None = None,
    scheduled_at: datetime | None = None,
    commit: bool = True,
) -> Followup:
    """
    Create a follow-up when customer requests a callback.
    """

    if lead.status == LeadStatus.DO_NOT_CALL:
        raise ValueError(
            "Cannot create callback for DO_NOT_CALL lead"
        )

    followup = Followup(
        lead_id=lead.id,
        scheduled_at=scheduled_at or _next_followup_time(CALLBACK_DELAY_MINUTES),
        reason="Customer requested callback",
        notes=notes,
        status=FollowupStatus.PENDING,
    )

    db.add(followup)

    lead.status = LeadStatus.CALLBACK

    if commit:
        db.commit()
        db.refresh(followup)

    return followup


def create_retry_followup(
    db: Session,
    lead: Lead,
    reason: str,
    notes: str | None = None,
    max_attempts: int = MAX_CALL_ATTEMPTS,
    commit: bool = True,
) -> Followup | None:
    """
    Create a retry follow-up if the lead has remaining attempts.
    """

    if lead.status == LeadStatus.DO_NOT_CALL:
        return None

    if lead.attempt_count >= max_attempts:
        lead.status = LeadStatus.FAILED

        if commit:
            db.commit()

        return None

    followup = Followup(
        lead_id=lead.id,
        scheduled_at=_next_followup_time(
            RETRY_DELAY_MINUTES
        ),
        reason=reason,
        notes=notes,
        status=FollowupStatus.PENDING,
    )

    db.add(followup)

    if commit:
        db.commit()
        db.refresh(followup)

    return followup
