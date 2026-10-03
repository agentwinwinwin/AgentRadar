from datetime import UTC, date, datetime

import pytest

from apps.datasets.acquisition_services import (
    CoverageAuditService,
    HeadCoverageService,
    QueryShardingService,
    RepositoryPoolService,
    star_bucket,
)
from apps.datasets.models import RepositoryPool, RepositoryPoolStatus, RepositoryPoolType
from apps.github.fakes import FakeGitHubClient
from apps.repositories.models import RepositoryCategory
from apps.repositories.tests.factories import github_repository_payload

from .test_backfill import create_repository


def test_star_buckets_preserve_null_semantics() -> None:
    assert star_bucket(None) == "UNKNOWN"
    assert star_bucket(99) == "STAR_0_99"
    assert star_bucket(100) == "STAR_100_999"
    assert star_bucket(1_000) == "STAR_1K_9K"
    assert star_bucket(10_000) == "STAR_10K_PLUS"


@pytest.mark.django_db
def test_coverage_and_stratified_pool_build_are_idempotent() -> None:
    categories = (RepositoryCategory.AGENT_FRAMEWORK, RepositoryCategory.MULTI_AGENT)
    for index in range(1, 13):
        repository = create_repository(index)
        repository.category = categories[index % 2]
        repository.stars = (50, 500, 5_000)[index % 3]
        repository.github_created_at = datetime(2024 if index % 2 else 2026, 1, 1, tzinfo=UTC)
        repository.save(update_fields=("category", "stars", "github_created_at"))

    audit = CoverageAuditService().report(as_of=date(2026, 8, 17))
    first = RepositoryPoolService().build(training_target=6, as_of=date(2026, 8, 17))
    second = RepositoryPoolService().build(training_target=6, as_of=date(2026, 8, 17))

    assert audit["repository_total"] == 12
    assert first == second
    assert first["candidate_pool"] == 12
    assert first["tracked_pool"] == 12
    assert first["training_pool"] == 6
    assert first["training_pool_status"] == RepositoryPoolStatus.DRAFT
    assert len(first["training_strata"]) > 1
    training_pool = RepositoryPool.objects.get(pool_type=RepositoryPoolType.TRAINING)
    assert training_pool.memberships.count() == 6


@pytest.mark.django_db
def test_head_coverage_reuses_existing_without_overwrite_and_adds_missing() -> None:
    existing = create_repository(1)
    existing.stars = 777
    existing.save(update_fields=("stars",))
    existing_payload = github_repository_payload(
        id=existing.github_id,
        full_name=existing.full_name,
        name=existing.name,
        stargazers_count=999_999,
    )
    missing_payload = github_repository_payload(
        id=999_001,
        full_name="new/head-agent",
        name="head-agent",
    )

    client = FakeGitHubClient([existing_payload, missing_payload])
    report = HeadCoverageService(client).ensure(top_n=2)

    existing.refresh_from_db()
    assert existing.stars == 777
    assert report["created_repository_ids"]
    assert RepositoryPool.objects.count() == 0


@pytest.mark.django_db
def test_query_shards_only_target_underrepresented_strata() -> None:
    repository = create_repository(1)
    repository.category = RepositoryCategory.AGENT_FRAMEWORK
    repository.stars = 50
    repository.save(update_fields=("category", "stars"))
    report = CoverageAuditService().report(as_of=date(2026, 8, 17))

    shards = QueryShardingService().plan(report)

    assert shards
    assert all(shard.shortage > 0 for shard in shards)
    assert all("created:" in shard.query for shard in shards)


@pytest.mark.django_db
def test_query_shard_execution_is_bounded_and_does_not_overwrite_existing() -> None:
    existing = create_repository(1)
    existing.stars = 321
    existing.category = RepositoryCategory.AGENT_FRAMEWORK
    existing.save(update_fields=("stars", "category"))
    report = CoverageAuditService().report(as_of=date(2026, 8, 17))
    QueryShardingService().plan(report)
    payload = github_repository_payload(
        id=existing.github_id,
        full_name=existing.full_name,
        name=existing.name,
        stargazers_count=999_999,
    )

    result = QueryShardingService(FakeGitHubClient([payload])).execute(limit_shards=1, per_shard=1)

    existing.refresh_from_db()
    assert result == {
        "shards_executed": 1,
        "repositories_seen": 1,
        "repositories_created": 0,
        "repositories_reused": 1,
    }
    assert existing.stars == 321


@pytest.mark.django_db
def test_training_size_simulation_does_not_replace_existing_pools() -> None:
    for index in range(1, 31):
        repository = create_repository(index)
        repository.category = (
            RepositoryCategory.AGENT_FRAMEWORK if index % 2 else RepositoryCategory.CODING_AGENT
        )
        repository.description = "agent repository"
        repository.github_pushed_at = datetime(2026, 8, 1, tzinfo=UTC)
        repository.save(update_fields=("category", "description", "github_pushed_at", "updated_at"))
    RepositoryPoolService().build_v2(training_target=600, as_of=date(2026, 8, 17))
    before = {
        pool.name: list(pool.memberships.values_list("repository_id", flat=True))
        for pool in RepositoryPool.objects.all()
    }

    report = RepositoryPoolService().simulate_training_sizes(
        targets=(10, 20),
        sample_dates=(date(2026, 4, 18), date(2026, 5, 18)),
        as_of=date(2026, 8, 17),
    )

    after = {
        pool.name: list(pool.memberships.values_list("repository_id", flat=True))
        for pool in RepositoryPool.objects.all()
    }
    assert before == after
    assert report["simulations"]["10"]["selected"] == 10
    assert report["simulations"]["20"]["selected"] == 20
