from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.enums import CallStatus, LeadStatus
from app.services.call_lifecycle import record_event, transition_call
from app.services.tabby_enrichment import apply_tabby_enrichment

logger = logging.getLogger(__name__)

# Tabbly does not publicly document its webhook payload schema, so status
# values arrive in several shapes. Map generously and parse defensively.
TABBLY_STATUS_MAP: dict[str, CallStatus] = {
    "initiated": CallStatus.INITIATED,
    "started": CallStatus.INITIATED,
    "queued": CallStatus.INITIATED,
    "ringing": CallStatus.RINGING,
    "answered": CallStatus.ANSWERED,
    "call_answered": CallStatus.ANSWERED,
    "connected": CallStatus.ANSWERED,
    "in_progress": CallStatus.IN_PROGRESS,
    "in_call": CallStatus.IN_PROGRESS,
    "conversation": CallStatus.IN_PROGRESS,
    "call_started": CallStatus.IN_PROGRESS,
    "completed": CallStatus.COMPLETED,
    "call_completed": CallStatus.COMPLETED,
    "ended": CallStatus.COMPLETED,
    "finished": CallStatus.COMPLETED,
    "done": CallStatus.COMPLETED,
    "no_answer": CallStatus.NO_ANSWER,
    "no_response": CallStatus.NO_ANSWER,
    "call_not_answered": CallStatus.NO_ANSWER,
    "call_not_answered_by_user": CallStatus.NO_ANSWER,
    "not_answered": CallStatus.NO_ANSWER,
    "not_answered_by_user": CallStatus.NO_ANSWER,
    "missed": CallStatus.NO_ANSWER,
    "unanswered": CallStatus.NO_ANSWER,
    "voicemail": CallStatus.NO_ANSWER,
    "number_unreachable": CallStatus.NO_ANSWER,
    "no_answer_ringing": CallStatus.NO_ANSWER,
    "busy": CallStatus.BUSY,
    "line_busy": CallStatus.BUSY,
    "failed": CallStatus.FAILED,
    "call_failed": CallStatus.FAILED,
    "error": CallStatus.FAILED,
    "failure": CallStatus.FAILED,
    "invalid_number": CallStatus.FAILED,
    "number_invalid": CallStatus.FAILED,
    "cancelled": CallStatus.CANCELLED,
    "canceled": CallStatus.CANCELLED,
    "aborted": CallStatus.CANCELLED,
    "abandoned": CallStatus.CANCELLED,
    "user_cancelled": CallStatus.CANCELLED,
}

_IDENTIFIER_KEYS = [
    "custom_identifiers",
    "custom_identifier",
    "identifiers",
]
_STATUS_KEYS = [
    "call_status",
    "callstatus",
    "event_status",
    "eventstatus",
    "status",
    "disposition",
    "state",
    "event_type",
    "event",
    "type",
]
_EVENT_ID_KEYS = [
    "provider_event_id",
    "webhook_event_id",
    "event_id",
    "webhook_id",
    "call_log_id",
    "record_id",
    "log_id",
]
_DURATION_KEYS = [
    "call_duration",
    "duration_seconds",
    "duration",
    "call_length",
]
_RECORDING_KEYS = [
    "call_recording",
    "recording_url",
    "recording",
    "recordingUrl",
]
_TRANSCRIPT_KEYS = [
    "call_transcript",
    "transcript",
    "transcription",
]
_CALL_ID_KEYS = [
    "call_id",
    "callId",
    "our_call_id",
    "calls_id",
]
_CAMPAIGN_ID_KEYS = [
    "tabbly_campaign_id",
    "campaign_id",
    "campaignId",
]

_CALLED_TO_KEYS = [
    "called_to",
    "called_number",
    "destination",
    "phone_number",
    "to_number",
]

_CALLED_TIME_KEYS = {
    "called_time",
    "call_time",
    "timestamp",
    "created_at",
    "event_time",
}

_CALLED_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
)

_VALUE_PAIR_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9_]*)\s*[:=]\s*([^,\s]+)"
)


def _normalize_status(value: Any) -> str:
    return (
        str(value)
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace("/", "_")
    )


def _deep_find_first(data: Any, keys: list[str] | set[str]) -> Any:
    """Return the first match for a candidate key in a nested dict/list.

    List keys are treated as ordered (priority); set keys are unordered.
    """
    if isinstance(data, dict):
        lowered = {str(key).lower(): value for key, value in data.items()}
        for target in keys:
            target = target.lower()
            if target in lowered:
                return lowered[target]
        for value in data.values():
            found = _deep_find_first(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _deep_find_first(item, keys)
            if found is not None:
                return found
    return None


def _parse_identifier_string(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(key): str(item) for key, item in parsed.items()}
        except (TypeError, ValueError):
            pass

        return {
            key: item
            for key, item in _VALUE_PAIR_RE.findall(raw)
        }

    return {}


def _collect_custom_identifiers(payload: dict[str, Any]) -> dict[str, str]:
    identifiers: dict[str, str] = {}

    raw = _deep_find_first(payload, _IDENTIFIER_KEYS)
    identifiers.update(_parse_identifier_string(raw))

    raw_list = _deep_find_first(payload, {"custom_identifiers_list"})
    if isinstance(raw_list, list):
        for entry in raw_list:
            identifiers.update(_parse_identifier_string(entry))

    return identifiers


_ACTIVE_CALL_STATUSES = {
    CallStatus.QUEUED,
    CallStatus.INITIATED,
    CallStatus.RINGING,
    CallStatus.ANSWERED,
    CallStatus.IN_PROGRESS,
}

_COMMITTED_STATUSES = {"completed", "call_completed", "ended", "finished", "done"}


def _normalize_phone_digits(value: Any) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _parse_called_time(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in _CALLED_TIME_FORMATS:
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None


def _match_by_destination(db: Session, payload: dict[str, Any]) -> Call | None:
    """Fallback: match a payload with no identifiers by destination number.

    Tabbly push webhooks (and call-log rows) are call-log-style payloads with
    at most called_to/called_time and no campaign or call identifier. When
    several campaigns share the same destination, prefer the candidate whose
    created_at is closest to the payload's called_time.

    Only active (non-terminal) tabbly calls are candidates so a late webhook
    for an old call cannot overwrite a newer terminal state.
    """
    called_to = _deep_find_first(payload, _CALLED_TO_KEYS)
    target_digits = _normalize_phone_digits(called_to)
    if not target_digits:
        return None

    called_time = _parse_called_time(
        _deep_find_first(payload, _CALLED_TIME_KEYS)
    )

    candidates = db.scalars(
        select(Call)
        .where(
            Call.provider.in_(("tabbly", "mock")),
            Call.status.in_(_ACTIVE_CALL_STATUSES),
        )
        .order_by(Call.id.desc())
        .limit(50)
    ).all()

    best: Call | None = None
    best_delta: float | None = None

    for candidate in candidates:
        candidate_digits = _normalize_phone_digits(candidate.phone_number)
        if not candidate_digits:
            continue
        if not (
            candidate_digits == target_digits
            or candidate_digits.endswith(target_digits[-10:])
        ):
            continue

        delta: float | None = None
        if called_time is not None and candidate.created_at is not None:
            try:
                delta = abs(
                    (called_time - candidate.created_at).total_seconds()
                )
                # called_time arrives in the account's wall-clock timezone
                # while created_at is stored in UTC, so compare with a wide
                # same-day window and rely on nearest-distance selection.
                if delta > 12 * 3600:
                    continue
            except (TypeError, ValueError):
                delta = None

        if best is None or (
            delta is not None
            and (best_delta is None or delta < best_delta)
        ):
            best = candidate
            best_delta = delta

    return best


def _resolve_call(db: Session, payload: dict[str, Any]) -> Call | None:
    identifiers = _collect_custom_identifiers(payload)

    call_id_raw = identifiers.get("call_id")
    if call_id_raw and call_id_raw.isdigit():
        call = db.get(Call, int(call_id_raw))
        if call is not None:
            return call

    explicit_call_id = _deep_find_first(payload, _CALL_ID_KEYS)
    if explicit_call_id is not None and str(explicit_call_id).isdigit():
        call = db.get(Call, int(explicit_call_id))
        if call is not None:
            return call

    campaign_id_raw = _deep_find_first(payload, _CAMPAIGN_ID_KEYS)
    if campaign_id_raw is not None:
        call = db.scalar(
            select(Call).where(
                Call.provider_call_id == str(campaign_id_raw)
            ).order_by(Call.id.desc())
        )
        if call is not None:
            return call

    identifiers_campaign = identifiers.get("campaign_id")
    if identifiers_campaign and identifiers_campaign.isdigit():
        call = db.scalar(
            select(Call).where(
                Call.provider_call_id == identifiers_campaign
            ).order_by(Call.id.desc())
        )
        return call

    return _match_by_destination(db, payload)


_REOPENABLE_TERMINAL = {
    CallStatus.NO_ANSWER,
    CallStatus.BUSY,
    CallStatus.FAILED,
}


def _reopen_terminal_call(
    db: Session,
    call: Call,
    from_status: CallStatus,
) -> None:
    """Force a settled terminal call back to ANSWERED.

    Tabbly emits one log row per dial attempt, and a 'Not Answered' row for
    the same provider call can land before the real 'Call Answered' row
    (e.g. an early ring that the customer picked up on the second attempt).
    When a later row proves the conversation happened, reopen the call so it
    can transition to COMPLETED and be enriched.
    """
    now = datetime.utcnow()
    call.status = CallStatus.ANSWERED
    call.started_at = call.started_at or now
    call.answered_at = call.answered_at or now
    call.lead.status = LeadStatus.CONNECTED
    record_event(
        db,
        call,
        "call.answered",
        from_status,
        CallStatus.ANSWERED,
        provider_event_id=f"reopen:{call.id}:{from_status.value}",
        payload={
            "reopened": True,
            "reason": "conversation row arrived after terminal settle",
        },
    )
    db.commit()
    db.refresh(call)


def process_tabbly_webhook(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply one Tabbly webhook event.

    Returns a result dict suitable for the HTTP response. Never raises for
    unknown calls or duplicate/out-of-order events; provider redeliveries are
    idempotent by design.
    """
    call = _resolve_call(db, payload)

    if call is None:
        logger.warning(
            "Tabbly webhook referenced an unknown call; ignoring. "
            "payload_keys=%s",
            sorted(payload.keys())[:20],
        )
        return {
            "success": False,
            "handled": False,
            "message": "unknown call",
        }

    status_value = _deep_find_first(payload, _STATUS_KEYS)
    status = TABBLY_STATUS_MAP.get(_normalize_status(status_value)) if status_value else None

    if status is None:
        logger.warning(
            "Tabbly webhook for call %s carried no recognised status; ignoring.",
            call.id,
        )
        return {
            "success": False,
            "handled": False,
            "call_id": call.id,
            "message": "unsupported status",
        }

    duration_value = _deep_find_first(payload, _DURATION_KEYS)
    duration_seconds = None
    if duration_value is not None:
        try:
            duration_seconds = max(0, int(str(duration_value).split(".")[0]))
        except (TypeError, ValueError):
            duration_seconds = None

    transcript = _deep_find_first(payload, _TRANSCRIPT_KEYS)
    recording_url = _deep_find_first(payload, _RECORDING_KEYS)

    # Tabbly reports an answered call as a single "Call Answered" row that
    # already carries the transcript, duration and JSON output; it never emits
    # a separate "completed" row. Treat an answered row that contains a real
    # conversation (duration + meaningful transcript) as terminal COMPLETED so
    # enrichment, outcomes and follow-ups actually run.
    has_conversation = bool(
        duration_seconds
        and duration_seconds > 0
        and transcript
        and len(str(transcript).strip()) >= 40
    )
    effective_status = (
        CallStatus.COMPLETED
        if status == CallStatus.ANSWERED and has_conversation
        else status
    )

    event_id_value = _deep_find_first(payload, _EVENT_ID_KEYS)
    provider_event_id = str(event_id_value) if event_id_value is not None else None

    if not provider_event_id:
        provider_event_id = ":".join(
            part
            for part in [
                str(call.provider_call_id or call.id),
                _normalize_status(status_value),
                str(duration_seconds or ""),
                str(_deep_find_first(payload, {"called_time", "timestamp", "created_at", "time"}) or ""),
            ]
            if part
        )

    # When COMPLETED was synthesized from an ANSWERED row, use a distinct
    # terminal event id so the duplicate guard in transition_call cannot block
    # the final upgrade (the same row may already have applied ANSWERED under
    # an earlier payload or code version).
    if effective_status == CallStatus.COMPLETED and status != CallStatus.COMPLETED:
        provider_event_id = (
            f"{provider_event_id}:completed" if provider_event_id else None
        )

    event_payload: dict[str, Any] = {
        "source": "tabbly",
        "status": str(status_value),
        "provider_call_id": call.provider_call_id,
    }
    if transcript:
        event_payload["transcript"] = str(transcript)[:10_000]
    if recording_url:
        event_payload["recording_url"] = str(recording_url)

    # A 'Call Answered' row can arrive after an earlier terminal settle (the
    # customer picked up on a later attempt of the same campaign). Reopen the
    # call so the proven conversation can be recorded and enriched. The call
    # was already resolved authoritatively by identifier (e.g. call_id) or
    # destination above, so no extra campaign check is needed here.
    if (
        effective_status == CallStatus.COMPLETED
        and has_conversation
        and call.status in _REOPENABLE_TERMINAL
    ):
        logger.info(
            "Tabbly webhook reopened call %s from %s after a conversation row "
            "arrived.",
            call.id,
            call.status.value,
        )
        _reopen_terminal_call(db, call, call.status)

    try:
        _, event = transition_call(
            db,
            call,
            effective_status,
            duration_seconds=duration_seconds,
            provider_event_id=provider_event_id,
            payload=event_payload,
        )
    except ValueError:
        # A terminal COMPLETED webhook can arrive without prior ringing or
        # answered events (batched or missed delivery). Bridge through ANSWERED
        # so the lifecycle stays internally consistent.
        if effective_status == CallStatus.COMPLETED and call.status in {
            CallStatus.INITIATED,
            CallStatus.RINGING,
        }:
            call, _ = transition_call(db, call, CallStatus.ANSWERED)
            _, event = transition_call(
                db,
                call,
                effective_status,
                duration_seconds=duration_seconds,
                provider_event_id=provider_event_id,
                payload=event_payload,
            )
        else:
            logger.info(
                "Tabbly webhook for call %s ignored (transition): %s -> %s",
                call.id,
                call.status.value if call.status else None,
                effective_status.value,
            )
            db.rollback()
            db.refresh(call)
            return {
                "success": True,
                "handled": False,
                "call_id": call.id,
                "message": "ignored",
            }

    if transcript:
        call.transcript = str(transcript)[:10_000]
    if recording_url:
        call.recording_url = str(recording_url)

    db.commit()
    db.refresh(call)

    duplicate = event is not None and event.previous_status == event.new_status

    enrichment = {}
    if effective_status == CallStatus.COMPLETED:
        try:
            enrichment = apply_tabby_enrichment(db, call, payload)
        except Exception:
            logger.exception(
                "Tabbly enrichment failed for call %s; skipping.",
                call.id,
            )

    logger.info(
        "Tabbly webhook applied status %s to call %s (duplicate=%s)",
        status.value,
        call.id,
        duplicate,
    )

    return {
        "success": True,
        "handled": True,
        "call_id": call.id,
        "status": call.status.value,
        "duplicate": bool(duplicate),
        "enriched": bool(enrichment.get("enriched")),
    }