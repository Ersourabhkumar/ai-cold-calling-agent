from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import FollowupStatus, LeadStatus
from app.models.followup import Followup
from app.models.lead import Lead
from app.schemas.followup import FollowupCreate, FollowupUpdate


def _utc_now() -> datetime:
    """
    Return current UTC time as timezone-naive datetime.

    PostgreSQL followups.scheduled_at currently uses
    timestamp without time zone.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_followup(
    db: Session,
    data: FollowupCreate,
) -> Followup:

    lead = db.get(Lead, data.lead_id)

    if lead is None:
        raise ValueError("Lead not found")

    if lead.status == LeadStatus.DO_NOT_CALL:
        raise ValueError(
            "Lead is marked as DO_NOT_CALL"
        )

    if data.scheduled_at < _utc_now():
        raise ValueError(
            "scheduled_at must be in the future"
        )

    followup = Followup(
        lead_id=lead.id,
        scheduled_at=data.scheduled_at,
        reason=data.reason,
        notes=data.notes,
        status=FollowupStatus.PENDING,
    )

    db.add(followup)

    db.commit()
    db.refresh(followup)

    return followup


def get_followup(
    db: Session,
    followup_id: int,
) -> Followup | None:

    return db.get(Followup, followup_id)


def get_followups(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[Followup]:

    statement = (
        select(Followup)
        .order_by(Followup.scheduled_at.asc())
        .offset(skip)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )


def get_lead_followups(
    db: Session,
    lead_id: int,
) -> list[Followup]:

    statement = (
        select(Followup)
        .where(
            Followup.lead_id == lead_id
        )
        .order_by(
            Followup.scheduled_at.asc()
        )
    )

    return list(
        db.scalars(statement).all()
    )


def get_pending_followups(
    db: Session,
    limit: int = 100,
) -> list[Followup]:

    now = _utc_now()

    statement = (
        select(Followup)
        .where(
            Followup.status == FollowupStatus.PENDING,
            Followup.scheduled_at <= now,
        )
        .order_by(
            Followup.scheduled_at.asc()
        )
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )


def update_followup(
    db: Session,
    followup: Followup,
    data: FollowupUpdate,
) -> Followup:

    update_data = data.model_dump(
        exclude_unset=True
    )

    if "scheduled_at" in update_data:

        scheduled_at = update_data["scheduled_at"]

        if (
            scheduled_at is not None
            and scheduled_at < _utc_now()
            and followup.status
            == FollowupStatus.PENDING
        ):
            raise ValueError(
                "scheduled_at must be in the future"
            )

    for field, value in update_data.items():
        setattr(
            followup,
            field,
            value,
        )

    db.commit()
    db.refresh(followup)

    return followup