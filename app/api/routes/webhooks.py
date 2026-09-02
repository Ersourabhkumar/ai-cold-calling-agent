from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.enums import CallStatus
from app.services.ai.conversation import process_customer_message
from app.services.call_lifecycle import transition_call
from app.services.call_service import get_call
from app.services.tabbly_webhook_service import process_tabbly_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


PLIVO_STATUS_MAP = {
    "ringing": CallStatus.RINGING,
    "in-progress": CallStatus.IN_PROGRESS,
    "answered": CallStatus.ANSWERED,
    "completed": CallStatus.COMPLETED,
    "busy": CallStatus.BUSY,
    "no-answer": CallStatus.NO_ANSWER,
    "failed": CallStatus.FAILED,
    "cancelled": CallStatus.CANCELLED,
}


def _verify_plivo_signature(
    request: Request,
    form: dict[str, str],
) -> None:
    if os.getenv("CALLING_MODE", "mock").lower() != "production":
        return

    token = os.getenv("PLIVO_AUTH_TOKEN")
    signature = request.headers.get("X-Plivo-Signature-V3", "")
    nonce = request.headers.get("X-Plivo-Signature-V3-Nonce", "")

    if not token or not signature or not nonce:
        raise HTTPException(
            status_code=403,
            detail="Missing Plivo webhook signature",
        )

    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    url = f"{base_url}{request.url.path}"

    if request.url.query:
        url = f"{url}?{request.url.query}"

    signed_params = "".join(
        f"{key}{form[key]}"
        for key in sorted(form)
    )

    expected = hmac.new(
        token.encode(),
        f"{url}{signed_params}{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()

    signatures = [
        value.strip()
        for value in signature.split(",")
    ]

    if not any(
        hmac.compare_digest(expected, value)
        for value in signatures
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid Plivo webhook signature",
        )


def _verify_tabbly_webhook(
    request: Request,
    body: dict,
) -> None:
    """
    Validate an optional Tabbly webhook secret.

    Tabbly does not publicly document webhook signatures, so this is opt-in.
    When TABBLY_WEBHOOK_SECRET is configured the request must present it
    (header or JSON body); otherwise a production warning is logged.
    """
    secret = os.getenv("TABBLY_WEBHOOK_SECRET")

    if not secret:
        if os.getenv("CALLING_MODE", "mock").lower() == "production":
            logger.warning(
                "Tabbly webhook accepted without signature validation; "
                "set TABBLY_WEBHOOK_SECRET to require one."
            )
        return

    presented = (
        request.headers.get("X-Tabbly-Signature", "")
        or request.headers.get("X-Webhook-Signature", "")
        or str(body.get("signature") or body.get("webhook_secret") or "")
    ).strip()

    if not presented or not hmac.compare_digest(presented, secret):
        raise HTTPException(
            status_code=403,
            detail="Invalid Tabbly webhook signature",
        )


@router.post("/tabbly/status")
async def tabbly_status_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw = await request.body()
    body: dict | list = {}

    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, (dict, list)):
                body = parsed
        except (TypeError, ValueError):
            form_data = await request.form()
            body = {
                key: str(value)
                for key, value in form_data.items()
            }

    if isinstance(body, list):
        results = []
        for item in body:
            if not isinstance(item, dict):
                continue
            _verify_tabbly_webhook(request, item)
            results.append(process_tabbly_webhook(db, item))
        return {
            "success": True,
            "handled_count": sum(1 for r in results if r.get("handled")),
            "results": results,
        }

    _verify_tabbly_webhook(request, body)
    result = process_tabbly_webhook(db, body)

    return {
        "success": result.get("success", False),
        "handled": result.get("handled", False),
        "call_id": result.get("call_id"),
        "status": result.get("status"),
        "message": result.get("message"),
        "enriched": result.get("enriched"),
    }


@router.post("/plivo/status")
async def plivo_status_webhook(
    call_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form_data = await request.form()

    form = {
        key: str(value)
        for key, value in form_data.items()
    }

    _verify_plivo_signature(request, form)

    call = get_call(db, call_id)

    if call is None:
        raise HTTPException(
            status_code=404,
            detail="Call not found",
        )

    raw_status = (
        form.get("CallStatus", "")
        .lower()
        .strip()
    )

    status = PLIVO_STATUS_MAP.get(raw_status)

    if status is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Plivo status: {raw_status}",
        )

    provider_call_id = form.get("CallUUID")

    event_id = (
        f"{provider_call_id}:{raw_status}:{form.get('EndTime', '')}"
        if provider_call_id
        else None
    )

    try:
        updated_call, _ = transition_call(
            db,
            call,
            status,
            provider="plivo",
            provider_event_id=event_id,
            payload={
                "source": "plivo",
                "status": raw_status,
                "provider_call_uuid": provider_call_id,
            },
        )

        return {
            "success": True,
            "call_id": updated_call.id,
            "status": updated_call.status.value,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/plivo/answer")
async def plivo_answer_webhook(
    call_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = await request.form()

    call = get_call(db, call_id)

    if call is None:
        raise HTTPException(
            status_code=404,
            detail="Call not found",
        )

    public_base_url = os.getenv(
        "PUBLIC_BASE_URL",
        "http://localhost:8000",
    ).rstrip("/")

    speech_url = (
        f"{public_base_url}/webhooks/plivo/speech"
        f"?call_id={call_id}"
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>

    <Speak language="en-IN">
        Hello, this is the AI assistant calling about your inquiry.
        Is now a convenient time for a brief conversation?
    </Speak>

    <GetInput
        action="{speech_url}"
        method="POST"
        inputType="speech"
        executionTimeout="10"
        speechEndTimeout="2"
    >
        <Speak language="en-IN">
            Please tell me how I can help you.
        </Speak>
    </GetInput>

    <Speak language="en-IN">
        I did not hear your response. Thank you for your time.
    </Speak>

    <Hangup/>

</Response>
"""

    return Response(
        content=xml,
        media_type="application/xml",
    )


@router.post("/plivo/speech")
async def plivo_speech_webhook(
    call_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form_data = await request.form()

    form = {
        key: str(value)
        for key, value in form_data.items()
    }

    _verify_plivo_signature(request, form)

    call = get_call(db, call_id)

    if call is None:
        raise HTTPException(
            status_code=404,
            detail="Call not found",
        )

    customer_text = (
        form.get("Speech")
        or form.get("speech")
        or ""
    ).strip()

    public_base_url = os.getenv(
        "PUBLIC_BASE_URL",
        "http://localhost:8000",
    ).rstrip("/")

    speech_url = (
        f"{public_base_url}/webhooks/plivo/speech"
        f"?call_id={call_id}"
    )

    if not customer_text:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>

    <Speak language="en-IN">
        Sorry, I could not understand that. Please try again.
    </Speak>

    <GetInput
        action="{speech_url}"
        method="POST"
        inputType="speech"
        executionTimeout="10"
        speechEndTimeout="2"
    />

</Response>
"""

        return Response(
            content=xml,
            media_type="application/xml",
        )

    try:
        result = process_customer_message(
            db,
            call,
            customer_text,
        )

        db.commit()
        db.refresh(call)

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    safe_reply = (
        result.caller_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>

    <Speak language="en-IN">
        {safe_reply}
    </Speak>

    <GetInput
        action="{speech_url}"
        method="POST"
        inputType="speech"
        executionTimeout="10"
        speechEndTimeout="2"
    >
        <Speak language="en-IN">
            Please continue.
        </Speak>
    </GetInput>

</Response>
"""

    return Response(
        content=xml,
        media_type="application/xml",
    )