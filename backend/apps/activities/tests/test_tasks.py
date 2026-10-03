import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from django.conf import settings
from django.utils import timezone

from apps.activities.models import RepositoryActivityMetric
from apps.activities.tasks import capture_daily_activity_metrics, sync_repository_activity
from apps.github.client import GitHubRateLimitError
from apps.github.fakes import FakeGitHubClient
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.tests.fakes import FakeRepositoryLock

from .fakes import FakeActivityGitHubClient


def create_repository():
    return RepositoryService(FakeGitHubClient()).upsert_from_github(github_repository_payload())[0]


@pytest.mark.django_db
def test_task_uses_lock_and_writes_metric() -> None:
    repository = create_repository()
    with (
        patch("apps.activities.tasks.RedisRepositoryLock", return_value=FakeRepositoryLock()),
        patch("apps.activities.tasks.RealGitHubClient", return_value=FakeActivityGitHubClient()),
        patch("apps.trends.tasks.dispatch_trend_score") as score_dispatch,
    ):
        result = sync_repository_activity.run(repository.id, "2026-08-16")

    assert result["created"] is True
    assert RepositoryActivityMetric.objects.count() == 1
    score_dispatch.assert_called_once_with(repository.id)


@pytest.mark.django_db
def test_task_retries_github_202_with_retry_after() -> None:
    repository = create_repository()
    with (
        patch("apps.activities.tasks.RedisRepositoryLock", return_value=FakeRepositoryLock()),
        patch(
            "apps.activities.tasks.RealGitHubClient",
            return_value=FakeActivityGitHubClient(stats_ready=False),
        ),
        patch.object(sync_repository_activity, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        sync_repository_activity.run(repository.id, "2026-08-16")

    assert retry.call_args.kwargs["countdown"] == 17
    assert RepositoryActivityMetric.objects.count() == 0


@pytest.mark.django_db
def test_parallel_task_is_rejected_by_repository_lock() -> None:
    repository = create_repository()
    with (
        patch(
            "apps.activities.tasks.RedisRepositoryLock",
            return_value=FakeRepositoryLock(acquired=False),
        ),
        patch.object(sync_repository_activity, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        sync_repository_activity.run(repository.id, "2026-08-16")

    assert retry.call_args.kwargs["countdown"] == settings.REPOSITORY_SYNC_LOCK_RETRY_SECONDS
    assert RepositoryActivityMetric.objects.count() == 0


@pytest.mark.django_db
def test_activity_task_waits_until_github_rate_limit_reset() -> None:
    repository = create_repository()
    reset_at = int(time.time()) + 45
    with (
        patch("apps.activities.tasks.RedisRepositoryLock", return_value=FakeRepositoryLock()),
        patch(
            "apps.activities.tasks.ActivityService.collect",
            side_effect=GitHubRateLimitError("limited", reset_at=reset_at),
        ),
        patch.object(sync_repository_activity, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        sync_repository_activity.run(repository.id, "2026-08-16")

    assert 45 <= retry.call_args.kwargs["countdown"] <= 46


@pytest.mark.django_db
def test_daily_dispatcher_excludes_inactive_repositories() -> None:
    active = create_repository()
    RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(id=124, full_name="x/archived", archived=True)
    )
    budget = {"resources": {"search": {"remaining": 30}}}
    with (
        patch("apps.activities.tasks.sync_repository_activity.delay") as dispatch,
        patch("apps.activities.tasks.RealGitHubClient.get_rate_limit", return_value=budget),
    ):
        result = capture_daily_activity_metrics.run()

    assert result["dispatched"] == 1
    assert result["budget_ok"] is True
    dispatch.assert_called_once_with(active.id, result["metric_date"])


def test_activity_beat_and_route_are_configured() -> None:
    schedule = settings.CELERY_BEAT_SCHEDULE["dispatch-due-repository-activity-hourly"]
    assert schedule["task"] == "activities.capture_daily_activity_metrics"
    assert schedule["schedule"] == 3600
    assert settings.CELERY_TASK_ROUTES["activities.*"]["queue"] == "github_normal"
    assert sync_repository_activity.rate_limit == settings.ACTIVITY_SYNC_RATE_LIMIT


@pytest.mark.django_db
def test_activity_dispatcher_only_selects_tier_rows_that_are_due() -> None:
    due = create_repository()
    recent = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(id=125, full_name="x/recent")
    )[0]
    RepositoryActivityMetric.objects.create(
        repository=due,
        metric_date=timezone.now().date() - timedelta(days=3),
    )
    RepositoryActivityMetric.objects.create(
        repository=recent,
        metric_date=timezone.now().date(),
    )
    budget = {"resources": {"search": {"remaining": 30}}}

    with (
        patch("apps.activities.tasks.sync_repository_activity.delay") as dispatch,
        patch("apps.activities.tasks.RealGitHubClient.get_rate_limit", return_value=budget),
    ):
        result = capture_daily_activity_metrics.run()

    assert result["dispatched"] == 1
    dispatch.assert_called_once_with(due.id, result["metric_date"])


@pytest.mark.django_db
def test_activity_dispatcher_pauses_when_search_budget_is_low() -> None:
    create_repository()
    budget = {
        "resources": {"search": {"remaining": settings.GITHUB_SEARCH_MIN_REMAINING}}
    }
    with (
        patch("apps.activities.tasks.sync_repository_activity.delay") as dispatch,
        patch("apps.activities.tasks.RealGitHubClient.get_rate_limit", return_value=budget),
    ):
        result = capture_daily_activity_metrics.run()

    assert result["budget_ok"] is False
    assert result["dispatched"] == 0
    dispatch.assert_not_called()
