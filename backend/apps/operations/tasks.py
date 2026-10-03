from celery import shared_task

from .retention import retention_counts


@shared_task(
    name="operations.enforce_data_retention",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def enforce_data_retention() -> dict:
    return retention_counts(apply=True)
