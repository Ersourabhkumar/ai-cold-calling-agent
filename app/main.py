import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env before importing services that read environment variables
load_dotenv()

from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

# Import models so SQLAlchemy resolves all relationship mappings at startup.
from app.models import (
    Call,
    CallEvent,
    CallMessage,
    CallSummary,
    Campaign,
    CampaignLead,
    Followup,
    Lead,
)

from app.api.routes.leads import router as leads_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.campaign_leads import router as campaign_leads_router
from app.api.routes.calling_queue import router as calling_queue_router
from app.api.routes.calls import router as calls_router
from app.api.routes import followups
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.admin import router as admin_router
from app.api.routes.ui import router as ui_router

from app.core.config import is_production, validate_production_config
from app.core.rate_limit import RateLimitMiddleware
from app.core.request_context import RequestContextMiddleware, setup_logging
from app.core.redis import check_redis
from app.core.security import ApiKeyMiddleware, SecurityHeadersMiddleware
from app.database.connection import engine

logger = logging.getLogger(__name__)

setup_logging()


def _run_startup_checks() -> None:
    health = validate_production_config()

    for warning in health.warnings:
        logger.warning("startup warning: %s", warning)

    if is_production() and not health.ok:
        summary = "; ".join(health.errors)
        logger.error("startup aborted on production config errors: %s", summary)
        raise RuntimeError(f"Production configuration invalid: {summary}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_startup_checks()
    logger.info("application started (mode=%s, provider=%s)",
                is_production() and "production" or "development",
                os.getenv("TELEPHONY_PROVIDER", "tabbly"))
    yield
    logger.info("application shutting down")


app = FastAPI(
    title="AI Cold Calling Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ApiKeyMiddleware)

app.include_router(leads_router)
app.include_router(campaigns_router)
app.include_router(campaign_leads_router)
app.include_router(calling_queue_router)
app.include_router(calls_router)
app.include_router(followups.router)
app.include_router(webhooks_router)
app.include_router(admin_router)
app.include_router(ui_router)


@app.get("/")
def root():
    return RedirectResponse(url="/ui", status_code=302)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ai-cold-calling-agent",
        "version": "1.0.0",
    }


@app.get("/health/db")
def database_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "dependency": "database",
        }

    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "dependency": "database",
            },
        )


@app.get("/health/redis")
def redis_health_check():
    if check_redis():
        return {
            "status": "ok",
            "dependency": "redis",
        }

    return JSONResponse(
        status_code=503,
        content={
            "status": "unavailable",
            "dependency": "redis",
        },
    )


@app.get("/health/config")
def config_health_check():
    health = validate_production_config()
    return {
        "status": "ok" if health.ok else "error",
        "errors": health.errors,
        "warnings": health.warnings,
    }


@app.get("/health/ready")
def readiness_checks():
    """Readiness: database and Redis must both be reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = check_redis()

    if not (db_ok and redis_ok):
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "database": "ok" if db_ok else "error",
                "redis": "ok" if redis_ok else "error",
            },
        )

    return {
        "status": "ready",
        "database": "ok",
        "redis": "ok",
    }