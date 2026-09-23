# 10. Sarvam Voice Readiness Audit

> **Audit date:** 2026-09-21
> **Last updated:** 2026-09-21 (Phase 6C complete)
> **Auditor:** opencode (mimo-v2-pro-max)

---

## Executive Summary

The Sarvam migration is **functionally complete for mock mode**. The app can create a lead, create a campaign, start a call in mock, simulate a Sarvam webhook, and enrich the lead. **140 tests pass, 2 pre-existing Tabbly tests fail** (not migration blockers).

**Standalone TTS and STT are now implemented** and unit-tested. Live voice quality testing requires a `SARVAM_API_KEY` but no phone number. No real call has been placed. No audio quality, latency, or voice behavior has been verified against a live API key.

---

## 1. Test Suite Status

```
140 passed, 2 failed, 1 warning in 43.26s
```

| Test file | Status | Notes |
|---|---|---|
| `test_sarvam_provider.py` | PASS | Unit + integration tests for `SarvamProvider` |
| `test_mock_call_flow.py` | PASS | 30 Sarvam-specific scenarios |
| `test_call_simulation.py` | PASS | End-to-end simulation flow |
| `test_enrichment.py` | PASS | Lead enrichment tests |
| `test_sarvam_voice.py` | PASS | 21 tests — TTS + STT + dataclasses |
| `test_tabbly_integration.py::test_tabby_webhook_resolves_call_by_destination_fallback` | **FAIL** | Pre-existing |
| `test_tabbly_integration.py::test_answered_call_with_conversation_completes_and_enriches` | **FAIL** | Pre-existing |

**Verdict:** Not migration blockers. Fix when removing Tabbly (Phase 5).

---

## 2. Sarvam API Verification (vs. Current Official Docs)

Verified against live docs fetched 2026-09-21.

### Instant Outbound API — CONFIRMED MATCH

| Check | Docs | Codebase | Status |
|---|---|---|---|
| Endpoint | `POST /api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds` | `sarvam_provider.py:19` | MATCH |
| Path params | `org_id`, `workspace_id` | `SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID` | MATCH |
| `app_config.app_id` | required | `SARVAM_APP_ID` | MATCH |
| `app_config.app_version` | required (int) | `SARVAM_APP_VERSION` | MATCH |
| `app_config.connection_config.connection_id` | required | `SARVAM_CONNECTION_ID` | MATCH |
| `app_config.connection_config.agent_phone_number` | required | `SARVAM_AGENT_PHONE_NUMBER` | MATCH |
| `app_config.agent_variables` | optional (map) | passed from `start_call()` | MATCH |
| `user_config.user_phone_number` | required | `to_number` param | MATCH |
| `webhook_config.url` | optional | `SARVAM_WEBHOOK_URL` | MATCH |
| Response | `{ "attempt_id": string }` | `result["attempt_id"]` | MATCH |

### TTS API — CONFIRMED MATCH

| Check | Docs | Codebase (`sarvam_tts.py`) | Status |
|---|---|---|---|
| Endpoint | `POST https://api.sarvam.ai/text-to-speech` | `_TTS_URL` | MATCH |
| Auth header | `api-subscription-key` | `headers["api-subscription-key"]` | MATCH |
| `text` | required (string) | `payload["text"]` | MATCH |
| `language_code` | required (BCP-47) | `payload["language_code"]` | MATCH |
| `speaker` | optional (default: shubh) | `payload["speaker"]` (default: priya) | MATCH |
| `model` | optional (bulbul:v3) | `payload["model"]` | MATCH |
| `speech_sample_rate` | optional (24000) | `payload["speech_sample_rate"]` | MATCH |
| `pace` | optional (1.0) | `payload["pace"]` | MATCH |
| Response | `{ "request_id", "audios": [base64] }` | `data["audios"][0]` | MATCH |
| Speaker `priya` | supported in bulbul:v3 | Used | MATCH |

### STT API — CONFIRMED MATCH

| Check | Docs | Codebase (`sarvam_stt.py`) | Status |
|---|---|---|---|
| Endpoint | `POST https://api.sarvam.ai/speech-to-text` | `_STT_URL` | MATCH |
| Auth header | `api-subscription-key` | `headers["api-subscription-key"]` | MATCH |
| Content-Type | `multipart/form-data` | multipart with boundary | MATCH |
| `file` | required (audio file) | audio bytes in multipart | MATCH |
| `model` | optional (saaras:v3) | `payload["model"]` | MATCH |
| `language_code` | optional (BCP-47) | `payload["language_code"]` | MATCH |
| `mode` | optional (transcribe) | `payload["mode"]` | MATCH |
| Response | `{ "request_id", "transcript", "language_code" }` | parsed correctly | MATCH |
| Hindi support | `hi-IN` | Supported | MATCH |
| English support | `en-IN` | Supported | MATCH |
| Auto-detect | `unknown` | Supported | MATCH |

### Authentication — FAILED (live, 2026-09-22)

- TTS/STT header name (`api-subscription-key`) matches the docs; unit tests confirm it is sent.
- The key stored in `.env` is **rejected by `api.sarvam.ai`** for both TTS and STT: HTTP 403 `invalid_api_key_error`, "Invalid or missing authentication credentials".
- No docs-vs-behavior schema difference was found — the failure is auth-only. Cause not determined (not guessing): the key may be expired/revoked, scoped differently, or the wrong key for these endpoints.
- Outbound API auth (`X-API-Key` against `apps.sarvam.ai`) is **still unverified live** — no live outbound call has been made (per constraints).
- Voice quality, latency, and STT accuracy are **unverified** — blocked on a working key.

### Webhook Payload — CONFIRMED MATCH

| Check | Docs | Codebase (`SarvamWebhookPayload`) | Status |
|---|---|---|---|
| `attempt_id` | required | `attempt_id` | MATCH |
| `status` | `connected`/`no_answer`/`busy`/`failed` | Same in `SarvamStatus` | MATCH |
| `channel_info` | required | `channel_info` | MATCH |
| `duration` | number or null | `duration` | MATCH |
| `interaction_id` | string or null | `interaction_id` | MATCH |
| `failure_reason` | string or null | `failure_reason` | MATCH |
| `final_agent_variables` | object or null | `agent_variables` | MATCH |
| `webhook_config` | object or null | `webhook_config` | MATCH |
| `interaction_transcript` | array of `{role, en_text}` | `interaction_transcript` | MATCH |

---

## 3. Standalone TTS Test

**Result:** Unit tests PASS (9 tests). **Live test FAIL — HTTP 403 `invalid_api_key_error` on all 10 cases (2026-09-22).**

Live run (`python scripts/test_sarvam_voice.py` with the key from `.env`):

| # | Case | TTS | Latency | Error |
|---|---|---|---|---|
| 1 | English greeting | FAIL | ~1244ms | HTTP 403 `invalid_api_key_error` |
| 2 | Hindi greeting | FAIL | ~1262ms | HTTP 403 `invalid_api_key_error` |
| 3 | Hinglish greeting | FAIL | ~1219ms | HTTP 403 `invalid_api_key_error` |
| 4–10 | Budget/location/type/timeline/site-visit | FAIL | ~1216–1306ms | HTTP 403 `invalid_api_key_error` |

Exact error body (no key leaked):
`{"error":{"message":"Invalid or missing authentication credentials","code":"invalid_api_key_error","request_id":"20260922_..."}}`

Request format, endpoint, and header name match the docs (verified by unit tests) — only the key itself was rejected. No audio was generated; nothing was saved to `scripts/voice_test_output/`.

**Voice/Config:**
- Model: `bulbul:v3`
- Speaker: `priya` (matches Priya agent)
- Language: `hi-IN`, `en-IN`
- Sample rate: 24000 Hz
- Pace: 1.0

**Generated audio location:** `scripts/voice_test_output/` (when run with live API key)

**Test coverage:**
- English TTS synthesis
- Hindi TTS synthesis
- Hinglish TTS synthesis
- Empty audio handling
- HTTP error handling (403, 500)
- Network error handling
- JSON parse error handling
- API key redaction in logs
- Timeout handling

---

## 4. Standalone STT Test

**Result:** Unit tests PASS (10 tests). **Live test FAIL — HTTP 403 `invalid_api_key_error` (2026-09-22).**

- Round-trip (TTS audio → STT) could not run: TTS produced no audio.
- Direct auth probe with a synthetic 16 kHz silent WAV (`en-IN`) also returned HTTP 403 `invalid_api_key_error` (~1730ms), same error body as TTS.
- Request format (multipart `file` + `model` + `language_code` + `mode`) matches the docs (verified by unit tests) — only the key itself was rejected.

**Language behavior:**
- Hindi (`hi-IN`): Supported
- English (`en-IN`): Supported
- Hinglish (code-mixed): Supported via `hi-IN` with `codemix` mode
- Auto-detect (`unknown`): Supported

**Test coverage:**
- Hindi transcription
- English auto-detect
- HTTP error handling (429)
- Network error handling
- JSON parse error handling
- API key redaction in logs
- Multipart body construction
- Timeout handling

**Round-trip test:** The script supports TTS → STT round-trip (generate audio, transcribe, compare). This tests voice quality end-to-end without a phone.

---

## 5. Voice Pipeline Architecture

### What the app does NOT handle (delegated to Sarvam)

| Component | Status | Notes |
|---|---|---|
| Real-time audio streaming | **NOT IN CODEBASE** | Sarvam handles telephony end-to-end |
| WebRTC / SIP | **NOT IN CODEBASE** | Not needed for Instant Outbound model |
| Audio codec conversion | **NOT IN CODEBASE** | Sarvam handles |
| VAD / silence detection | **NOT IN CODEBASE** | Sarvam handles |
| Interruption / barge-in | **NOT IN CODEBASE** | Sarvam handles |
| Phone number management | **NOT IN CODEBASE** | Done in Sarvam dashboard |

### Standalone STT/TTS (now implemented)

| API | Endpoint | In Codebase | Unit Tested |
|---|---|---|---|
| STT (Saaras v3) | `POST https://api.sarvam.ai/speech-to-text` | `app/services/sarvam_stt.py` | YES (10 tests) |
| TTS (Bulbul v3) | `POST https://api.sarvam.ai/text-to-speech` | `app/services/sarvam_tts.py` | YES (9 tests) |

---

## 6. Architecture Audit: Old vs. New

### Components that will be removed in Phase 5

| File | Lines | Purpose | Status |
|---|---|---|---|
| `app/services/calling/tabbly_provider.py` | 371 | Tabbly provider | **DEAD CODE** |
| `app/services/tabbly_webhook_service.py` | 493 | Tabbly webhook handler | **ACTIVE** — will be removed |
| `app/services/calling/twilio_provider.py` | 416 | Twilio provider | **DORMANT** |
| `app/services/twilio_webhook_service.py` | 211 | Twilio webhook handler | **DORMANT** |
| `app/workers/call_worker.py` | 197 | Celery worker | **DEAD CODE** |
| `app/api/routes/plivo.py` | 129 | Plivo routes | **DUPLICATE** |

### What remains useful

| Component | Status |
|---|---|
| `app/services/calling/sarvam_provider.py` | Active |
| `app/services/sarvam_webhook_service.py` | Active |
| `app/services/sarvam_enrichment.py` | Active |
| `app/services/sarvam_tts.py` | Active (NEW) |
| `app/services/sarvam_stt.py` | Active (NEW) |
| `app/services/calling/mock_provider.py` | Active |
| `scripts/test_sarvam_voice.py` | Active (NEW) |

---

## 7. What Was Verified WITHOUT a Phone Number

| Item | Verified | Method |
|---|---|---|
| TTS API endpoint | YES | Official docs + unit test |
| TTS request format | YES | Official docs + unit test |
| TTS response format | YES | Official docs + unit test |
| TTS auth method | YES | `api-subscription-key` header confirmed |
| TTS speaker `priya` | YES | Listed in bulbul:v3 speakers |
| STT API endpoint | YES | Official docs + unit test |
| STT request format | YES | Official docs + unit test |
| STT response format | YES | Official docs + unit test |
| STT auth method | YES | `api-subscription-key` header confirmed |
| STT Hindi/English support | YES | `hi-IN`, `en-IN` language codes |
| Outbound API schema | YES | Official docs + unit test |
| Webhook payload schema | YES | Official docs + unit test |
| API key redaction in logs | YES | Unit test verifies |
| Error handling (HTTP, network, timeout) | YES | Unit tests verify |
| Voice quality (actual audio) | **NO** | Blocked — key rejected (403) |
| Voice latency (actual) | **NO** | Blocked — key rejected (403) |
| STT accuracy (actual) | **NO** | Blocked — key rejected (403) |

## 8. What Still Requires Telephony

| Item | Required | Phase |
|---|---|---|
| Phone number | Connection + number in Sarvam dashboard | 6A |
| Real outbound call | Phone number + Connection ID | 6B |
| Webhook delivery | Public URL + phone number | 6B |
| End-to-end voice quality | Real call with audio | 6C (live) |
| Agent prompt tuning | Real conversations | 6D |
| Production mode | All above verified | Phase 7+ |

---

## 9. Files Created in Phase 6C

| File | Purpose |
|---|---|
| `app/services/sarvam_tts.py` | Standalone TTS provider (Bulbul v3) |
| `app/services/sarvam_stt.py` | Standalone STT provider (Saaras v3) |
| `scripts/test_sarvam_voice.py` | Live voice quality test script |
| `tests/test_sarvam_voice.py` | 21 unit tests with mocked HTTP |
| `docs/10_SARVAM_VOICE_READINESS.md` | This document |

---

## 10. Recommended Next Steps

### Phase 6D: Resolve API key (BLOCKED — needs user action, no code)
- Live TTS/STT both return HTTP 403 `invalid_api_key_error` with the current key.
- Provide a valid Sarvam API key with TTS/STT scope (verify in Sarvam dashboard), then re-run:
```bash
python scripts/test_sarvam_voice.py
```
- This needs no phone number and changes no calling/telephony code.
- Only after TTS/STT return 200 should voice quality, latency, and accuracy be assessed.

### Phase 7: Sarvam Dashboard Setup (manual)
1. Create Voice Agent in Sarvam dashboard
2. Add telephony connection (rent from Sarvam or bring Exotel/Twilio)
3. Get phone number + Connection ID
4. Update `.env`
5. Set webhook URL

### Phase 8: Production Hardening
1. Redis-based dedup for webhooks
2. TTL eviction for `last_attempt_id`
3. Monitoring/alerting
4. Remove dead code (Tabbly, Twilio, Plivo, call_worker)
