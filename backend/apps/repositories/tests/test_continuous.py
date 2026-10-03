from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.datasets.models import RepositoryPool, RepositoryPoolType
from apps.github.fakes import FakeGitHubClient
from apps.repositories.continuous import ContinuousDiscoveryService
from apps.repositories.models import GitHubDiscoveryQuery, MonitoringTier, Repository
from apps.repositories.tests.factories import github_repository_payload


class BudgetFakeGitHubClient(FakeGitHubClient):
    def get_rate_limit(self):
        return {
            "resources": {
                "core": {"remaining": 5000, "reset": 0},
                "search": {"remaining": 30, "reset": 0},
            }
        }


@pytest.mark.django_db(transaction=True)
def test_continuous_discovery_deduplicates_and_adds_candidate_only() -> None:
    GitHubDiscoveryQuery.objects.all().delete()
    GitHubDiscoveryQuery.objects.create(query='"coding agent"')
    payload = github_repository_payload(id=999, full_name="new/coding-agent")
    client = BudgetFakeGitHubClient([payload])

    with (
        patch("apps.snapshots.tasks.create_repository_snapshot.delay") as snapshot,
        patch("apps.learning.tasks.calculate_repository_learning.delay") as learning,
        patch(
            "apps.enterprise.tasks.calculate_repository_enterprise.delay"
        ) as enterprise,
    ):
        result = ContinuousDiscoveryService(client).discover(mode="new", now=timezone.now())

    repository = Repository.objects.get(github_id=999)
    assert result.created == 1
    assert repository.monitoring_tier == MonitoringTier.NEW
    assert (
        RepositoryPool.objects.get(pool_type=RepositoryPoolType.CANDIDATE)
        .repositories.filter(pk=repository.pk)
        .exists()
    )
    assert not RepositoryPool.objects.filter(
        pool_type=RepositoryPoolType.TRAINING,
        repositories=repository,
    ).exists()
    snapshot.assert_called_once_with(repository.id)
    learning.assert_called_once_with(repository.id)
    enterprise.assert_called_once_with(repository.id)

    second = ContinuousDiscoveryService(client).discover(mode="new", now=timezone.now())
    assert second.created == 0
    assert second.reused == 1
    assert Repository.objects.filter(github_id=999).count() == 1
