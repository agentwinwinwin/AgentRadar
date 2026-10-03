import logging
import time

from celery.signals import task_failure, task_postrun, task_prerun, task_retry

logger = logging.getLogger("agentradar.celery")
_started: dict[str, float] = {}


@task_prerun.connect
def on_task_prerun(task_id=None, task=None, **kwargs):
    if task_id:
        _started[task_id] = time.monotonic()
    logger.info(
        "task_started",
        extra={"task_id": task_id, "task_name": getattr(task, "name", None)},
    )


@task_postrun.connect
def on_task_postrun(task_id=None, task=None, state=None, **kwargs):
    started = _started.pop(task_id, None)
    logger.info(
        "task_completed",
        extra={
            "task_id": task_id,
            "task_name": getattr(task, "name", None),
            "status_code": state,
            "duration_ms": round((time.monotonic() - started) * 1000, 2) if started else None,
        },
    )


@task_retry.connect
def on_task_retry(request=None, reason=None, **kwargs):
    logger.warning(
        "task_retry",
        extra={
            "task_id": getattr(request, "id", None),
            "task_name": getattr(request, "task", None),
        },
    )


@task_failure.connect
def on_task_failure(task_id=None, sender=None, exception=None, **kwargs):
    logger.error(
        "task_failed",
        extra={"task_id": task_id, "task_name": getattr(sender, "name", None)},
        exc_info=(type(exception), exception, exception.__traceback__) if exception else None,
    )
