import logging

from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.redis import redis_client
from app.models.call import Call
from app.models.enums import CallStatus


CALL_QUEUE_NAME = "calling:queue"
logger = logging.getLogger(__name__)


def enqueue_call(call: Call) -> bool:
    """
    Add a QUEUED call to Redis calling queue.
    """

    if call.status != CallStatus.QUEUED:
        return False

    try:
        redis_client.rpush(CALL_QUEUE_NAME, str(call.id))
        return True
    except RedisError:
        logger.warning("Redis is unavailable; call %s remains queued in the database", call.id)
        return False


def dequeue_call() -> int | None:
    """
    Get next call ID from Redis queue.
    """

    try:
        call_id = redis_client.lpop(CALL_QUEUE_NAME)
    except RedisError:
        return None

    if call_id is None:
        return None

    return int(call_id)


def queue_size() -> int:
    """
    Return number of waiting calls.
    """

    try:
        return redis_client.llen(CALL_QUEUE_NAME)
    except RedisError:
        return 0


def enqueue_existing_call(
    db: Session,
    call_id: int,
) -> bool:

    call = db.get(Call, call_id)

    if call is None:
        return False

    return enqueue_call(call)
