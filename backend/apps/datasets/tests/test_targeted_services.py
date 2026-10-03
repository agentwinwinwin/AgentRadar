from datetime import UTC, date, datetime

import pytest

from apps.datasets.acquisition_services import RepositoryPoolService
from apps.datasets.models import HistoricalActivityWindow, RepositoryPool
from apps.datasets.targeted_services import TargetedCoverageService
from apps.datasets.tests.test_backfill import create_repository
from apps.datasets.tests.test_builder import create_windows
from apps.repositories.models import RepositoryCategory


@pytest.mark.django_db
def test_targeted_coverage_distinguishes_historical_and_label_complete() -> None:
    sample_date = date(2026, 4, 18)
    repositories = [create_repository(index) for index in range(1, 21)]
    for index, repository in enumerate(repositories):
        repository.category = RepositoryCategory.AGENT_FRAMEWORK
        repository.description = "agent framework"
        repository.github_created_at = datetime(2025, 1, 1, tzinfo=UTC)
        repository.github_pushed_at = datetime(2026, 1, 1, tzinfo=UTC)
        repository.save(
            update_fields=(
                "category",
                "description",
                "github_created_at",
                "github_pushed_at",
                "updated_at",
            )
        )
        create_windows(repository, sample_date, index + 1)
    label = HistoricalActivityWindow.objects.get(
        repository=repositories[-1], window_start=date(2026, 4, 19)
    )
    label.active_contributors = None
    label.save(update_fields=("active_contributors",))
    RepositoryPoolService().build_v2(training_target=600, as_of=date(2026, 8, 17))
    pool = RepositoryPool.objects.get(name="sprint8-training-v2")

    report = TargetedCoverageService().report(
        pool,
        categories=(RepositoryCategory.AGENT_FRAMEWORK,),
        sample_dates=(sample_date,),
    )

    values = report["matrix"][RepositoryCategory.AGENT_FRAMEWORK][sample_date.isoformat()]
    assert values == {
        "theoretical_repository_count": 20,
        "historical_complete_repository_count": 20,
        "label_complete_repository_count": 19,
        "effective_cohort_size": 0,
    }
