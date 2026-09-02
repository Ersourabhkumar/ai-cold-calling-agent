from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.campaign_lead import (
    CampaignLeadCreate,
    CampaignLeadResponse,
)
from app.services.campaign_lead_service import (
    assign_lead_to_campaign,
    get_campaign_leads,
    remove_lead_from_campaign,
)


router = APIRouter(
    prefix="/api/campaigns",
    tags=["Campaign Leads"],
)


@router.post(
    "/{campaign_id}/leads/{lead_id}",
    response_model=CampaignLeadResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_lead_endpoint(
    campaign_id: int,
    lead_id: int,
    db: Session = Depends(get_db),
):
    try:
        return assign_lead_to_campaign(
            db,
            campaign_id,
            lead_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/{campaign_id}/leads",
    response_model=list[CampaignLeadResponse],
)
def list_campaign_leads_endpoint(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    return get_campaign_leads(
        db,
        campaign_id,
    )


@router.delete(
    "/{campaign_id}/leads/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_lead_endpoint(
    campaign_id: int,
    lead_id: int,
    db: Session = Depends(get_db),
):
    removed = remove_lead_from_campaign(
        db,
        campaign_id,
        lead_id,
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead is not assigned to this campaign",
        )