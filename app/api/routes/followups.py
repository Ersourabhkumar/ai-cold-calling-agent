from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.followup import (
    FollowupCreate,
    FollowupResponse,
    FollowupUpdate,
)
from app.services.followup_service import (
    create_followup,
    get_followup,
    get_followups,
    get_lead_followups,
    update_followup,
)

router = APIRouter(
    prefix="/api/followups",
    tags=["Followups"],
)


@router.post(
    "",
    response_model=FollowupResponse,
    status_code=201,
)
def create_followup_endpoint(
    data: FollowupCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_followup(db, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[FollowupResponse],
)
def list_followups(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_followups(db, skip=skip, limit=limit)


@router.get(
    "/lead/{lead_id}",
    response_model=list[FollowupResponse],
)
def list_lead_followups(
    lead_id: int,
    db: Session = Depends(get_db),
):
    return get_lead_followups(db, lead_id)


@router.get(
    "/{followup_id}",
    response_model=FollowupResponse,
)
def get_followup_endpoint(
    followup_id: int,
    db: Session = Depends(get_db),
):
    followup = get_followup(db, followup_id)

    if followup is None:
        raise HTTPException(
            status_code=404,
            detail="Followup not found",
        )

    return followup


@router.patch(
    "/{followup_id}",
    response_model=FollowupResponse,
)
def update_followup_endpoint(
    followup_id: int,
    data: FollowupUpdate,
    db: Session = Depends(get_db),
):
    followup = get_followup(db, followup_id)

    if followup is None:
        raise HTTPException(
            status_code=404,
            detail="Followup not found",
        )

    return update_followup(db, followup, data)