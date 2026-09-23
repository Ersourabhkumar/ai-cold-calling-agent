# Environment Variables

**Date:** 2026-09-21

---

## Required Variables

### Database
```
DATABASE_URL=postgresql+psycopg://coldcalling:coldcalling_dev_password@localhost:5432/cold_calling_db
```
**Status:** REQUIRED
**Used by:** Database connection

### Sarvam Voice Agent
```
SARVAM_API_KEY=<your-api-key>
SARVAM_ORG_ID=<your-org-id>
SARVAM_WORKSPACE_ID=<your-workspace-id>
SARVAM_APP_ID=<your-app-id>
SARVAM_APP_VERSION=1
SARVAM_CONNECTION_ID=<your-connection-id>
SARVAM_AGENT_PHONE_NUMBER=+91804XXXXXXX
```
**Status:** REQUIRED (for production)
**Used by:** SarvamCallingProvider

### Application
```
PUBLIC_BASE_URL=https://your-domain.com
```
**Status:** REQUIRED (for webhooks)
**Used by:** Webhook URL construction

### Calling Mode
```
CALLING_MODE=mock
```
**Status:** REQUIRED
**Values:** `mock` (development) | `production` (live calls)
**Used by:** Provider factory

---

## Optional Variables

### Redis
```
REDIS_URL=redis://localhost:6379/0
```
**Status:** OPTIONAL
**Used by:** Celery broker, call queue

### API Security
```
API_KEY=<your-api-key>
```
**Status:** OPTIONAL (recommended in production)
**Used by:** ApiKeyMiddleware

### Rate Limiting
```
RATE_LIMIT_PER_MINUTES=120
```
**Status:** OPTIONAL
**Default:** 120
**Used by:** RateLimitMiddleware

### Call Configuration
```
MAX_CALL_ATTEMPTS=3
RETRY_DELAY_MINUTES=30
CALLBACK_DELAY_MINUTES=1440
```
**Status:** OPTIONAL
**Defaults:** 3, 30, 1440
**Used by:** retry_service, call_config

---

## Legacy Variables (Remove After Migration)

### Tabbly
```
TABBLY_API_KEY=
TABBLY_AGENT_ID=
TABBLY_PHONE_NUMBER=
TABBLY_ORGANIZATION_ID=
TABBLY_WEBHOOK_SECRET=
TABBLY_START_FUTURE_MINUTES=5
```
**Status:** REMOVE after Sarvam migration

### Twilio
```
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
```
**Status:** REMOVE after Sarvam migration

### Plivo
```
PLIVO_AUTH_ID=
PLIVO_AUTH_TOKEN=
PLIVO_PHONE_NUMBER=
```
**Status:** REMOVE after Sarvam migration

### LLM
```
LLM_MODE=test
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```
**Status:** REMOVE (Sarvam handles LLM)

---

## Development-Only Variables

```
APP_ENV=development
TELEPHONY_PROVIDER=mock
STT_MODE=mock
TTS_MODE=mock
AUTO_DISPATCH_CALLS=false
```
**Status:** DEVELOPMENT ONLY
**Used by:** Local testing

---

## Complete .env.example (Target)

```env
# Database
DATABASE_URL=postgresql+psycopg://coldcalling:coldcalling_dev_password@localhost:5432/cold_calling_db

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# Application
PUBLIC_BASE_URL=http://localhost:8000

# Calling Mode
CALLING_MODE=mock

# Sarvam Voice Agent
SARVAM_API_KEY=
SARVAM_ORG_ID=
SARVAM_WORKSPACE_ID=
SARVAM_APP_ID=
SARVAM_APP_VERSION=1
SARVAM_CONNECTION_ID=
SARVAM_AGENT_PHONE_NUMBER=

# API Security (optional in dev)
API_KEY=

# Rate Limiting
RATE_LIMIT_PER_MINUTE=120

# Call Configuration
MAX_CALL_ATTEMPTS=3
RETRY_DELAY_MINUTES=30
CALLBACK_DELAY_MINUTES=1440
```
