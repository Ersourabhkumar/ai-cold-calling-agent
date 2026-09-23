from __future__ import annotations

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.phone_validation import mask_phone, validate_phone
from app.services.calling.provider import (
    CallRequest,
    CallResult,
    CallingProvider,
)

logger = logging.getLogger(__name__)

# Verified Sarvam Instant Outbound API endpoint.
_SARVAM_OUTBOUND_URL_TEMPLATE = (
    "https://apps.sarvam.ai/api/outbounds/v1"
    "/orgs/{org_id}/workspaces/{workspace_id}/outbounds"
)

# Verified Sarvam Analytics API endpoints (for future use).
_SARVAM_TRANSCRIPT_URL_TEMPLATE = (
    "https://apps.sarvam.ai/api/analytics/v1"
    "/{org_id}/{workspace_id}/{app_id}/transcripts/{interaction_id}"
)
_SARVAM_RECORDING_URL_TEMPLATE = (
    "https://apps.sarvam.ai/api/analytics/v1"
    "/{org_id}/{workspace_id}/{app_id}/recordings/{interaction_id}"
)


def _redact_secrets(text: str) -> str:
    api_key = os.getenv("SARVAM_API_KEY") or ""
    if api_key:
        return text.replace(api_key, "[REDACTED]")
    return text


class SarvamCallingProvider(CallingProvider):
    """
    Sarvam Voice Agent outbound calling provider.

    Uses the Sarvam Instant Outbound API to place calls.
    Sarvam handles the entire voice conversation.
    Our application remains responsible for:
    - lead
    - campaign
    - call record
    - call lifecycle
    - CRM data enrichment via webhook

    Verified API docs:
    - https://docs.sarvam.ai/conversations/api/instant-outbound/create
    - https://docs.sarvam.ai/conversations/api/instant-outbound/webhook-payload
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("SARVAM_API_KEY")
        self.org_id = os.getenv("SARVAM_ORG_ID")
        self.workspace_id = os.getenv("SARVAM_WORKSPACE_ID")
        self.app_id = os.getenv("SARVAM_APP_ID")
        self.app_version = os.getenv("SARVAM_APP_VERSION", "1")
        self.connection_id = os.getenv("SARVAM_CONNECTION_ID")
        self.agent_phone_number = os.getenv("SARVAM_AGENT_PHONE_NUMBER")

        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured")
        if not self.org_id:
            raise RuntimeError("SARVAM_ORG_ID is not configured")
        if not self.workspace_id:
            raise RuntimeError("SARVAM_WORKSPACE_ID is not configured")
        if not self.app_id:
            raise RuntimeError("SARVAM_APP_ID is not configured")
        if not self.connection_id:
            raise RuntimeError("SARVAM_CONNECTION_ID is not configured")
        if not self.agent_phone_number:
            raise RuntimeError("SARVAM_AGENT_PHONE_NUMBER is not configured")

        self._validated = False

    def _request(
        self,
        url: str,
        payload: dict | None = None,
        *,
        method: str = "POST",
    ) -> dict:
        body = (
            json.dumps(payload).encode("utf-8")
            if payload is not None and method == "POST"
            else None
        )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-Key": self.api_key,
        }

        request = Request(
            url,
            data=body,
            method=method,
            headers=headers,
        )

        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)

        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Sarvam API request failed "
                f"with status {exc.code}: {_redact_secrets(error_body)}"
            ) from exc

        except URLError as exc:
            raise RuntimeError(
                f"Sarvam API request could not be completed: {exc.reason}"
            ) from exc

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Sarvam returned an invalid JSON response"
            ) from exc

    def _build_outbound_url(self) -> str:
        return _SARVAM_OUTBOUND_URL_TEMPLATE.format(
            org_id=self.org_id,
            workspace_id=self.workspace_id,
        )

    def _build_webhook_url(self, request: CallRequest) -> str:
        base = request.webhook_url.rstrip("/")
        return f"{base}/webhooks/sarvam/status"

    def _build_agent_variables(self, request: CallRequest) -> dict:
        lead = request.lead_context or {}
        return {
            "call_id": str(request.call_id),
            "lead_id": str(request.lead_id),
            "campaign_id": str(request.campaign_id),
            "customer_name": (lead.get("name") or "").strip(),
            "city": (lead.get("city") or "").strip(),
            "requirement": (lead.get("requirement") or "").strip(),
            "budget": (lead.get("budget") or "").strip(),
            "timeline": (lead.get("timeline") or "").strip(),
        }

    def _build_initial_bot_message(self, request: CallRequest) -> str:
        lead = request.lead_context or {}
        name = (lead.get("name") or "").strip() or "the person who enquired"
        requirement = (lead.get("requirement") or "").strip()

        if requirement:
            return (
                f"Hello, am I speaking with {name}? "
                f"This is a quick call from our real estate team about your "
                f"enquiry regarding a {requirement.lower()}. "
                "Is now a convenient time for a brief conversation?"
            )
        return (
            "Hello, am I speaking with the person who enquired about a "
            "property? This is a quick call from our real estate team. "
            "Is now a convenient time for a brief conversation?"
        )

    def _get_app_version(self) -> int:
        try:
            return max(1, int(self.app_version))
        except (TypeError, ValueError):
            return 1

    def start_call(self, request: CallRequest) -> CallResult:
        validation = validate_phone(request.phone_number)
        if not validation.valid:
            raise RuntimeError(
                f"Refusing to dial invalid phone number "
                f"{mask_phone(request.phone_number)}: {validation.reason}"
            )
        phone_number = validation.normalized or request.phone_number

        logger.info(
            "Placing Sarvam outbound call for %s (call_id=%s)",
            mask_phone(phone_number),
            request.call_id,
        )

        webhook_url = self._build_webhook_url(request)
        agent_variables = self._build_agent_variables(request)
        initial_bot_message = self._build_initial_bot_message(request)

        payload = {
            "app_config": {
                "app_id": self.app_id,
                "app_version": self._get_app_version(),
                "connection_config": {
                    "connection_id": self.connection_id,
                    "agent_phone_number": self.agent_phone_number,
                },
                "agent_variables": agent_variables,
                "app_overrides": {
                    "initial_bot_message": initial_bot_message,
                },
            },
            "user_config": {
                "user_phone_number": phone_number,
            },
            "webhook_config": {
                "url": webhook_url,
                "metadata": {
                    "call_id": str(request.call_id),
                    "lead_id": str(request.lead_id),
                    "campaign_id": str(request.campaign_id),
                },
            },
        }

        url = self._build_outbound_url()

        logger.info(
            "Sarvam outbound request: url=%s, app_id=%s, phone=%s",
            url,
            self.app_id,
            mask_phone(phone_number),
        )

        response = self._request(url, payload)

        attempt_id = response.get("attempt_id")
        if not attempt_id:
            raise RuntimeError(
                f"Sarvam API did not return an attempt_id: "
                f"{_redact_secrets(json.dumps(response))}"
            )

        logger.info(
            "Sarvam outbound call accepted: attempt_id=%s, call_id=%s",
            attempt_id,
            request.call_id,
        )

        return CallResult(
            provider="sarvam",
            provider_call_id=str(attempt_id),
            status="INITIATED",
            metadata={
                "attempt_id": str(attempt_id),
                "app_id": self.app_id,
            },
        )

    def hangup_call(self, provider_call_id: str) -> None:
        # Sarvam manages the live call lifecycle.
        # This method remains part of our provider abstraction.
        logger.info(
            "Sarvam hangup requested for attempt_id=%s (no-op)",
            provider_call_id,
        )
        return None

    def fetch_transcript(self, interaction_id: str) -> dict | None:
        """Fetch transcript from Sarvam Analytics API.

        Verified endpoint:
        GET /api/analytics/v1/{org_id}/{workspace_id}/{app_id}/transcripts/{interaction_id}
        """
        url = _SARVAM_TRANSCRIPT_URL_TEMPLATE.format(
            org_id=self.org_id,
            workspace_id=self.workspace_id,
            app_id=self.app_id,
            interaction_id=interaction_id,
        )
        try:
            return self._request(url, method="GET")
        except RuntimeError:
            logger.warning(
                "Failed to fetch Sarvam transcript for interaction_id=%s",
                interaction_id,
            )
            return None

    def fetch_recording(self, interaction_id: str) -> dict | None:
        """Fetch recording from Sarvam Analytics API.

        Verified endpoint:
        GET /api/analytics/v1/{org_id}/{workspace_id}/{app_id}/recordings/{interaction_id}
        """
        url = _SARVAM_RECORDING_URL_TEMPLATE.format(
            org_id=self.org_id,
            workspace_id=self.workspace_id,
            app_id=self.app_id,
            interaction_id=interaction_id,
        )
        try:
            return self._request(url, method="GET")
        except RuntimeError:
            logger.warning(
                "Failed to fetch Sarvam recording for interaction_id=%s",
                interaction_id,
            )
            return None
