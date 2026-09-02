from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadUpdate


def create_lead(db: Session, data: LeadCreate) -> Lead:
    lead = Lead(**data.model_dump())

    db.add(lead)
    db.commit()
    db.refresh(lead)

    return lead


def get_lead(db: Session, lead_id: int) -> Lead | None:
    return db.get(Lead, lead_id)


def get_leads(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[Lead]:

    statement = (
        select(Lead)
        .order_by(Lead.id.desc())
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def update_lead(
    db: Session,
    lead: Lead,
    data: LeadUpdate,
) -> Lead:

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(lead, field, value)

    db.commit()
    db.refresh(lead)

    return lead


def delete_lead(db: Session, lead: Lead) -> None:
    db.delete(lead)
    db.commit()