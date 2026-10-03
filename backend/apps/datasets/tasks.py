import logging
from datetime import date

from celery import shared_task
from django.db import DatabaseError

from apps.activities.services import ContributorStatisticsPendingError
from apps.github.client import GitHubClientError, RealGitHubClient
from apps.repositories.models import Repository

from .services import DatasetBuilder, HistoricalBackfillService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="datasets.backfill_repository_activity",
    max_retries=3,
    soft_time_limit=270,
    time_limit=300,
)
def backfill_repository_activity(
    self, repository_id: int, sample_date: str
) -> dict[str, int | str | bool]:
    try:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        result = HistoricalBackfillService(RealGitHubClient()).collect(
            repository, date.fromisoformat(sample_date)
        )
        return {
            "repository_id": repository_id,
            "sample_date": sample_date,
            "windows": len(result.windows),
            "created": result.created,
        }
    except Repository.DoesNotExist:
        return {"repository_id": repository_id, "sample_date": sample_date, "found": False}
    except ContributorStatisticsPendingError as exc:
        raise self.retry(exc=exc, countdown=exc.retry_after or 60) from exc
    except (GitHubClientError, DatabaseError) as exc:
        logger.warning("dataset backfill retry", extra={"repository_id": repository_id})
        raise self.retry(exc=exc, countdown=30) from exc


@shared_task(name="datasets.build_training_samples")
def build_training_samples(sample_date: str) -> dict[str, int]:
    return DatasetBuilder().build(date.fromisoformat(sample_date))
