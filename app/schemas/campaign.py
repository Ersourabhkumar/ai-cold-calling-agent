from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CampaignStatus


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
    )

    calling_start_time: time | None = None
    calling_end_time: time | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )

    description: str | None = None

    status: CampaignStatus | None = None

    max_attempts: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )

    calling_start_time: time | None = None
    calling_end_time: time | None = None


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: CampaignStatus
    max_attempts: int
    calling_start_time: time | None
    calling_end_time: time | None
    created_at: datetime
    updated_at: datetime


class CampaignDispatchRequest(BaseModel):
    """Bulk-dispatch a campaign. dry_run=True (default) only previews."""

    max_calls: int | None = Field(default=50, ge=1, le=500)
    dry_run: bool = True


class DispatchLeadResult(BaseModel):
    lead_id: int
    call_id: int | None = None
    status: str | None = None
    reason: str | None = None


class CampaignDispatchResponse(BaseModel):
    campaign_id: int
    dry_run: bool
    eligible: int
    dispatched: list[DispatchLeadResult] = []
    skipped: list[DispatchLeadResult] = []
    failed: list[DispatchLeadResult] = []