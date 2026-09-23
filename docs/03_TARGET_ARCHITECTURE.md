# Target Architecture

**Date:** 2026-09-21

---

## Target System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    BROWSER UI (Jinja2)                       │
│  Dashboard │ Leads │ Calls │ Follow-ups │ Fire Live Call     │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    FASTAPI APPLICATION                        │
│                                                              │
│  Routes:                                                     │
│    /api/leads        → Lead CRUD                             │
│    /api/campaigns    → Campaign CRUD                         │
│    /api/calls        → Call CRUD + lifecycle                  │
│    /api/followups    → Follow-up CRUD                        │
│    /api/admin        → Test call, diagnostics                │
│    /ui/*             → Dashboard pages                        │
│    /webhooks/sarvam  → Sarvam status webhooks                │
│    /health/*         → Health checks                          │
│                                                              │
│  Services:                                                   │
│    lead_service         → Lead CRUD                          │
│    campaign_service     → Campaign CRUD                      │
│    call_service         → Call CRUD + lifecycle               │
│    call_dispatcher      → Dispatch to provider               │
│    call_lifecycle       → State machine + events             │
│    followup_service     → Follow-up CRUD                     │
│    followup_scheduler   → Process pending follow-ups         │
│    retry_service        → Create retry/callback follow-ups   │
│    queue_service        → Redis call queue (optional)        │
│    sarvam_webhook_service → Parse Sarvam webhooks            │
│    sarvam_enrichment    → Agent vars → CRM data              │
│                                                              │
│  Calling Providers:                                          │
│    SarvamCallingProvider (production)                        │
│    MockCallingProvider (development/testing)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    CELERY WORKERS (Optional)                  │
│                                                              │
│  call_worker.dispatch_queued_call    → Dispatch QUEUED calls │
│  followup_worker.process_followups   → Process due follow-ups│
│                                                              │
│  Beat Schedule:                                               │
│    process-pending-followups (every 30s)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    SARVAM VOICE AGENT PLATFORM                │
│                                                              │
│  Instant Outbound API → Places call                          │
│  AI Agent → Handles conversation (Hindi/English/Hinglish)    │
│  Webhook → Delivers status + transcript + agent variables    │
│  Analytics API → Fetch transcripts + recordings              │
│  Phone Numbers → Indian numbers via Exotel/Twilio           │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    DATA STORES                                │
│                                                              │
│  PostgreSQL (Primary):                                       │
│    leads, campaigns, campaign_leads, calls,                  │
│    call_events, call_messages, call_summaries, followups     │
│                                                              │
│  Redis (Optional):                                           │
│    calling:queue (call dispatch queue)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Target Data Flow

```
1. Create Lead → POST /api/leads
2. Create Campaign → POST /api/campaigns
3. Assign Lead to Campaign → POST /api/campaigns/{id}/leads/{id}
4. Create Call → POST /api/calls
5. Dispatch Call → POST /api/calls/{id}/start
   ↓
   CallDispatcher → SarvamCallingProvider.start_call()
   ↓
   POST to Sarvam Instant Outbound API
   ↓
   Sarvam returns attempt_id → stored as provider_call_id
   ↓
6. Sarvam immediately dials the number
   ↓
7. Sarvam AI agent conducts conversation (Hindi/English/Hinglish)
   ↓
8. Sarvam Webhook → POST /webhooks/sarvam/status
   ↓
   process_sarvam_webhook() → transition_call() → update call status
   ↓
9. On COMPLETED → apply_sarvam_enrichment()
   ↓
   Parse interaction_transcript → Create CallMessage rows
   Parse final_agent_variables → Create/update CallSummary
   Update Lead (requirement, budget, timeline, status)
   ↓
10. If callback → create_callback_followup()
11. If no answer → create_retry_followup()
```

---

## Component Status: KEEP / REPLACE / REMOVE / MODIFY / NEW

### Models (KEEP ALL)

| Model | Action | Notes |
|-------|--------|-------|
| Lead | KEEP | Perfect for MVP |
| Campaign | KEEP | Clean structure |
| CampaignLead | KEEP | Assignment tracking |
| Call | KEEP | All fields needed |
| CallEvent | KEEP | Audit trail |
| CallMessage | KEEP | Transcript messages |
| CallSummary | KEEP | Qualification data |
| Followup | KEEP | Retry/callback scheduling |
| SystemInfo | KEEP | System metadata |

### Enums (KEEP ALL)

| Enum | Action | Notes |
|------|--------|-------|
| LeadStatus | KEEP | Complete |
| CampaignStatus | KEEP | Complete |
| CallStatus | KEEP | Complete |
| CallOutcome | KEEP | Complete |
| FollowupStatus | KEEP | Complete |
| QualificationStatus | KEEP | Complete |

### Services (MODIFY)

| Service | Action | Notes |
|---------|--------|-------|
| lead_service | KEEP | CRUD unchanged |
| campaign_service | KEEP | CRUD unchanged |
| call_service | KEEP | CRUD unchanged |
| call_dispatcher | KEEP | Provider-agnostic |
| call_lifecycle | KEEP | State machine unchanged |
| followup_service | KEEP | CRUD unchanged |
| followup_scheduler | KEEP | Logic unchanged |
| retry_service | KEEP | Logic unchanged |
| queue_service | KEEP | Optional Redis queue |
| calling_queue_service | KEEP | Queue queries unchanged |
| campaign_lead_service | KEEP | CRUD unchanged |
| tabbly_webhook_service | REMOVE | Replaced by Sarvam handler |
| tabby_enrichment | REMOVE | Replaced by Sarvam enrichment |
| call_log_sync | REMOVE | Not needed with webhooks |
| twilio_webhook_service | REMOVE | Not needed |
| conversation | REMOVE | Sarvam handles conversation |

### Calling Providers (MODIFY)

| Provider | Action | Notes |
|----------|--------|-------|
| provider.py (ABC) | KEEP | Abstract interface unchanged |
| sarvam_provider.py | NEW | Sarvam Instant Outbound API |
| mock_provider.py | KEEP | Development/testing |
| tabbly_provider.py | REMOVE | Replaced by Sarvam |
| twilio_provider.py | REMOVE | Not needed |
| plivo_provider.py | REMOVE | Not needed |
| factory.py | MODIFY | Add Sarvam, remove others |

### AI Services (REMOVE)

| Service | Action | Notes |
|---------|--------|-------|
| ai/providers.py | REMOVE | Sarvam handles STT/TTS/LLM |
| ai/conversation.py | REMOVE | Sarvam handles conversation |

### Webhooks (MODIFY)

| Route | Action | Notes |
|-------|--------|-------|
| /webhooks/tabbly/status | REMOVE | Replaced by Sarvam |
| /webhooks/plivo/status | REMOVE | Not needed |
| /webhooks/plivo/answer | REMOVE | Not needed |
| /webhooks/plivo/speech | REMOVE | Not needed |
| /webhooks/sarvam/status | NEW | Sarvam webhook endpoint |

### Admin (MODIFY)

| Endpoint | Action | Notes |
|----------|--------|-------|
| /api/admin/sync/tabbly-call-logs | REMOVE | Not needed |
| /api/admin/tabbly/campaigns/{id}/activate | REMOVE | Not needed |
| /api/admin/test-call | KEEP | Provider-agnostic |
| /api/admin/test-call/status | KEEP | Provider-agnostic |

### Workers (MODIFY)

| Worker | Action | Notes |
|--------|--------|-------|
| call_worker | KEEP | Dispatch unchanged |
| followup_worker | KEEP | Processing unchanged |
| tabby_sync_worker | REMOVE | Not needed |

### Core (MODIFY)

| Module | Action | Notes |
|--------|--------|-------|
| config.py | MODIFY | Add Sarvam config, remove Tabbly |
| celery_app.py | MODIFY | Remove tabby_sync_worker |
| phone_validation | KEEP | E.164 validation unchanged |
| redis | KEEP | Optional queue unchanged |
| security | KEEP | Auth unchanged |
| rate_limit | KEEP | Rate limiting unchanged |
| request_context | KEEP | Logging unchanged |
| call_config | KEEP | Retry config unchanged |

### Routes (MODIFY)

| Route | Action | Notes |
|-------|--------|-------|
| leads.py | KEEP | CRUD unchanged |
| campaigns.py | KEEP | CRUD unchanged |
| calls.py | KEEP | Mostly unchanged |
| followups.py | KEEP | CRUD unchanged |
| calling_queue.py | KEEP | Queue queries unchanged |
| campaign_leads.py | KEEP | Assignment unchanged |
| admin.py | MODIFY | Remove Tabbly-specific endpoints |
| ui.py | MODIFY | Remove Tabbly-specific UI |
| webhooks.py | MODIFY | Replace with Sarvam endpoint |

### Templates (KEEP)

| Template | Action | Notes |
|----------|--------|-------|
| base.html | KEEP | Layout unchanged |
| dashboard.html | KEEP | Stats unchanged |
| leads.html | KEEP | Lead list unchanged |
| lead_detail.html | KEEP | Lead detail unchanged |
| calls.html | KEEP | Call list unchanged |
| followups.html | KEEP | Follow-up list unchanged |
| fire_call.html | KEEP | Fire call form unchanged |
| _status.html | KEEP | Status partial unchanged |

### Tests (MODIFY)

| Test | Action | Notes |
|------|--------|-------|
| test_free_trial_api.py | KEEP | Provider-agnostic |
| test_conversation.py | REMOVE | Sarvam handles conversation |
| test_admin_test_call.py | KEEP | Provider-agnostic |
| test_phone_validation.py | KEEP | Validation unchanged |
| test_security.py | KEEP | Security unchanged |
| test_hardening.py | MODIFY | Update for Sarvam config |
| test_ui.py | KEEP | UI unchanged |
| test_tabbly_integration.py | REMOVE | Tabbly-specific |
| test_tabby_enrichment.py | REMOVE | Tabbly-specific |
| test_call_log_sync.py | REMOVE | Tabbly-specific |
| test_sarvam_provider.py | NEW | Sarvam provider tests |
| test_sarvam_webhook.py | NEW | Sarvam webhook tests |
| test_sarvam_enrichment.py | NEW | Sarvam enrichment tests |

---

## File Change Summary

### Files to CREATE (3)
1. `app/services/calling/sarvam_provider.py`
2. `app/services/sarvam_webhook_service.py`
3. `app/services/sarvam_enrichment.py`

### Files to MODIFY (8)
1. `app/services/calling/factory.py`
2. `app/core/config.py`
3. `app/api/routes/webhooks.py`
4. `app/api/routes/admin.py`
5. `app/core/celery_app.py`
6. `.env.example`
7. `pyproject.toml`
8. `tests/test_hardening.py`

### Files to REMOVE (12)
1. `app/services/calling/tabbly_provider.py`
2. `app/services/calling/twilio_provider.py`
3. `app/services/calling/plivo_provider.py`
4. `app/services/tabbly_webhook_service.py`
5. `app/services/tabby_enrichment.py`
6. `app/services/call_log_sync.py`
7. `app/services/twilio_webhook_service.py`
8. `app/workers/tabby_sync_worker.py`
9. `app/services/ai/conversation.py`
10. `app/services/ai/providers.py`
11. `tests/test_tabbly_integration.py`
12. `tests/test_tabby_enrichment.py`
13. `tests/test_call_log_sync.py`
14. `tests/test_conversation.py`

### Files to KEEP UNCHANGED (35+)
All models, enums, schemas, most services, all routes (except webhooks/admin), all templates, all core modules (except config/celery), database connection, Docker setup.
