from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.phone_validation import mask_phone, validate_phone
from app.services.calling.provider import (
    CallRequest,
    CallResult,
    CallingProvider,
)

logger = logging.getLogger(__name__)

# Verified working Tabbly endpoints (documented at tabbly.gitbook.io/tabbly-docs).
_TABBLY_AGENTS_URL = "https://www.tabbly.io/api/get-agents"
_TABBLY_ENDPOINTS_URL = "https://www.tabbly.io/dashboard/agents/endpoints"
# Dialing window length. Long enough that Tabbly's scheduler ticks will not
# miss the contact.
_TABBLY_CALL_WINDOW_HOURS = 6
# Tabbly's scheduler only picks up campaigns whose start time is in the
# future ("End time earlier than start time implies next day" per docs).
# Schedule the window a few minutes ahead of creation so the scheduler has a
# concrete begin event, while keeping the window long enough to cover ticks.
_TABBLY_START_FUTURE_MINUTES = 5
# Tabbly expects wall-clock HH:MM plus a time zone; the account is IST.
_TABBLY_TIME_ZONE = "IST"
_IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


def _normalize_phone(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _redact_secrets(text: str) -> str:
    api_key = os.getenv("TABBLY_API_KEY") or os.getenv("TABBLY_AGENT_ID") or ""
    if api_key:
        return text.replace(api_key, "[REDACTED]")
    return text


class TabblyCallingProvider(CallingProvider):
    """
    Tabbly outbound calling provider.

    Tabbly handles the actual AI voice conversation.
    Our application remains responsible for:
    - lead
    - campaign
    - call record
    - call lifecycle
    - CRM data

    The documented Tabbly outbound flow is campaign-based:
    create-campaign (Active by default) -> add-campaign-contacts.
    There is no documented single-number "dial now" endpoint, so each
    dispatched call is backed by its own campaign containing one contact.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("TABBLY_API_KEY")
        self.agent_id = (
            os.getenv("TABBLY_AGENT_ID")
            or os.getenv("TABLLY_AGENT_ID")
        )
        self.expected_phone = (
            os.getenv("TABBLY_PHONE_NUMBER")
            or os.getenv("TABLLY_PHONE_NUMBER")
        )
        self.organization_id = (
            os.getenv("TABBLY_ORGANIZATION_ID")
            or os.getenv("TABLLY_ORGANIZATION_ID")
        )

        if not self.api_key:
            raise RuntimeError(
                "TABBLY_API_KEY is not configured"
            )

        if not self.agent_id:
            raise RuntimeError(
                "TABBLY_AGENT_ID is not configured"
            )

        self._validated = False

    def _request(
        self,
        url: str,
        payload: dict,
        *,
        method: str = "POST",
    ) -> dict:
        body = json.dumps(
            {
                "api_key": self.api_key,
                **payload,
            }
        ).encode("utf-8") if method == "POST" else None

        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)

        except HTTPError as exc:
            error_body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                f"Tabbly API request failed "
                f"with status {exc.code}: {_redact_secrets(error_body)}"
            ) from exc

        except URLError as exc:
            raise RuntimeError(
                f"Tabbly API request could not be completed: {exc.reason}"
            ) from exc

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Tabbly returned an invalid JSON response"
            ) from exc

    def _get_agents(self) -> list[dict]:
        response = self._request(_TABBLY_AGENTS_URL, {})

        if response.get("status") == "error":
            raise RuntimeError(
                _redact_secrets(
                    response.get("message", "Tabbly get-agents failed")
                )
            )

        agents = response.get("data") or response.get("agents") or []

        if not isinstance(agents, list):
            raise RuntimeError(
                "Tabbly get-agents returned an unexpected response"
            )

        return agents

    def validate_config(self) -> None:
        """
        Verify the configured Tabbly agent and phone number exist.

        Called once per process; network result is cached.
        """
        if self._validated:
            return

        agents = self._get_agents()

        agent = next(
            (
                item
                for item in agents
                if str(item.get("id")) == str(self.agent_id)
            ),
            None,
        )

        if agent is None:
            available = [
                str(item.get("id"))
                for item in agents
                if item.get("id") is not None
            ]
            raise RuntimeError(
                f"Tabbly agent id {self.agent_id} was not found. "
                f"Available agent ids: {', '.join(available) or 'none'}."
            )

        agent_phone = agent.get("phone_number")

        if self.expected_phone and agent_phone and (
            _normalize_phone(str(agent_phone))
            != _normalize_phone(self.expected_phone)
        ):
            raise RuntimeError(
                f"Tabbly agent {self.agent_id} phone mismatch: "
                f"expected {self.expected_phone}, "
                f"agent resolves to {agent_phone}. "
                f"Update TABBLY_PHONE_NUMBER to match the Tabbly account."
            )

        self._validated = True

    def start_call(
        self,
        request: CallRequest,
    ) -> CallResult:
        self.validate_config()

        validation = validate_phone(request.phone_number)
        if not validation.valid:
            raise RuntimeError(
                f"Refusing to dial invalid phone number "
                f"{mask_phone(request.phone_number)}: {validation.reason}"
            )
        phone_number = validation.normalized or request.phone_number
        logger.info(
            "Dialing real Tabbly call for %s (call_id=%s)",
            mask_phone(phone_number),
            request.call_id,
        )

        now = datetime.now(timezone.utc)

        try:
            future_minutes = int(
                os.getenv(
                    "TABBLY_START_FUTURE_MINUTES",
                    _TABBLY_START_FUTURE_MINUTES,
                )
            )
        except (TypeError, ValueError):
            future_minutes = _TABBLY_START_FUTURE_MINUTES

        future_minutes = max(1, min(60, future_minutes))

        start_dt = now + timedelta(minutes=future_minutes)
        window_end = start_dt + timedelta(hours=_TABBLY_CALL_WINDOW_HOURS)

        logger.info(
            "Scheduling Tabbly dial window %s -> %s "
            "(start in +%s minutes, zone=%s)",
            start_dt.isoformat(),
            window_end.isoformat(),
            future_minutes,
            _TABBLY_TIME_ZONE,
        )

        lead = request.lead_context or {}
        name = (lead.get("name") or "").strip() or "the person who enquired"
        requirement = (lead.get("requirement") or "").strip()
        budget = (lead.get("budget") or "").strip()
        timeline = (lead.get("timeline") or "").strip()
        city = (lead.get("city") or "").strip()

        known_facts = [
            fact
            for fact in (
                f"Requirement: {requirement}" if requirement else None,
                f"Budget: {budget}" if budget else None,
                f"Timeline: {timeline}" if timeline else None,
                f"Preferred location: {city}" if city else None,
            )
            if fact
        ]

        if requirement:
            custom_first_line = (
                f"Hello, am I speaking with {name}? "
                f"This is a quick call from our real estate team about your "
                f"enquiry regarding a {requirement.lower()}. "
                "Is now a convenient time for a brief conversation?"
            )
        else:
            custom_first_line = (
                "Hello, am I speaking with the person who enquired about a "
                "property? This is a quick call from our real estate team. "
                "Is now a convenient time for a brief conversation?"
            )

        custom_instruction = (
            "You are a real-estate lead qualification assistant. "
            "You already know what this customer enquired about from our "
            "system, so sound informed instead of asking blind questions:"
        )
        if known_facts:
            custom_instruction += (
                "\nKnown information about this customer:\n"
                + "\n".join(f"- {fact}" for fact in known_facts)
            )
        custom_instruction += (
            "\nAfter the first line and a short greeting, qualify the lead "
            "naturally by asking one question at a time: "
            "1) confirm what they are looking for, building on the known "
            "requirement and only asking to fill gaps, "
            "2) the property type (flat, villa, plot) and BHK, "
            "3) preferred location, "
            "4) approximate budget in lakhs, "
            "5) buying timeline in months, "
            "6) purpose (self use or investment), "
            "and at the end ask whether they want a property visit scheduled "
            "or a callback. "
            "Listen carefully to the customer, acknowledge their concern "
            "briefly in your own words, answer their questions concisely "
            "without repeating yourself, and keep everything short and "
            "conversational. "
            "At the end of the call, write a JSON summary in call_json_output "
            "with keys: property_type, bhk, location, budget, budget_amount, "
            "timeline, purpose, interested (true/false), appointment_requested "
            "(true/false), callback_requested (true/false), missing_info."
        )

        campaign_name = f"call-{request.call_id}"

        campaign_response = self._request(
            _TABBLY_ENDPOINTS_URL + "/create-campaign",
            {
                "campaign_name": campaign_name,
                "agent_id": int(self.agent_id),
                "start_time": (
                    start_dt.astimezone(_IST_OFFSET).strftime("%H:%M")
                ),
                "end_time": (
                    window_end.astimezone(_IST_OFFSET).strftime("%H:%M")
                ),
                "time_zone": _TABBLY_TIME_ZONE,
                "custom_first_line": custom_first_line,
                "created_by": "ai-cold-calling-agent",
            },
        )

        if campaign_response.get("status") == "error":
            raise RuntimeError(
                _redact_secrets(
                    campaign_response.get(
                        "message",
                        "Tabbly create-campaign failed",
                    )
                )
            )

        campaign_data = (
            campaign_response.get("data")
            or campaign_response
        )

        campaign_id = campaign_data.get("campaign_id")

        if not campaign_id:
            raise RuntimeError(
                f"Tabbly create-campaign did not return a campaign ID"
            )

        contact_response = self._request(
            _TABBLY_ENDPOINTS_URL + "/add-campaign-contacts",
            {
                "phone_number": phone_number,
                "campaign_id": int(campaign_id),
                "participant_identity": campaign_name,
                "use_agent_id": int(self.agent_id),
                "created_by": "ai-cold-calling-agent",
                "custom_first_line": custom_first_line,
                "custom_instruction": custom_instruction,
                "sip_call_id": "",
                "called": 0,
                "call_counter": 0,
                "custom_identifiers": (
                    f"call_id={request.call_id},"
                    f"lead_id={request.lead_id},"
                    f"campaign_id={request.campaign_id}"
                ),
            },
        )

        if contact_response.get("status") != "success":
            raise RuntimeError(
                _redact_secrets(
                    contact_response.get(
                        "message",
                        "Tabbly add-campaign-contacts failed",
                    )
                )
            )

        contact_id = contact_response.get("id")

        return CallResult(
            provider="tabbly",
            provider_call_id=str(campaign_id),
            status="INITIATED",
            metadata={
                "tabbly_campaign_id": str(campaign_id),
                "tabbly_contact_id": str(contact_id) if contact_id else None,
                "tabbly_agent_id": str(self.agent_id),
                "custom_identifiers": (
                    f"call_id={request.call_id},"
                    f"lead_id={request.lead_id},"
                    f"campaign_id={request.campaign_id}"
                ),
            },
        )

    def ensure_campaign_active(
        self,
        campaign_id,
        *,
        extend_hours: int = _TABBLY_CALL_WINDOW_HOURS,
    ) -> bool:
        """Re-activate a Tabbly campaign and extend its dialing window.

        Tabbly has no documented per-contact "dial now" endpoint, so the dialer
        runs on the campaign schedule. This best-effort helper flips the
        campaign to Active and pushes the end time forward so contacts already
        on the campaign get dialled.

        Requires TABBLY_ORGANIZATION_ID. Returns False when the org id or the
        campaign id is missing, or when update-campaign is unavailable.
        """
        if not self.organization_id:
            send_org_id = os.getenv(
                "TABBLY_ORGANIZATION_ID"
            ) or os.getenv("TABLLY_ORGANIZATION_ID")
            if not send_org_id:
                logger.warning(
                    "Cannot re-activate Tabbly campaign %s without "
                    "TABBLY_ORGANIZATION_ID.",
                    campaign_id,
                )
                return False
            self.organization_id = str(send_org_id)

        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=max(1, int(extend_hours)))

        payload: dict = {
            "id": int(campaign_id),
            "organization_id": self.organization_id,
            "current_status": "Active",
            "start_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end.strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            response = self._request(
                _TABBLY_ENDPOINTS_URL + "/update-campaign",
                payload,
            )
        except RuntimeError:
            logger.exception(
                "Tabbly update-campaign failed for campaign %s",
                campaign_id,
            )
            return False

        if isinstance(response, dict) and response.get("status") == "error":
            logger.warning(
                "Tabbly update-campaign reported an error for campaign %s: %s",
                campaign_id,
                _redact_secrets(str(response.get("message"))),
            )
            return False

        logger.info(
            "Tabbly campaign %s re-activated until %s",
            campaign_id,
            end.isoformat(),
        )
        return True

    @staticmethod
    def webhook_payload(log: dict) -> dict | None:
        """Map a call-log row to a status-webhook style payload for the sink.

        Returns None when the log carries no call status (e.g. a parked
        contact that was never dialled).
        """
        if not isinstance(log, dict):
            return None

        status_value = log.get("call_status") or log.get("status")
        if not status_value:
            return None

        payload: dict = {
            "call_status": str(status_value),
            "call_duration": log.get("call_duration"),
            "call_recording": log.get("call_recording"),
            "call_transcript": log.get("call_transcript"),
            "record_id": log.get("id"),
            "called_time": log.get("called_time"),
            "called_to": log.get("called_to"),
            "call_sentiment": log.get("call_sentiment"),
            "call_json_output": log.get("call_json_output"),
            "call_summary": log.get("call_summary"),
        }

        custom_identifiers = log.get("custom_identifiers")
        if custom_identifiers:
            payload["custom_identifiers"] = custom_identifiers
        elif log.get("campaign_id"):
            payload["campaign_id"] = str(log["campaign_id"])

        # Drop empty fields so the flexible webhook parser stays tidy.
        return {k: v for k, v in payload.items() if v not in (None, "")}

    def get_call_logs(self, limit: int = 50) -> list[dict]:
        """
        Fetch recent Tabbly call logs via call-logs-v2.

        Requires TABBLY_ORGANIZATION_ID. Raises a clear error otherwise.
        """
        if not self.organization_id:
            raise RuntimeError(
                "TABBLY_ORGANIZATION_ID is required to fetch Tabbly call logs"
            )

        url = (
            f"{_TABBLY_ENDPOINTS_URL}/call-logs-v2?"
            f"api_key={self.api_key}"
            f"&organization_id={self.organization_id}"
            f"&limit={int(limit)}"
        )

        response = self._request(url, {}, method="GET")

        if response.get("status") == "error":
            raise RuntimeError(
                _redact_secrets(
                    response.get("message", "Tabbly call-logs failed")
                )
            )

        data = response.get("data") or []
        return data if isinstance(data, list) else []

    def hangup_call(
        self,
        provider_call_id: str,
    ) -> None:
        # Tabbly currently manages the live call lifecycle.
        # This method remains part of our provider abstraction.
        return None