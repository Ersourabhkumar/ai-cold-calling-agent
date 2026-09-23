# Implementation Progress

**Date:** 2026-09-21

---

## PHASE 0: AUDIT — COMPLETE

### DONE
- Full repository inspection (80+ files)
- Architecture analysis
- Tabbly dependency mapping
- Sarvam API documentation research
- Database schema review
- Test suite verification (43/45 passing)
- Documentation created (10 files)

### RESULT
PASS — Project is well-structured, clean provider abstraction, ready for migration.

---

## PHASE 1 + 2 + 3 + 4: SARVAM CORE IMPLEMENTATION — COMPLETE

### DONE
- Created `app/services/calling/sarvam_provider.py` — Sarvam Instant Outbound API
- Created `app/services/sarvam_webhook_service.py` — Webhook handler
- Created `app/services/sarvam_enrichment.py` — Agent variables + transcript → CRM
- Updated `app/services/calling/factory.py` — Added Sarvam provider
- Updated `app/core/config.py` — Added Sarvam config validation
- Updated `app/api/routes/webhooks.py` — Added `/webhooks/sarvam/status`
- Updated `.env` — Added Sarvam credentials (mode=mock for safety)
- Created 46 tests across 3 test files — ALL PASSING
- Fixed enrichment callback priority bug
- Fixed duplicate webhook idempotency

### TEST RESULTS
```
89 passed, 2 failed (pre-existing Tabbly tests)
All 46 new Sarvam tests pass.
```

### VERIFIED SARVAM APIs
- Instant Outbound: `POST /api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds`
- Webhook: `POST /webhooks/sarvam/status` (connected|no_answer|busy|failed)
- Analytics Transcript: `GET /api/analytics/v1/{org_id}/{workspace_id}/{app_id}/transcripts/{interaction_id}`
- Analytics Recording: `GET /api/analytics/v1/{org_id}/{workspace_id}/{app_id}/recordings/{interaction_id}`
- Auth: `X-API-Key` header

---

## PHASE 4A: SARVAM TELEPHONY VERIFICATION — COMPLETE

**Date:** 2026-09-21

### OFFICIAL DOCUMENTATION REFERENCES
All verified from `https://docs.sarvam.ai/conversations/`:

1. **Instant Outbound API** — `https://docs.sarvam.ai/conversations/api/instant-outbound/create.md`
2. **Instant Outbound Webhook** — `https://docs.sarvam.ai/conversations/api/instant-outbound/webhook-payload.md`
3. **Campaign API** — `https://docs.sarvam.ai/conversations/api/campaigns/create.md`
4. **Campaign Webhook** — `https://docs.sarvam.ai/conversations/api/campaigns/webhooks/webhook-payload.md`
5. **Phone Numbers** — `https://docs.sarvam.ai/conversations/deploy/telephony.md`
6. **Campaigns** — `https://docs.sarvam.ai/conversations/deploy/campaigns.md`
7. **Deploy with Code** — `https://docs.sarvam.ai/conversations/deploy/deploy-with-code.md`
8. **Overview** — `https://docs.sarvam.ai/conversations/overview.md`
9. **Variables & Personalization** — `https://docs.sarvam.ai/conversations/build/variables-personalization.md`

### SARVAM VOICE AGENT ARCHITECTURE (VERIFIED)

Sarvam offers **two distinct outbound mechanisms**:

#### Mechanism 1: Instant Outbound API (SINGLE CALL)
- **Endpoint:** `POST /api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds`
- **Purpose:** Place a single outbound call immediately
- **Auth:** `X-API-Key` header
- **Request body:**
  ```json
  {
    "app_config": {
      "app_id": "string",
      "app_version": 1,
      "connection_config": {
        "connection_id": "string",
        "agent_phone_number": "string"
      },
      "agent_variables": {"key": "value"},
      "app_overrides": {
        "initial_bot_message": "string",
        "initial_language_name": "Hindi"
      }
    },
    "user_config": {
      "user_phone_number": "+91..."
    },
    "webhook_config": {
      "url": "https://...",
      "metadata": {"call_id": "123"}
    }
  }
  ```
- **Response:** `{"attempt_id": "string"}`
- **Webhook payload:** `attempt_id`, `status` (connected|no_answer|busy|failed), `duration`, `interaction_id`, `final_agent_variables`, `interaction_transcript`, `webhook_config.metadata`
- **Retry:** NOT managed by Sarvam — caller manages retries

#### Mechanism 2: Campaign API (BATCH CALL)
- **Endpoint:** `POST /api/scheduling/v1/orgs/{org_id}/workspaces/{workspace_id}/campaigns`
- **Purpose:** Batch outbound calling with schedule, retries, concurrency
- **Auth:** `X-API-Key` header
- **Request body:** `name`, `app_config` (with `connection_configs`, `retry_config`), `start_timestamp`, `end_timestamp`, `allowed_schedule`
- **Contacts:** Uploaded via cohort (CSV + transformation JSON)
- **Webhook payload:** Much richer — includes `campaign_id`, `cohort_id`, `completion_status`, `connectivity_status`, `next_action_status`, `initial_agent_variables`, `final_agent_variables`, `output_agent_variables`, `interaction_transcript`
- **Retry:** Managed by Sarvam (`retry_config` with `max_retries`, `retry_on` conditions)

### PHONE NUMBER / CONNECTION SETUP (VERIFIED)

From `https://docs.sarvam.ai/conversations/deploy/telephony.md`:

**Two ways to get phone numbers:**

1. **Bring Your Own Telephony** — Connect existing Exotel, Twilio, Smartflo, Pulse, Intalk, or Vobiz account
2. **Rent from Sarvam** — Rent numbers directly inside Voice Agents

**Connection hierarchy:**
- **Connection:** Link between Sarvam and telephony provider (set up once)
- **Number:** Phone number under a connection
- **Group:** Optional bundle of numbers for rotation

**For Instant Outbound API:**
- Requires `connection_id` (from Deploy → Phone Numbers)
- Requires `agent_phone_number` (E.164 format, from the connection)

**For Campaign API:**
- Requires `connection_configs[].connection_id`
- Requires `connection_configs[].phone_numbers[]` (array)
- Supports phone number rotation across pool

### OUR IMPLEMENTATION ASSESSMENT

#### CURRENT PROVIDER IMPLEMENTATION: VALID

Our `SarvamCallingProvider` uses the **Instant Outbound API**, which is:
- **Officially documented** for the current Voice Agents product
- **Suitable for production outbound calls**
- **Correct** for our use case (one call at a time, immediate dial)
- **Compatible** with existing `CallingProvider` abstraction

**What our implementation gets RIGHT:**
1. Correct endpoint: `POST /api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds`
2. Correct auth: `X-API-Key` header
3. Correct request body structure (app_config, user_config, webhook_config)
4. Correct webhook payload parsing (status, transcript, agent variables)
5. Lead context passed via `agent_variables`
6. Webhook correlation via `webhook_config.metadata`
7. Status mapping: connected→COMPLETED, no_answer→NO_ANSWER, busy→BUSY, failed→FAILED

**What our implementation correctly handles:**
1. Phone validation (E.164)
2. Duplicate webhook idempotency
3. INITIATED→COMPLETED bridging (for batched webhook delivery)
4. Transcript storage as CallMessage rows
5. Agent variable enrichment to CallSummary/Lead
6. Outcome inference from agent variables

#### CAMPAIGN API: NOT REQUIRED FOR OUR USE CASE

The Campaign API is designed for batch dialing with schedule/retries. Our cold calling agent:
- Calls one lead at a time (not batch)
- Manages retries ourselves (retry_service.py)
- Dispatches calls immediately (not scheduled)
- Passes lead context per-call (not via cohort upload)

**If we needed batch dialing**, the Campaign API would be better because:
- Sarvam manages retries and scheduling
- Phone number rotation across pool
- Richer webhook payload
- Built-in concurrency control

**For our use case**, Instant Outbound is simpler and more appropriate.

### WHAT FROM OUR IMPLEMENTATION REMAINS VALID

| Component | Status | Notes |
|-----------|--------|-------|
| `SarvamCallingProvider.start_call()` | VALID | Correct API, correct auth, correct request |
| `SarvamCallingProvider.hangup_call()` | VALID | No-op (Sarvam manages call lifecycle) |
| `SarvamCallingProvider.fetch_transcript()` | VALID | Correct analytics endpoint |
| `SarvamCallingProvider.fetch_recording()` | VALID | Correct analytics endpoint |
| `process_sarvam_webhook()` | VALID | Correct payload parsing, status mapping |
| `apply_sarvam_enrichment()` | VALID | Correct agent variable parsing |
| `/webhooks/sarvam/status` endpoint | VALID | Correct webhook handler |
| Status mapping | VALID | Matches documented status values |
| Transcript parsing | VALID | Matches documented `interaction_transcript` format |
| Agent variable parsing | VALID | Matches documented `final_agent_variables` format |

### WHAT MUST CHANGE

| Change | Priority | Notes |
|--------|----------|-------|
| Obtain `SARVAM_CONNECTION_ID` | BLOCKING | Required for production calls |
| Obtain `SARVAM_AGENT_PHONE_NUMBER` | BLOCKING | Required for production calls |
| Set up public HTTPS webhook URL | BLOCKING | Required for webhook delivery |
| Switch `CALLING_MODE=production` | LATER | After all blockers resolved |

### WHAT IS BLOCKED

1. **Phone Number** — Need Indian phone number (E.164 format) from Sarvam or Exotel/Twilio
2. **Connection ID** — Need connection ID from Sarvam dashboard (Deploy → Phone Numbers)
3. **Public Webhook URL** — Need HTTPS endpoint for Sarvam to POST callbacks

### EXACT CREDENTIALS/CONFIGURATION STILL REQUIRED

```
SARVAM_CONNECTION_ID=<from Sarvam dashboard>
SARVAM_AGENT_PHONE_NUMBER=+91XXXXXXXXXX
PUBLIC_BASE_URL=https://your-domain.com  (or cloudflare tunnel URL)
```

**How to obtain:**
1. Go to `https://indus.sarvam.ai/samvaad` → Deploy → Phone Numbers
2. Add Connection (Exotel/Twilio/Rent from Sarvam)
3. Note the `connection_id`
4. Note the assigned phone number (E.164 format)
5. Set up webhook URL (cloudflare tunnel, ngrok, or production domain)

### AUTHENTICATION (VERIFIED)

From official docs:
- All API requests require `X-API-Key` header
- API key obtained from Sarvam dashboard → Settings → API Key
- Our implementation correctly uses this header

### REQUEST/RESPONSE SCHEMAS (VERIFIED)

**Instant Outbound Request:**
```json
{
  "app_config": {
    "app_id": "Conversatio-f68881c7-7408",
    "app_version": 3,
    "connection_config": {
      "connection_id": "string",
      "agent_phone_number": "+91..."
    },
    "agent_variables": {"call_id": "1", "lead_id": "10"},
    "app_overrides": {
      "initial_bot_message": "Hello, am I speaking with..."
    }
  },
  "user_config": {
    "user_phone_number": "+91..."
  },
  "webhook_config": {
    "url": "https://...",
    "metadata": {"call_id": "1", "lead_id": "10"}
  }
}
```

**Instant Outbound Response:**
```json
{"attempt_id": "string"}
```

**Instant Outbound Webhook:**
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
  "interaction_id": "20250920/...",
  "failure_reason": null,
  "final_agent_variables": {"key": "value"},
  "webhook_config": {"url": "...", "metadata": {...}},
  "interaction_transcript": [{"role": "agent", "en_text": "..."}]
}
```

### RECOMMENDATION

**Keep the Instant Outbound API implementation.** It is:
- Officially documented
- Correct for our use case
- Simpler than Campaign API
- Compatible with existing architecture

**Proceed to obtain:**
1. Connection ID from Sarvam dashboard
2. Phone number (E.164 format)
3. Public HTTPS webhook URL

Then switch to production mode and test with a real call.

---

## PHASE 5: REMOVE TABBLY CODE — PENDING (not started)

### TODO
- Remove `tabbly_provider.py`, `tabbly_webhook_service.py`, `tabby_enrichment.py`
- Remove `call_log_sync.py`, `twilio_webhook_service.py`
- Remove `twilio_provider.py`
- Remove `tabby_sync_worker.py`
- Remove `ai/conversation.py`, `ai/providers.py`
- Remove Tabbly-specific tests
- Update celery_app.py, admin.py
- Update pyproject.toml (remove twilio dependency)
- Run tests

### BLOCKED BY
- Sarvam verified with real call (after Phase 8)

---

## PHASE 6: FULL TESTING — PENDING

### TODO
- Run all unit tests (done — 89/91 pass)
- Run mock end-to-end test via API
- Verify health checks pass with Sarvam config
- Verify UI still works
- Test dispatch → webhook → enrichment flow

### BLOCKED BY
- Nothing — ready to proceed

---

## PHASE 7: REAL CALL PREPARATION — PENDING

### TODO
- [ ] Obtain Indian phone number (from Sarvam or Exotel/Twilio)
- [ ] Set SARVAM_CONNECTION_ID in .env
- [ ] Set SARVAM_AGENT_PHONE_NUMBER in .env
- [ ] Set up public HTTPS webhook URL (cloudflare tunnel or ngrok)
- [ ] Verify agent is published in Sarvam dashboard
- [ ] Switch CALLING_MODE=production in .env
- [ ] Create test lead
- [ ] Verify mock mode works end-to-end
- [ ] STOP and report to user

### BLOCKED BY
- Phone Number
- Connection ID
- Public Webhook URL

---

## PHASE 8: FIRST REAL CALL — PENDING

### TODO
- [ ] WAIT for explicit GO from user
- [ ] Create test lead
- [ ] Dispatch call via API
- [ ] Monitor webhook delivery
- [ ] Verify transcript in webhook
- [ ] Verify agent variables in webhook
- [ ] Verify CallMessage rows created
- [ ] Verify CallSummary populated
- [ ] Verify Lead status updated
- [ ] Verify recording URL accessible
- [ ] Report results

### BLOCKED BY
- Explicit GO from user
- All items from Phase 7

---

## FILES CREATED (this session)

| File | Purpose |
|------|---------|
| `app/services/calling/sarvam_provider.py` | Sarvam Instant Outbound API client |
| `app/services/sarvam_webhook_service.py` | Webhook payload handler |
| `app/services/sarvam_enrichment.py` | Agent variables → CRM enrichment |
| `tests/test_sarvam_provider.py` | Provider unit tests (10 tests) |
| `tests/test_sarvam_webhook.py` | Webhook handler tests (11 tests) |
| `tests/test_sarvam_enrichment.py` | Enrichment tests (25 tests) |

## FILES MODIFIED (this session)

| File | Change |
|------|--------|
| `app/services/calling/factory.py` | Added Sarvam provider |
| `app/core/config.py` | Added Sarvam validation |
| `app/api/routes/webhooks.py` | Added `/webhooks/sarvam/status` |
| `.env` | Added Sarvam credentials, mode=mock |

## FILES PRESERVED (rollback)

| File | Status |
|------|--------|
| `app/services/calling/tabbly_provider.py` | Kept for rollback |
| `app/services/tabbly_webhook_service.py` | Kept for rollback |
| `app/services/tabby_enrichment.py` | Kept for rollback |
