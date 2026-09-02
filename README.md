# AI Cold Calling Agent

A real-estate cold-calling system that **dials real prospects through Tabbly's AI voice agent**, records the conversation, extracts qualification data automatically, updates the CRM, and schedules follow-ups — all with a clean browser dashboard.

```
Lead → Campaign → Celery → Tabbly AI calls prospect → Transcript + JSON
  → Qualification → CRM update → Follow-up scheduled
```

**Current status: fully working and demo-proven (live).** The agent answered a real call in Hindi/Hinglish, understood "3 BHK villa, Jaipur, ₹1.2 crore, investment", and the system stored the qualification and marked the lead `QUALIFIED`.

---

## 🚀 Quick start (browser UI — no curl needed)

The simplest way to use the whole system is the built-in dashboard.

```powershell
# 1. One-time setup
Copy-Item .env.example .env        # edit .env with your Tabbly keys (below)
uv sync --group dev                # install dependencies
alembic upgrade head               # create tables

# 2. Run the API (opens the dashboard + all JSON APIs)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000** in your browser. You'll land on the dashboard with a sidebar:

| Page | What it does |
|---|---|
| **Dashboard** | Overview counts + recent calls & leads |
| **Leads / CRM** | Add leads, see all prospects & status, click one for full history |
| **Calls** | Every outbound call, status, outcome, duration |
| **Follow-ups** | Auto-created retries / callbacks |
| **Fire Live Call** | Create lead + dispatch one real Tabbly call, then watch it update |

From the **Fire Live Call** page you can fill a small form (phone, name, requirement, budget) and dispatch a real call — no commands needed.

---

## 🔑 The `.env` file (Tabbly production)

Set these to dial **real** calls through Tabbly:

| Variable | Purpose |
|---|---|
| `CALLING_MODE=production` | Enables live provider dispatch |
| `TELEPHONY_PROVIDER=tabbly` | Selects the Tabbly adapter |
| `TABBLY_API_KEY` | Tabbly API key (required) |
| `TABBLY_AGENT_ID` | The calling agent id |
| `TABBLY_PHONE_NUMBER` | The agent's calling number (must match account) |
| `TABBLY_ORGANIZATION_ID` | Enables call-log auto-sync + enrichment |
| `TABBLY_WEBHOOK_SECRET` | Optional webhook signature secret |
| `LLM_MODE=test` | Deterministic local engine (no paid LLM key needed) |

> ⚠️ **Important**: Tabbly dials each call on its own schedule — the window opens **~5 minutes** after you dispatch it. Keep the phone ready during that window.

---

## ❓ Why do I see background cmd/python windows?

Those are the **FastAPI server** and **Celery worker/beat** running in the background (redirected to log files, no popups). The system needs them to:
- serve the dashboard/API on port `8000`
- poll Tabbly every 60s (`sync-tabby-call-logs`) to fetch completed calls, transcripts and enrich the CRM
- process scheduled follow-ups

You can stop them anytime with a Ctrl+C if you started them yourself, or kill the process on port 8000. They are normal and expected for this app.

---

## ▶️ How to run it again later (in the future)

Every time you want to restart the project:

```powershell
# Start the real database stack (Postgres + Redis)
docker compose up -d

# Start the API (dashboard + APIs)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# (recommended) Celery worker + beat for auto-sync & follow-ups
uv run celery -A app.core.celery_app worker --loglevel INFO --pool=solo -Q calling
uv run celery -A app.core.celery_app beat --loglevel INFO
```

Open **http://127.0.0.1:8000** → done.

---

## 👥 How to share this project with someone

1. **Share the code**: zip the repo (or push to GitHub). The person runs `.env.example` → `uv sync` → migrations → start (above).
2. **Share as a live demo**: start the server, then give them a link to `http://{your-ip}:8000`. Anyone on your network can open the dashboard in their browser — no install needed.
3. **For public/backoffice sharing**: set `API_KEY` in `.env` to protect the `/api/*` endpoints (the dashboard stays open for easy use). See *Production hardening*.

---

## 👤 How to add a lead to the CRM (future)

You have three options — all create a lead that can then be called:

1. **UI (easiest)**: go to **Leads / CRM → + Add Lead**, fill the form, Save. It appears instantly.
2. **API (for scripts/integrations)**:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/leads \
     -H "Content-Type: application/json" \
     -d '{"name":"Rahul","phone":"+919876543210","city":"Jaipur","requirement":"2 BHK flat","budget":"50 lakh","timeline":"1-3 months"}'
   ```
3. **Bulk import**: add rows via the API in a loop, or through a small script that calls `/api/leads`.

After a lead is added, put it in a campaign and create a call (UI **Fire Live Call** does all three automatically, or use the `/api/calls` flow for campaigns with many leads).

---

## 🏠 The dashboard (UI)

- **Dark, responsive** — works on desktop and mobile.
- **Fire Live Call** form → dispatches one real call, shows the call id, and a **Refresh Status** box to watch it live until it completes.
- **Lead detail** shows every call, the transcript, structured qualification (property/BHK/location/budget/purpose), and all follow-ups.
- The dashboard reuses the same authenticated JSON APIs, so anything you can do in the UI you can automate via API.

---

## 📦 Project layout (short)

```
app/
├── main.py                  # FastAPI app + dashboard route wiring
├── api/routes/              # API + admin + UI dashboard routes
├── models/                  # DB tables (lead, campaign, call, ...)
├── services/
│   ├── calling/             # Tabbly / Twilio / Plivo / mock providers
│   ├── ai/                  # local test-LM engine + conversation
│   ├── tabby_enrichment.py  # transcript → qualification → CRM
│   └── call_log_sync.py     # poll Tabbly every 60s
├── workers/                 # Celery tasks (call, follow-up, sync)
└── templates/               # dashboard HTML
tests/                       # 44 tests, all passing
```

---

## 🧪 Tests & verification

```powershell
uv run pytest -q        # 44 tests pass
```

Covers provider dispatch, the Tabbly webhook lifecycle, the answer→complete→enrich flow (including the "answered after no-answer" edge case), qualification extraction, security/hardening, and the new UI.

---

## 🔧 Production hardening

When `API_KEY` is set, `/api/*` endpoints require `X-API-Key`. Rate limiting, security headers, request tracing and health checks (`/health`, `/health/db`, `/health/redis`, `/health/ready`, `/health/config`) are built in. Full runbook: [`docs/PRODUCTION_RUNBOOK.md`](docs/PRODUCTION_RUNBOOK.md).

### Docker Compose

```powershell
docker compose up --build
```

Runs API (auto-migrate), PostgreSQL, Redis, Celery worker and beat.

---

## 📜 Lifecycle guarantee

`QUEUED → INITIATED → RINGING → ANSWERED → IN_PROGRESS → COMPLETED`

Terminal statuses (`NO_ANSWER`, `BUSY`, `FAILED`) auto-create a capped retry follow-up; a completed conversation enriches the lead and assigns a qualification/outcome.

Swagger API docs: **http://127.0.0.1:8000/docs**
