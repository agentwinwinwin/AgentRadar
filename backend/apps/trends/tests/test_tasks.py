from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.conf import settings

from apps.github.fakes import FakeGitHubClient
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot
from apps.snapshots.tasks import snapshot_persisted
from apps.trends.models import RepositoryTrendScore
from apps.trends.tasks import calculate_all_trend_scores, calculate_trend_score


@pytest.mark.django_db
def test_trend_task_is_idempotent() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload()
    )

    with (
        patch("apps.trends.tasks.dispatch_potential_score") as dispatch,
        patch("apps.trends.tasks.dispatch_unique_repository_task") as child_dispatch,
    ):
        first = calculate_trend_score.run(repository.id)
        second = calculate_trend_score.run(repository.id)

    assert first["created"] is True
    assert second["created"] is False
    assert RepositoryTrendScore.objects.filter(repository=repository).count() == 1
    assert dispatch.call_count == 2
    assert child_dispatch.call_count == 4


@pytest.mark.django_db
def test_trend_dispatcher_excludes_disabled_repositories() -> None:
    service = RepositoryService(FakeGitHubClient())
    active, _ = service.upsert_from_github(github_repository_payload(id=1, full_name="x/active"))
    service.upsert_from_github(
        github_repository_payload(id=2, full_name="x/disabled", disabled=True)
    )
    with patch("apps.trends.tasks.dispatch_trend_score", return_value=True) as dispatch:
        result = calculate_all_trend_scores.run()

    assert result == {"dispatched": 1}
    dispatch.assert_called_once_with(active.id)


def test_trend_tasks_use_scoring_queue() -> None:
    assert settings.CELERY_TASK_ROUTES["trends.*"]["queue"] == "scoring"


@pytest.mark.django_db
def test_committed_snapshot_dispatches_scoring() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload()
    )
    observed_at = datetime(2026, 8, 16, 12, tzinfo=UTC)
    snapshot = RepositorySnapshot.objects.create(
        repository=repository,
        snapshot_at=observed_at,
        snapshot_date=observed_at.date(),
        snapshot_bucket="2026-08-16T12",
        data_completeness=0.0,
    )

    with (
        patch("apps.trends.tasks.dispatch_trend_score") as dispatch,
    ):
        snapshot_persisted.run(snapshot.id)

    dispatch.assert_called_once_with(repository.id)
