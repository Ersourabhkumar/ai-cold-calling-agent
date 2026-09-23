from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CallOutcome, CallStatus


class CallCreate(BaseModel):
    lead_id: int = Field(gt=0)
    campaign_id: int = Field(gt=0)


class CallUpdate(BaseModel):
    status: CallStatus | None = None
    outcome: CallOutcome | None = None
    provider: str | None = Field(default=None, max_length=50)
    provider_call_id: str | None = Field(default=None, max_length=255)
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    recording_url: str | None = None
    transcript: str | None = None


class CallStatusEvent(BaseModel):
    status: CallStatus
    provider_event_id: str | None = Field(default=None, max_length=255)
    duration_seconds: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] | None = None


class CallSimulationRequest(BaseModel):
    scenario: Literal["conversation", "no_answer", "busy", "failed", "cancelled", "sarvam"] = (
        "conversation"
    )
    customer_text: str | None = Field(default=None, min_length=1, max_length=4_000)
    complete: bool = False
    sarvam_transcript: list[dict] | None = None
    sarvam_agent_variables: dict | None = None
    sarvam_duration: int | None = None


class CallComplete(BaseModel):
    outcome: CallOutcome | None = None


class CallMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    sequence: int
    speaker: str
    text: str
    created_at: datetime


class CallEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    event_type: str
    previous_status: str | None
    new_status: str | None
    provider_event_id: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class QualificationResponse(BaseModel):
    interested: bool
    budget: str | None
    timeline: str | None
    requirement: str | None
    decision_maker: str | None
    callback_requested: bool
    appointment_requested: bool
    qualification_score: int = Field(ge=0, le=100)
    qualification_status: str


class CallSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    summary: str
    customer_intent: str | None
    interest_level: str | None
    requirements: str | None
    objections: str | None
    next_action: str | None
    qualification_status: str
    qualification: dict[str, Any]
    followup_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    campaign_id: int
    phone_number: str
    status: CallStatus
    provider: str | None
    provider_call_id: str | None
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    outcome: CallOutcome | None
    recording_url: str | None
    transcript: str | None
    attempt_number: int
    max_attempts: int
    next_retry_at: datetime | None
    retry_reason: str | None
    created_at: datetime
    updated_at: datetime
