from unittest.mock import Mock, patch

import pytest
from celery.exceptions import Retry
from django.conf import settings

from apps.github.fakes import FakeGitHubClient
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot
from apps.snapshots.tasks import (
    capture_due_repository_snapshots,
    create_repository_snapshot,
    reassess_monitoring_tiers,
)

from .fakes import FakeRepositoryLock


@pytest.mark.django_db(transaction=True)
def test_snapshot_task_uses_client_lock_and_commit_hook() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload()
    )
    callback = Mock()
    with (
        patch("apps.snapshots.tasks.RedisRepositoryLock", return_value=FakeRepositoryLock()),
        patch(
            "apps.snapshots.tasks.RealGitHubClient",
            return_value=FakeGitHubClient([github_repository_payload()]),
        ),
        patch("apps.snapshots.tasks.snapshot_persisted.delay", callback),
    ):
        result = create_repository_snapshot.run(repository.id)

    assert result["created"] is True
    assert RepositorySnapshot.objects.count() == 1
    callback.assert_called_once_with(RepositorySnapshot.objects.get().id)


@pytest.mark.django_db(transaction=True)
def test_snapshot_task_retries_when_parallel_worker_holds_lock() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload()
    )
    with (
        patch(
            "apps.snapshots.tasks.RedisRepositoryLock",
            return_value=FakeRepositoryLock(acquired=False),
        ),
        patch.object(create_repository_snapshot, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        create_repository_snapshot.run(repository.id)

    retry.assert_called_once()
    assert RepositorySnapshot.objects.count() == 0


@pytest.mark.django_db
def test_beat_dispatcher_excludes_archived_and_disabled_repositories() -> None:
    service = RepositoryService(FakeGitHubClient())
    active, _ = service.upsert_from_github(github_repository_payload(id=1, full_name="a/active"))
    service.upsert_from_github(
        github_repository_payload(id=2, full_name="a/archived", archived=True)
    )
    service.upsert_from_github(
        github_repository_payload(id=3, full_name="a/disabled", disabled=True)
    )

    budget = {"resources": {"core": {"remaining": 5000}}}
    with (
        patch("apps.snapshots.tasks.create_repository_snapshot.delay") as dispatch,
        patch("apps.snapshots.tasks.RealGitHubClient.get_rate_limit", return_value=budget),
    ):
        result = capture_due_repository_snapshots.run()

    assert result == {"dispatched": 1, "budget_ok": True}
    dispatch.assert_called_once_with(active.id)


def test_celery_beat_schedule_and_route_are_configured() -> None:
    schedule = settings.CELERY_BEAT_SCHEDULE["dispatch-due-snapshots-hourly"]

    assert schedule["task"] == "snapshots.dispatch_due_snapshots"
    assert schedule["schedule"] == 3600
    assert schedule["options"]["queue"] == "github_normal"
    assert settings.CELERY_TASK_ROUTES["snapshots.*"]["queue"] == "github_normal"
    reassessment = settings.CELERY_BEAT_SCHEDULE["reassess-monitoring-tiers-daily"]
    assert reassessment["task"] == "snapshots.reassess_monitoring_tiers"
    assert reassessment["options"]["queue"] == "operations"


@pytest.mark.django_db
def test_monitoring_reassessment_is_idempotent() -> None:
    repository = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            id=91,
            full_name="a/dormant",
            created_at="2020-01-01T00:00:00Z",
            pushed_at="2020-01-01T00:00:00Z",
        )
    )[0]

    class Lock:
        acquired = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    with patch("apps.capabilities.locks.RedisCapabilityLock", return_value=Lock()):
        first = reassess_monitoring_tiers.run()
        second = reassess_monitoring_tiers.run()

    repository.refresh_from_db()
    assert first["changed"] == 0
    assert second["changed"] == 0
    assert repository.monitoring_tier == "NORMAL"


@pytest.mark.django_db
def test_snapshot_dispatcher_never_spends_reserved_core_budget() -> None:
    service = RepositoryService(FakeGitHubClient())
    service.upsert_from_github(github_repository_payload(id=10, full_name="a/one"))
    service.upsert_from_github(github_repository_payload(id=11, full_name="a/two"))
    budget = {
        "resources": {"core": {"remaining": settings.GITHUB_CORE_MIN_REMAINING + 1}}
    }
    with (
        patch("apps.snapshots.tasks.create_repository_snapshot.delay") as dispatch,
        patch("apps.snapshots.tasks.RealGitHubClient.get_rate_limit", return_value=budget),
    ):
        result = capture_due_repository_snapshots.run()

    assert result == {"dispatched": 1, "budget_ok": True}
    assert dispatch.call_count == 1
