from __future__ import annotations

import logging

from celery import Task

from app.core.celery_app import celery_app
from app.database.connection import SessionLocal
from app.models.call import Call
from app.models.enums import CallStatus
from app.services.call_dispatcher import dispatch_call


logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """
    Base Celery task.
    """

    abstract = True


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.workers.call_worker.dispatch_queued_call",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 3},
)
def dispatch_queued_call(
    self,
    call_id: int,
) -> dict:

    db = SessionLocal()

    try:

        call = db.get(Call, call_id)

        if call is None:
            logger.warning(
                "Call %s not found",
                call_id,
            )

            return {
                "success": False,
                "call_id": call_id,
                "error": "Call not found",
            }

        if call.status != CallStatus.QUEUED:
            logger.info(
                "Call %s is already in status %s",
                call_id,
                call.status.value,
            )

            return {
                "success": True,
                "call_id": call.id,
                "status": call.status.value,
                "provider": call.provider,
                "provider_call_id": call.provider_call_id,
            }

        updated_call = dispatch_call(
            db,
            call,
        )

        return {
            "success": True,
            "call_id": updated_call.id,
            "status": updated_call.status.value,
            "provider": updated_call.provider,
            "provider_call_id": updated_call.provider_call_id,
        }

    except Exception:

        db.rollback()

        logger.exception(
            "Failed to dispatch call %s",
            call_id,
        )

        raise

    finally:

        db.close()