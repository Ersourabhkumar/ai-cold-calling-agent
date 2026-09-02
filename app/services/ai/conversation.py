from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.call_message import CallMessage
from app.models.call_summary import CallSummary
from app.schemas.call import QualificationResponse
from app.services.ai.providers import get_llm_provider


@dataclass(frozen=True)
class ConversationResult:
    caller_text: str
    qualification: QualificationResponse


def _next_sequence(db: Session, call_id: int) -> int:
    # SessionLocal disables autoflush, so persist pending turns before deriving
    # the next sequence number. This keeps the per-call ordering constraint safe.
    db.flush()
    return int(db.scalar(select(func.coalesce(func.max(CallMessage.sequence), 0)).where(CallMessage.call_id == call_id)) or 0) + 1


def _append_message(db: Session, call: Call, speaker: str, text: str) -> CallMessage:
    message = CallMessage(
        call_id=call.id,
        sequence=_next_sequence(db, call.id),
        speaker=speaker,
        text=text,
    )
    db.add(message)
    return message


def _render_transcript(db: Session, call: Call) -> str:
    db.flush()
    messages = db.scalars(
        select(CallMessage)
        .where(CallMessage.call_id == call.id)
        .order_by(CallMessage.sequence)
    ).all()
    return "\n".join(f"{message.speaker}: {message.text}" for message in messages)


def _upsert_summary(
    db: Session,
    call: Call,
    qualification: QualificationResponse,
    customer_text: str,
) -> CallSummary:
    summary = call.summary
    if summary is None:
        summary = CallSummary(call_id=call.id, summary="Conversation started.")
        db.add(summary)

    if qualification.callback_requested:
        intent = "callback"
        next_action = "Create a callback follow-up"
        followup_at = datetime.utcnow() + timedelta(days=1)
    elif qualification.appointment_requested:
        intent = "appointment"
        next_action = "Confirm appointment details"
        followup_at = None
    elif qualification.interested:
        intent = "interested"
        next_action = "Continue qualification"
        followup_at = None
    elif qualification.qualification_status == "DO_NOT_CONTACT":
        intent = "do_not_contact"
        next_action = "Do not contact this lead"
        followup_at = None
    else:
        intent = "unknown"
        next_action = "Continue conversation"
        followup_at = None

    summary.summary = f"Customer intent: {intent}. Latest response: {customer_text}"
    summary.customer_intent = intent
    summary.interest_level = "high" if qualification.interested else "low" if qualification.qualification_status == "UNQUALIFIED" else "unknown"
    summary.requirements = qualification.requirement
    summary.objections = customer_text if qualification.qualification_status in {"UNQUALIFIED", "DO_NOT_CONTACT"} else None
    summary.next_action = next_action
    summary.qualification_status = qualification.qualification_status
    summary.qualification = qualification.model_dump()
    summary.followup_at = followup_at
    return summary


def add_opening_message(db: Session, call: Call) -> None:
    if db.scalar(select(CallMessage.id).where(CallMessage.call_id == call.id).limit(1)):
        return
    _append_message(
        db,
        call,
        "CALLER",
        "Hello, this is the AI assistant calling about your inquiry. Is now a convenient time for a brief conversation?",
    )
    call.transcript = _render_transcript(db, call)


def process_customer_message(
    db: Session,
    call: Call,
    customer_text: str,
) -> ConversationResult:

    # Make sure the AI opening message exists
    add_opening_message(db, call)

    # Save customer's latest message
    _append_message(
        db,
        call,
        "CUSTOMER",
        customer_text,
    )

    # Build complete conversation history
    conversation_history = _render_transcript(
        db,
        call,
    )

    # Give the AI the information already known about the lead
    lead_context = "\n".join(
        [
            f"Name: {call.lead.name}",
            f"Phone: {call.lead.phone}",
            f"City: {call.lead.city or 'Unknown'}",
            f"Requirement: {call.lead.requirement or 'Unknown'}",
            f"Budget: {call.lead.budget or 'Unknown'}",
            f"Timeline: {call.lead.timeline or 'Unknown'}",
            f"Lead status: {call.lead.status.value}",
        ]
    )

    # Ask LLM for the next response
    reply = get_llm_provider().respond(
        customer_text=customer_text,
        lead_name=call.lead.name,
        conversation_history=conversation_history,
        lead_context=lead_context,
    )

    # Save AI response
    _append_message(
        db,
        call,
        "CALLER",
        reply.text,
    )

    # Update transcript
    call.transcript = _render_transcript(
        db,
        call,
    )

    # Update AI qualification summary
    _upsert_summary(
        db,
        call,
        reply.qualification,
        customer_text,
    )

    db.flush()

    return ConversationResult(
        caller_text=reply.text,
        qualification=reply.qualification,
    )
