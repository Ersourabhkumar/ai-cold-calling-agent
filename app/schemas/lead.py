from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LeadStatus


class LeadCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=100)
    requirement: str | None = None
    budget: str | None = Field(default=None, max_length=100)
    timeline: str | None = Field(default=None, max_length=100)


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=100)
    requirement: str | None = None
    budget: str | None = Field(default=None, max_length=100)
    timeline: str | None = Field(default=None, max_length=100)
    status: LeadStatus | None = None
    lead_score: int | None = Field(default=None, ge=0, le=100)


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    email: str | None
    city: str | None
    source: str | None
    requirement: str | None
    budget: str | None
    timeline: str | None
    status: LeadStatus
    lead_score: int
    attempt_count: int
    last_called_at: datetime | None
    next_call_at: datetime | None
    created_at: datetime
    updated_at: datetime