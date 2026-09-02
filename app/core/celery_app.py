import os

from celery import Celery


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)


celery_app = Celery(
    "cold_calling_agent",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.workers.followup_worker",
        "app.workers.call_worker",
        "app.workers.tabby_sync_worker",
    ],
)


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    timezone="UTC",
    enable_utc=True,

    task_track_started=True,

    worker_prefetch_multiplier=1,

    task_acks_late=True,

    task_reject_on_worker_lost=True,

    broker_connection_retry_on_startup=True,

    task_default_queue="calling",

    task_routes={
        "app.workers.followup_worker.*": {
            "queue": "calling",
        },
        "app.workers.call_worker.*": {
            "queue": "calling",
        },
        "app.workers.tabby_sync_worker.*": {
            "queue": "calling",
        },
    },

    beat_schedule={
        "process-pending-followups": {
            "task": (
                "app.workers.followup_worker."
                "process_pending_followups"
            ),
            "schedule": 30.0,
        },
        "sync-tabby-call-logs": {
            "task": (
                "app.workers.tabby_sync_worker."
                "sync_tabby_call_logs"
            ),
            "schedule": 60.0,
        },
    },
)