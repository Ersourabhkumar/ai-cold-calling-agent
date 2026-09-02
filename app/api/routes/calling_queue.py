from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.calling_queue import CallingQueueItem
from app.services.calling_queue_service import get_calling_queue


router = APIRouter(
    prefix="/api/calling-queue",
    tags=["Calling Queue"],
)


@router.get(
    "/{campaign_id}",
    response_model=list[CallingQueueItem],
)
def calling_queue_endpoint(
    campaign_id: int,
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
):
    return get_calling_queue(
        db,
        campaign_id=campaign_id,
        limit=limit,
    )