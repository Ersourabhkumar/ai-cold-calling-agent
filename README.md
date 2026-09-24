# 📞 AI Cold Calling Agent

> Autonomous AI voice agent for real-estate outbound calling — dials real prospects, holds natural Hindi / Hinglish conversations, extracts qualification data, updates the CRM, and schedules follow-ups automatically.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.6-37814A.svg)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Live & production-tested.** The agent places real calls via **Sarvam Voice Agent (Instant Outbound)**, qualifies leads (BHK, budget, city, timeline, intent), and writes everything — transcript, recording, qualification, outcome — back to PostgreSQL.

---

## 📑 Table of Contents

- [How It Works](#-how-it-works)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [API Reference](#-api-reference)
- [Call Lifecycle](#-call-lifecycle)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Security](#-security)
- [Cost Estimate](#-cost-estimate)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)

---

## 🔄 How It Works

```text
Lead → Campaign → Redis Queue → Celery Worker
  → Sarvam Instant Outbound API → prospect's phone rings
  → AI voice conversation (Hindi / Hinglish, lead-aware)
  → Sarvam webhook → transcript + recording
  → Auto-enrichment → qualification + outcome + CRM update
  → Follow-up scheduled (retry / callback)
```

Everything is visible in the browser dashboard at `http://localhost:8000/ui`.

---

## ✨ Features

**📇 Lead & Campaign Management**

- Full CRM — add, import, search, and track leads with status (`NEW → CONTACTED → QUALIFIED / ...`)
- CSV bulk import with phone validation (E.164, `+91` + 10 digits)
- Campaigns with `DRAFT / ACTIVE` guard — no accidental dialing
- Dry-run dispatch preview before spending money

**📞 Real AI Calling (Sarvam)**

- Instant outbound dialing — phone rings within seconds
- Natural Hindi / Hinglish voice, lead-aware (already knows requirement, budget, city)
- Transcript, recording URL, duration, and per-call cost captured automatically
- Mock provider (`CALLING_MODE=mock`) for free local testing — zero spend

**🧠 Auto-Qualification**

- Extracts `property_type, bhk, budget, city, timeline, interest_level, appointment_day/time`
- Classifies outcome: `APPOINTMENT_BOOKED / INTERESTED / CALLBACK / NOT_INTERESTED / ...`
- Updates the lead record + creates `CallSummary` + `Qualification` rows

**🔁 Follow-ups & Retries**

- Terminal states (`NO_ANSWER`, `BUSY`, `FAILED`) → capped auto-retry
- Callback requests → timed `PENDING` follow-up, processed by Celery Beat
- Manual + automatic follow-up tracking in one page

**🖥️ Dashboard UI**

- Dark, responsive, mobile-friendly — Dashboard, Leads, Calls, Follow-ups, Lead Detail, Fire Live Call
- One-click **Fire Live Call** — fill a form, dispatch a real call, watch status live
- Per-call cost split + usage page

**🔌 Integrations**

- Generic CRM webhook — forwards every completed call as JSON (Zoho / HubSpot / Sheets / custom)
- Native CRM connector base class ready (`app/services/crm/`)
- Health checks, request tracing, rate limiting, API-key auth built in

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI, Uvicorn, Pydantic |
| DB / Migrations | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| Queue / Jobs | Redis 7, Celery (worker + beat) |
| Voice AI | Sarvam Voice Agent — STT / LLM / TTS / Telephony |
| Frontend | Jinja2 + vanilla JS (server-rendered dashboard) |
| DevOps | Docker Compose, `uv` package manager, pytest |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11, [uv](https://docs.astral.sh/uv/), Docker Desktop
- A Sarvam account with a Voice Agent (only for live calls — mock mode needs nothing)

### 1. Setup

```powershell
# Clone & configure
Copy-Item .env.example .env   # fill Sarvam keys (see below)

# Install deps + create tables
uv sync --group dev
alembic upgrade head

# Start infrastructure
docker compose up -d postgres redis
```

### 2. Run (4 terminals)

```powershell
# Terminal 1 — API + dashboard
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — public webhook tunnel (required for Sarvam callbacks)
cloudflared tunnel --url http://localhost:8000
# → copy the https://...trycloudflare.com URL into .env as PUBLIC_BASE_URL, restart Terminal 1

# Terminal 3 — background worker
uv run celery -A app.core.celery_app.celery_app worker --loglevel=INFO --pool=solo

# Terminal 4 — scheduler (follow-ups)
uv run celery -A app.core.celery_app.celery_app beat --loglevel=INFO
```

Open **http://localhost:8000/ui** → done. 🎉

> **Free trial (no spend):** keep `CALLING_MODE=mock` in `.env` — the full Lead → Call → Transcript → Qualification loop runs locally with simulated conversations.

### Docker (one command)

```powershell
docker compose up --build
```

Runs API (auto-migrate) + Postgres + Redis + worker + beat.

---

## ⚙️ Configuration

Key variables in `.env` (see `.env.example` for the full list):

| Variable | Example | Purpose |
|---|---|---|
| `CALLING_MODE` | `mock` / `production` | `mock` = free simulation, `production` = real dialing |
| `TELEPHONY_PROVIDER` | `sarvam` | Voice provider selector |
| `SARVAM_API_KEY` | `sk_...` | Sarvam dashboard → API key |
| `SARVAM_ORG_ID` / `SARVAM_WORKSPACE_ID` | `...` | Workspace settings |
| `SARVAM_APP_ID` | `...` | Your Voice Agent app |
| `SARVAM_APP_VERSION` | `1` | Bump this every time you commit agent changes |
| `SARVAM_CONNECTION_ID` | `...` | Telephony connection |
| `SARVAM_AGENT_PHONE_NUMBER` | `+91...` | Caller ID shown to prospects |
| `PUBLIC_BASE_URL` | `https://xxx.trycloudflare.com` | Webhook callback URL for Sarvam |
| `API_KEY` | `xy-admin-key` | Protects `/api/*` via `X-API-Key` header |
| `CRM_PROVIDER` / `CRM_WEBHOOK_URL` | `none` / `webhook` | Optional CRM forwarding |
| `DATABASE_URL` / `REDIS_URL` | `postgresql+psycopg://...` | Infra connection strings |

Health: `GET /health/ready` → `{"status":"ready","database":"ok","redis":"ok"}`

---

## 📖 Usage

### A. Single live call (dashboard — easiest)

1. Open `http://localhost:8000/ui` → enter API key in the sidebar (once)
2. Go to **Fire Live Call** → fill phone (`+91...`), name, city, requirement, budget
3. Use a **unique campaign name** every time (e.g. `Team-2026-09-24-A`)
4. Click **Fire Live Call** → prospect's phone rings in seconds
5. After the call, click **Refresh Status** → transcript, qualification, recording appear; lead flips to `QUALIFIED` / `CALLBACK` / etc.

### B. Single live call (API / Swagger)

Swagger docs: `http://localhost:8000/docs` → Authorize (`X-API-Key`) → `POST /api/admin/test-call`:

```json
{
  "phone": "+917822007138",
  "lead_name": "Test Lead",
  "city": "Mumbai",
  "requirement": "2 BHK flat",
  "budget": "5000000",
  "timeline": "3 months",
  "campaign_name": "UNIQUE-NAME-HERE"
}
```

Check status: `POST /api/admin/test-call/status` with `{ "call_id": 12 }`.

### C. Bulk campaign calling

```text
1. POST /api/campaigns                          → create campaign
2. PATCH /api/campaigns/{id} {"status":"ACTIVE"} → activate (safety guard)
3. POST /api/campaigns/{id}/leads/{lead_id}      → assign leads (or POST /api/leads/import for CSV)
4. POST /api/campaigns/{id}/dispatch {"dry_run": true}            → safe preview (eligible / skipped)
5. POST /api/campaigns/{id}/dispatch {"dry_run": false, "max_calls": 50} → live dial
```

Rules: DND leads auto-skip · max-attempts leads skip · inactive campaign → `409` · `max_calls` caps spend (default 50, max 500).

### D. CSV import

```csv
name,phone,city,requirement,budget,timeline
Asha Sharma,+919000000041,Jaipur,2 BHK,50 lakh,3 months
```

Swagger → `POST /api/leads/import` → upload → response shows `created` + per-row `failed` reasons.

### E. CRM forwarding (optional)

```env
CRM_PROVIDER=webhook
CRM_WEBHOOK_URL=https://your-crm/incoming-webhook
```

Every completed call POSTs:

```json
{
  "event": "call.completed",
  "call_id": 12,
  "lead_id": 5,
  "lead": { "name": "...", "phone": "+91..." },
  "outcome": "APPOINTMENT_BOOKED",
  "duration_seconds": 80,
  "recording_url": "...",
  "qualification": { "bhk": "2", "budget_amount": 5000000 }
}
```

Failures never block the call flow (best-effort + logged). Default `CRM_PROVIDER=none` = fully local.

---

## 📡 API Reference

Full interactive docs: **`http://localhost:8000/docs`**

| Area | Endpoints |
|---|---|
| Leads | `POST /api/leads` · `GET /api/leads` · `GET /api/leads/{id}` · `POST /api/leads/import` |
| Campaigns | `POST /api/campaigns` · `PATCH /api/campaigns/{id}` · `POST /api/campaigns/{id}/leads/{lead_id}` · `POST /api/campaigns/{id}/dispatch` |
| Calls | `GET /api/calls` · `GET /api/calls/{id}` · `POST /api/admin/test-call` · `POST /api/admin/test-call/status` |
| Follow-ups | `GET /api/followups` · `POST /api/followups` |
| Queue | `GET /api/queue` (calling queue status) |
| Webhooks | `POST /webhooks/sarvam/*` (provider callbacks — open, no API key) |
| Health | `GET /health` · `/health/db` · `/health/redis` · `/health/ready` · `/health/config` |

Auth: when `API_KEY` is set, send `X-API-Key: <value>` on all `/api/*` and `/ui/api/*` requests.

---

## 📜 Call Lifecycle

```text
QUEUED → INITIATED → RINGING → ANSWERED → IN_PROGRESS → COMPLETED
                                              ├→ NO_ANSWER / BUSY / FAILED → auto-retry follow-up
                                              └→ CALLBACK_REQUESTED → timed callback follow-up
```

A `COMPLETED` call always produces: transcript → `CallSummary` + `Qualification` → lead update → optional CRM webhook.

---

## 🧪 Testing

```powershell
uv run pytest -q
```

Covers: mock call flow, Sarvam provider + webhooks, enrichment/qualification, campaign dispatch (dry-run, DND skip, caps), CSV import, phone validation, CRM forwarding, auth/rate-limit hardening, and UI routes.

---

## 🐳 Deployment

- **Local / demo:** `docker compose up -d postgres redis` + uvicorn + Celery (see Quick Start)
- **Full stack:** `docker compose up --build` (API + Postgres + Redis + worker + scheduler)
- **Production:** set `API_KEY`, `RATE_LIMIT_PER_MINUTE`, real `DATABASE_URL`/`REDIS_URL`, HTTPS `PUBLIC_BASE_URL`; runbook in [`docs/PRODUCTION_RUNBOOK.md`](docs/PRODUCTION_RUNBOOK.md); team SOP in [`docs/12_USAGE_GUIDE.md`](docs/12_USAGE_GUIDE.md)

---

## 🔒 Security

- `X-API-Key` auth on all `/api/*` routes (webhooks + health stay open for providers/monitors)
- Per-IP rate limiting, security headers, request-ID tracing
- E.164 phone validation before any dial (invalid numbers never reach Sarvam)
- `ACTIVE`-only dispatch guard + `max_calls` cap prevent accidental bulk spend

---

## 💰 Cost Estimate

Sarvam pricing (approx): **~₹9–10 per 80-sec call** (₹4.50/min voice + ₹0.40/min telephony).

| Volume | Approx. cost |
|---|---|
| 1 call | ~₹10 |
| 200 calls/day | ~₹1,900/day (~₹50k/month) |

Per-call cost breakdown is visible in the dashboard Usage page. To reduce cost: shorten the agent prompt (fewer questions) and improve conversion — the per-minute rate is fixed.

---

## 📁 Project Structure

```text
app/
├── main.py                 # FastAPI app, middleware, health checks
├── api/routes/             # leads, campaigns, calls, followups, webhooks, admin, ui
├── models/                 # Lead, Campaign, Call, CallMessage, CallSummary, Qualification, Followup
├── services/
│   ├── calling/            # Sarvam + mock providers, dispatcher, lifecycle
│   ├── ai/                 # conversation engine (test-LLM + OpenAI path)
│   ├── crm/                # webhook + native connector base
│   ├── sarvam_enrichment.py# transcript → qualification → CRM update
│   └── *.py                # lead, campaign, followup, retry, queue services
├── workers/                # Celery tasks (dispatch, sync, follow-ups)
├── core/                   # config, security, rate-limit, redis, validation
└── templates/              # dashboard UI (Jinja2)
tests/                      # 16 test modules, full flow coverage
docs/                       # runbooks, architecture, usage SOP
migrations/                 # Alembic migrations
```

---

## 🆘 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 Invalid API key` | Key missing in Swagger/UI | Authorize in Swagger or sidebar key field |
| `409 campaign exists` | Reused campaign name | Use a fresh unique name per call |
| Call stuck in `INITIATED` | Webhook never returned | Check `cloudflared` tunnel is live + `PUBLIC_BASE_URL` matches |
| `502` on Swagger | Opened tunnel URL in browser | Always use `localhost:8000/docs` locally |
| Sarvam `401` on dispatch | Wrong API key | Verify Settings → API Key in Sarvam dashboard |
| Sarvam `422` on dispatch | Undeclared agent variable | Declare the variable name from the error in the agent |
| `/health/ready` error | Postgres/Redis down | `docker compose up -d postgres redis` |

---

## 🗺️ Roadmap

- [ ] Native Zoho / HubSpot / Salesforce connectors
- [ ] Full login + role-based access (replace single API key)
- [ ] Real-time call streaming in the dashboard (WebSocket)
- [ ] Bulk retry dashboard + DND list management UI
- [ ] Hosted deployment (domain + HTTPS + managed Postgres/Redis)

---

## 📄 License

MIT — see [LICENSE](LICENSE) (add one if missing).

---

<p align="center">Built with ❤️ for high-velocity real-estate sales teams.<br/>Star ⭐ the repo if it helped you close faster.</p>
