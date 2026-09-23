from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.sarvam_webhook_service import process_sarvam_webhook

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/sarvam/status")
async def sarvam_status_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle Sarvam Voice Agent webhook callbacks.

    Verified webhook schema:
    https://docs.sarvam.ai/conversations/api/instant-outbound/webhook-payload

    Sarvam sends one POST per call attempt with status, transcript,
    and agent output variables.
    """
    raw = await request.body()
    body: dict | list = {}

    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, (dict, list)):
                body = parsed
        except (TypeError, ValueError):
            pass

    if isinstance(body, list):
        results = []
        for item in body:
            if not isinstance(item, dict):
                continue
            results.append(process_sarvam_webhook(db, item))
        return {
            "success": True,
            "handled_count": sum(1 for r in results if r.get("handled")),
            "results": results,
        }

    result = process_sarvam_webhook(db, body)

    return {
        "success": result.get("success", False),
        "handled": result.get("handled", False),
        "call_id": result.get("call_id"),
        "status": result.get("status"),
        "message": result.get("message"),
        "enriched": result.get("enriched"),
        "duplicate": result.get("duplicate", False),
    }
