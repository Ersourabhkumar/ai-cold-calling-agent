from __future__ import annotations

import os

from twilio.rest import Client

from app.services.calling.provider import (
    CallRequest,
    CallResult,
    CallingProvider,
)


class TwilioCallingProvider(CallingProvider):
    """
    Production Twilio voice provider.
    """

    def __init__(self) -> None:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")

        if not account_sid:
            raise RuntimeError(
                "TWILIO_ACCOUNT_SID is not configured"
            )

        if not auth_token:
            raise RuntimeError(
                "TWILIO_AUTH_TOKEN is not configured"
            )

        if not from_number:
            raise RuntimeError(
                "TWILIO_PHONE_NUMBER is not configured"
            )

        self.client = Client(
            account_sid,
            auth_token,
        )

        self.from_number = from_number

    def start_call(
        self,
        request: CallRequest,
    ) -> CallResult:

        base_url = request.webhook_url.rstrip("/")

        twiml_url = (
            f"{base_url}/api/calls/twiml"
            f"?call_id={request.call_id}"
        )

        webhook_url = (
            f"{base_url}/api/calls/webhook"
            f"?call_id={request.call_id}"
        )

        call = self.client.calls.create(
            to=request.phone_number,
            from_=self.from_number,
            url=twiml_url,
            method="POST",
            status_callback=webhook_url,
            status_callback_method="POST",
            status_callback_event=[
                "initiated",
                "ringing",
                "answered",
                "completed",
            ],
        )

        return CallResult(
            provider="twilio",
            provider_call_id=call.sid,
            status="INITIATED",
        )

    def hangup_call(
        self,
        provider_call_id: str,
    ) -> None:

        self.client.calls(
            provider_call_id
        ).update(
            status="completed"
        )
