# Current Architecture

**Date:** 2026-09-21

---

## System Overview

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
│    /api/admin        → Test call, sync, diagnostics          │
│    /ui/*             → Dashboard pages                        │
│    /webhooks/tabbly  → Tabbly status webhooks                │
│    /webhooks/plivo   → Plivo status webhooks                 │
│    /health/*         → Health checks                          │
│                                                              │
│  Middleware:                                                  │
│    RequestContextMiddleware (request ID, logging)             │
│    SecurityHeadersMiddleware (nosniff, DENY, etc.)           │
│    RateLimitMiddleware (per-IP rate limiting)                 │
│    ApiKeyMiddleware (X-API-Key authentication)                │
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
│    queue_service        → Redis call queue                   │
│    tabbly_webhook_service → Parse Tabbly webhooks            │
│    tabby_enrichment     → Transcript → CRM data              │
│    call_log_sync        → Poll Tabbly call logs              │
│    twilio_webhook_service → Parse Twilio webhooks            │
│    conversation         → AI conversation engine             │
│                                                              │
│  Calling Providers:                                          │
│    TabblyCallingProvider (production, current)               │
│    TwilioCallingProvider (incomplete)                        │
│    PlivoCallingProvider (incomplete)                         │
│    MockCallingProvider (development/testing)                 │
│                                                              │
│  AI Providers:                                               │
│    TestLLMProvider (deterministic, no API key)               │
│    STTProvider (abstract)                                    │
│    TTSProvider (abstract)                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    CELERY WORKERS                             │
│                                                              │
│  call_worker.dispatch_queued_call    → Dispatch QUEUED calls │
│  followup_worker.process_followups   → Process due follow-ups│
│  tabby_sync_worker.sync_tabby_logs   → Poll Tabbly call logs│
│                                                              │
│  Beat Schedule:                                               │
│    process-pending-followups (every 30s)                     │
│    sync-tabby-call-logs (every 60s)                          │
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
│    Rate limiting (in-memory fallback)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Current Tabbly Integration

```
1. Create Lead → POST /api/leads
2. Create Campaign → POST /api/campaigns
3. Assign Lead to Campaign → POST /api/campaigns/{id}/leads/{id}
4. Create Call → POST /api/calls
5. Dispatch Call → POST /api/calls/{id}/start
   ↓
   CallDispatcher → TabblyCallingProvider.start_call()
   ↓
   Creates Tabbly campaign → Adds contact → Returns campaign_id
   ↓
6. Tabbly Scheduler dials (~5 minutes later)
   ↓
7. Tabbly Webhook → POST /webhooks/tabbly/status
   ↓
   process_tabbly_webhook() → transition_call() → update call status
   ↓
8. On COMPLETED → apply_tabby_enrichment()
   ↓
   Parse transcript → Create CallMessage rows
   Parse call_json_output → Create/update CallSummary
   Update Lead (requirement, budget, timeline, status)
   ↓
9. If callback → create_callback_followup()
10. If no answer → create_retry_followup()
```

---

## Database Schema

```
leads
├── id (PK)
├── name, phone, email, city, source
├── requirement, budget, timeline
├── status (LeadStatus enum)
├── lead_score, attempt_count
├── last_called_at, next_call_at
├── created_at, updated_at
└── relationships: campaign_links, followups, calls

campaigns
├── id (PK)
├── name (unique), description
├── status (CampaignStatus enum)
├── max_attempts
├── calling_start_time, calling_end_time
├── created_at, updated_at
└── relationships: lead_links, calls

campaign_leads
├── id (PK)
├── campaign_id (FK → campaigns)
├── lead_id (FK → leads)
├── attempt_count
├── created_at
└── unique(campaign_id, lead_id)

calls
├── id (PK)
├── lead_id (FK → leads)
├── campaign_id (FK → campaigns)
├── phone_number, status (CallStatus enum)
├── provider, provider_call_id
├── started_at, answered_at, ended_at
├── duration_seconds
├── outcome (CallOutcome enum)
├── recording_url, transcript
├── attempt_number, max_attempts
├── next_retry_at, retry_reason
├── created_at, updated_at
└── relationships: lead, campaign, events, messages, summary

call_events
├── id (PK)
├── call_id (FK → calls)
├── event_type, previous_status, new_status
├── provider_event_id (unique)
├── payload (JSON)
└── created_at

call_messages
├── id (PK)
├── call_id (FK → calls)
├── sequence, speaker, text
├── created_at
└── unique(call_id, sequence)

call_summaries
├── id (PK)
├── call_id (FK → calls, unique)
├── summary, customer_intent, interest_level
├── requirements, objections, next_action
├── qualification_status
├── qualification (JSON)
├── followup_at
├── created_at, updated_at

followups
├── id (PK)
├── lead_id (FK → leads)
├── scheduled_at, reason, notes
├── status (FollowupStatus enum)
└── created_at
```

---

## Call Lifecycle State Machine

```
QUEUED → INITIATED → RINGING → ANSWERED → IN_PROGRESS → COMPLETED
                    ↘         ↘          ↘              ↘
                   FAILED    NO_ANSWER   BUSY            FAILED
                    ↓          ↓          ↓
                 RETRY      RETRY      RETRY
                (if attempts remain)
```

---

## Existing Provider Abstraction

```python
class CallingProvider(ABC):
    @abstractmethod
    def start_call(self, request: CallRequest) -> CallResult:
        raise NotImplementedError

    @abstractmethod
    def hangup_call(self, provider_call_id: str) -> None:
        raise NotImplementedError

@dataclass(frozen=True)
class CallRequest:
    phone_number: str
    call_id: int
    lead_id: int
    campaign_id: int
    webhook_url: str
    lead_context: dict[str, str] | None = None

@dataclass(frozen=True)
class CallResult:
    provider: str
    provider_call_id: str
    status: str
    metadata: dict[str, Any] | None = None
```

**Factory:**
```python
def get_calling_provider() -> CallingProvider:
    # Reads CALLING_MODE and TELEPHONY_PROVIDER env vars
    # Returns MockCallingProvider, TabblyCallingProvider, or TwilioCallingProvider
```
