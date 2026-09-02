from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.campaign import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
)
from app.services.campaign_service import (
    create_campaign,
    delete_campaign,
    get_campaign,
    get_campaigns,
    update_campaign,
)


router = APIRouter(
    prefix="/api/campaigns",
    tags=["Campaigns"],
)


@router.post(
    "",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_campaign_endpoint(
    data: CampaignCreate,
    db: Session = Depends(get_db),
):
    return create_campaign(db, data)


@router.get(
    "",
    response_model=list[CampaignResponse],
)
def list_campaigns_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_campaigns(
        db,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{campaign_id}",
    response_model=CampaignResponse,
)
def get_campaign_endpoint(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    campaign = get_campaign(db, campaign_id)

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return campaign


@router.patch(
    "/{campaign_id}",
    response_model=CampaignResponse,
)
def update_campaign_endpoint(
    campaign_id: int,
    data: CampaignUpdate,
    db: Session = Depends(get_db),
):
    campaign = get_campaign(db, campaign_id)

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return update_campaign(
        db,
        campaign,
        data,
    )


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_campaign_endpoint(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    campaign = get_campaign(db, campaign_id)

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    delete_campaign(db, campaign)