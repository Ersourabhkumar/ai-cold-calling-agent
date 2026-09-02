from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.enums import CallStatus
from app.services.call_lifecycle import transition_call
from app.services.calling import CallRequest, get_calling_provider

logger = logging.getLogger(__name__)


class CallDispatchError(RuntimeError):
    """Raised when the telephony provider fails to accept a call dispatch."""


def _mark_dispatch_failed(
    db: Session,
    call: Call,
    *,
    provider_name: str | None,
    error_message: str,
) -> RuntimeError:
    """
    Persist a failed dispatch through the valid lifecycle path.

    QUEUED cannot transition directly to FAILED, so the call is first
    recorded as attempted (INITIATED) and then marked FAILED. The FAILED
    transition schedules a retry follow-up when attempts remain.
    """
    initiated_call, _ = transition_call(
        db,
        call,
        CallStatus.INITIATED,
        provider=provider_name,
        payload={"dispatch_attempted": True},
    )

    transition_call(
        db,
        initiated_call,
        CallStatus.FAILED,
        provider_event_id=(
            f"dispatch-fail:{initiated_call.id}:"
            f"{initiated_call.attempt_number}"
        ),
        payload={
            "provider_error": str(error_message)[:500],
            "dispatch_error": True,
        },
    )

    return RuntimeError(error_message)


def dispatch_call(
    db: Session,
    call: Call,
) -> Call:
    if call.status != CallStatus.QUEUED:
        return call

    if call.lead.status.name == "DO_NOT_CALL":
        updated_call, _ = transition_call(
            db,
            call,
            CallStatus.CANCELLED,
        )
        return updated_call

    public_base_url = os.getenv(
        "PUBLIC_BASE_URL",
        "http://localhost:8000",
    ).rstrip("/")

    provider = get_calling_provider()

    request = CallRequest(
        phone_number=call.phone_number,
        call_id=call.id,
        lead_id=call.lead_id,
        campaign_id=call.campaign_id,
        webhook_url=public_base_url,
        lead_context={
            "name": call.lead.name or "",
            "city": call.lead.city or "",
            "requirement": call.lead.requirement or "",
            "budget": str(call.lead.budget or ""),
            "timeline": call.lead.timeline or "",
        },
    )

    try:
        result = provider.start_call(request)
    except Exception as exc:
        # Never leave the call falsely INITIATED when the provider rejects it.
        # Record the failure, transition to FAILED (which schedules a retry
        # when attempts remain), then surface a clean error to the caller.
        error_message = str(exc)

        logger.warning(
            "Provider dispatch failed for call %s: %s",
            call.id,
            error_message,
        )

        raise CallDispatchError(
            f"Telephony provider failed to place call {call.id}: {error_message}"
        ) from _mark_dispatch_failed(
            db,
            call,
            provider_name=getattr(provider, "provider", "unknown"),
            error_message=error_message,
        )

    if not result or not result.provider_call_id:
        raise CallDispatchError(
            f"Telephony provider returned no call ID for call {call.id}"
        ) from _mark_dispatch_failed(
            db,
            call,
            provider_name=getattr(result, "provider", None),
            error_message="Provider returned no call ID",
        )

    updated_call, _ = transition_call(
        db,
        call,
        CallStatus.INITIATED,
        provider=result.provider,
        provider_call_id=result.provider_call_id,
        payload={
            "provider_status": result.status,
            **(result.metadata or {}),
        },
    )

    return updated_call