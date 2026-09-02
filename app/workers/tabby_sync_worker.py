from __future__ import annotations

import os

from celery import Task

from app.core.celery_app import celery_app
from app.database.connection import SessionLocal
from app.services.call_log_sync import sync_tabby_call_logs as _sync_tabby_call_logs


class DatabaseTask(Task):
    """Base Celery task for database lifecycle."""

    abstract = True


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.workers.tabby_sync_worker.sync_tabby_call_logs",
)
def sync_tabby_call_logs(
    self,
    limit: int = 50,
) -> dict:
    """Periodically reconcile local call records with Tabbly call logs."""

    if os.getenv("CALLING_MODE", "mock").lower() != "production":
        return {
            "success": True,
            "skipped": "CALLING_MODE is not production",
        }

    db = SessionLocal()

    try:
        result = _sync_tabby_call_logs(db, limit=limit)
        return {
            "success": True,
            **result,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
    finally:
        db.close()