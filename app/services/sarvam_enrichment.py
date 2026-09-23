"""Enrich a completed, Sarvam-originated call with CRM data.

Sarvam Voice Agent handles the live conversation. This module ingests the
artefacts it produces (agent output variables, transcript) into our own
CRM records:

  lead -> call -> events -> messages -> qualification -> lead update

The agent variables come from the webhook's `final_agent_variables` field.
The transcript comes from the webhook's `interaction_transcript` field.

Idempotency: every call is enriched at most once (guarded by a marker in
CallSummary.qualification).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.call_message import CallMessage
from app.models.call_summary import CallSummary
from app.models.enums import CallStatus, LeadStatus

logger = logging.getLogger(__name__)

# Marker that identifies a qualification record written by Sarvam ingestion.
_SARVAM_SOURCE = "sarvam"


def _parse_budget(value) -> int | None:
    """Parse values like '50 lakh', '5000000', '50L', 5000000.0 into INR."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if not match:
        return None
    number = float(match.group(1))
    if "crore" in text.lower() or "cr" in text.lower():
        number *= 10_000_000
    elif "lakh" in text.lower() or "lac" in text.lower() or "l" in text.lower():
        number *= 100_000
    elif number < 1000:
        number = int(number)
    return int(number)


def _parse_timeline(value) -> str | None:
    """Normalize a timeline like '2 months', 'within two months', 'immediately'."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    numbers = {
        "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6",
    }
    lowered = text.lower()
    match = re.search(
        r"(\d+|\bone\b|\btwo\b|\bthree\b|\bfour\b|\bfive\b|\bsix\b)", lowered
    )
    unit = "months"
    if "week" in lowered:
        unit = "weeks"
    elif "day" in lowered:
        unit = "days"
    elif "year" in lowered or "yr" in lowered:
        unit = "years"
    elif "immediate" in lowered or "asap" in lowered or "soon" in lowered:
        return "immediately"
    if not match:
        return text if len(text) <= 40 else text[:40]
    return f"{numbers.get(match.group(1).lower(), match.group(1))} {unit}"


def _ingest_transcript(db: Session, call: Call, transcript_text: str) -> None:
    """Persist the transcript as ordered CallMessage rows (once)."""
    existing = db.scalar(
        select(func.count()).select_from(CallMessage).where(
            CallMessage.call_id == call.id
        )
    )
    if existing:
        return

    raw_lines = [line for line in transcript_text.splitlines() if line.strip()]
    parsed: list[tuple[str, str]] = []
    for line in raw_lines:
        match = re.match(
            r"^\s*(?P<speaker>agent|user|caller|customer|assistant|bot)\s*[:\-]\s*(?P<text>.+)$",
            line,
            re.IGNORECASE,
        )
        if match:
            speaker = "CALLER" if match.group("speaker").lower() in {
                "agent", "caller", "assistant", "bot",
            } else "CUSTOMER"
            parsed.append((speaker, match.group("text").strip()))
        else:
            speaker = "CUSTOMER" if parsed and parsed[-1][0] == "CALLER" else "CALLER"
            parsed.append((speaker, line.strip()))

    if not parsed:
        parsed.append(("CALLER", transcript_text.strip()[:500]))
        return

    for sequence, (speaker, text) in enumerate(parsed, start=1):
        db.add(
            CallMessage(
                call_id=call.id,
                sequence=sequence,
                speaker=speaker,
                text=text[:2_000],
            )
        )


def _infer_outcome(qualification: dict) -> str | None:
    """Infer CallOutcome from qualification dict."""
    if qualification.get("callback_requested"):
        return "CALLBACK"
    if qualification.get("appointment_requested"):
        return "APPOINTMENT_BOOKED"
    if qualification.get("qualification_status") == "DO_NOT_CONTACT":
        return "DO_NOT_CALL"
    if qualification.get("interested"):
        return "INTERESTED"
    if qualification.get("qualification_status") == "UNQUALIFIED":
        return "NOT_INTERESTED"
    return None


def _flatten_agent_variables(agent_variables: dict) -> dict:
    """Flatten nested agent variables to a flat dict.

    Sarvam agent variables can be nested (e.g. qualification sub-dict).
    We flatten for consistency with existing qualification format.
    """
    flat: dict = {}
    for key, value in agent_variables.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[sub_key] = sub_value
        else:
            flat[key] = value
    return flat


def apply_sarvam_enrichment(
    db: Session,
    call: Call,
    *,
    final_agent_variables: dict | None = None,
    interaction_transcript: list[dict] | None = None,
) -> dict[str, str | bool | None]:
    """Enrich a completed Sarvam call with agent variables and transcript.

    Returns a small result summary; never re-applies to an already-enriched
    call.
    """
    if call.status != CallStatus.COMPLETED:
        return {
            "enriched": False,
            "message": f"call status is {call.status.value}, not COMPLETED",
        }

    if call.summary is not None and (
        call.summary.qualification or {}
    ).get("source") == _SARVAM_SOURCE:
        return {
            "enriched": False,
            "message": "already enriched",
        }

    agent_vars = _flatten_agent_variables(final_agent_variables or {})

    qualification: dict = {"source": _SARVAM_SOURCE}
    for key in (
        "property_type", "bhk", "location", "city",
        "budget", "budget_amount", "timeline", "purpose",
        "interested", "appointment_requested", "callback_requested",
        "missing_info", "disposition", "call_step", "tenure",
        "qualification_status",
    ):
        if key in agent_vars and agent_vars[key] not in (None, ""):
            qualification[key] = agent_vars[key]

    if interaction_transcript:
        transcript_text = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('en_text', '')}"
            for turn in interaction_transcript
            if isinstance(turn, dict)
        )
        if transcript_text:
            _ingest_transcript(db, call, transcript_text)
            call.transcript = transcript_text[:10_000]

    requirement_parts = " ".join(
        str(qualification.get(k) or "").strip()
        for k in ("property_type", "bhk", "location")
        if qualification.get(k)
    )

    summary_qualification = db.scalar(
        select(CallSummary).where(CallSummary.call_id == call.id)
    )
    if summary_qualification is None:
        summary_qualification = CallSummary(call_id=call.id, summary="")
        db.add(summary_qualification)

    interested = bool(qualification.get("interested")) or (
        qualification.get("appointment_requested")
        or qualification.get("callback_requested")
    )

    raw_status = qualification.get("qualification_status", "")
    if raw_status == "DO_NOT_CONTACT":
        qualification_status = "DO_NOT_CONTACT"
    elif qualification_status := (
        "QUALIFIED"
        if interested
        else "UNQUALIFIED"
        if raw_status == "UNQUALIFIED"
        else "UNKNOWN"
    ):
        pass

    lead = call.lead
    budget_amount = (
        qualification.get("budget_amount")
        or _parse_budget(qualification.get("budget"))
    )
    timeline = _parse_timeline(qualification.get("timeline"))

    summary_qualification.summary = (
        summary_qualification.summary or "Sarvam voice-agent call completed."
    )
    summary_qualification.customer_intent = (
        "interested"
        if interested
        else "not_interested"
        if qualification_status == "UNQUALIFIED"
        else "unknown"
    )
    summary_qualification.interest_level = (
        "high" if interested else "low" if qualification_status == "UNQUALIFIED" else "unknown"
    )
    summary_qualification.requirements = (
        requirement_parts or qualification.get("requirement") or call.transcript
    )
    summary_qualification.objections = None
    next_action = qualification_status if qualification_status != "UNKNOWN" else "review"
    if qualification.get("callback_requested"):
        next_action = "callback"
    elif qualification.get("appointment_requested"):
        next_action = "schedule visit"
    summary_qualification.next_action = next_action
    summary_qualification.qualification_status = qualification_status
    summary_qualification.qualification = {
        **qualification,
        "interested": bool(qualification.get("interested")),
        "appointment_requested": bool(qualification.get("appointment_requested")),
        "callback_requested": bool(qualification.get("callback_requested")),
        "requirement": requirement_parts or None,
        "budget": budget_amount,
        "timeline": timeline,
        "qualification_status": qualification_status,
        "source": _SARVAM_SOURCE,
    }
    summary_qualification.followup_at = (
        datetime.utcnow().replace(microsecond=0) + timedelta(days=1)
        if qualification.get("callback_requested")
        else None
    )

    if requirement_parts:
        lead.requirement = summary_qualification.requirements
    if budget_amount is not None:
        lead.budget = budget_amount
    if timeline:
        lead.timeline = timeline
    if qualification.get("location"):
        lead.city = str(qualification["location"])
    elif qualification.get("city"):
        lead.city = str(qualification["city"])

    outcome = _infer_outcome(summary_qualification.qualification)
    if outcome:
        call.outcome = outcome

    if outcome == "CALLBACK":
        lead.status = LeadStatus.CALLBACK
        from app.services.retry_service import create_callback_followup
        followup = create_callback_followup(
            db, lead, notes=call.transcript, commit=False
        )
        call.next_retry_at = followup.scheduled_at
    elif outcome == "APPOINTMENT_BOOKED":
        lead.status = LeadStatus.APPOINTMENT_BOOKED
    elif outcome == "DO_NOT_CALL":
        lead.status = LeadStatus.DO_NOT_CALL
    elif outcome == "INTERESTED":
        lead.status = LeadStatus.INTERESTED
    elif outcome == "NOT_INTERESTED":
        lead.status = LeadStatus.NOT_INTERESTED
    elif qualification_status == "QUALIFIED":
        lead.status = LeadStatus.QUALIFIED
    else:
        lead.status = LeadStatus.COMPLETED

    db.commit()
    db.refresh(call)

    return {
        "enriched": True,
        "call_id": call.id,
        "outcome": outcome,
        "qualification_status": qualification_status,
    }
