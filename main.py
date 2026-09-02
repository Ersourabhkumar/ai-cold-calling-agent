from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.models import Lead, Campaign, CampaignLead, Followup

from app.api.routes.leads import router as leads_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.campaign_leads import router as campaign_leads_router
from app.api.routes.calling_queue import router as calling_queue_router
from app.api.routes.calls import router as calls_router
from app.api.routes import followups
from app.api.routes.webhooks import router as webhooks_router
from app.core.redis import check_redis
from app.database.connection import engine

app = FastAPI(
    title="AI Cold Calling Agent",
    version="0.1.0",
)


app.include_router(leads_router)
app.include_router(campaigns_router)
app.include_router(campaign_leads_router)
app.include_router(calling_queue_router)
app.include_router(calls_router)
app.include_router(followups.router)
app.include_router(webhooks_router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ai-cold-calling-agent",
    }


@app.get("/health/db")
def database_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "dependency": "database"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "dependency": "database"},
        )


@app.get("/health/redis")
def redis_health_check():
    if check_redis():
        return {"status": "ok", "dependency": "redis"}
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "dependency": "redis"},
    )
