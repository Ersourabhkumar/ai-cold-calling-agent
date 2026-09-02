# Production runbook

## Decision

Use **Plivo India** as the first production telephony candidate. Its published India price is ₹0.38/min for domestic outbound calls, ₹200/month for a domestic number, and audio streaming is included. Its Voice API supports real-time audio streams over WebSocket and bidirectional audio. By comparison, Twilio documents that calls to Indian recipients must originate from international (non-Indian) numbers, which makes it a poor fit for a domestic Indian cold-calling operation.

The code includes a `PlivoCallingProvider` selected with:

```env
CALLING_MODE=production
TELEPHONY_PROVIDER=plivo
PLIVO_AUTH_ID=
PLIVO_AUTH_TOKEN=
PLIVO_PHONE_NUMBER=
PUBLIC_BASE_URL=https://your-public-domain
```

It initiates calls and validates Plivo V3 webhook signatures. It is **not sufficient to enable live AI calls yet**: the production audio WebSocket, streaming STT/TTS, barge-in logic, authentication, and live acceptance tests remain a release gate.

## India compliance gate

Before using `CALLING_MODE=production`:

1. Register the business as the appropriate Principal Entity/telemarketer and retain auditable customer consent.
2. Complete the provider's India KYC and attach an accepted compliance application to the caller number.
3. Use a number series permitted for the actual call type. Plivo documents 140-series numbers for promotional voice calls, while ordinary landline series are service/transactional only.
4. Enforce `DO_NOT_CALL` immediately, maintain consent records, and obtain legal advice for the campaign and target audience.

TRAI says commercial senders must register and obtain customer consent; Plivo rejects calls whose Indian caller number lacks an accepted compliance application or is suspended for UCC complaints. This is a hard launch blocker, not an optional checklist item.

## Published cost basis (checked 31 August 2026)

| Component | Published rate | Source |
| --- | ---: | --- |
| Plivo domestic outbound | ₹0.38/min | [Plivo India Voice Pricing](https://www.plivo.com/voice/pricing/in/) |
| Plivo domestic number | ₹200/month | [Plivo India Voice Pricing](https://www.plivo.com/voice/pricing/in/) |
| Plivo audio streaming | Included | [Plivo India Voice Pricing](https://www.plivo.com/voice/pricing/in/) |
| Plivo multilingual TTS | ₹0/min | [Plivo India Voice Pricing](https://www.plivo.com/voice/pricing/in/) |
| Plivo ASR | ₹1.70 / 15 seconds | [Plivo India Voice Pricing](https://www.plivo.com/voice/pricing/in/) |
| OpenAI GPT-5.6 Luna text | $0.20 input / $1.20 output per million tokens | [OpenAI Models](https://developers.openai.com/api/docs/models) |

Cost estimates below use only those published rates. They assume 3 answered minutes/call, one number, and a compact text turn budget of 1,000 input + 400 output tokens/call. Plivo bills answered calls with a 60-second minimum; unanswered, busy, and failed calls are documented as unbilled.

| Answered calls/month | Voice + number (₹) | GPT-5.6 Luna text ($) | Plivo ASR if run for all 3 minutes (₹) |
| ---: | ---: | ---: | ---: |
| 100 | 314 | 0.07 | 2,040 |
| 500 | 770 | 0.34 | 10,200 |
| 1,000 | 1,340 | 0.68 | 20,400 |
| 5,000 | 5,900 | 3.40 | 102,000 |
| 10,000 | 11,600 | 6.80 | 204,000 |

The tables deliberately exclude cloud infrastructure and any alternative STT provider because neither a deployment region nor a tested STT vendor has been selected. They also do not convert USD to INR; exchange rates are volatile. The cost implication is clear: keep prompts compact, summarize state, use the small text model for routine turns, and benchmark an external streaming STT before paying Plivo's full-duration ASR rate.

## Production implementation sequence

1. Provision an India-region Plivo account, finish KYC/DLT/consent work, rent the appropriate compliant number, and configure an HTTPS public domain.
2. Add a streaming audio worker: validate the Plivo WebSocket, consume audio chunks, run streaming STT, send bounded context to the LLM, synthesize audio, and use `clearedAudio`/the provider's clear mechanism for barge-in.
3. Add an authenticated CRM user model, role checks, API rate limiting, secret manager, structured logs with request/call/lead/provider IDs, and alerting.
4. Deploy API, worker, scheduler, PostgreSQL, and Redis with `docker compose` only for development; use managed PostgreSQL/Redis and a process manager/orchestrator in production.
5. Set `CALLING_MODE=production` only in a staging account first. Verify signatures, webhook replay handling, status ordering, media reconnects, provider timeouts, and call recording retention.
6. Run a consented pilot with a small internal list. Reconcile provider call detail records against `call_events`, then expand only after error rate, latency, opt-out handling, and costs are acceptable.

## Mandatory pre-release tests

- Normal, busy, no-answer, failed, invalid-number, cancellation, and retry-cap paths.
- Duplicate and out-of-order webhooks; provider and database outage recovery.
- Consent, opt-out, wrong-number, callback, appointment, rejection, silence, interruption, and long-call cases.
- STT/TTS/LLM timeout and fallback behavior; no secret values in logs.
- Barge-in and audio latency under the target network conditions.

## Free local testing vs production

The mock free trial is intentionally isolated from all paid services. It uses deterministic text, a mock telephony provider, and no Redis requirement for call creation. Production uses the same `CallingProvider` boundary but must add the audio pipeline described above before it can be considered a real voice agent.
