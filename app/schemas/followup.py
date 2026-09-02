from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FollowupStatus


class FollowupCreate(BaseModel):
    lead_id: int = Field(gt=0)
    scheduled_at: datetime
    reason: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class FollowupUpdate(BaseModel):
    scheduled_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    status: FollowupStatus | None = None


class FollowupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    scheduled_at: datetime
    reason: str | None
    notes: str | None
    status: FollowupStatus
    created_at: datetime