from datetime import UTC, datetime

import pytest

from apps.datasets.discovery_expansion import (
    CREATED_SHARDS,
    KEYWORDS,
    STAR_SHARDS,
    DiscoveryExpansionService,
)
from apps.datasets.models import AcquisitionQueryShard, RepositoryDiscoveryEvidence
from apps.github.fakes import FakeGitHubClient
from apps.repositories.models import Repository
from apps.repositories.tests.factories import github_repository_payload


@pytest.mark.django_db
def test_discovery_plan_is_idempotent_and_three_dimensional() -> None:
    service = DiscoveryExpansionService(FakeGitHubClient())

    first = service.plan()
    second = service.plan()

    assert first == second == len(KEYWORDS) * len(STAR_SHARDS) * len(CREATED_SHARDS)


@pytest.mark.django_db
def test_discovery_execute_deduplicates_and_records_evidence() -> None:
    payload = github_repository_payload(id=901, full_name="owner/new-agent")
    service = DiscoveryExpansionService(FakeGitHubClient([payload]))
    service.plan()

    result = service.execute(target=1, max_shards=1)

    assert result.repository_total == 1
    assert result.created == 1
    assert Repository.objects.get(github_id=901).full_name == "owner/new-agent"
    assert RepositoryDiscoveryEvidence.objects.count() == 1


@pytest.mark.django_db
def test_truncated_year_shard_creates_month_children() -> None:
    shard = AcquisitionQueryShard.objects.create(
        query='"agent framework" stars:0..9 created:2026-01-01..2026-12-31',
        category="AGENT_FRAMEWORK",
        star_bucket="STAR_0_9",
        age_cohort="CREATED_2026",
        shortage=100,
        shard_metadata={
            "version": "discovery-shards-v2.0.0",
            "keyword": '"agent framework"',
            "star": "stars:0..9",
            "created": "created:2026-01-01..2026-12-31",
        },
        last_executed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    DiscoveryExpansionService._split_truncated(shard)

    assert (
        AcquisitionQueryShard.objects.filter(shard_metadata__parent_shard_id=shard.id).count() == 12
    )
