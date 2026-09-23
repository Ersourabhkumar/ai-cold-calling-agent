"""Browser UI dashboard (server-rendered with Jinja2).

Lets the operator drive the whole system from the browser instead of curl:
view dashboard / leads / calls / follow-ups, add CRM leads, and fire + watch a
live Sarvam call. The JSON action endpoints (/ui/api/*) require the API key
via X-API-Key (stored in the browser), exactly like /api/*.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.phone_validation import mask_phone, validate_phone
from app.database.connection import get_db
from app.models.call import Call
from app.models.call_summary import CallSummary
from app.models.campaign import Campaign
from app.models.followup import Followup
from app.models.lead import Lead
from app.services.call_dispatcher import CallDispatchError, dispatch_call
from app.services.call_service import create_call
from app.schemas.admin import TestCallRequest
from app.schemas.call import CallCreate

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES = Jinja2Templates(directory=str(_BASE / "app" / "templates"))

router = APIRouter(prefix="/ui", tags=["UI"])


def _serialize_lead(l: Lead) -> dict:
    return {
        "id": l.id,
        "name": l.name,
        "phone": l.phone,
        "phone_masked": mask_phone(l.phone),
        "email": l.email,
        "city": l.city,
        "source": l.source,
        "requirement": l.requirement,
        "budget": l.budget,
        "timeline": l.timeline,
        "status": l.status.value if l.status else None,
        "lead_score": l.lead_score or 0,
        "created_at": l.created_at.strftime("%Y-%m-%d %H:%M"),
    }


def _serialize_call(c: Call) -> dict:
    return {
        "id": c.id,
        "lead_id": c.lead_id,
        "lead_name": c.lead.name if c.lead else "?",
        "phone_masked": mask_phone(c.phone_number),
        "status": c.status.value if c.status else None,
        "outcome": c.outcome.value if c.outcome else None,
        "duration_seconds": c.duration_seconds or 0,
        "provider": c.provider,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
        "transcript": c.transcript,
        "summary": c.summary,
    }


def _draw_summary_stats(db: Session, leads: list[Lead], calls: list[Call], followups: list[Followup], campaigns: list[Campaign]) -> dict:
    qualified = sum(1 for l in leads if l.status and l.status.name == "QUALIFIED")
    answered = sum(1 for c in calls if c.status and c.status.name in {"ANSWERED", "IN_PROGRESS", "COMPLETED"}
                   and c.duration_seconds)
    pending = sum(1 for f in followups if f.status and f.status.name == "PENDING")
    return {
        "leads": len(leads),
        "qualified": qualified,
        "calls": len(calls),
        "answered": answered,
        "pending_followups": pending,
        "campaigns": len(campaigns),
    }


# ---------------------------------------------------------------- pages
@router.get("", response_class=HTMLResponse)
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).order_by(Lead.id.desc()).limit(50)).all()
    calls = db.scalars(select(Call).order_by(Call.id.desc()).limit(50)).all()
    followups = db.scalars(select(Followup).order_by(Followup.id.desc()).limit(50)).all()
    campaigns = db.scalars(select(Campaign).order_by(Campaign.id.desc()).limit(50)).all()
    recent_calls = [_serialize_call(c) for c in calls[:8]]
    recent_leads = [_serialize_lead(l) for l in leads[:8]]
    stats = _draw_summary_stats(db, leads, calls, followups, campaigns)
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        {"active": "dashboard", "stats": stats, "recent_calls": recent_calls, "recent_leads": recent_leads},
    )


@router.get("/leads", response_class=HTMLResponse)
def ui_leads(request: Request, db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).order_by(Lead.id.desc()).limit(200)).all()
    return TEMPLATES.TemplateResponse(
        request, "leads.html", {"active": "leads", "leads": [_serialize_lead(l) for l in leads]}
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def ui_lead_detail(request: Request, lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    calls = db.scalars(
        select(Call).where(Call.lead_id == lead_id).order_by(Call.id.desc())
    ).all()
    followups = db.scalars(
        select(Followup).where(Followup.lead_id == lead_id).order_by(Followup.id.desc())
    ).all()
    call_objs = []
    for c in calls:
        obj = _serialize_call(c)
        obj["summary"] = c.summary
        call_objs.append(obj)
    return TEMPLATES.TemplateResponse(
        request,
        "lead_detail.html",
        {
            "active": "leads",
            "lead": _serialize_lead(lead),
            "calls": call_objs,
            "followups": followups,
        },
    )


@router.get("/calls", response_class=HTMLResponse)
def ui_calls(request: Request, db: Session = Depends(get_db)):
    calls = db.scalars(select(Call).order_by(Call.id.desc()).limit(500)).all()
    return TEMPLATES.TemplateResponse(
        request, "calls.html", {"active": "calls", "calls": [_serialize_call(c) for c in calls]}
    )


@router.get("/followups", response_class=HTMLResponse)
def ui_followups(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Followup, Lead).join(Lead, Followup.lead_id == Lead.id).order_by(Followup.id.desc()).limit(500)
    ).all()
    followups = []
    for f, l in rows:
        followups.append(
            {
                "id": f.id,
                "lead_id": f.lead_id,
                "lead_name": l.name,
                "scheduled_at": f.scheduled_at.strftime("%Y-%m-%d %H:%M"),
                "status": f.status.value if f.status else None,
                "reason": f.reason,
                "notes": f.notes,
            }
        )
    pending = sum(1 for f in followups if f["status"] == "PENDING")
    done = sum(1 for f in followups if f["status"] == "DONE")
    return TEMPLATES.TemplateResponse(
        request,
        "followups.html",
        {"active": "followups", "followups": followups, "pending": pending, "done": done},
    )


@router.get("/new-call", response_class=HTMLResponse)
def ui_new_call(request: Request):
    return TEMPLATES.TemplateResponse(request, "fire_call.html", {"active": "newcall"})


# ---------------------------------------------------------------- actions
class _UILeadCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = None
    city: str | None = None
    source: str | None = "web"
    requirement: str | None = None
    budget: str | None = None
    timeline: str | None = None


@router.post("/api/leads")
def ui_create_lead(data: _UILeadCreate, db: Session = Depends(get_db)):
    from app.models.enums import LeadStatus

    v = validate_phone(data.phone)
    if not v.valid:
        raise HTTPException(status_code=422, detail=f"Invalid phone: {v.reason}")
    lead = Lead(
        name=data.name.strip(),
        phone=v.normalized or data.phone.strip(),
        email=data.email,
        city=data.city,
        source=data.source or "web",
        requirement=data.requirement,
        budget=data.budget,
        timeline=data.timeline,
        status=LeadStatus.NEW,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return {"id": lead.id, "name": lead.name, "status": lead.status.value}


@router.post("/api/test-call")
def ui_fire_call(data: TestCallRequest, db: Session = Depends(get_db)):
    """Create lead + one-shot campaign and dispatch exactly one live call."""
    existing = db.scalar(select(Campaign).where(Campaign.name == data.campaign_name))
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Campaign '{data.campaign_name}' already exists; use a unique campaign_name.")

    v = validate_phone(data.phone)
    if not v.valid:
        raise HTTPException(status_code=422, detail=f"Invalid phone: {v.reason}")

    from app.models.enums import CampaignStatus, LeadStatus

    lead = Lead(
        name=data.lead_name.strip(),
        phone=v.normalized or data.phone.strip(),
        city=data.city,
        source="LIVE_DEMO",
        requirement=data.requirement,
        budget=data.budget,
        timeline=data.timeline,
        status=LeadStatus.NEW,
    )
    db.add(lead)
    db.flush()

    campaign = Campaign(
        name=data.campaign_name.strip(),
        status=CampaignStatus.ACTIVE,
        max_attempts=1,
    )
    db.add(campaign)
    db.flush()

    from app.models.campaign_lead import CampaignLead

    db.add(CampaignLead(campaign_id=campaign.id, lead_id=lead.id))
    db.flush()

    try:
        call = create_call(db, CallCreate(lead_id=lead.id, campaign_id=campaign.id))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        call = dispatch_call(db, call)
    except CallDispatchError as exc:
        db.refresh(call)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.refresh(call)
    return {
        "success": True,
        "call": {
            "id": call.id,
            "status": call.status.value,
            "provider": call.provider,
            "provider_call_id": call.provider_call_id,
            "phone_masked": mask_phone(call.phone_number),
        },
        "lead": {"id": lead.id, "name": lead.name},
    }


@router.post("/api/test-call/status")
def ui_call_status(call_id: int, db: Session = Depends(get_db)):
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    summary = db.scalar(select(CallSummary).where(CallSummary.call_id == call.id))
    return {
        "success": True,
        "call": {
            "id": call.id,
            "status": call.status.value if call.status else None,
            "outcome": call.outcome.value if call.outcome else None,
            "duration_seconds": call.duration_seconds,
            "recording_url": call.recording_url,
            "transcript_available": bool(call.transcript),
        },
        "qualification": (summary.qualification if summary and summary.qualification else None),
    }
