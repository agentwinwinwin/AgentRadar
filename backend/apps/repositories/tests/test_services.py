import pytest
from django.db import IntegrityError

from apps.github.fakes import FakeGitHubClient
from apps.repositories.models import (
    GitHubDiscoveryQuery,
    Repository,
    RepositoryCategory,
    RepositoryTopic,
)
from apps.repositories.services import RepositoryDiscoveryService, RepositoryService

from .factories import github_repository_payload


@pytest.mark.django_db
def test_repository_sync_creates_verified_current_state_and_topics() -> None:
    payload = github_repository_payload(unverified_field="not-persisted")
    repository, created = RepositoryService(FakeGitHubClient()).upsert_from_github(payload)

    assert created is True
    assert repository.github_id == 123
    assert repository.category == RepositoryCategory.BROWSER_AGENT
    assert repository.stars == 42
    assert set(repository.topics.values_list("normalized_name", flat=True)) == {
        "ai-agent",
        "browser-agent",
    }
    assert "unverified_field" not in repository.raw_metadata


@pytest.mark.django_db
def test_repository_sync_updates_by_github_id_and_preserves_manual_category() -> None:
    service = RepositoryService(FakeGitHubClient())
    repository, _ = service.upsert_from_github(github_repository_payload())
    repository.category = RepositoryCategory.RESEARCH_AGENT
    repository.save(update_fields=("category",))

    updated, created = service.upsert_from_github(
        github_repository_payload(
            full_name="renamed/browser-agent",
            owner={"id": 10, "login": "renamed"},
            stargazers_count=100,
            topics=["computer-use"],
        )
    )

    assert created is False
    assert updated.pk == repository.pk
    assert updated.full_name == "renamed/browser-agent"
    assert updated.stars == 100
    assert updated.category == RepositoryCategory.RESEARCH_AGENT
    assert list(updated.topics.values_list("normalized_name", flat=True)) == ["computer-use"]


@pytest.mark.django_db
def test_repository_topic_constraint_prevents_duplicates() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload()
    )
    relation = RepositoryTopic.objects.first()

    with pytest.raises(IntegrityError):
        RepositoryTopic.objects.create(repository=repository, topic=relation.topic)


@pytest.mark.django_db
def test_discovery_uses_active_query_pool_and_is_idempotent() -> None:
    GitHubDiscoveryQuery.objects.update(is_active=False)
    GitHubDiscoveryQuery.objects.filter(query="topic:ai-agent").update(is_active=True)
    fake = FakeGitHubClient([github_repository_payload()])
    service = RepositoryDiscoveryService(fake)

    first = service.discover(pages_per_query=1)
    second = service.discover(pages_per_query=1)

    assert first.repositories_created == 1
    assert second.repositories_created == 0
    assert second.repositories_updated == 1
    assert Repository.objects.count() == 1
    assert fake.search_calls == [
        "topic:ai-agent archived:false fork:false stars:>10",
        "topic:ai-agent archived:false fork:false stars:>10",
    ]


@pytest.mark.django_db
def test_discovery_skips_forks_and_archived_results() -> None:
    GitHubDiscoveryQuery.objects.update(is_active=False)
    GitHubDiscoveryQuery.objects.filter(query="topic:ai-agent").update(is_active=True)
    fake = FakeGitHubClient(
        [
            github_repository_payload(id=1, full_name="example/valid"),
            github_repository_payload(id=2, full_name="example/fork", fork=True),
            github_repository_payload(id=3, full_name="example/archived", archived=True),
        ]
    )

    result = RepositoryDiscoveryService(fake).discover(per_query=100)

    assert result.repositories_seen == 3
    assert result.repositories_created == 1
    assert result.repositories_skipped == 2
    assert Repository.objects.count() == 1
