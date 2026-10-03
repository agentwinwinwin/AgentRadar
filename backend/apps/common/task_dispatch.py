import logging
from uuid import uuid4

from celery import Task
from django.conf import settings
from redis import Redis

logger = logging.getLogger(__name__)


def dispatch_unique_repository_task(
    task: Task,
    repository_id: int,
    *,
    purpose: str,
    ttl: int | None = None,
) -> bool:
    """Coalesce repeated repository work before it reaches the Celery queue.

    The key intentionally lives for a short debounce window instead of being
    removed when the task completes. Snapshot and activity commits close
    together, and both should be represented by one calculation against the
    latest persisted database state.
    """

    client = Redis.from_url(settings.CELERY_BROKER_URL)
    key = f"agentradar:celery:pending:{purpose}:{repository_id}"
    token = uuid4().hex
    expires_in = ttl or settings.REPOSITORY_TASK_COALESCE_TTL_SECONDS
    if not client.set(key, token, nx=True, ex=expires_in):
        logger.info(
            "repository task coalesced",
            extra={"repository_id": repository_id, "purpose": purpose},
        )
        return False
    try:
        task.delay(repository_id)
    except Exception:
        client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            token,
        )
        raise
    return True
