# 11. Fresh Architecture + Requirements Audit

> **Audit date:** 2026-09-22
> **Auditor:** opencode (mimo-v2-pro-max)
> **Method:** Full independent code inspection — every file, every route, every test, every service
> **Previous reports checked:** docs/00 through docs/10

---

## 1. Executive Summary

**The project has NOT drifted.** The core architecture is sound and still aligned to the original product: an AI real-estate outbound calling agent named Priya that qualifies leads through natural conversation.

**What IS working:**
- Complete mock call flow end-to-end (lead → campaign → call → dispatch → webhook → enrichment → followup)
- Sarvam provider integration (outbound API, webhook processing, enrichment)
- State machine lifecycle, retry logic, followup scheduling
- Comprehensive test suite (140 pass, 2 pre-existing Tabbly failures)
- Safety guards against accidental real calls

**What is NOT working:**
- No real call has ever been placed (blocked on telephony setup)
- No real conversation quality has been verified
- Standalone TTS/STT uses wrong API key type (Samvaad key vs AI platform key)
- No production LLM provider exists (only test regex engine)
- The `property_type` field in enrichment is legacy data collection — it is NOT property recommendation

**Key finding:** The `property_type` field appears in enrichment because old Tabbly flows captured it as a qualification requirement. The agent does NOT recommend properties. This is a data capture field, not a product drift.

---

## 2. Original Product We Intended To Build

An AI outbound calling agent for real-estate lead qualification:

- **Agent persona:** Female, name Priya
- **Languages:** Hindi, English, Hinglish
- **Purpose:** Call leads, qualify them conversationally, capture requirements
- **DO:** Greet, ask permission, understand requirements, handle objections, summarize, coordinate site visits
- **DO NOT:** Recommend properties, select inventory, pitch projects, act as property recommendation engine

**Flow:** GREETING → PERMISSION → NATURAL QUALIFICATION → SUMMARY_CONFIRM → CLOSING → VISIT_BOOKING → END

---

## 3. Current Product Actually Implemented

| Component | Status | Evidence |
|---|---|---|
| Lead CRUD | IMPLEMENTED | `app/api/routes/leads.py` — full CRUD |
| Campaign management | IMPLEMENTED | `app/api/routes/campaigns.py` — full CRUD |
| Campaign-lead assignment | IMPLEMENTED | `app/api/routes/campaign_leads.py` |
| Call creation & lifecycle | IMPLEMENTED | `app/api/routes/calls.py` — 14 endpoints |
| Provider abstraction | IMPLEMENTED | `app/services/calling/` — 5 providers (mock, sarvam, tabbly, twilio, plivo) |
| Provider factory | IMPLEMENTED | `app/services/calling/factory.py` — env-based selection |
| Mock provider | IMPLEMENTED | `app/services/calling/mock_provider.py` — fake UUID, no real calls |
| Sarvam provider | IMPLEMENTED | `app/services/calling/sarvam_provider.py` — Instant Outbound API |
| Sarvam webhook | IMPLEMENTED | `app/services/sarvam_webhook_service.py` — idempotent, with bridging |
| Sarvam enrichment | IMPLEMENTED | `app/services/sarvam_enrichment.py` — lead + summary update |
| Tabbly provider | IMPLEMENTED (LEGACY) | `app/services/calling/tabbly_provider.py` — campaign-based |
| Tabbly webhook | IMPLEMENTED (LEGACY) | `app/services/tabbly_webhook_service.py` — 591 lines |
| Tabbly enrichment | IMPLEMENTED (LEGACY) | `app/services/tabby_enrichment.py` |
| Twilio provider | IMPLEMENTED (LEGACY) | `app/services/calling/twilio_provider.py` |
| Plivo provider | IMPLEMENTED (DEAD) | `app/services/calling/plivo_provider.py` — NOT wired in factory |
| AI conversation engine | IMPLEMENTED (TEST ONLY) | `app/services/ai/providers.py` — regex-based `TestLLMProvider` |
| Production LLM | NOT IMPLEMENTED | `get_llm_provider()` raises ValueError for non-test modes |
| Standalone TTS | IMPLEMENTED (DIAGNOSTIC) | `app/services/sarvam_tts.py` — not wired into calling |
| Standalone STT | IMPLEMENTED (DIAGNOSTIC) | `app/services/sarvam_stt.py` — not wired into calling |
| Call state machine | IMPLEMENTED | `app/services/call_lifecycle.py` — validated transitions |
| Retry logic | IMPLEMENTED | `app/services/retry_service.py` — callback + auto-retry |
| Followup scheduling | IMPLEMENTED | `app/services/followup_scheduler.py` + Celery worker |
| Call queue | IMPLEMENTED | `app/services/queue_service.py` — Redis-based |
| Webhook dedup | IMPLEMENTED | `sarvam_webhook_service.py` — `last_attempt_id` dict |
| UI dashboard | IMPLEMENTED | `app/api/routes/ui.py` — Jinja2 server-rendered |
| Admin test-call | IMPLEMENTED | `app/api/routes/admin.py` — one-shot live call endpoint |
| Phone validation | IMPLEMENTED | `app/core/phone_validation.py` — E.164 strict |
| Security headers | IMPLEMENTED | `app/core/security.py` |
| Rate limiting | IMPLEMENTED | `app/core/rate_limit.py` — in-memory fixed window |
| Request context | IMPLEMENTED | `app/core/request_context.py` — request IDs, timing |

---

## 4. Current Architecture Diagram

```
                          ┌─────────────┐
                          │   UI (Jinja2)│
                          └──────┬──────┘
                                 │
┌──────────┐  ┌──────────┐  ┌────▼────┐  ┌──────────┐  ┌──────────┐
│ Leads API │  │Campaigns │  │ Calls   │  │Followups │  │ Webhooks │
│ CRUD      │  │  API     │  │  API    │  │  API     │  │          │
└─────┬────┘  └────┬─────┘  └────┬────┘  └────┬─────┘  └────┬─────┘
      │            │             │             │             │
      └────────────┴──────┬──────┴─────────────┘             │
                          │                                   │
                   ┌──────▼──────┐                   ┌───────▼────────┐
                   │ call_service │                   │ webhook_service│
                   │ call_lifecycle│                   │ (sarvam/tabbly)│
                   └──────┬──────┘                   └───────┬────────┘
                          │                                   │
                   ┌──────▼──────┐                   ┌───────▼────────┐
                   │call_dispatcher│                  │  enrichment    │
                   └──────┬──────┘                   └───────┬────────┘
                          │                                   │
                   ┌──────▼──────┐                            │
                   │   factory   │                            │
                   └──────┬──────┘                            │
                          │                                   │
            ┌─────────────┼─────────────┐                     │
            │             │             │                     │
     ┌──────▼─────┐ ┌────▼────┐ ┌─────▼─────┐               │
     │   Mock     │ │ Sarvam  │ │  Tabbly   │               │
     │  Provider  │ │Provider │ │  Provider │               │
     └────────────┘ └────┬────┘ └───────────┘               │
                         │                                   │
                  ┌──────▼──────┐                   ┌───────▼────────┐
                  │ Sarvam API  │                   │    Database    │
                  │ (outbound)  │                   │  (PostgreSQL)  │
                  └──────┬──────┘                   └────────────────┘
                         │
                  ┌──────▼──────┐
                  │   Webhook   │
                  │  (callback) │
                  └─────────────┘
```

---

## 5. Intended Architecture Diagram

```
Lead → FastAPI → CallingProvider → Sarvam Voice Agent → Phone Call
                                                              ↓
                                                    Priya conversation
                                                              ↓
                                                    Sarvam webhook
                                                              ↓
                                                    Backend processing
                                                              ↓
                                                    Transcript + Variables
                                                              ↓
                                                    Lead enrichment
                                                              ↓
                                                    Database + Followup
```

**Comparison:** The current architecture MATCHES the intended architecture. The only difference is that old providers (Tabbly, Twilio, Plivo) still exist in the codebase as legacy code. The Sarvam path is complete and correctly wired.

---

## 6. Requirement-by-Requirement Comparison

| # | Requirement | Implementation | File:Function | Status | Evidence |
|---|---|---|---|---|---|
| 1 | Natural greeting | `sarvam_provider.py:_build_initial_bot_message` | line 155 | MOCK TESTED | Builds personalized greeting with name + requirement |
| 2 | Permission to continue | Part of initial_bot_message | line 165 | MOCK TESTED | "Is now a convenient time?" |
| 3 | Natural qualification | `ai/providers.py:TestLLMProvider.respond` | line 64 | MOCK TESTED (test provider only) | Regex-based extraction |
| 4 | Budget capture | `ai/providers.py:200-231` | lakh/crore/number extraction | MOCK TESTED | Unit tests verify |
| 5 | Location capture | `ai/providers.py:255-310` | city/area extraction | MOCK TESTED | Unit tests verify |
| 6 | Property type capture | `ai/providers.py:164-193` | BHK/flat/apartment extraction | MOCK TESTED | Captured as requirement, NOT recommended |
| 7 | Purpose capture | Not explicitly extracted | — | PARTIAL | Purpose not in TestLLMProvider |
| 8 | Purchase timeline | `ai/providers.py:237-253` | within X months/weeks | MOCK TESTED | Unit tests verify |
| 9 | Summary | `ai/conversation.py:_upsert_summary` | line 50 | MOCK TESTED | Written to CallSummary |
| 10 | Summary confirmation | Not implemented in TestLLMProvider | — | NOT IMPLEMENTED | No confirmation flow |
| 11 | Not interested | `ai/providers.py:100-110` | "not interested" phrases | MOCK TESTED | Sets DO_NOT_CONTACT |
| 12 | DND handling | `call_dispatcher.py:66-72` | DO_NOT_CALL check before dispatch | MOCK TESTED | Cancels instead of dispatching |
| 13 | Wrong number | `ai/providers.py` not explicitly handled | — | PARTIAL | No wrong number detection |
| 14 | Callback | `ai/providers.py:112-123` | "call me back" phrases | MOCK TESTED | Creates followup |
| 15 | Site visit interest | `ai/providers.py:125-138` | "site visit", "appointment" | MOCK TESTED | Sets appointment_requested |
| 16 | Site visit date | Not implemented | — | NOT IMPLEMENTED | No date/time capture |
| 17 | Site visit time | Not implemented | — | NOT IMPLEMENTED | No date/time capture |
| 18 | Explicit confirmation before booking | Not implemented | — | NOT IMPLEMENTED | Auto-books on appointment_requested |
| 19 | No property recommendation | CORRECT | — | PASS | No recommendation code exists |
| 20 | No inventory recommendation | CORRECT | — | PASS | No inventory code exists |
| 21 | Hindi | Sarvam agent handles | — | NOT TESTED LIVE | Agent configured in Sarvam dashboard |
| 22 | English | Sarvam agent handles | — | NOT TESTED LIVE | Agent configured in Sarvam dashboard |
| 23 | Hinglish | Sarvam agent handles | — | NOT TESTED LIVE | Agent configured in Sarvam dashboard |
| 24 | Agent variables | `sarvam_provider.py:_build_agent_variables` | line 142 | MOCK TESTED | call_id, lead_id, campaign_id, customer_name, city, requirement, budget, timeline |
| 25 | Call disposition | `call_lifecycle.py:_apply_outcome` | line 98 | MOCK TESTED | Maps outcome to LeadStatus |
| 26 | Transcript | `sarvam_webhook_service.py:264` | stores interaction_transcript | MOCK TESTED | Written to Call.transcript + CallMessage |
| 27 | Webhook | `app/api/routes/webhooks.py:364` | POST /webhooks/sarvam/status | MOCK TESTED | 12 tests verify |
| 28 | Lead enrichment | `sarvam_enrichment.py:apply_sarvam_enrichment` | line 160 | MOCK TESTED | 24 tests verify |
| 29 | Database persistence | PostgreSQL via SQLAlchemy | all models | MOCK TESTED | 140 tests use SQLite |
| 30 | Followup persistence | `followup_service.py:create_followup` | line 22 | MOCK TESTED | Created on callback |
| 31 | Mock call | `mock_provider.py:start_call` | line 19 | TESTED | Returns mock UUID |
| 32 | Sarvam outbound | `sarvam_provider.py:start_call` | line 179 | MOCK TESTED | urlopen patched in tests |
| 33 | Real telephony | — | — | NOT TESTED | No real call made |
| 34 | Real audio | — | — | NOT TESTED | No audio verified |
| 35 | Real STT | — | — | NOT TESTED | Key rejected (403) |
| 36 | Real TTS | — | — | NOT TESTED | Key rejected (403) |
| 37 | Latency | — | — | NOT TESTED | No real call timing |
| 38 | Interruption/barge-in | — | — | NOT APPLICABLE | Sarvam handles on their side |
| 39 | Error handling | `sarvam_provider.py:_request` | HTTP/URL/JSON errors | MOCK TESTED | Unit tests verify |
| 40 | Retry handling | `retry_service.py:create_retry_followup` | line 63 | MOCK TESTED | MAX_CALL_ATTEMPTS=3 |
| 41 | Webhook idempotency | `sarvam_webhook_service.py:189-204` | duplicate detection | MOCK TESTED | 12 tests verify |
| 42 | Security | `security.py:ApiKeyMiddleware` | API key auth | MOCK TESTED | Timing-safe comparison |
| 43 | Accidental call protection | `factory.py:24-28` + `config.py:15` | mock default, production guard | CONFIRMED | Cannot accidentally call |
| 44 | Production readiness | — | — | NOT READY | No real call tested, no production LLM |

---

## 7. Runtime Path Analysis

### PATH A — MOCK (CURRENTLY ACTIVE)

```
POST /api/leads          → LeadCreate → DB write → 201
POST /api/campaigns      → CampaignCreate → DB write → 201
POST /api/campaigns/1/leads/1 → CampaignLeadCreate → DB write → 201
POST /api/calls          → CallCreate → DB write + Redis enqueue → 201
POST /api/calls/1/start  → dispatch_call() → MockCallingProvider.start_call()
                         → returns "mock-{uuid}" → Call status=INITIATED → 200
POST /webhooks/sarvam/status → process_sarvam_webhook()
                         → resolve call → transition COMPLETED → store transcript
                         → apply_sarvam_enrichment() → update Lead → create Followup
```

**Verified by:** test_mock_call_flow.py (30 tests), test_free_trial_api.py (3 tests)

### PATH B — SARVAM (WIRING COMPLETE, NOT LIVE TESTED)

```
POST /api/calls/1/start  → dispatch_call() → SarvamCallingProvider.start_call()
                         → POST https://apps.sarvam.ai/api/outbounds/v1/.../outbounds
                         → returns attempt_id → Call status=INITIATED
                         ↓
Sarvam dials the phone → conversation happens on Sarvam's infrastructure
                         ↓
POST /webhooks/sarvam/status → process_sarvam_webhook()
                         → resolve by attempt_id or metadata.call_id
                         → transition with bridging
                         → store transcript from interaction_transcript
                         → apply_sarvam_enrichment() from final_agent_variables
                         → update Lead → create Followup if callback_requested
```

**NOT TESTED:** Real Sarvam API call, real webhook from Sarvam, real conversation

### PATH C — REAL TELEPHONY (NEVER TESTED)

Every component in this path has NEVER been tested with a real call:

| Component | File | Live Tested? |
|---|---|---|
| Sarvam outbound API | `sarvam_provider.py:179` | NO |
| Sarvam voice agent config | Sarvam dashboard | NO |
| Phone connection | Sarvam dashboard | NO |
| Phone number | Not obtained | NO |
| Real conversation | Sarvam infrastructure | NO |
| Webhook delivery | Public URL needed | NO |
| Webhook processing | `sarvam_webhook_service.py:141` | NO (unit tested only) |
| Enrichment from real data | `sarvam_enrichment.py:160` | NO |
| Lead field updates | DB writes | NO |
| Followup creation | DB writes | NO |

---

## 8. Sarvam Integration Audit

### 8.1 Outbound API

| Aspect | Verification | Status |
|---|---|---|
| Endpoint URL | `https://apps.sarvam.ai/api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds` | CONFIRMED BY DOCS + UNIT TEST |
| Auth header | `X-API-Key` | CONFIRMED BY DOCS + UNIT TEST |
| Request body schema | app_config, user_config, webhook_config | CONFIRMED BY DOCS + UNIT TEST |
| Response schema | `{ "attempt_id": string }` | CONFIRMED BY DOCS + UNIT TEST |
| Phone validation | E.164 strict before dispatch | CONFIRMED BY CODE + UNIT TEST |
| Agent variables | call_id, lead_id, campaign_id, customer_name, city, requirement, budget, timeline | CONFIRMED BY UNIT TEST |
| Initial bot message | Personalized with name + requirement | CONFIRMED BY UNIT TEST |
| Webhook URL | `{PUBLIC_BASE_URL}/webhooks/sarvam/status` | CONFIRMED BY CODE |
| Timeout | 30 seconds | CONFIRMED BY CODE |
| Error handling | HTTPError, URLError, JSONDecodeError | CONFIRMED BY UNIT TEST |
| API key redaction | `_redact_secrets()` in logs | CONFIRMED BY UNIT TEST |

### 8.2 Webhook Processing

| Aspect | Verification | Status |
|---|---|---|
| Call resolution by metadata.call_id | Primary resolution method | CONFIRMED BY UNIT TEST |
| Call resolution by attempt_id | Fallback resolution | CONFIRMED BY UNIT TEST |
| Status mapping | connected→COMPLETED, no_answer→NO_ANSWER, busy→BUSY, failed→FAILED | CONFIRMED BY UNIT TEST |
| State bridging | INITIATED→COMPLETED skips intermediate states | CONFIRMED BY UNIT TEST |
| Idempotency | Duplicate webhooks detected via `last_attempt_id` | CONFIRMED BY UNIT TEST |
| Transcript storage | Written to Call.transcript + CallMessage rows | CONFIRMED BY UNIT TEST |
| Recording URL | Built from org/workspace/app/interaction_id | CONFIRMED BY UNIT TEST |
| Enrichment trigger | Called after webhook processing | CONFIRMED BY UNIT TEST |
| Batch webhooks | List payloads supported | CONFIRMED BY UNIT TEST |

### 8.3 Enrichment

| Aspect | Verification | Status |
|---|---|---|
| Agent variable flattening | Nested→flat | CONFIRMED BY UNIT TEST |
| Budget parsing | lakh/crore/raw numbers | CONFIRMED BY UNIT TEST |
| Timeline parsing | "3 months", "immediately" | CONFIRMED BY UNIT TEST |
| Outcome inference | callback/appointment/interested/dnd/unqualified | CONFIRMED BY UNIT TEST |
| Lead field updates | budget, timeline, city, status, requirement | CONFIRMED BY UNIT TEST |
| CallSummary creation | summary, qualification, qualification_status | CONFIRMED BY UNIT TEST |
| Transcript ingestion | interaction_transcript → CallMessage rows | CONFIRMED BY UNIT TEST |
| Callback followup | Creates Followup when callback_requested | CONFIRMED BY UNIT TEST |
| Idempotency | Second enrichment returns enriched=False | CONFIRMED BY UNIT TEST |

### 8.4 What HAS NOT Been Verified

| Aspect | Status | Blocker |
|---|---|---|
| Real API call | NOT TESTED | Phone number + connection needed |
| Real webhook delivery | NOT TESTED | Public URL + phone needed |
| Real transcript content | NOT TESTED | Real conversation needed |
| Real agent variables | NOT TESTED | Real conversation needed |
| Real latency | NOT TESTED | Real call needed |
| Sarvam auth with `X-API-Key` | UNVERIFIED LIVE | Key works for `apps.sarvam.ai` but not verified |
| Sarvam auth for TTS/STT | FAILED (403) | `sk_samvaad_*` key rejected by `api.sarvam.ai` |

---

## 9. Voice Architecture Audit

### Does the current architecture need standalone TTS/STT?

**NO.** For the Sarvam Instant Outbound model:
- Sarvam handles ALL voice processing (TTS, STT, VAD, barge-in, codec, streaming)
- Our app only makes the outbound API call and receives the webhook
- Standalone TTS/STT are diagnostic tools only — not required for the calling architecture

### Voice component assessment

| Component | Needed? | Why |
|---|---|---|
| Standalone TTS | NOT NEEDED | Sarvam handles TTS during the call |
| Standalone STT | NOT NEEDED | Sarvam handles STT during the call |
| Custom audio streaming | NOT NEEDED | Sarvam handles all audio |
| WebSocket audio handling | NOT NEEDED | Not required for Instant Outbound |
| Codec conversion | NOT NEEDED | Sarvam handles |
| VAD | NOT NEEDED | Sarvam handles |
| Barge-in handling | NOT NEEDED | Sarvam handles |

### Standalone TTS/STT files

| File | Status | Safe to remove from critical path? |
|---|---|---|
| `app/services/sarvam_tts.py` | DIAGNOSTIC ONLY | YES — not wired into calling |
| `app/services/sarvam_stt.py` | DIAGNOSTIC ONLY | YES — not wired into calling |
| `scripts/test_sarvam_voice.py` | DIAGNOSTIC SCRIPT | YES — standalone test script |
| `tests/test_sarvam_voice.py` | UNIT TESTS | KEEP — validates API client code |

**These files are NOT blockers.** They can remain as diagnostic tools but should NOT delay the first real call.

---

## 10. Mock vs Integration vs Live Test Matrix

| Component | Unit Tested | API Tested | Integration Tested | Mock E2E | Live Tested |
|---|---|---|---|---|---|
| Lead CRUD | — | YES | YES | YES | NO |
| Campaign CRUD | — | YES | YES | YES | NO |
| Campaign-lead assignment | — | YES | YES | YES | NO |
| Call creation | — | YES | YES | YES | NO |
| Call dispatch (mock) | — | YES | YES | YES | NO |
| Call dispatch (sarvam) | YES | — | — | YES | NO |
| Call dispatch (tabbly) | YES | — | YES | YES | NO |
| Call lifecycle state machine | — | — | YES | YES | NO |
| Sarvam webhook processing | YES | — | YES | YES | NO |
| Sarvam enrichment | YES | — | — | YES | NO |
| Tabbly webhook processing | — | — | YES | YES | NO |
| Tabbly enrichment | YES | — | — | YES | NO |
| Followup creation | — | — | — | YES | NO |
| Followup processing | — | — | — | YES | NO |
| Retry logic | — | — | — | YES | NO |
| Phone validation | YES | — | — | — | NO |
| Security headers | — | YES | — | — | NO |
| Rate limiting | YES | YES | — | — | NO |
| API key auth | — | YES | — | — | NO |
| UI pages | — | YES | — | — | NO |
| Production config validation | YES | — | — | — | NO |
| TTS provider | YES | — | — | — | NO (403) |
| STT provider | YES | — | — | — | NO (403) |
| Real telephony | — | — | — | — | NO |
| Real conversation quality | — | — | — | — | NO |
| Real voice/TTS/STT | — | — | — | — | NO |
| Real latency | — | — | — | — | NO |

---

## 11. Test Suite Analysis

### Current test status

```
140 passed, 2 failed, 1 warning in 26.88s
```

### Test categorization

| Category | Count | Files |
|---|---|---|
| Unit tests | ~47 | test_phone_validation, test_conversation, test_call_log_sync, test_sarvam_enrichment, test_sarvam_voice, test_sarvam_provider, test_hardening |
| API tests | ~18 | test_admin_test_call, test_ui, test_security, test_hardening |
| Integration tests | ~15 | test_tabbly_integration, test_free_trial_api, test_mock_call_flow |
| Database tests | ~12 | test_sarvam_enrichment, test_sarvam_webhook, test_tabby_enrichment |
| Mock E2E tests | ~37 | test_mock_call_flow, test_free_trial_api, test_tabbly_integration |
| Safety/edge tests | ~11 | test_hardening, test_security, test_mock_call_flow edge cases |

### False confidence analysis

| Test | What it proves | What it does NOT prove |
|---|---|---|
| test_sarvam_provider.py | Request construction is correct | Actual API response handling |
| test_sarvam_webhook.py | Webhook processing logic works | Real webhook from Sarvam |
| test_sarvam_enrichment.py | Enrichment logic works | Real agent variables from a call |
| test_mock_call_flow.py | Full mock flow works end-to-end | Any real external interaction |
| test_sarvam_voice.py | TTS/STT client code works | Real API authentication or audio quality |

### The 2 failing tests

| Test | Root cause | Migration blocker? |
|---|---|---|
| `test_tabby_webhook_resolves_call_by_destination_fallback` | Tabbly webhook uses `called_to` but mock call has no phone | NO |
| `test_answered_call_with_conversation_completes_and_enriches` | Same root cause — Tabbly-specific | NO |

---

## 12. Old / Duplicate / Dead Code

| File | Lines | Status | Risk if removed now |
|---|---|---|---|
| `app/services/calling/tabbly_provider.py` | 544 | LEGACY — still wired, used by admin sync | MEDIUM — breaks admin sync |
| `app/services/tabbly_webhook_service.py` | 591 | LEGACY — still wired to /webhooks/tabbly/status | MEDIUM — breaks Tabbly webhook |
| `app/services/tabby_enrichment.py` | 323 | LEGACY — used by tabbly webhook + sync | MEDIUM — breaks Tabbly enrichment |
| `app/services/calling/twilio_provider.py` | 93 | DORMANT — wired but never tested | LOW |
| `app/services/twilio_webhook_service.py` | 64 | DORMANT — wired but unreachable | LOW |
| `app/services/calling/plivo_provider.py` | 74 | DEAD — NOT wired in factory | NONE |
| `app/workers/call_worker.py` | 98 | DEAD — only imported in tabbly_provider | LOW |
| `app/workers/tabby_sync_worker.py` | 49 | LEGACY — Celery beat sync for Tabbly | LOW |
| `app/services/call_log_sync.py` | 94 | LEGACY — Tabbly call-log reconciliation | LOW |
| `app/services/sarvam_tts.py` | 170 | DIAGNOSTIC — not in calling pipeline | NONE |
| `app/services/sarvam_stt.py` | 186 | DIAGNOSTIC — not in calling pipeline | NONE |
| Duplicate `plivo_speech_webhook` in webhooks.py | lines 300-361, 413-526 | DEAD — first definition overridden | NONE |
| `OPENAI_API_KEY` / `OPENAI_MODEL` in .env | — | UNUSED — never read by code | NONE |
| `APP_ENV`, `STT_MODE`, `TTS_MODE`, `AUTO_DISPATCH_CALLS` | — | UNUSED — placeholder env vars | NONE |
| `QualificationStatus` enum in enums.py | — | UNUSED — defined but never imported | NONE |
| `SystemInfo` model | — | MIGRATION ONLY — exists for initial migration | NONE |

### Key finding: `property_type` in enrichment

The `property_type` field appears in:
- `sarvam_enrichment.py:190,211` — captured from agent variables
- `tabby_enrichment.py:199,216` — captured from Tabbly JSON output
- `calls.py:243` — hardcoded in simulate endpoint

**This is NOT property recommendation.** It is a qualification data field captured from the lead's stated requirements. The agent asks "what type of property are you looking for?" and stores the answer. This matches the original product requirement to "capture property type."

---

## 13. Product Drift Analysis

| Signal | Status | Evidence |
|---|---|---|
| Property recommendation code | NOT FOUND | No code suggests properties to leads |
| Inventory/project selection | NOT FOUND | No project database or selection logic |
| Unnecessary LLM layers | NOT FOUND | Only one TestLLMProvider (regex-based) |
| Duplicate voice pipelines | NOT FOUND | Single pipeline: Sarvam outbound → webhook |
| Custom audio pipeline | NOT FOUND | Standalone TTS/STT are diagnostic only |
| Unused CRM code | NOT FOUND | No external CRM integration exists |
| Premature production code | MINOR | Production config validation exists but is appropriate |
| Unnecessary Celery workers | MINOR | 3 workers: call_worker (dead), followup_worker (active), tabby_sync (legacy) |
| Unnecessary Redis dependency | NO | Redis used for call queue and rate limiting — appropriate |
| Duplicate telephony providers | YES | 4 providers (tabbly, twilio, plivo, sarvam) — legacy accumulation |
| Duplicate webhook systems | YES | 3 webhook handlers (tabbly, twilio, sarvam) — legacy accumulation |

**Drift verdict:** The project has NOT drifted from the original product. Legacy code accumulation is expected during a migration. The core architecture still serves the original product goal.

---

## 14. Security / Configuration Risks

| Risk | Severity | Evidence | Location |
|---|---|---|---|
| `.env` contains real API keys | HIGH | Sarvam, Tabbly keys present | `.env` (should be gitignored) |
| `/ui/api/test-call` has no auth | HIGH | No API key middleware on /ui routes | `app/api/routes/ui.py:220` |
| `/webhooks/*` bypass auth | MEDIUM | Webhooks in open paths list | `app/core/security.py:24-26` |
| No Sarvam webhook signature verification | MEDIUM | No HMAC check on /webhooks/sarvam/status | `app/api/routes/webhooks.py:364` |
| No HTTPS enforcement (warning only) | MEDIUM | Production only warns, doesn't block | `app/core/config.py:127-134` |
| Missing API_KEY only warns | MEDIUM | Production doesn't enforce API key | `app/core/config.py:136-139` |
| Rate limiter not distributed | LOW | In-memory only, per-process | `app/core/rate_limit.py` |
| Rate limiter doesn't cover /webhooks/ or /ui/ | LOW | Only /api/ paths rate-limited | `app/core/rate_limit.py:85` |
| `PlivoCallingProvider` unreachable | LOW | Factory has no plivo branch | `app/services/calling/factory.py` |
| Typo aliases (TABLLY_*) | LOW | Intentional but confusing | `tabbly_provider.py:66-77` |

---

## 15. Real-Call Safety Analysis

### How accidental real calls are prevented

| Guard | Location | Effect |
|---|---|---|
| Default `CALLING_MODE=mock` | `config.py:15` | Mock provider used unless explicitly overridden |
| Production rejects mock providers | `factory.py:24-28` | Cannot set production + mock |
| Production rejects SQLite | `config.py:105-109` | Must use PostgreSQL in production |
| Production startup validation | `app/main.py:54-57` | App refuses to start with bad config |
| Phone E.164 validation | `phone_validation.py:16` | Rejects non-E.164 numbers before dispatch |
| DO_NOT_CALL check | `call_dispatcher.py:66-72` | Cancels call instead of dispatching |
| Simulate blocks real provider | `calls.py:36-41` | Cannot simulate when real provider configured |
| Tabby sync skips non-production | `tabby_sync_worker.py:29` | No Tabbly API calls in mock mode |

### Gaps

| Gap | Severity | Detail |
|---|---|---|
| `/ui/api/test-call` has no auth | HIGH | Anyone on the network can trigger a real call via UI if production mode is on |
| `/api/admin/test-call` requires API key only | MEDIUM | No additional confirmation for real calls |
| No webhook signature on Sarvam | MEDIUM | Spoofed webhook could trigger enrichment |

### Assessment

**The safety guards are SUFFICIENT for the current development phase.** The critical guard is `CALLING_MODE=mock` as default. A real call requires:
1. Explicitly setting `CALLING_MODE=production`
2. Setting `TELEPHONY_PROVIDER=sarvam` (or another real provider)
3. Having valid credentials in `.env`
4. Having a phone number and connection configured
5. Either calling `/api/calls/{id}/start` or `/api/admin/test-call`

None of these happen accidentally.

---

## 16. Current Blockers

| # | Blocker | Impact | Can be worked around? |
|---|---|---|---|
| 1 | No phone number obtained from Sarvam | Cannot make real calls | User action needed |
| 2 | No connection configured in Sarvam | Cannot make real calls | User action needed |
| 3 | No production LLM provider | Agent conversation is regex-based only | TestLLMProvider sufficient for testing |
| 4 | Sarvam TTS/STT key mismatch | Standalone voice testing blocked | Not needed for calling architecture |
| 5 | 2 pre-existing Tabbly test failures | Not blocking Sarvam path | Fix when removing Tabbly |

---

## 17. Missing Requirements

| # | Requirement | Status | Priority |
|---|---|---|---|
| 1 | Purpose capture | Not in TestLLMProvider | LOW — agent captures via variables |
| 2 | Summary confirmation flow | Not implemented | MEDIUM — agent should confirm before closing |
| 3 | Site visit date/time capture | Not implemented | MEDIUM — agent should capture specific slot |
| 4 | Wrong number detection | Not explicit | LOW — agent handles via disposition |
| 5 | Production LLM provider | Not implemented | HIGH — needed for real conversations |
| 6 | Real telephony verification | Not done | CRITICAL — blocks production |

---

## 18. What We Should NOT Do Yet

1. Do NOT remove Tabbly/Twilio/Plivo code — keep as fallback
2. Do NOT switch to production mode
3. Do NOT make a real call
4. Do NOT integrate external CRM
5. Do NOT implement a production LLM (not needed for Sarvam — Sarvam handles conversation)
6. Do NOT add standalone TTS/STT to the calling pipeline
7. Do NOT refactor the calling architecture
8. Do NOT remove dead code (Plivo, call_worker) — low risk but no urgency

---

## 19. Exact Remaining Phases

### Phase 0 — Fresh Audit (COMPLETE)
This document.

### Phase 1 — Sarvam Dashboard Setup (USER ACTION)
1. Create Voice Agent in Sarvam dashboard
2. Add telephony connection (rent from Sarvam or bring Exotel/Twilio)
3. Get phone number + Connection ID
4. Update `.env` with real values
5. Set webhook URL to public server

### Phase 2 — Pre-flight Safety Test (CODE + USER)
1. Verify all `.env` values are correct
2. Test webhook delivery with a manual POST
3. Verify Sarvam dashboard shows the agent

### Phase 3 — First Real Call (USER GO + CODE)
1. User explicitly says GO
2. Call `/api/admin/test-call` with a test number
3. Verify: call initiated, webhook received, enrichment applied

### Phase 4 — Real Conversation Verification (CODE + USER)
1. Review transcript from first call
2. Verify agent variables captured correctly
3. Verify lead enrichment worked
4. Verify followup created if callback requested

### Phase 5 — Multiple Call Testing (CODE + USER)
1. Test with 3-5 different leads
2. Test all dispositions (interested, not interested, callback, DND)
3. Measure latency
4. Review conversation quality

### Phase 6 — Production Hardening (CODE)
1. Redis-based webhook dedup
2. TTL eviction for `last_attempt_id`
3. Monitoring/alerting
4. Remove dead code (Plivo, call_worker)

### Phase 7 — Old Provider Cleanup (CODE)
1. Remove Tabbly provider + webhook + enrichment
2. Remove Twilio provider + webhook
3. Remove Plivo provider + routes
4. Remove Celery workers no longer needed

---

## 20. Exact Test Plan For Each Phase

### Phase 1 — Dashboard Setup
- Verify `.env` has all required Sarvam values
- Verify `SARVAM_CONNECTION_ID` is non-empty
- Verify `SARVAM_AGENT_PHONE_NUMBER` is non-empty

### Phase 2 — Pre-flight
- `python -c "from app.services.calling.factory import get_calling_provider; p = get_calling_provider(); print(type(p))"` with production env → should return `SarvamCallingProvider`
- Manual webhook POST to `/webhooks/sarvam/status` → should return `success=True, handled=False`
- `curl /health/config` → should show no errors

### Phase 3 — First Call
- `POST /api/admin/test-call` with test phone → verify `success=True, call.status=INITIATED`
- Wait for webhook → verify `status=COMPLETED` or `NO_ANSWER`
- Check `GET /api/calls/{id}` → verify transcript, duration, recording_url
- Check `GET /api/leads/{id}` → verify status updated

### Phase 4 — Conversation
- Review `CallSummary` → verify qualification fields populated
- Review `CallMessage` rows → verify transcript parsed into messages
- Check `Lead.budget`, `Lead.timeline`, `Lead.city` → verify enrichment
- If callback → check `Followup` created with `PENDING` status

### Phase 5 — Multiple Calls
- Repeat Phase 3-4 for 3-5 leads
- Test with Hindi, English, Hinglish conversations
- Test DND scenario → verify `DO_NOT_CALL` status
- Test wrong number → verify appropriate disposition
- Measure webhook latency

---

## 21. What OpenCode Must Do

1. **Write the test script** for Phase 2 pre-flight verification
2. **Monitor first real call** and verify all data flows
3. **Review transcript quality** after first calls
4. **Implement production hardening** after calls are proven
5. **Clean up legacy code** after Sarvam path is stable
6. **Fix the 2 Tabbly test failures** when removing Tabbly

---

## 22. What I Must Provide

1. **Sarvam dashboard access** — create Voice Agent, add connection
2. **Phone number** — from Sarvam or telephony provider
3. **Connection ID** — from Sarvam dashboard
4. **Public webhook URL** — or use ngrok for testing
5. **Explicit GO** — before any real call
6. **Test phone numbers** — numbers to call for testing
7. **Sarvam AI API key** — for TTS/STT if standalone voice testing is desired (separate from Samvaad key)

---

## 23. Definition of Done

| Milestone | Done when |
|---|---|
| Mock backend verified | All 140 tests pass (2 Tabbly failures acceptable) |
| Sarvam integration verified | First real call placed, webhook received, enrichment applied |
| Voice quality verified | Transcript shows natural conversation, no awkward pauses |
| Multiple calls verified | 3-5 calls with different dispositions all work |
| Production ready | Redis dedup, monitoring, no dead code, all tests pass |

---

## 24. Recommended Next Action

**NO REAL CALL SHOULD BE MADE YET.**

The ONE next action is:

**Set up the Sarvam Voice Agent in the Sarvam dashboard:**
1. Go to Sarvam dashboard
2. Create a Voice Agent
3. Add a telephony connection (rent a number or connect Exotel/Twilio)
4. Note the Connection ID and phone number
5. Update `.env` with `SARVAM_CONNECTION_ID` and `SARVAM_AGENT_PHONE_NUMBER`

This is a USER ACTION. No code changes needed.

---

## CURRENT STATUS:

- **Overall architecture:** PASS
- **Product alignment:** PASS
- **Mock backend:** PASS
- **Sarvam integration:** PARTIAL (wired but not live tested)
- **Voice:** NOT VERIFIED (standalone TTS/STT blocked by wrong key type)
- **Telephony:** NOT TESTED
- **Webhook:** PASS (unit + integration tested)
- **Database:** PASS
- **Security:** PARTIAL (UI routes unprotected, no Sarvam webhook auth)
- **Production readiness:** NOT READY

---

## TOP 5 PROBLEMS

1. No real call has ever been placed — all verification is in mock/test mode
2. No production LLM provider (TestLLMProvider is regex-based only)
3. Standalone TTS/STT blocked by wrong API key type (Samvaad vs AI platform)
4. UI routes (`/ui/api/test-call`) have no authentication — can dispatch real calls without auth
5. 2 pre-existing Tabbly test failures (not blocking)

## TOP 5 THINGS ALREADY WORKING

1. Complete mock call flow end-to-end (140 tests pass)
2. Sarvam outbound provider correctly wired and unit-tested
3. Sarvam webhook processing with idempotency and state bridging
4. Sarvam enrichment correctly populates lead fields and summary
5. Safety guards prevent accidental real calls (CALLING_MODE=mock default)

## WHAT MUST NOT BE TOUCHED YET

- Tabbly provider + webhook + enrichment (keep as fallback)
- Twilio provider + webhook (keep as fallback)
- Plivo provider + routes (dead but harmless)
- Production mode settings
- Phone configuration
- Real calling
- External CRM

## EXACT NEXT STEP

Set up the Sarvam Voice Agent in the Sarvam dashboard (user action — no code).
