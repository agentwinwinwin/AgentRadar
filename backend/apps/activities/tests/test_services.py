from datetime import date

import pytest

from apps.activities.models import (
    Contributor,
    RepositoryActivityMetric,
    RepositoryContributor,
    RepositoryRelease,
)
from apps.activities.services import ActivityService, ContributorStatisticsPendingError
from apps.github.fakes import FakeGitHubClient
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload

from .fakes import FakeActivityGitHubClient


def create_repository():
    return RepositoryService(FakeGitHubClient()).upsert_from_github(github_repository_payload())[0]


@pytest.mark.django_db
def test_collects_and_idempotently_upserts_activity_data() -> None:
    repository = create_repository()
    service = ActivityService(FakeActivityGitHubClient())

    first = service.collect(repository, metric_date=date(2026, 8, 16))
    second = service.collect(repository, metric_date=date(2026, 8, 16))

    assert first.created is True
    assert second.created is False
    assert RepositoryActivityMetric.objects.count() == 1
    assert Contributor.objects.count() == 1
    assert RepositoryContributor.objects.count() == 1
    assert RepositoryRelease.objects.count() == 1
    metric = second.metric
    assert metric.commits_7d == 11
    assert metric.prs_created_30d == 5
    assert metric.prs_merged_7d == 3
    assert metric.issues_created_7d == 9
    assert metric.issues_closed_30d == 7
    assert metric.active_contributors_30d == 1
    assert metric.releases_30d == 1
    assert metric.days_since_last_release == 6
    repository.refresh_from_db()
    assert repository.community_health == 87


@pytest.mark.django_db
def test_incomplete_search_counts_are_persisted_as_null_not_zero() -> None:
    result = ActivityService(FakeActivityGitHubClient(incomplete=True)).collect(
        create_repository(), metric_date=date(2026, 8, 16)
    )

    assert result.metric.commits_7d is None
    assert result.metric.prs_created_30d is None
    assert result.metric.issues_closed_7d is None


@pytest.mark.django_db
def test_pending_contributor_statistics_does_not_write_partial_data() -> None:
    with pytest.raises(ContributorStatisticsPendingError) as exc_info:
        ActivityService(FakeActivityGitHubClient(stats_ready=False)).collect(
            create_repository(), metric_date=date(2026, 8, 16)
        )

    assert exc_info.value.retry_after == 17
    assert RepositoryActivityMetric.objects.count() == 0
