from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone_validation import mask_phone, validate_phone
from app.database.connection import get_db
from app.services.call_log_sync import (
    CallLogSyncError,
    sync_tabby_call_logs,
)
from app.models.call import Call
from app.models.call_summary import CallSummary
from app.models.campaign import Campaign
from app.models.campaign_lead import CampaignLead
from app.models.enums import CampaignStatus
from app.models.lead import Lead
from app.services.call_dispatcher import CallDispatchError, dispatch_call
from app.services.call_service import create_call
from app.services.calling import get_calling_provider
from app.services.calling.tabbly_provider import TabblyCallingProvider
from app.schemas.admin import TestCallRequest, TestCallStatusRequest
from app.schemas.call import CallCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.post("/sync/tabbly-call-logs")
def sync_tabby_call_logs_endpoint(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Manually reconcile local calls with recent Tabbly call logs.

    Requires TELEPHONY_PROVIDER=tabbly and TABBLY_ORGANIZATION_ID. This is the
    poll-based fallback when status webhooks cannot reach a public URL.
    """
    try:
        return sync_tabby_call_logs(db, limit=limit)
    except CallLogSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Tabbly call-log sync endpoint failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/tabbly/campaigns/{call_id}/activate")
def re_activate_tabby_campaign(
    call_id: int,
    db: Session = Depends(get_db),
):
    """Re-activate and extend the Tabbly campaign backing a call.

    Use this when a call was dispatched but never dialled because the Tabbly
    scheduler did not run within the original window. Requires
    TABBLY_ORGANIZATION_ID.
    """
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    if not call.provider_call_id:
        raise HTTPException(
            status_code=409,
            detail="Call has no Tabbly campaign (provider_call_id is empty)",
        )

    provider = get_calling_provider()
    if not isinstance(provider, TabblyCallingProvider):
        raise HTTPException(
            status_code=409,
            detail="Tabbly re-activation requires TELEPHONY_PROVIDER=tabbly",
        )

    ok = provider.ensure_campaign_active(call.provider_call_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=(
                "Could not re-activate the Tabbly campaign. Ensure "
                "TABBLY_ORGANIZATION_ID is set and the campaign still exists."
            ),
        )

    return {
        "success": True,
        "call_id": call.id,
        "provider_call_id": call.provider_call_id,
        "message": (
            "Campaign re-activated. The Tabbly scheduler (or a dashboard "
            "Run action) will dial the contact within the new window."
        ),
    }


def _public_diagnostics(call: Call, detail: str | None = None) -> dict:
    """Render a diagnostic map without leaking secrets or full numbers."""
    tabs = {
        "Provider": call.provider or "unknown",
        "Internal Call ID": call.id,
        "Campaign ID": call.campaign_id,
        "Agent ID": os.getenv("TABBLY_AGENT_ID") or os.getenv("TABLLY_AGENT_ID") or "not set",
        "Provider Call ID": call.provider_call_id or "none",
        "Provider Status": call.status.value if call.status else "none",
        "Destination": mask_phone(call.phone_number),
        "Local Status": call.status.value if call.status else "none",
        "Lead Status": call.lead.status.value if call.lead else "none",
    }
    if detail:
        tabs["Detail"] = detail
    return tabs


@router.post("/test-call")
def create_test_call(
    data: TestCallRequest,
    db: Session = Depends(get_db),
):
    """Create a lead, a one-shot campaign, and dispatch EXACTLY ONE live call.

    Admin-only (X-API-Key required when API_KEY is set). Accepts
    ``{"phone": "+91..."}`` and returns everything needed to watch the call.
    No bulk dialing is possible from this endpoint: it creates a single call
    per request against an ACTIVE campaign with max_attempts=1.
    """
    validation = validate_phone(data.phone)
    if not validation.valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid phone number: {validation.reason}",
        )

    existing_campaign = db.scalar(
        select(Campaign).where(Campaign.name == data.campaign_name)
    )
    if existing_campaign is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Campaign '{data.campaign_name}' already exists; use a "
                "unique campaign_name or reuse the existing campaign via the "
                "regular lead/call endpoints."
            ),
        )

    lead = Lead(
        name=data.lead_name.strip(),
        phone=validation.normalized or data.phone.strip(),
        city=data.city,
        source="LIVE_DEMO",
        requirement=data.requirement,
        budget=data.budget,
        timeline=data.timeline,
    )
    db.add(lead)
    db.flush()

    campaign = Campaign(
        name=data.campaign_name.strip(),
        description=(
            "One-shot live demo campaign created by POST /api/admin/test-call."
        ),
        status=CampaignStatus.ACTIVE,
        max_attempts=1,
    )
    db.add(campaign)
    db.flush()

    db.add(
        CampaignLead(
            campaign_id=campaign.id,
            lead_id=lead.id,
        )
    )
    db.flush()

    try:
        call = create_call(
            db,
            CallCreate(lead_id=lead.id, campaign_id=campaign.id),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        call = dispatch_call(db, call)
    except CallDispatchError as exc:
        detail = str(exc)
        if call is not None:
            db.refresh(call)
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Live dispatch failed",
                    "diagnostics": _public_diagnostics(call, detail=detail[:300]),
                },
            ) from exc
        raise HTTPException(status_code=502, detail=detail) from exc

    db.refresh(call)
    return {
        "success": True,
        "message": (
            "One live call dispatched. Watch the destination phone and then "
            "refresh with POST /api/admin/test-call/status."
        ),
        "call": {
            "id": call.id,
            "status": call.status.value,
            "provider": call.provider,
            "provider_call_id": call.provider_call_id,
        },
        "lead": {"id": lead.id, "name": lead.name},
        "campaign": {"id": campaign.id, "name": campaign.name},
        "diagnostics": _public_diagnostics(call),
    }


@router.post("/test-call/status")
def test_call_status(
    data: TestCallStatusRequest,
    call_id: int,
    db: Session = Depends(get_db),
):
    """Return live call diagnostics; optionally reconcile Tabbly logs.

    Requires call_id. When TABBLY_ORGANIZATION_ID is configured, this also
    polls Tabbly call-logs-v2 and applies any terminal status/transcript.
    """
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    sync_result = None
    organization_id = os.getenv("TABBLY_ORGANIZATION_ID") or os.getenv(
        "TABLLY_ORGANIZATION_ID"
    )
    if organization_id:
        try:
            sync_result = sync_tabby_call_logs(db, limit=50)
            db.refresh(call)
        except Exception as exc:
            sync_result = {"error": str(exc)[:300]}

    summary = db.scalar(
        select(CallSummary).where(CallSummary.call_id == call.id)
    )

    outcome = None
    if summary is not None:
        outcome = summary.qualification or {}

    return {
        "success": True,
        "call": {
            "id": call.id,
            "status": call.status.value,
            "provider": call.provider,
            "provider_call_id": call.provider_call_id,
            "outcome": call.outcome.value if call.outcome else None,
            "duration_seconds": call.duration_seconds,
            "recording_url": call.recording_url,
            "transcript_available": bool(call.transcript),
        },
        "lead": {
            "id": call.lead.id if call.lead else None,
            "status": call.lead.status.value if call.lead else None,
            "requirement": call.lead.requirement if call.lead else None,
            "budget": call.lead.budget if call.lead else None,
            "timeline": call.lead.timeline if call.lead else None,
        },
        "qualification": outcome,
        "tabbly_sync": sync_result,
        "diagnostics": _public_diagnostics(call),
    }