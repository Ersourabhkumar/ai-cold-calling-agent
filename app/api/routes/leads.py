from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.lead import LeadCreate, LeadResponse, LeadUpdate
from app.services.lead_service import (
    create_lead,
    delete_lead,
    get_lead,
    get_leads,
    update_lead,
)

router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
)


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lead_endpoint(
    data: LeadCreate,
    db: Session = Depends(get_db),
):
    return create_lead(db, data)


@router.get(
    "",
    response_model=list[LeadResponse],
)
def list_leads_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_leads(db, skip=skip, limit=limit)


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
)
def get_lead_endpoint(
    lead_id: int,
    db: Session = Depends(get_db),
):
    lead = get_lead(db, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    return lead


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
)
def update_lead_endpoint(
    lead_id: int,
    data: LeadUpdate,
    db: Session = Depends(get_db),
):
    lead = get_lead(db, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    return update_lead(db, lead, data)


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_lead_endpoint(
    lead_id: int,
    db: Session = Depends(get_db),
):
    lead = get_lead(db, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    delete_lead(db, lead)