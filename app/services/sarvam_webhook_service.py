"""Handle Sarvam Voice Agent webhook payloads.

Verified webhook schema:
https://docs.sarvam.ai/conversations/api/instant-outbound/webhook-payload

Each inbound POST from Sarvam carries:
- attempt_id: matches the id returned when creating the outbound call
- status: connected | no_answer | busy | failed
- channel_info: channel_type, channel_provider, agent_phone_number
- duration: seconds (null if not connected)
- interaction_id: for analytics lookup (null if not connected)
- failure_reason: human-readable (null on success)
- final_agent_variables: dict of agent output (null if not connected)
- webhook_config: echoed metadata for correlation
- interaction_transcript: list of {role, en_text} turns (null if not connected)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.enums import CallStatus, LeadStatus
from app.services.call_lifecycle import transition_call
from app.services.sarvam_enrichment import apply_sarvam_enrichment

logger = logging.getLogger(__name__)

# Verified Sarvam status values -> internal CallStatus.
SARVAM_STATUS_MAP: dict[str, CallStatus] = {
    "connected": CallStatus.COMPLETED,
    "no_answer": CallStatus.NO_ANSWER,
    "busy": CallStatus.BUSY,
    "failed": CallStatus.FAILED,
}

# Bridge invalid transitions: a terminal webhook may land when the call is
# still INITIATED or RINGING (e.g. batched delivery).
_BRIDGE_TRANSITIONS: dict[CallStatus, set[CallStatus]] = {
    CallStatus.INITIATED: {CallStatus.RINGING, CallStatus.ANSWERED},
    CallStatus.RINGING: {CallStatus.ANSWERED},
    CallStatus.ANSWERED: {CallStatus.IN_PROGRESS},
}


def _resolve_call(db: Session, payload: dict[str, Any]) -> Call | None:
    """Resolve the internal Call record from the webhook payload.

    Strategy:
    1. webhook_config.metadata.call_id (our internal ID, most reliable)
    2. attempt_id (provider_call_id)
    3. Fallback: match by lead phone (last resort)
    """
    webhook_config = payload.get("webhook_config") or {}
    metadata = webhook_config.get("metadata") or {}

    call_id_raw = metadata.get("call_id")
    if call_id_raw is not None:
        try:
            call_id = int(call_id_raw)
            call = db.get(Call, call_id)
            if call is not None:
                return call
        except (TypeError, ValueError):
            pass

    attempt_id = payload.get("attempt_id")
    if attempt_id:
        call = db.scalar(
            select(Call).where(Call.provider_call_id == str(attempt_id))
        )
        if call is not None:
            return call

    logger.warning(
        "Sarvam webhook could not resolve call: attempt_id=%s, metadata=%s",
        attempt_id,
        metadata,
    )
    return None


def _transition_with_bridge(
    db: Session,
    call: Call,
    target_status: CallStatus,
    *,
    duration_seconds: int | None = None,
    provider_event_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[Call, Any]:
    """Attempt transition, bridging through intermediate states if needed.

    Sarvam sends a single final webhook per call attempt. The call may still
    be in INITIATED/RINGING from dispatch. We bridge through intermediate
    states so the terminal transition succeeds.
    """
    try:
        return transition_call(
            db,
            call,
            target_status,
            duration_seconds=duration_seconds,
            provider_event_id=provider_event_id,
            payload=payload,
        )
    except ValueError:
        bridge_states = _BRIDGE_TRANSITIONS.get(call.status, set())
        if target_status in bridge_states or target_status == CallStatus.COMPLETED:
            intermediate = sorted(
                bridge_states & {CallStatus.ANSWERED, CallStatus.IN_PROGRESS},
                key=lambda s: {
                    CallStatus.RINGING: 0,
                    CallStatus.ANSWERED: 1,
                    CallStatus.IN_PROGRESS: 2,
                }.get(s, 99),
            )
            for bridge_status in intermediate:
                if bridge_status != target_status and bridge_status in _BRIDGE_TRANSITIONS.get(
                    call.status, set()
                ):
                    call, _ = transition_call(db, call, bridge_status)
                    if bridge_status == target_status:
                        return call, None

            return transition_call(
                db,
                call,
                target_status,
                duration_seconds=duration_seconds,
                provider_event_id=provider_event_id,
                payload=payload,
            )
        raise


def process_sarvam_webhook(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Process one Sarvam instant-outbound webhook event.

    Returns a result dict suitable for the HTTP response. Never raises for
    unknown calls; provider redeliveries are idempotent by design.
    """
    attempt_id = payload.get("attempt_id", "")
    sarvam_status = payload.get("status", "")

    if not attempt_id or not sarvam_status:
        logger.warning(
            "Sarvam webhook missing attempt_id or status; ignoring."
        )
        return {
            "success": False,
            "handled": False,
            "message": "missing attempt_id or status",
        }

    call = _resolve_call(db, payload)

    if call is None:
        logger.warning(
            "Sarvam webhook for unknown attempt_id=%s; ignoring.",
            attempt_id,
        )
        return {
            "success": False,
            "handled": False,
            "message": "unknown call",
        }

    target_status = SARVAM_STATUS_MAP.get(sarvam_status)
    if target_status is None:
        logger.warning(
            "Sarvam webhook for call %s has unknown status=%s; ignoring.",
            call.id,
            sarvam_status,
        )
        return {
            "success": False,
            "handled": False,
            "call_id": call.id,
            "message": f"unsupported status: {sarvam_status}",
        }

    # Idempotency: if the call is already in the target terminal state,
    # this is a duplicate webhook delivery. Accept silently.
    if call.status == target_status:
        logger.info(
            "Sarvam webhook duplicate for call %s (already %s); accepting.",
            call.id,
            target_status.value,
        )
        return {
            "success": True,
            "handled": True,
            "call_id": call.id,
            "status": call.status.value,
            "duplicate": True,
        }

    duration_value = payload.get("duration")
    duration_seconds = None
    if duration_value is not None:
        try:
            duration_seconds = max(0, int(float(duration_value)))
        except (TypeError, ValueError):
            duration_seconds = None

    interaction_id = payload.get("interaction_id")
    interaction_transcript = payload.get("interaction_transcript") or []
    final_agent_variables = payload.get("final_agent_variables") or {}
    failure_reason = payload.get("failure_reason")

    event_payload: dict[str, Any] = {
        "source": "sarvam",
        "status": sarvam_status,
        "attempt_id": attempt_id,
        "interaction_id": interaction_id,
        "failure_reason": failure_reason,
    }
    if interaction_transcript:
        event_payload["transcript"] = str(interaction_transcript)[:10_000]
    if final_agent_variables:
        event_payload["agent_variables"] = final_agent_variables

    provider_event_id = f"sarvam:{attempt_id}:{sarvam_status}"

    try:
        updated_call, event = _transition_with_bridge(
            db,
            call,
            target_status,
            duration_seconds=duration_seconds,
            provider_event_id=provider_event_id,
            payload=event_payload,
        )
    except ValueError:
        logger.info(
            "Sarvam webhook for call %s ignored (transition): %s -> %s",
            call.id,
            call.status.value if call.status else None,
            target_status.value,
        )
        db.rollback()
        db.refresh(call)
        return {
            "success": True,
            "handled": False,
            "call_id": call.id,
            "message": "ignored",
        }

    if interaction_transcript:
        transcript_text = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('en_text', '')}"
            for turn in interaction_transcript
            if isinstance(turn, dict)
        )
        updated_call.transcript = transcript_text[:10_000]

    if interaction_id:
        from app.services.calling.sarvam_provider import (
            _SARVAM_RECORDING_URL_TEMPLATE,
        )
        import os
        org_id = os.getenv("SARVAM_ORG_ID")
        workspace_id = os.getenv("SARVAM_WORKSPACE_ID")
        app_id = os.getenv("SARVAM_APP_ID")
        if org_id and workspace_id and app_id:
            updated_call.recording_url = (
                f"https://apps.sarvam.ai/api/analytics/v1"
                f"/{org_id}/{workspace_id}/{app_id}/recordings/{interaction_id}"
            )

    db.commit()
    db.refresh(updated_call)

    duplicate = event is not None and event.previous_status == event.new_status

    enrichment = {}
    if target_status == CallStatus.COMPLETED:
        try:
            enrichment = apply_sarvam_enrichment(
                db,
                updated_call,
                final_agent_variables=final_agent_variables,
                interaction_transcript=interaction_transcript,
            )
        except Exception:
            logger.exception(
                "Sarvam enrichment failed for call %s; skipping.",
                updated_call.id,
            )

    logger.info(
        "Sarvam webhook applied status %s to call %s (duplicate=%s)",
        sarvam_status,
        updated_call.id,
        duplicate,
    )

    return {
        "success": True,
        "handled": True,
        "call_id": updated_call.id,
        "status": updated_call.status.value,
        "duplicate": bool(duplicate),
        "enriched": bool(enrichment.get("enriched")),
    }
