"""CRM integration layer.

Default provider is "none": everything stays local, zero external calls.
Set CRM_PROVIDER=webhook + CRM_WEBHOOK_URL to forward every completed call
(lead, outcome, qualification) to any CRM with an incoming webhook
(Zoho / HubSpot / custom / Sheets-catcher). Native per-CRM connectors can
subclass CRMProvider later without touching the call flow.
"""

from __future__ import annotations

import logging
import os

from app.services.crm.base import CRMProvider
from app.services.crm.none import NoOpCRMProvider

logger = logging.getLogger(__name__)


def get_crm_provider() -> CRMProvider:
    provider = (os.getenv("CRM_PROVIDER", "none") or "none").lower()
    if provider == "none":
        return NoOpCRMProvider()
    if provider == "webhook":
        from app.services.crm.webhook import WebhookCRMProvider

        return WebhookCRMProvider()
    raise ValueError(f"Unsupported CRM provider: {provider}")


def sync_call_to_crm(db, call_id: int) -> dict:
    """Push one completed call to the configured CRM (best effort)."""
    from app.models.call import Call

    provider = get_crm_provider()
    if isinstance(provider, NoOpCRMProvider):
        return {"synced": False, "reason": "crm-disabled"}

    call = db.get(Call, call_id)
    if call is None:
        return {"synced": False, "reason": "call not found"}

    lead = call.lead
    summary = call.summary
    qualification = dict(summary.qualification or {}) if summary else {}
    payload = {
        "event": "call.completed",
        "call_id": call.id,
        "lead_id": call.lead_id,
        "lead": {
            "name": lead.name if lead else None,
            "phone": lead.phone if lead else None,
        },
        "outcome": call.outcome.value if call.outcome else None,
        "duration_seconds": call.duration_seconds,
        "recording_url": call.recording_url,
        "qualification": qualification,
    }
    return provider.push_call_result(payload)
