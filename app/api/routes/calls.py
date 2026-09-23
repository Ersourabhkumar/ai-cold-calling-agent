from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.call_event import CallEvent
from app.models.call_message import CallMessage
from app.models.call_summary import CallSummary
from app.models.enums import CallOutcome, CallStatus
from app.schemas.call import (
    CallComplete,
    CallCreate,
    CallEventResponse,
    CallMessageResponse,
    CallResponse,
    CallSimulationRequest,
    CallStatusEvent,
    CallSummaryResponse,
    CallUpdate,
)
from app.services.ai.conversation import add_opening_message, process_customer_message
from app.services.call_dispatcher import CallDispatchError, dispatch_call
from app.services.call_lifecycle import transition_call
from app.services.call_service import create_call, get_call, get_calls, get_lead_calls, update_call
from app.services.sarvam_webhook_service import process_sarvam_webhook


router = APIRouter(prefix="/api/calls", tags=["Calls"])


def _real_provider_configured() -> bool:
    mode = os.getenv("CALLING_MODE", "mock").lower()
    if mode != "production":
        return False
    provider = os.getenv("TELEPHONY_PROVIDER", "sarvam").lower()
    return provider not in {"mock", "test", "local"}


def _require_call(db: Session, call_id: int):
    call = get_call(db, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


def _infer_outcome(call) -> CallOutcome | None:
    if call.summary is None:
        return None
    qualification = call.summary.qualification or {}
    if qualification.get("callback_requested"):
        return CallOutcome.CALLBACK
    if qualification.get("appointment_requested"):
        return CallOutcome.APPOINTMENT_BOOKED
    if qualification.get("qualification_status") == "DO_NOT_CONTACT":
        return CallOutcome.DO_NOT_CALL
    if qualification.get("interested"):
        return CallOutcome.INTERESTED
    if qualification.get("qualification_status") == "UNQUALIFIED":
        return CallOutcome.NOT_INTERESTED
    return None


def _ensure_conversation_started(db: Session, call) -> None:
    if call.status == CallStatus.QUEUED and _real_provider_configured():
        raise ValueError(
            "This call is QUEUED for a real provider call. "
            "Start it with POST /api/calls/{id}/start before running a "
            "conversation. Simulation requires CALLING_MODE=mock."
        )
    if call.status == CallStatus.QUEUED:
        call = dispatch_call(db, call)
    if call.status == CallStatus.INITIATED:
        call, _ = transition_call(db, call, CallStatus.RINGING)
    if call.status == CallStatus.RINGING:
        call, _ = transition_call(db, call, CallStatus.ANSWERED)
    if call.status == CallStatus.ANSWERED:
        call, _ = transition_call(db, call, CallStatus.IN_PROGRESS)
    if call.status != CallStatus.IN_PROGRESS:
        raise ValueError(f"Call cannot enter a conversation from {call.status.value}")
    add_opening_message(db, call)
    db.commit()


@router.post("", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
def create_call_endpoint(data: CallCreate, db: Session = Depends(get_db)):
    try:
        return create_call(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[CallResponse])
def list_calls_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_calls(db, skip=skip, limit=limit)


@router.get("/lead/{lead_id}", response_model=list[CallResponse])
def lead_call_history_endpoint(lead_id: int, db: Session = Depends(get_db)):
    return get_lead_calls(db, lead_id)


@router.get("/{call_id:int}", response_model=CallResponse)
def get_call_endpoint(call_id: int, db: Session = Depends(get_db)):
    return _require_call(db, call_id)


@router.patch("/{call_id:int}", response_model=CallResponse)
def update_call_endpoint(call_id: int, data: CallUpdate, db: Session = Depends(get_db)):
    call = _require_call(db, call_id)
    try:
        return update_call(db, call, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{call_id:int}/start", response_model=CallResponse)
def start_call_endpoint(call_id: int, db: Session = Depends(get_db)):
    call = _require_call(db, call_id)
    try:
        return dispatch_call(db, call)
    except CallDispatchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{call_id:int}/events", response_model=CallEventResponse)
def add_call_event_endpoint(
    call_id: int, data: CallStatusEvent, db: Session = Depends(get_db)
):
    call = _require_call(db, call_id)
    try:
        _, event = transition_call(
            db,
            call,
            data.status,
            duration_seconds=data.duration_seconds,
            provider_event_id=data.provider_event_id,
            payload=data.payload,
        )
        if event is None:
            raise HTTPException(status_code=409, detail="Duplicate status without a provider event ID")
        return event
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
@router.post("/{call_id:int}/conversation")
def conversation_endpoint(
    call_id: int,
    customer_text: str,
    db: Session = Depends(get_db),
):
    call = _require_call(db, call_id)

    try:
        _ensure_conversation_started(db, call)

        result = process_customer_message(
            db,
            call,
            customer_text,
        )

        db.commit()
        db.refresh(call)

        return {
            "call_id": call.id,
            "caller_text": result.caller_text,
            "qualification": result.qualification,
            "transcript": call.transcript,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

@router.post("/{call_id:int}/simulate")
def simulate_call_endpoint(
    call_id: int, data: CallSimulationRequest, db: Session = Depends(get_db)
):
    call = _require_call(db, call_id)
    if _real_provider_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Simulation is disabled when a real provider is configured "
                "(CALLING_MODE=production). Use POST /api/calls/{id}/start "
                "for a real Sarvam call instead."
            ),
        )
    try:
        if data.scenario == "cancelled":
            if call.status == CallStatus.QUEUED:
                call, _ = transition_call(db, call, CallStatus.CANCELLED)
            else:
                call, _ = transition_call(db, call, CallStatus.CANCELLED)
            return {"call": CallResponse.model_validate(call), "caller_text": None, "qualification": None}

        if call.status == CallStatus.QUEUED:
            call = dispatch_call(db, call)
        if call.status == CallStatus.INITIATED:
            call, _ = transition_call(db, call, CallStatus.RINGING)

        terminal_scenarios = {
            "no_answer": CallStatus.NO_ANSWER,
            "busy": CallStatus.BUSY,
            "failed": CallStatus.FAILED,
        }
        if data.scenario in terminal_scenarios:
            call, _ = transition_call(db, call, terminal_scenarios[data.scenario])
            return {"call": CallResponse.model_validate(call), "caller_text": None, "qualification": None}

        if data.scenario == "sarvam":
            if call.status == CallStatus.QUEUED:
                call = dispatch_call(db, call)
            if call.status not in {CallStatus.INITIATED, CallStatus.RINGING, CallStatus.ANSWERED, CallStatus.IN_PROGRESS}:
                raise ValueError(f"Cannot simulate Sarvam flow from status {call.status.value}")
            default_transcript = [
                {"role": "agent", "en_text": "Hello, this is the AI assistant calling about your inquiry. Is now a convenient time for a brief conversation?"},
                {"role": "user", "en_text": "Yes, tell me more."},
                {"role": "agent", "en_text": "Could you share what type of property you are looking for?"},
                {"role": "user", "en_text": "I am looking for a 2 BHK apartment in Bangalore."},
                {"role": "agent", "en_text": "What is your budget range?"},
                {"role": "user", "en_text": "Around 50 lakh."},
                {"role": "agent", "en_text": "What is your preferred timeline?"},
                {"role": "user", "en_text": "Within 3 months."},
                {"role": "agent", "en_text": "Would you like to schedule a property visit?"},
                {"role": "user", "en_text": "Yes, please schedule a visit."},
            ]
            default_agent_variables = {
                "property_type": "apartment",
                "bhk": "2",
                "location": "Bangalore",
                "budget": "50 lakh",
                "budget_amount": 5000000,
                "timeline": "3 months",
                "purpose": "self-use",
                "interested": True,
                "appointment_requested": True,
                "qualification_status": "QUALIFIED",
            }
            sarvam_payload = {
                "attempt_id": call.provider_call_id,
                "status": "connected",
                "duration": data.sarvam_duration or 120,
                "interaction_id": f"simulated-int-{call.id}",
                "failure_reason": None,
                "final_agent_variables": data.sarvam_agent_variables or default_agent_variables,
                "interaction_transcript": data.sarvam_transcript or default_transcript,
                "webhook_config": {"metadata": {"call_id": str(call.id)}},
            }
            result = process_sarvam_webhook(db, sarvam_payload)
            db.refresh(call)
            summary = None
            if call.summary:
                summary = CallSummaryResponse.model_validate(call.summary)
            return {
                "success": result.get("success"),
                "handled": result.get("handled"),
                "call_id": result.get("call_id"),
                "call": CallResponse.model_validate(call),
                "enriched": result.get("enriched"),
                "summary": summary,
            }

        _ensure_conversation_started(db, call)
        db.refresh(call)
        result = None
        if data.customer_text:
            result = process_customer_message(db, call, data.customer_text)
            db.commit()
            db.refresh(call)
        if data.complete:
            call, _ = transition_call(db, call, CallStatus.COMPLETED, outcome=_infer_outcome(call))
        return {
            "call": CallResponse.model_validate(call),
            "caller_text": result.caller_text if result else None,
            "qualification": result.qualification if result else None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{call_id:int}/complete", response_model=CallResponse)
def complete_call_endpoint(
    call_id: int, data: CallComplete, db: Session = Depends(get_db)
):
    call = _require_call(db, call_id)
    try:
        completed_call, _ = transition_call(
            db, call, CallStatus.COMPLETED, outcome=data.outcome or _infer_outcome(call)
        )
        return completed_call
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{call_id:int}/cancel", response_model=CallResponse)
def cancel_call_endpoint(call_id: int, db: Session = Depends(get_db)):
    call = _require_call(db, call_id)
    try:
        cancelled_call, _ = transition_call(db, call, CallStatus.CANCELLED)
        return cancelled_call
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{call_id:int}/events", response_model=list[CallEventResponse])
def list_call_events_endpoint(call_id: int, db: Session = Depends(get_db)):
    _require_call(db, call_id)
    return list(
        db.scalars(
            select(CallEvent).where(CallEvent.call_id == call_id).order_by(CallEvent.created_at)
        ).all()
    )


@router.get("/{call_id:int}/messages", response_model=list[CallMessageResponse])
def list_call_messages_endpoint(call_id: int, db: Session = Depends(get_db)):
    _require_call(db, call_id)
    return list(
        db.scalars(
            select(CallMessage)
            .where(CallMessage.call_id == call_id)
            .order_by(CallMessage.sequence)
        ).all()
    )


@router.get("/{call_id:int}/summary", response_model=CallSummaryResponse)
def get_call_summary_endpoint(call_id: int, db: Session = Depends(get_db)):
    _require_call(db, call_id)
    summary = db.scalar(select(CallSummary).where(CallSummary.call_id == call_id))
    if summary is None:
        raise HTTPException(status_code=404, detail="Call summary not available")
    return summary
