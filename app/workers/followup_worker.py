from celery import Task

from app.core.celery_app import celery_app
from app.database.connection import SessionLocal
from app.services.followup_scheduler import (
    process_followup,
)
from app.services.followup_service import (
    get_pending_followups,
)


class DatabaseTask(Task):
    """
    Base Celery task for database lifecycle.
    """

    abstract = True


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name=(
        "app.workers.followup_worker."
        "process_pending_followups"
    ),
)
def process_pending_followups(
    self,
) -> dict:

    db = SessionLocal()

    processed = 0
    failed = 0

    try:

        followups = get_pending_followups(
            db,
            limit=100,
        )

        for followup in followups:

            try:

                success = process_followup(
                    db,
                    followup,
                )

                if success:
                    processed += 1

            except Exception:

                failed += 1
                db.rollback()

        return {
            "processed": processed,
            "failed": failed,
        }

    finally:

        db.close()