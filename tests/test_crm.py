"""Tests for the CRM integration layer (defaults to local-only)."""

from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.call import Call
from app.models.enums import CallStatus, LeadStatus
from app.models.lead import Lead
from app.services.crm import get_crm_provider, sync_call_to_crm
from app.services.crm.none import NoOpCRMProvider


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_default_provider_is_noop(monkeypatch):
    monkeypatch.delenv("CRM_PROVIDER", raising=False)
    provider = get_crm_provider()
    assert isinstance(provider, NoOpCRMProvider)
    assert provider.push_call_result({})["synced"] is False


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "salesforce")
    with pytest.raises(ValueError):
        get_crm_provider()


def test_webhook_provider_needs_url(monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "webhook")
    monkeypatch.delenv("CRM_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError):
        get_crm_provider()


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_webhook_push_posts_json(monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "webhook")
    monkeypatch.setenv("CRM_WEBHOOK_URL", "https://crm.test/hook")

    captured: dict = {}

    def _fake_urlopen(request, timeout=10):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr("app.services.crm.webhook.urlopen", _fake_urlopen)

    result = get_crm_provider().push_call_result({"event": "call.completed"})
    assert result == {"synced": True, "status": 200}
    assert captured["url"] == "https://crm.test/hook"
    assert captured["body"]["event"] == "call.completed"


def test_sync_disabled_by_default(db_session, monkeypatch):
    monkeypatch.delenv("CRM_PROVIDER", raising=False)
    lead = Lead(id=500, name="CRM Test", phone="+919000000051")
    db_session.add(lead)
    call = Call(
        id=600, lead_id=500, campaign_id=1, phone_number="+919000000051",
        status=CallStatus.COMPLETED, provider="sarvam",
    )
    db_session.add(call)
    db_session.commit()

    result = sync_call_to_crm(db_session, 600)
    assert result == {"synced": False, "reason": "crm-disabled"}


def test_sync_pushes_completed_call(db_session, monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "webhook")
    monkeypatch.setenv("CRM_WEBHOOK_URL", "https://crm.test/hook")

    captured: dict = {}

    def _fake_urlopen(request, timeout=10):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr("app.services.crm.webhook.urlopen", _fake_urlopen)

    lead = Lead(id=501, name="CRM Lead", phone="+919000000052")
    db_session.add(lead)
    db_session.flush()
    call = Call(
        id=601, lead_id=501, campaign_id=1, phone_number="+919000000052",
        status=CallStatus.COMPLETED, provider="sarvam",
    )
    db_session.add(call)
    db_session.commit()

    result = sync_call_to_crm(db_session, 601)
    assert result["synced"] is True
    assert captured["body"]["call_id"] == 601
    assert captured["body"]["lead"]["phone"] == "+919000000052"


def test_sync_never_breaks_enrichment_on_crm_failure(
    db_session, monkeypatch
):
    from app.services.sarvam_enrichment import apply_sarvam_enrichment

    monkeypatch.setenv("CRM_PROVIDER", "webhook")
    monkeypatch.setenv("CRM_WEBHOOK_URL", "https://crm.test/hook")

    def _boom(request, timeout=10):
        raise ConnectionError("crm down")

    monkeypatch.setattr("app.services.crm.webhook.urlopen", _boom)

    lead = Lead(
        id=502, name="CRM Safe", phone="+919000000053",
        status=LeadStatus.CONNECTED,
    )
    db_session.add(lead)
    db_session.flush()
    call = Call(
        id=602, lead_id=502, campaign_id=1, phone_number="+919000000053",
        status=CallStatus.COMPLETED, provider="sarvam",
    )
    db_session.add(call)
    db_session.commit()

    result = apply_sarvam_enrichment(
        db_session, call, final_agent_variables={"interested": True}
    )
    assert result["enriched"] is True
