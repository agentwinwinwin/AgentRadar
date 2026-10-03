from datetime import UTC, date, datetime

import pytest

from apps.datasets.management.commands.validate_bucket_backfill import stratified_memberships
from apps.datasets.models import (
    RepositoryPool,
    RepositoryPoolMembership,
    RepositoryPoolStatus,
    RepositoryPoolType,
)
from apps.repositories.models import Repository, RepositoryCategory


@pytest.mark.django_db
def test_stratified_validation_selection_covers_strata_and_excludes_too_new() -> None:
    pool = RepositoryPool.objects.create(
        name="confirmed-training",
        pool_type=RepositoryPoolType.TRAINING,
        status=RepositoryPoolStatus.CONFIRMED,
    )
    values = [
        (RepositoryCategory.CODING_AGENT, "STAR_0_99", "AGE_181_730"),
        (RepositoryCategory.CODING_AGENT, "STAR_10K_PLUS", "AGE_731_PLUS"),
        (RepositoryCategory.BROWSER_AGENT, "STAR_100_999", "AGE_181_730"),
    ]
    for index, (category, stars, age) in enumerate(values):
        repository = Repository.objects.create(
            github_id=index + 1,
            owner="owner",
            full_name=f"owner/repo-{index}",
            name=f"repo-{index}",
            category=category,
            default_branch="main",
            github_created_at=datetime(2020, 1, index + 1, tzinfo=UTC),
            github_updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            last_synced_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        RepositoryPoolMembership.objects.create(
            pool=pool,
            repository=repository,
            category=category,
            star_bucket=stars,
            age_cohort=age,
            activity_level="UNKNOWN",
            selection_reason="test",
            stratum_rank=1,
        )
    too_new = Repository.objects.create(
        github_id=99,
        owner="owner",
        full_name="owner/too-new",
        name="too-new",
        category=RepositoryCategory.AGENT_FRAMEWORK,
        default_branch="main",
        github_created_at=datetime(2026, 6, 1, tzinfo=UTC),
        github_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        last_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    RepositoryPoolMembership.objects.create(
        pool=pool,
        repository=too_new,
        category=too_new.category,
        star_bucket="STAR_0_99",
        age_cohort="AGE_0_30",
        activity_level="UNKNOWN",
        selection_reason="test",
        stratum_rank=1,
    )

    selected = stratified_memberships(pool, 3, date(2026, 2, 18))

    assert len(selected) == 3
    assert {item.repository.full_name for item in selected} == {
        "owner/repo-0",
        "owner/repo-1",
        "owner/repo-2",
    }
