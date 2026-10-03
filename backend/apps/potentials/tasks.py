import logging

from celery import shared_task
from django.db import DatabaseError

from apps.common.task_dispatch import dispatch_unique_repository_task
from apps.repositories.models import Repository
from apps.trends.models import RepositoryTrendScore

from .services import PotentialService

logger = logging.getLogger(__name__)


def dispatch_potential_score(repository_id: int) -> bool:
    return dispatch_unique_repository_task(
        calculate_potential_score,
        repository_id,
        purpose="potential-score",
    )


@shared_task(
    bind=True,
    name="potentials.calculate_potential_score",
    max_retries=3,
    soft_time_limit=270,
    time_limit=300,
)
def calculate_potential_score(self, repository_id: int) -> dict[str, int | bool | str | None]:
    try:
        result = PotentialService().calculate_repository(repository_id)
        from apps.watchlists.tasks import evaluate_repository_alerts

        dispatch_unique_repository_task(
            evaluate_repository_alerts,
            repository_id,
            purpose="alert-evaluation",
        )
        return {
            "potential_score_id": result.potential.id,
            "created": result.created,
            "algorithm_version": result.potential.algorithm_version,
            "potential_score": (
                str(result.potential.potential_score)
                if result.potential.potential_score is not None
                else None
            ),
        }
    except (Repository.DoesNotExist, RepositoryTrendScore.DoesNotExist):
        return {"repository_id": repository_id, "created": False}
    except DatabaseError as exc:
        logger.warning("potential calculation retry", extra={"repository_id": repository_id})
        raise self.retry(exc=exc, countdown=10) from exc


@shared_task(name="potentials.calculate_all_potential_scores")
def calculate_all_potential_scores() -> dict[str, int]:
    repository_ids = RepositoryTrendScore.objects.values_list("repository_id", flat=True).distinct()
    dispatched = 0
    for repository_id in repository_ids.iterator(chunk_size=500):
        dispatched += int(dispatch_potential_score(repository_id))
    return {"dispatched": dispatched}
