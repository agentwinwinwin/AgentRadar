from datetime import UTC, date, datetime

import pytest
from django.utils import timezone

from apps.activities.models import Contributor, RepositoryActivityMetric, RepositoryContributor
from apps.github.fakes import FakeGitHubClient
from apps.repositories.models import RepositoryCategory
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import ALGORITHM_VERSION
from apps.trends.models import HypeRiskStatus, RepositoryTrendScore
from apps.trends.services import TrendService

CALCULATION_DATE = date(2026, 8, 16)


def create_repository(index: int, *, category: str = RepositoryCategory.BROWSER_AGENT):
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            id=10_000 + index,
            full_name=f"trend/repo-{index}",
            name=f"repo-{index}",
            created_at="2025-08-16T00:00:00Z",
        )
    )
    repository.category = category
    repository.community_health = 80
    repository.save(update_fields=("category", "community_health", "updated_at"))
    return repository


def add_complete_data(repository, scale: int) -> None:
    snapshots = (
        ("2026-07-17T12", datetime(2026, 7, 17, 12, tzinfo=UTC), 100 * scale, 20 * scale),
        ("2026-08-09T12", datetime(2026, 8, 9, 12, tzinfo=UTC), 130 * scale, 25 * scale),
        ("2026-08-16T12", datetime(2026, 8, 16, 12, tzinfo=UTC), 160 * scale, 30 * scale),
    )
    for bucket, observed_at, stars, forks in snapshots:
        RepositorySnapshot.objects.create(
            repository=repository,
            snapshot_at=observed_at,
            snapshot_date=observed_at.date(),
            snapshot_bucket=bucket,
            stars=stars,
            forks=forks,
            subscribers=1,
            open_issues=1,
            github_pushed_at=observed_at,
            data_completeness=1.0,
        )
    RepositoryActivityMetric.objects.create(
        repository=repository,
        metric_date=CALCULATION_DATE,
        commits_7d=5 * scale,
        commits_30d=20 * scale,
        commits_90d=60 * scale,
        prs_created_7d=2 * scale,
        prs_created_30d=8 * scale,
        prs_merged_7d=1 * scale,
        prs_merged_30d=6 * scale,
        issues_created_7d=2 * scale,
        issues_created_30d=10 * scale,
        issues_closed_7d=2 * scale,
        issues_closed_30d=8 * scale,
        active_contributors_30d=3 * scale,
        releases_30d=scale,
        releases_90d=3 * scale,
        days_since_last_push=1,
        days_since_last_release=5,
    )
    for offset, total in enumerate((70, 30)):
        contributor = Contributor.objects.create(
            github_user_id=repository.github_id * 10 + offset,
            login=f"dev-{repository.id}-{offset}",
        )
        RepositoryContributor.objects.create(
            repository=repository,
            contributor=contributor,
            contributions_total=total,
            last_observed_at=timezone.now(),
        )


@pytest.mark.django_db
def test_service_uses_only_category_age_cohort_and_persists_explainable_score() -> None:
    low = create_repository(1)
    target = create_repository(2)
    high = create_repository(3)
    outsider = create_repository(4, category=RepositoryCategory.CODING_AGENT)
    for repository, scale in ((low, 1), (target, 2), (high, 3), (outsider, 100)):
        add_complete_data(repository, scale)

    result = TrendService().calculate_repository(target.id, calculation_date=CALCULATION_DATE)

    assert result.created is True
    assert result.trend.algorithm_version == ALGORITHM_VERSION
    assert result.trend.data_completeness == pytest.approx(0.9)
    assert result.trend.topic_momentum_score is None
    assert result.trend.hype_risk_status != HypeRiskStatus.INSUFFICIENT_HISTORY
    assert result.trend.evidence["cohort_size"] == 3
    assert result.trend.evidence["percentiles"]["commits_30d"] == 50.0
    assert result.trend.evidence["raw_features"]["commits_30d"] == 40
    assert "trend_weights" in result.trend.evidence


@pytest.mark.django_db
def test_insufficient_history_keeps_growth_null_and_lowers_completeness() -> None:
    repository = create_repository(10)
    observed_at = datetime(2026, 8, 16, 12, tzinfo=UTC)
    RepositorySnapshot.objects.create(
        repository=repository,
        snapshot_at=observed_at,
        snapshot_date=observed_at.date(),
        snapshot_bucket="2026-08-16T12",
        stars=10,
        forks=0,
        data_completeness=0.4,
    )

    trend = (
        TrendService().calculate_repository(repository.id, calculation_date=CALCULATION_DATE).trend
    )

    assert trend.evidence["raw_features"]["star_growth_7d"] is None
    assert trend.evidence["raw_features"]["star_growth_30d"] is None
    assert trend.hype_risk is None
    assert trend.hype_risk_status == HypeRiskStatus.INSUFFICIENT_HISTORY
    assert trend.data_completeness < 0.5


@pytest.mark.django_db
def test_hype_is_not_calculated_from_partial_activity_components() -> None:
    repository = create_repository(11)
    snapshots = (
        ("2026-07-17T12", datetime(2026, 7, 17, 12, tzinfo=UTC), 10, 1),
        ("2026-08-16T12", datetime(2026, 8, 16, 12, tzinfo=UTC), 100, 2),
    )
    for bucket, observed_at, stars, forks in snapshots:
        RepositorySnapshot.objects.create(
            repository=repository,
            snapshot_at=observed_at,
            snapshot_date=observed_at.date(),
            snapshot_bucket=bucket,
            stars=stars,
            forks=forks,
            data_completeness=0.4,
        )
    RepositoryActivityMetric.objects.create(
        repository=repository,
        metric_date=CALCULATION_DATE,
        commits_30d=5,
    )

    trend = (
        TrendService().calculate_repository(repository.id, calculation_date=CALCULATION_DATE).trend
    )

    assert trend.development_score is not None
    assert trend.hype_risk is None
    assert trend.hype_risk_status == HypeRiskStatus.INSUFFICIENT_HISTORY


@pytest.mark.django_db
def test_recalculation_is_idempotent_and_deterministic() -> None:
    repository = create_repository(20)
    add_complete_data(repository, 1)
    service = TrendService()

    first = service.calculate_repository(repository.id, calculation_date=CALCULATION_DATE)
    first_evidence = first.trend.evidence
    first_score = first.trend.trend_score
    second = service.calculate_repository(repository.id, calculation_date=CALCULATION_DATE)

    assert first.created is True
    assert second.created is False
    assert RepositoryTrendScore.objects.filter(repository=repository).count() == 1
    assert second.trend.trend_score == first_score
    assert second.trend.evidence == first_evidence
