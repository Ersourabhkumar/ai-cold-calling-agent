"""Generic outbound-webhook CRM provider.

Works with any CRM that accepts an incoming JSON webhook (Zoho Deluge
webhooks, HubSpot workflows webhooks, custom endpoints, webhook catchers
feeding Google Sheets, ...). No per-CRM code needed.
"""

from __future__ import annotations

import json
import logging
import os
from urllib.request import Request, urlopen

from app.services.crm.base import CRMProvider

logger = logging.getLogger(__name__)


class WebhookCRMProvider(CRMProvider):
    name = "webhook"

    def __init__(self) -> None:
        self.url = os.getenv("CRM_WEBHOOK_URL")
        if not self.url:
            raise RuntimeError("CRM_WEBHOOK_URL is not configured")

    def push_call_result(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ai-cold-calling-agent/crm-sync",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                return {"synced": True, "status": response.status}
        except Exception as exc:
            raise RuntimeError(
                f"CRM webhook delivery failed: {exc}"
            ) from exc
