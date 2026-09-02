from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.services.calling.provider import CallRequest, CallResult, CallingProvider


class PlivoCallingProvider(CallingProvider):
    """Production India telephony adapter using Plivo's Voice API.

    It is deliberately isolated from the rest of the application. Credentials
    and KYC-approved caller numbers are required before this provider can run.
    """

    def __init__(self) -> None:
        self.auth_id = os.getenv("PLIVO_AUTH_ID")
        self.auth_token = os.getenv("PLIVO_AUTH_TOKEN")
        self.from_number = os.getenv("PLIVO_PHONE_NUMBER")
        if not all((self.auth_id, self.auth_token, self.from_number)):
            raise RuntimeError(
                "PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, and PLIVO_PHONE_NUMBER must be configured"
            )

    def _request(self, url: str, data: dict[str, str] | None = None, method: str = "POST") -> dict:
        encoded = urlencode(data or {}).encode() if data is not None else None
        credentials = base64.b64encode(f"{self.auth_id}:{self.auth_token}".encode()).decode()
        request = Request(
            url,
            data=encoded,
            method=method,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed provider URL
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Plivo API request failed with status {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Plivo API request could not be completed") from exc

    def start_call(self, request: CallRequest) -> CallResult:
        base_url = request.webhook_url.rstrip("/")
        callback = f"{base_url}/webhooks/plivo/status?call_id={request.call_id}"
        response = self._request(
            f"https://api.plivo.com/v1/Account/{self.auth_id}/Call/",
            {
                "from": self.from_number,
                "to": request.phone_number,
                "answer_url": f"{base_url}/webhooks/plivo/answer?call_id={request.call_id}",
                "answer_method": "POST",
                "ring_url": callback,
                "ring_method": "POST",
                "hangup_url": callback,
                "hangup_method": "POST",
            },
        )
        provider_call_id = response.get("request_uuid")
        if not provider_call_id:
            raise RuntimeError("Plivo did not return a request UUID")
        return CallResult(provider="plivo", provider_call_id=provider_call_id, status="INITIATED")

    def hangup_call(self, provider_call_id: str) -> None:
        self._request(
            f"https://api.plivo.com/v1/Account/{self.auth_id}/Request/{provider_call_id}/",
            method="DELETE",
        )
