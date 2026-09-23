# Sarvam Migration Plan

**Date:** 2026-09-21
**Status:** IN PROGRESS

---

## Migration Strategy

**Approach:** Incremental migration - keep all existing business logic, replace only the telephony provider layer.

**Principle:** The existing project has a clean `CallingProvider` abstraction. We replace the Tabbly implementation with a Sarvam implementation while preserving all business logic.

---

## Sarvam API Capabilities (Verified)

| Feature | Status | API | Notes |
|---------|--------|-----|-------|
| Instant outbound call | CONFIRMED | POST `/api/outbounds/...` | Single call API |
| Campaign calling | CONFIRMED | POST `/api/scheduling/...` | Batch calling |
| Webhook (status) | CONFIRMED | POST to configured URL | After each call attempt |
| Webhook (transcript) | CONFIRMED | In webhook payload | `interaction_transcript` field |
| Webhook (agent variables) | CONFIRMED | In webhook payload | `final_agent_variables` field |
| Analytics transcript | CONFIRMED | GET `/api/analytics/.../transcripts/{interaction_id}` | Fetch by interaction_id |
| Analytics recording | CONFIRMED | GET `/api/analytics/.../recordings/{interaction_id}` | Fetch by interaction_id |
| Phone number rental | CONFIRMED | Via dashboard | "Rent from Sarvam" |
| Indian phone numbers | CONFIRMED | Exotel/Twilio/Smartflo via Sarvam | Multiple providers |
| Hindi/English/Hinglish | CONFIRMED | Agent language config | Via agent configuration |
| Agent variables (input) | CONFIRMED | `agent_variables` in request | Pass lead context |
| Agent variables (output) | CONFIRMED | `final_agent_variables` in webhook | Qualification data |

---

## Migration Phases

### Phase 1: Create SarvamCallingProvider

**Files to create:**
- `app/services/calling/sarvam_provider.py`

**Files to modify:**
- `app/services/calling/factory.py` - Add Sarvam provider
- `app/core/config.py` - Add Sarvam config validation
- `.env.example` - Add Sarvam env vars
- `pyproject.toml` - Remove twilio dependency

**What it does:**
- Calls Sarvam Instant Outbound API: `POST https://apps.sarvam.ai/api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds`
- Passes lead context as `agent_variables`
- Returns `attempt_id` as `provider_call_id`
- Supports `initial_bot_message` and `initial_language_name` overrides

**Sarvam API request structure:**
```json
{
  "app_config": {
    "app_id": "<SARVAM_APP_ID>",
    "app_version": <SARVAM_APP_VERSION>,
    "connection_config": {
      "connection_id": "<SARVAM_CONNECTION_ID>",
      "agent_phone_number": "<SARVAM_AGENT_PHONE_NUMBER>"
    },
    "agent_variables": {
      "customer_name": "...",
      "city": "...",
      "requirement": "...",
      "budget": "...",
      "timeline": "..."
    },
    "app_overrides": {
      "initial_bot_message": "Hello, am I speaking with {name}?",
      "initial_language_name": "Hindi"
    }
  },
  "user_config": {
    "user_phone_number": "+91..."
  },
  "webhook_config": {
    "url": "https://your-domain.com/webhooks/sarvam/status",
    "metadata": {
      "call_id": "123",
      "lead_id": "456"
    }
  }
}
```

### Phase 2: Create Sarvam Webhook Handler

**Files to create:**
- `app/services/sarvam_webhook_service.py`

**Files to modify:**
- `app/api/routes/webhooks.py` - Add Sarvam webhook endpoint

**Webhook payload structure (from Sarvam docs):**
```json
{
  "attempt_id": "string",
  "status": "connected|no_answer|busy|failed",
  "channel_info": {
    "channel_type": "v2v",
    "channel_provider": "exotel",
    "agent_phone_number": "+91..."
  },
  "duration": 42.5,
  "interaction_id": "...",
  "failure_reason": null,
  "final_agent_variables": {
    "customer_name": "Rahul",
    "disposition": "interested",
    "budget": "75 lakh",
    "timeline": "3 months"
  },
  "webhook_config": {
    "url": "...",
    "metadata": {"call_id": "123", "lead_id": "456"}
  },
  "interaction_transcript": [
    {"role": "agent", "en_text": "Hello, am I speaking with Rahul?"},
    {"role": "user", "en_text": "Yes, this is Rahul."}
  ]
}
```

**Status mapping:**
```python
SARVAM_STATUS_MAP = {
    "connected": CallStatus.COMPLETED,  # or IN_PROGRESS → COMPLETED
    "no_answer": CallStatus.NO_ANSWER,
    "busy": CallStatus.BUSY,
    "failed": CallStatus.FAILED,
}
```

### Phase 3: Create Sarvam Enrichment

**Files to create:**
- `app/services/sarvam_enrichment.py`

**What it does:**
- Parse `final_agent_variables` → qualification data
- Parse `interaction_transcript` → CallMessage rows
- Update CallSummary with structured qualification
- Update Lead with requirements, budget, timeline
- Infer CallOutcome from agent variables

**Agent variables to qualification mapping:**
```
final_agent_variables.qualification_status → summary.qualification_status
final_agent_variables.interested → summary.interest_level
final_agent_variables.budget → lead.budget
final_agent_variables.timeline → lead.timeline
final_agent_variables.location → lead.city
final_agent_variables.property_type + bhk → lead.requirement
final_agent_variables.callback_requested → CallOutcome.CALLBACK
final_agent_variables.appointment_requested → CallOutcome.APPOINTMENT_BOOKED
```

### Phase 4: Remove Tabbly Code

**Files to remove:**
- `app/services/calling/tabbly_provider.py`
- `app/services/tabbly_webhook_service.py`
- `app/services/tabby_enrichment.py`
- `app/services/call_log_sync.py`
- `app/services/twilio_webhook_service.py`
- `app/workers/tabby_sync_worker.py`

**Files to simplify:**
- `app/services/calling/factory.py` - Remove Tabbly/Twilio/Plivo
- `app/api/routes/webhooks.py` - Remove Tabbly/Twilio/Plivo endpoints
- `app/api/routes/admin.py` - Remove Tabbly-specific endpoints
- `app/core/config.py` - Remove Tabbly/Twilio/Plivo validation
- `app/core/celery_app.py` - Remove tabby_sync_worker
- `.env.example` - Remove Tabbly/Twilio/Plivo vars
- `pyproject.toml` - Remove twilio dependency

### Phase 5: Update Tests

**Files to remove:**
- `tests/test_tabbly_integration.py`
- `tests/test_tabby_enrichment.py`
- `tests/test_call_log_sync.py`

**Files to create:**
- `tests/test_sarvam_provider.py`
- `tests/test_sarvam_webhook.py`
- `tests/test_sarvam_enrichment.py`

---

## Tabbly Component Migration Map

```
TabblyCallingProvider
    ↓ Creates Tabbly campaign + contact
    ↓ Tabbly dials on its schedule
    ↓ Webhook/call-log delivers status
    ↓ Enrichment parses Tabbly JSON output
↓
SarvamCallingProvider
    ↓ Calls Sarvam Instant Outbound API
    ↓ Sarvam dials immediately
    ↓ Webhook delivers status + transcript + agent variables
    ↓ Enrichment parses agent variables
```

**Key differences:**
1. Tabbly uses campaign-based dialing; Sarvam uses instant outbound
2. Tabbly has delayed dialing (~5 min); Sarvam dials immediately
3. Tabbly returns transcript in webhook; Sarvam returns transcript + agent variables
4. Tabbly requires call-log polling; Sarvam provides complete webhook data
5. Tabbly has flexible/unstructured payload; Sarvam has structured payload

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sarvam API changes | HIGH | Pin API version, monitor changelog |
| Webhook delivery failure | HIGH | Implement retry queue, use analytics API as fallback |
| Agent variable format changes | MEDIUM | Validate in enrichment, log unknowns |
| Phone number availability | MEDIUM | Use "Rent from Sarvam" for Indian numbers |
| Language support gaps | LOW | Test Hindi/English/Hinglish thoroughly |
