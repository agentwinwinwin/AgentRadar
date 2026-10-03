import logging

from celery import shared_task
from django.db import DatabaseError

from apps.common.task_dispatch import dispatch_unique_repository_task
from apps.potentials.tasks import dispatch_potential_score
from apps.repositories.models import Repository

from .services import TrendService

logger = logging.getLogger(__name__)


def dispatch_trend_score(repository_id: int) -> bool:
    return dispatch_unique_repository_task(
        calculate_trend_score,
        repository_id,
        purpose="trend-score",
    )


@shared_task(
    bind=True,
    name="trends.calculate_trend_score",
    max_retries=3,
    soft_time_limit=270,
    time_limit=300,
)
def calculate_trend_score(self, repository_id: int) -> dict[str, int | bool | str | None]:
    try:
        result = TrendService().calculate_repository(repository_id)
        dispatch_potential_score(repository_id)
        from apps.enterprise.tasks import calculate_repository_enterprise
        from apps.learning.tasks import calculate_repository_learning

        dispatch_unique_repository_task(
            calculate_repository_learning,
            repository_id,
            purpose="learning-score",
        )
        dispatch_unique_repository_task(
            calculate_repository_enterprise,
            repository_id,
            purpose="enterprise-score",
        )
        return {
            "trend_score_id": result.trend.id,
            "created": result.created,
            "algorithm_version": result.trend.algorithm_version,
            "trend_score": (
                str(result.trend.trend_score) if result.trend.trend_score is not None else None
            ),
        }
    except Repository.DoesNotExist:
        return {"repository_id": repository_id, "created": False}
    except DatabaseError as exc:
        logger.warning("trend calculation retry", extra={"repository_id": repository_id})
        raise self.retry(exc=exc, countdown=10) from exc


@shared_task(name="trends.calculate_all_trend_scores")
def calculate_all_trend_scores() -> dict[str, int]:
    dispatched = 0
    repository_ids = Repository.objects.filter(is_disabled=False).values_list("id", flat=True)
    for repository_id in repository_ids.iterator(chunk_size=500):
        dispatched += int(dispatch_trend_score(repository_id))
    return {"dispatched": dispatched}
