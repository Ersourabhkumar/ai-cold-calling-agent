"""Tests for SarvamCallingProvider."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.calling.provider import CallRequest
from app.services.calling.sarvam_provider import SarvamCallingProvider


SARVAM_ENV = {
    "SARVAM_API_KEY": "sk_test_key",
    "SARVAM_ORG_ID": "org-test-123",
    "SARVAM_WORKSPACE_ID": "ws-test-456",
    "SARVAM_APP_ID": "TestApp-abc123",
    "SARVAM_APP_VERSION": "3",
    "SARVAM_CONNECTION_ID": "conn-test-789",
    "SARVAM_AGENT_PHONE_NUMBER": "+918040000000",
}


def _make_request(**overrides) -> CallRequest:
    defaults = {
        "phone_number": "+917665035514",
        "call_id": 1,
        "lead_id": 10,
        "campaign_id": 20,
        "webhook_url": "http://localhost:8000",
        "lead_context": {
            "name": "Rahul",
            "city": "Mumbai",
            "requirement": "2 BHK flat",
            "budget": "75 lakh",
            "timeline": "3 months",
        },
    }
    defaults.update(overrides)
    return CallRequest(**defaults)


class TestSarvamCallingProviderInit:
    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    def test_init_succeeds_with_all_config(self):
        provider = SarvamCallingProvider()
        assert provider.api_key == "sk_test_key"
        assert provider.org_id == "org-test-123"
        assert provider.app_id == "TestApp-abc123"

    @patch.dict(os.environ, {}, clear=True)
    def test_init_fails_without_api_key(self):
        with pytest.raises(RuntimeError, match="SARVAM_API_KEY"):
            SarvamCallingProvider()

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    def test_init_fails_without_org_id(self):
        env = {k: v for k, v in SARVAM_ENV.items() if k != "SARVAM_ORG_ID"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="SARVAM_ORG_ID"):
                SarvamCallingProvider()

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    def test_init_fails_without_app_id(self):
        env = {k: v for k, v in SARVAM_ENV.items() if k != "SARVAM_APP_ID"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="SARVAM_APP_ID"):
                SarvamCallingProvider()


class TestSarvamCallingProviderStartCall:
    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    @patch("app.services.calling.sarvam_provider.urlopen")
    def test_start_call_builds_correct_request(self, mock_urlopen):
        response_data = json.dumps({"attempt_id": "attempt-abc-123"}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        provider = SarvamCallingProvider()
        request = _make_request()
        result = provider.start_call(request)

        assert result.provider == "sarvam"
        assert result.provider_call_id == "attempt-abc-123"
        assert result.status == "INITIATED"
        assert result.metadata["attempt_id"] == "attempt-abc-123"

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.full_url == (
            "https://apps.sarvam.ai/api/outbounds/v1"
            "/orgs/org-test-123/workspaces/ws-test-456/outbounds"
        )
        assert req.method == "POST"
        assert req.get_header("X-api-key") == "sk_test_key"

        body = json.loads(req.data.decode())
        assert body["app_config"]["app_id"] == "TestApp-abc123"
        assert body["app_config"]["app_version"] == 3
        assert body["app_config"]["connection_config"]["connection_id"] == "conn-test-789"
        assert body["user_config"]["user_phone_number"] == "+917665035514"
        assert body["webhook_config"]["url"] == "http://localhost:8000/webhooks/sarvam/status"
        assert body["webhook_config"]["metadata"]["call_id"] == "1"
        assert body["webhook_config"]["metadata"]["lead_id"] == "10"
        assert body["app_config"]["agent_variables"]["customer_name"] == "Rahul"
        assert body["app_config"]["agent_variables"]["city"] == "Mumbai"

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    @patch("app.services.calling.sarvam_provider.urlopen")
    def test_start_call_builds_greeting_with_requirement(self, mock_urlopen):
        response_data = json.dumps({"attempt_id": "att-1"}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        provider = SarvamCallingProvider()
        request = _make_request()
        provider.start_call(request)

        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        greeting = body["app_config"]["app_overrides"]["initial_bot_message"]
        assert "Rahul" in greeting
        assert "2 bhk flat" in greeting.lower()

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    @patch("app.services.calling.sarvam_provider.urlopen")
    def test_start_call_builds_greeting_without_requirement(self, mock_urlopen):
        response_data = json.dumps({"attempt_id": "att-2"}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        provider = SarvamCallingProvider()
        request = _make_request(
            lead_context={"name": "", "city": "", "requirement": "", "budget": "", "timeline": ""}
        )
        provider.start_call(request)

        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        greeting = body["app_config"]["app_overrides"]["initial_bot_message"]
        assert "person who enquired" in greeting.lower()

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    def test_start_call_rejects_invalid_phone(self):
        provider = SarvamCallingProvider()
        request = _make_request(phone_number="invalid")
        with pytest.raises(RuntimeError, match="invalid phone number"):
            provider.start_call(request)

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    @patch("app.services.calling.sarvam_provider.urlopen")
    def test_start_call_raises_on_missing_attempt_id(self, mock_urlopen):
        response_data = json.dumps({}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        provider = SarvamCallingProvider()
        request = _make_request()
        with pytest.raises(RuntimeError, match="attempt_id"):
            provider.start_call(request)

    @patch.dict(os.environ, SARVAM_ENV, clear=False)
    def test_hangup_call_is_noop(self):
        provider = SarvamCallingProvider()
        provider.hangup_call("any-id")
