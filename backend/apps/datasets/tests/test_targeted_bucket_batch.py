from collections import Counter
from datetime import UTC, date, datetime

import pytest

from apps.datasets.management.commands.run_targeted_bucket_batch import targeted_memberships
from apps.datasets.models import (
    RepositoryPool,
    RepositoryPoolMembership,
    RepositoryPoolStatus,
    RepositoryPoolType,
)
from apps.datasets.tests.test_backfill import create_repository


@pytest.mark.django_db
def test_targeted_selection_is_category_balanced_and_bounded() -> None:
    pool = RepositoryPool.objects.create(
        name="targeted",
        pool_type=RepositoryPoolType.TRAINING,
        status=RepositoryPoolStatus.CONFIRMED,
    )
    categories = (
        "AGENT_FRAMEWORK",
        "MULTI_AGENT",
        "CODING_AGENT",
        "COMPUTER_USE",
        "BROWSER_AGENT",
    )
    for category_index, category in enumerate(categories):
        for index in range(3):
            repository = create_repository(category_index * 10 + index + 1)
            repository.category = category
            repository.github_created_at = datetime(2020, 1, 1, tzinfo=UTC)
            repository.raw_metadata = {"source": "github"}
            repository.save(
                update_fields=("category", "github_created_at", "raw_metadata", "updated_at")
            )
            RepositoryPoolMembership.objects.create(
                pool=pool,
                repository=repository,
                category=category,
                star_bucket=("STAR_0_99", "STAR_100_999", "STAR_1K_9K")[index],
                age_cohort="AGE_731_PLUS",
                activity_level="UNKNOWN",
                selection_reason="test",
                stratum_rank=index + 1,
            )

    selected = targeted_memberships(pool, limit=10, eligible_at=date(2026, 4, 18))

    assert len(selected) == 10
    assert Counter(item.category for item in selected) == Counter(
        {category: 2 for category in categories}
    )
