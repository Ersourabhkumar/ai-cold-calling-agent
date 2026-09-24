"""Default CRM provider: keep everything local, call nothing."""

from __future__ import annotations

from app.services.crm.base import CRMProvider


class NoOpCRMProvider(CRMProvider):
    name = "none"

    def push_call_result(self, payload: dict) -> dict:
        return {"synced": False, "reason": "crm-disabled"}
