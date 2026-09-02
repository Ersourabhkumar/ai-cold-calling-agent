# AI Cold Calling Agent — Demo Guide (show to Sir)

## 1. What this project does (one line)
An end-to-end **AI outbound cold-calling system**: a lead is stored in the CRM, a
campaign is created, a call is queued, Celery dispatches it to **Tabbly**, Tabbly's
AI voice agent **calls the prospect and has a real conversation**, and the result
(transcript, qualification, sentiment, summary, follow-up) lands back in PostgreSQL.

## 2. Architecture (10-second diagram)

```
Lead → Campaign → Queue (Redis) → Celery (queue "calling")
   → Tabbly campaign + contact (create-campaign / add-campaign-contacts)
   → Tabbly scheduler dials the number  →  REAL PHONE RINGS
   → AI voice conversation (agent 7174)  →  call_logs-v2 poll sync
   → Enrichment → CallSummary + Qualification + Lead update + Follow-up (PostgreSQL)
```

Stack (Docker): `cold-calling-postgres` (Postgres 16) + `cold-calling-redis` (Redis 7).
App: FastAPI on `http://127.0.0.1:8000`, Celery worker (queue `calling`), Celery beat (sync every 60s).

## 3. Start the stack (exact commands)

```powershell
docker start cold-calling-postgres cold-calling-redis

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run celery -A app.core.celery_app worker --pool=solo -Q calling --loglevel INFO
uv run celery -A app.core.celery_app beat --loglevel INFO
```

Check health: `GET http://127.0.0.1:8000/health/ready` → `{"status":"ready","database":"ok","redis":"ok"}`

## 4. The live demo (5 minutes with Sir) — via the UI dashboard

The whole demo is now **click-only** — no commands needed while showing Sir.

1. Open the dashboard in the browser: **http://127.0.0.1:8000** (auto-redirects to `/ui`).
2. Show the **Dashboard** (lead/call/follow-up counts), **Leads / CRM** (prospects +
   status), **Calls**, and **Follow-ups** pages.
3. Go to **Fire Live Call**, fill the form (phone, name, requirement, budget, campaign
   name) and click **"Fire Live Call"**. It dispatches a real Tabbly call and shows the
   call id. (API equivalent: `POST /api/admin/test-call`.)
4. **~5 minutes later the phone rings.** Sir answers — the AI (now lead-aware, so it
   already knows the requirement/budget and speaks Hindi/Hinglish naturally) qualifies
   the lead in ~60–100 seconds.
5. Click **"Refresh Status"** in the UI → the call flips to `COMPLETED`, showing
   `outcome` (e.g. `APPOINTMENT_BOOKED`), duration, and the full qualification
   (property/BHK/location/budget/purpose).
6. Open the **Leads / CRM** page → click the lead → show the transcript and the
   qualification, and confirm the lead status changed to `QUALIFIED`.

> Automated verification: `uv run pytest -q` → 44 tests pass, including the
> "answered after no-answer" edge case that closes the live loop.

## 5. What to show in the Database (pgAdmin)

pgAdmin → Register server: Host `127.0.0.1`, Port `5432`, DB `cold_calling_db`,
user `coldcalling`, password `coldcalling_dev_password`.

Verify with these queries (Tools → Query Tool):

```sql
-- the call and its Tabbly status
select id, provider, provider_call_id, status, duration_seconds, recording_url
from calls order by id desc limit 5;

-- AI qualification captured from the voice call
select c.id, q.source, q.property_type, q.bhk, q.budget_amount,
       q.timeline, q.interest_level, q.appointment_required
from calls c left join qualifications q on q.call_id = c.id
order by c.id desc limit 5;

-- lead updated by the AI conversation
select id, name, status, requirement, budget, timeline from leads order by id desc limit 5;

-- follow-up created when the lead asked for a callback
select * from followups order by id desc limit 5;
```

## 6. Key environment variables (.env)

| Variable | Value | Purpose |
| --- | --- | --- |
| `TELEPHONY_PROVIDER` | `tabbly` | Live provider |
| `TABBLY_API_KEY` | (dashboard) | Auth |
| `TABBLY_AGENT_ID` | `7174` | The AI voice agent |
| `TABBLY_PHONE_NUMBER` | `08065830111` | Must match the agent's number on Tabbly |
| `TABBLY_ORGANIZATION_ID` | `3701` | Enables call-log sync / campaign re-activation |
| `CALLING_MODE` | `production` | Real dialing (not mock) |

## 7. Trouble-shooting checklist

- No ring? Re-activate the campaign: `POST /api/admin/tabby/campaigns/{call_id}/activate`,
  then watch the dashboard campaign status.
- Status stuck `INITIATED`? The beat/sync task needs `TABBLY_ORGANIZATION_ID`; also poll
  the status endpoint manually.
- Phone mismatch error? Run `GET /api/admin/test-call/status` and set `TABBLY_PHONE_NUMBER`
  to whatever `get-agents` returns for the agent.
- Remember: **active campaign ≠ success**. Success = the phone rings and Tabbly shows a
  call-log row (`call_status`).