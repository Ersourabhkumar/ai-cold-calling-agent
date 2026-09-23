# Runbook

**Date:** 2026-09-21

---

## Local Development

### Terminal 1: Database + Redis
```bash
docker compose up -d postgres redis
```
**Must remain open:** No (runs in background)
**What happens if closed:** Database and Redis stop

### Terminal 2: API Server
```bash
cd ai-cold-calling-agent
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```
**Must remain open:** Yes
**What happens if closed:** Dashboard and API unavailable

### Terminal 3: Celery Worker (Optional)
```bash
cd ai-cold-calling-agent
uv run celery -A app.core.celery_app worker --loglevel INFO --pool=solo -Q calling
```
**Must remain open:** Yes (if using background dispatch)
**What happens if closed:** Calls must be dispatched manually

### Terminal 4: Celery Beat (Optional)
```bash
cd ai-cold-calling-agent
uv run celery -A app.core.celery_app beat --loglevel INFO
```
**Must remain open:** Yes (if using scheduled follow-ups)
**What happens if closed:** Follow-ups not auto-processed

### Terminal 5: Webhook Tunnel (Production)
```bash
# Option A: Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8000

# Option B: ngrok
ngrok http 8000
```
**Must remain open:** Yes (for webhook delivery)
**What happens if closed:** Sarvam webhooks cannot reach your server

---

## Docker Compose (All-in-One)

```bash
docker compose up --build
```

Runs: API (auto-migrate), PostgreSQL, Redis, Celery worker, Celery beat

**Must remain open:** Yes
**What happens if closed:** All services stop

---

## First-Time Setup

```bash
# 1. Copy environment
Copy-Item .env.example .env

# 2. Edit .env with Sarvam credentials
notepad .env

# 3. Install dependencies
uv sync --group dev

# 4. Create database tables
uv run alembic upgrade head

# 5. Start services
docker compose up -d postgres redis
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## Restart Procedure

```bash
# Stop all
docker compose down

# Start database
docker compose up -d postgres redis

# Run migrations
uv run alembic upgrade head

# Start API
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Database health
curl http://localhost:8000/health/db

# Redis health
curl http://localhost:8000/health/redis

# Readiness
curl http://localhost:8000/health/ready

# Config
curl http://localhost:8000/health/config
```

---

## Webhook Setup

### For Development (Cloudflare Tunnel)
```bash
cloudflared tunnel --url http://localhost:8000
# Use the generated URL as PUBLIC_BASE_URL in .env
# Register https://<tunnel-url>/webhooks/sarvam/status in Sarvam dashboard
```

### For Development (ngrok)
```bash
ngrok http 8000
# Use the generated URL as PUBLIC_BASE_URL in .env
# Register https://<ngrok-url>/webhooks/sarvam/status in Sarvam dashboard
```

### For Production
```bash
# Set PUBLIC_BASE_URL to your production domain
# Ensure SSL certificate is valid
# Register https://your-domain.com/webhooks/sarvam/status in Sarvam dashboard
```

---

## Troubleshooting

### "SARVAM_API_KEY is not configured"
- Set SARVAM_API_KEY in .env

### "Webhook not receiving events"
- Check PUBLIC_BASE_URL is accessible from internet
- Check tunnel is running (dev) or DNS is configured (prod)
- Check webhook URL registered in Sarvam dashboard

### "Call not connecting"
- Check SARVAM_CONNECTION_ID is correct
- Check agent phone number is valid
- Check Sarvam account has credits
- Check target number is not DND registered

### "Database connection failed"
- Check docker compose up -d postgres
- Check DATABASE_URL in .env
- Check PostgreSQL is running
