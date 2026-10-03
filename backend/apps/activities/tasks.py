import logging
import time
from datetime import date, timedelta

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError, models
from django.utils import timezone

from apps.github.client import GitHubClientError, GitHubRateLimitError, RealGitHubClient
from apps.repositories.models import Repository
from apps.snapshots.locks import RedisRepositoryLock
from apps.snapshots.tasks import RepositoryLockUnavailable

from .services import ActivityService, ContributorStatisticsPendingError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="activities.sync_repository_activity",
    max_retries=5,
    soft_time_limit=270,
    time_limit=300,
    rate_limit=settings.ACTIVITY_SYNC_RATE_LIMIT,
)
def sync_repository_activity(
    self, repository_id: int, metric_date: str | None = None
) -> dict[str, int | bool | str]:
    try:
        repository = Repository.objects.get(pk=repository_id)
        with RedisRepositoryLock(repository_id) as lock:
            if not lock.acquired:
                raise RepositoryLockUnavailable(f"repository {repository_id} is already syncing")
            result = ActivityService(RealGitHubClient()).collect(
                repository,
                metric_date=date.fromisoformat(metric_date) if metric_date else None,
            )
        from apps.trends.tasks import dispatch_trend_score

        dispatch_trend_score(repository_id)
        return {
            "activity_metric_id": result.metric.id,
            "metric_date": result.metric.metric_date.isoformat(),
            "created": result.created,
        }
    except Repository.DoesNotExist:
        return {"repository_id": repository_id, "created": False}
    except ContributorStatisticsPendingError as exc:
        raise self.retry(
            exc=exc,
            countdown=exc.retry_after or settings.CONTRIBUTOR_STATS_RETRY_SECONDS,
        ) from exc
    except GitHubRateLimitError as exc:
        countdown = max((exc.reset_at or int(time.time()) + 60) - int(time.time()) + 1, 10)
        logger.warning(
            "repository activity rate limited",
            extra={"repository_id": repository_id, "retry_after_seconds": countdown},
        )
        raise self.retry(exc=exc, countdown=countdown) from exc
    except (RepositoryLockUnavailable, GitHubClientError, DatabaseError) as exc:
        logger.warning("repository activity retry", extra={"repository_id": repository_id})
        raise self.retry(exc=exc, countdown=settings.REPOSITORY_SYNC_LOCK_RETRY_SECONDS) from exc


@shared_task(name="activities.capture_daily_activity_metrics")
def capture_daily_activity_metrics() -> dict[str, int | str]:
    today = timezone.now().date()
    metric_date = today.isoformat()
    due = models.Q(latest_activity_date__isnull=True)
    for tier, interval_days in settings.ACTIVITY_TIER_INTERVAL_DAYS.items():
        due |= models.Q(
            monitoring_tier=tier,
            latest_activity_date__lte=today - timedelta(days=interval_days),
        )

    repositories = (
        Repository.objects.filter(
            monitoring_enabled=True,
            is_archived=False,
            is_disabled=False,
        )
        .annotate(latest_activity_date=models.Max("activity_metrics__metric_date"))
        .filter(due)
        .order_by("latest_activity_date", "id")
    )
    try:
        resources = RealGitHubClient().get_rate_limit()["resources"]
    except GitHubClientError:
        logger.warning("activity dispatcher paused because GitHub budget could not be read")
        return {"dispatched": 0, "metric_date": metric_date, "budget_ok": False}
    search = resources.get("search", {})
    if int(search.get("remaining", 0)) <= settings.GITHUB_SEARCH_MIN_REMAINING:
        logger.warning("activity dispatcher paused for GitHub search budget")
        return {"dispatched": 0, "metric_date": metric_date, "budget_ok": False}

    repository_ids = list(
        repositories.values_list("id", flat=True)[: settings.ACTIVITY_DISPATCH_BATCH_SIZE]
    )
    for repository_id in repository_ids:
        sync_repository_activity.delay(repository_id, metric_date)
    return {"dispatched": len(repository_ids), "metric_date": metric_date, "budget_ok": True}
