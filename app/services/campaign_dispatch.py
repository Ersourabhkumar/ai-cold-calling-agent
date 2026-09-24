"""Bulk-dispatch all pending leads of a campaign.

Designed for variable daily volumes: preview with dry_run first, then dial
with an explicit cap. Per-lead guards (DO_NOT_CALL, max attempts, inactive
campaign) are enforced by reusing create_call/dispatch_call, so a single bad
lead never blocks the rest of the batch.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.campaign_lead import CampaignLead
from app.models.enums import LeadStatus
from app.models.lead import Lead
from app.schemas.call import CallCreate
from app.services.call_dispatcher import CallDispatchError, dispatch_call
from app.services.call_service import create_call
from app.services.campaign_lead_service import get_campaign_leads

logger = logging.getLogger(__name__)


def _skip_reason(
    campaign: Campaign,
    campaign_lead: CampaignLead,
    lead: Lead | None,
) -> str | None:
    if lead is None:
        return "lead missing"
    if lead.status == LeadStatus.DO_NOT_CALL:
        return "DO_NOT_CALL"
    if campaign_lead.attempt_count >= campaign.max_attempts:
        return "max attempts reached"
    return None


def dispatch_campaign(
    db: Session,
    campaign_id: int,
    *,
    max_calls: int | None = 50,
    dry_run: bool = True,
) -> dict:
    """Dispatch pending campaign leads, sequentially with a cap.

    dry_run=True performs zero writes and only reports who is eligible.
    Live mode creates one call per eligible lead (up to max_calls) and
    dispatches it through the configured provider; per-lead failures are
    collected, never raised.
    """
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError("Campaign not found")
    if campaign.status.value != "ACTIVE":
        raise ValueError("Campaign is not active")

    eligible: list[Lead] = []
    skipped: list[dict] = []
    for campaign_lead in get_campaign_leads(db, campaign_id):
        lead = db.get(Lead, campaign_lead.lead_id)
        reason = _skip_reason(campaign, campaign_lead, lead)
        if reason is None and lead is not None:
            eligible.append(lead)
        else:
            skipped.append(
                {"lead_id": campaign_lead.lead_id, "reason": reason or "unknown"}
            )

    result: dict = {
        "campaign_id": campaign.id,
        "dry_run": dry_run,
        "eligible": len(eligible),
        "dispatched": [],
        "skipped": skipped,
        "failed": [],
    }
    if dry_run:
        return result

    limit = max_calls if max_calls is not None else len(eligible)
    for lead in eligible[:limit]:
        try:
            call = create_call(
                db, CallCreate(lead_id=lead.id, campaign_id=campaign.id)
            )
            call = dispatch_call(db, call)
            result["dispatched"].append(
                {
                    "lead_id": lead.id,
                    "call_id": call.id,
                    "status": call.status.value,
                }
            )
        except (ValueError, CallDispatchError) as exc:
            db.rollback()
            logger.warning(
                "Bulk dispatch skipped lead %s: %s", lead.id, exc
            )
            result["failed"].append(
                {"lead_id": lead.id, "reason": str(exc)[:300]}
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Bulk dispatch failed for lead %s", lead.id)
            result["failed"].append(
                {"lead_id": lead.id, "reason": str(exc)[:300]}
            )
    return result
