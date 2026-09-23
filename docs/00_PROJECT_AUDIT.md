# Project Audit Report

**Date:** 2026-09-21
**Status:** COMPLETE

---

## A. What already works?

| Component | Status | Notes |
|-----------|--------|-------|
| Lead CRUD | WORKING | Full create/read/update/delete with validation |
| Campaign management | WORKING | Draft → Active lifecycle, max attempts |
| Call lifecycle | WORKING | QUEUED → INITIATED → RINGING → ANSWERED → IN_PROGRESS → COMPLETED |
| Call dispatch | WORKING | Provider abstraction with factory pattern |
| Webhook handling | WORKING | Flexible payload parsing for Tabbly |
| Call enrichment | WORKING | Transcript → qualification → CRM update |
| Follow-up scheduling | WORKING | Retry/callback follow-ups via Celery |
| Dashboard UI | WORKING | Server-rendered Jinja2 templates |
| Phone validation | WORKING | E.164 strict validation |
| Security | WORKING | API key auth, rate limiting, security headers |
| Health checks | WORKING | DB, Redis, config, readiness |
| Tests | WORKING | 43/45 passing |

## B. What is incomplete?

| Component | Status | Notes |
|-----------|--------|-------|
| Plivo provider | INCOMPLETE | Provider exists but no streaming STT/TTS |
| Twilio provider | INCOMPLETE | Basic TwiML, no real voice pipeline |
| OpenAI LLM integration | INCOMPLETE | Only test/mock LLM implemented |
| CRM integration | MISSING | No external CRM adapter |
| Site visit scheduling | PARTIAL | Follow-up exists but no site visit model |

## C. What is broken?

| Component | Issue | Impact |
|-----------|-------|--------|
| 2 Tabbly tests | Destination fallback fails in mock mode | Low - pre-existing, mock provider mismatch |

## D. What is unnecessary?

| Component | Why Unnecessary | Action |
|-----------|----------------|--------|
| Plivo provider | Sarvam handles telephony internally | REMOVE after migration |
| Twilio provider | Sarvam handles telephony internally | REMOVE after migration |
| Tabbly provider | Being replaced by Sarvam | REPLACE |
| Tabbly webhook service | Being replaced by Sarvam webhooks | REPLACE |
| Tabbly enrichment | Being replaced by Sarvam enrichment | REPLACE |
| Tabbly call-log sync | Sarvam provides webhooks + analytics API | REMOVE |
| Tabby sync worker | No longer needed with Sarvam webhooks | REMOVE |
| Custom conversation engine | Sarvam handles AI conversation | REMOVE (keep for mock mode) |
| AI providers module | Sarvam handles STT/TTS/LLM | SIMPLIFY |

## E. What is Tabbly-specific?

| File | Purpose | Migration Action |
|------|---------|-----------------|
| `app/services/calling/tabbly_provider.py` | Tabbly API integration | REPLACE with SarvamProvider |
| `app/services/tabbly_webhook_service.py` | Tabbly webhook parsing | REPLACE with Sarvam webhook handler |
| `app/services/tabby_enrichment.py` | Tabbly transcript enrichment | REPLACE with Sarvam enrichment |
| `app/services/call_log_sync.py` | Poll Tabbly call logs | REMOVE (use webhooks) |
| `app/workers/tabby_sync_worker.py` | Celery task for sync | REMOVE |
| `app/api/routes/webhooks.py` | Tabbly webhook endpoint | REPLACE with Sarvam webhook |
| `app/api/routes/admin.py` | Tabbly admin endpoints | MODIFY |
| `app/core/config.py` | Tabbly config validation | MODIFY |
| `.env` | Tabbly env vars | REPLACE |
| Tests | Tabbly-specific tests | REPLACE |

## F. What can be reused?

| Component | Reusable As-Is | Notes |
|-----------|---------------|-------|
| Lead model | YES | Perfect for MVP |
| Campaign model | YES | Clean structure |
| Call model | YES | All fields needed |
| CallEvent model | YES | Audit trail |
| CallMessage model | YES | Transcript messages |
| CallSummary model | YES | Qualification data |
| CampaignLead model | YES | Assignment tracking |
| Followup model | YES | Retry/callback scheduling |
| Enums | YES | LeadStatus, CallStatus, CallOutcome |
| Call lifecycle | YES | State machine logic |
| Phone validation | YES | E.164 validation |
| Retry service | YES | Callback/retry logic |
| Queue service | YES | Redis queue (optional) |
| Lead service | YES | CRUD operations |
| Campaign service | YES | CRUD operations |
| Call service | YES | CRUD + lifecycle |
| Followup service | YES | CRUD + scheduling |
| Dashboard UI | YES | Server-rendered templates |
| Security middleware | YES | API key, rate limit, headers |
| Health checks | YES | All endpoints |
| Database connection | YES | PostgreSQL setup |
| Docker setup | YES | docker-compose |

## G. What must be replaced?

| Component | Replacement | Priority |
|-----------|-------------|----------|
| TabblyCallingProvider | SarvamCallingProvider | HIGH |
| Tabbly webhook handler | Sarvam webhook handler | HIGH |
| Tabbly enrichment | Sarvam enrichment | HIGH |
| Tabbly call-log sync | REMOVE (not needed) | HIGH |
| Tabbly sync worker | REMOVE | HIGH |
| Tabbly admin endpoints | MODIFY for Sarvam | MEDIUM |

## H. What should be simplified?

| Component | Current | Simplified |
|-----------|---------|------------|
| Provider factory | 5 providers | 2: Sarvam + Mock |
| Config validation | Checks Tabbly/Twilio/Plivo | Check Sarvam only |
| Environment vars | 20+ Tabbly vars | 6 Sarvam vars |
| Webhook parsing | Flexible multi-key guessing | Sarvam-specific parser |
| Enrichment | Tabbly JSON output parsing | Sarvam agent variables |

## I. What needs new code?

| Component | Description | Priority |
|-----------|-------------|----------|
| SarvamCallingProvider | Sarvam Instant Outbound API | HIGH |
| Sarvam webhook handler | Process Sarvam webhook payloads | HIGH |
| Sarvam enrichment | Parse agent variables → qualification | HIGH |
| Sarvam config | New env vars and validation | HIGH |
| Sarvam tests | Unit + integration tests | HIGH |

## J. What external services are required?

| Service | Purpose | Required |
|---------|---------|----------|
| Sarvam account | Voice Agent platform | YES |
| Sarvam API key | Authentication | YES |
| Sarvam agent (app) | Voice agent configuration | YES |
| Sarvam phone number | Outbound caller ID | YES |
| Sarvam telephony connection | Exotel/Twilio/etc via Sarvam | YES |
| PostgreSQL | Database | YES |
| Redis | Queue (optional) | OPTIONAL |

## K. What credentials/API keys do I need?

| Credential | Where | Required |
|------------|-------|----------|
| SARVAM_API_KEY | Settings → API Key | YES |
| SARVAM_ORG_ID | Dashboard URL / Settings | YES |
| SARVAM_WORKSPACE_ID | Dashboard URL / Settings | YES |
| SARVAM_APP_ID | Agent deployment | YES |
| SARVAM_APP_VERSION | Agent version | YES |
| SARVAM_CONNECTION_ID | Phone Numbers → Connection | YES |
| SARVAM_AGENT_PHONE_NUMBER | E.164 format | YES |
| DATABASE_URL | PostgreSQL | YES |
| REDIS_URL | Redis | OPTIONAL |
| PUBLIC_BASE_URL | HTTPS for webhooks | YES |

## L. What must I keep running?

| Terminal | Service | Command | Required |
|----------|---------|---------|----------|
| 1 | PostgreSQL + Redis | `docker compose up -d postgres redis` | YES |
| 2 | API server | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | YES |
| 3 | Celery worker | `celery -A app.core.celery_app worker` | OPTIONAL |
| 4 | Celery beat | `celery -A app.core.celery_app beat` | OPTIONAL |
| 5 | Tunnel (ngrok/cloudflared) | For webhook delivery | YES (prod) |

## M. What needs Docker?

| Component | Docker Required | Notes |
|-----------|----------------|-------|
| PostgreSQL | YES (compose) | postgres:16-alpine |
| Redis | YES (compose) | redis:7-alpine |
| API | YES (compose) | Custom Dockerfile |
| Worker | YES (compose) | Same image, different command |
| Scheduler | YES (compose) | Same image, different command |

## N. What can be removed?

| File/Module | Reason |
|-------------|--------|
| `app/services/calling/plivo_provider.py` | Not needed with Sarvam |
| `app/services/calling/twilio_provider.py` | Not needed with Sarvam |
| `app/services/calling/tabbly_provider.py` | Replaced by Sarvam |
| `app/services/tabbly_webhook_service.py` | Replaced by Sarvam handler |
| `app/services/tabby_enrichment.py` | Replaced by Sarvam enrichment |
| `app/services/call_log_sync.py` | Not needed with webhooks |
| `app/services/twilio_webhook_service.py` | Not needed |
| `app/workers/tabby_sync_worker.py` | Not needed |
| `app/services/ai/conversation.py` | Sarvam handles conversation |
| `app/services/ai/providers.py` | Sarvam handles STT/TTS/LLM |
| `tests/test_tabbly_integration.py` | Tabbly-specific tests |
| `tests/test_tabby_enrichment.py` | Tabbly-specific tests |
| `tests/test_call_log_sync.py` | Tabbly-specific tests |
| `twilio` dependency in pyproject.toml | Not needed |

## O. What tests already exist?

| Test File | Tests | Status |
|-----------|-------|--------|
| test_free_trial_api.py | 3 | PASS |
| test_conversation.py | 2 | PASS |
| test_admin_test_call.py | 5 | PASS |
| test_phone_validation.py | 6 | PASS |
| test_security.py | 1 | PASS |
| test_hardening.py | 5 | PASS |
| test_ui.py | 5 | PASS |
| test_tabbly_integration.py | 8 | 6 PASS, 2 FAIL |
| test_tabby_enrichment.py | 3 | PASS |
| test_call_log_sync.py | 3 | PASS |
| **TOTAL** | **41** | **39 PASS, 2 FAIL** |

## P. What tests are missing?

| Test Category | Tests Needed |
|---------------|-------------|
| Sarvam provider | Unit tests for API calls |
| Sarvam webhook | Integration tests |
| Sarvam enrichment | Unit tests |
| Sarvam config | Validation tests |
| End-to-end mock | Full flow with mock Sarvam |
| Error handling | Sarvam API failures |
| Idempotency | Duplicate webhooks |
| Multi-language | Hindi/English/Hinglish |
