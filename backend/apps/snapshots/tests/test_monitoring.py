from datetime import UTC, datetime, timedelta

import pytest

from apps.github.fakes import FakeGitHubClient
from apps.repositories.models import MonitoringTier
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.monitoring import (
    determine_monitoring_tier,
    next_snapshot_time,
    refresh_repository_monitoring,
)
from apps.snapshots.services import SnapshotService

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)


@pytest.mark.django_db
def test_new_and_archived_tiers_are_deterministic() -> None:
    service = RepositoryService(FakeGitHubClient())
    new, _ = service.upsert_from_github(
        github_repository_payload(created_at="2026-08-12T00:00:00Z")
    )
    archived, _ = service.upsert_from_github(
        github_repository_payload(id=2, full_name="example/old", archived=True)
    )

    assert determine_monitoring_tier(new, now=NOW) == MonitoringTier.NEW
    assert determine_monitoring_tier(archived, now=NOW) == MonitoringTier.ARCHIVED
    assert next_snapshot_time(MonitoringTier.HOT, from_time=NOW) == NOW + timedelta(hours=6)


@pytest.mark.django_db
def test_repository_leaves_new_tier_after_first_seven_days() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(created_at="2026-08-09T00:00:00Z")
    )

    assert determine_monitoring_tier(repository, now=NOW) == MonitoringTier.NORMAL


@pytest.mark.django_db(transaction=True)
def test_real_growth_can_promote_stable_repository_to_rising() -> None:
    payload = github_repository_payload(
        created_at="2020-01-01T00:00:00Z",
        pushed_at="2026-07-01T00:00:00Z",
        stargazers_count=100,
        forks_count=10,
    )
    old = SnapshotService(FakeGitHubClient()).persist_payload(
        payload, observed_at=NOW - timedelta(days=8)
    )
    payload["stargazers_count"] = 140
    payload["forks_count"] = 12
    SnapshotService(FakeGitHubClient()).persist_payload(payload, observed_at=NOW)

    assert determine_monitoring_tier(old.snapshot.repository, now=NOW) == MonitoringTier.RISING


@pytest.mark.django_db
def test_watchlisted_repository_is_hot_even_when_old() -> None:
    from django.contrib.auth import get_user_model

    from apps.watchlists.models import Watchlist, WatchlistItem

    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            created_at="2020-01-01T00:00:00Z",
            pushed_at="2025-01-01T00:00:00Z",
        )
    )
    owner = get_user_model().objects.create_user(username="monitor-owner")
    watchlist = Watchlist.objects.create(owner=owner)
    WatchlistItem.objects.create(watchlist=watchlist, repository=repository)

    assert determine_monitoring_tier(repository, now=NOW) == MonitoringTier.HOT


@pytest.mark.django_db
def test_confirmed_training_repository_never_falls_below_normal() -> None:
    from apps.datasets.models import (
        RepositoryPool,
        RepositoryPoolMembership,
        RepositoryPoolStatus,
        RepositoryPoolType,
    )

    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            created_at="2020-01-01T00:00:00Z",
            pushed_at="2025-01-01T00:00:00Z",
        )
    )
    pool = RepositoryPool.objects.create(
        name="monitor-training",
        pool_type=RepositoryPoolType.TRAINING,
        status=RepositoryPoolStatus.CONFIRMED,
    )
    RepositoryPoolMembership.objects.create(
        pool=pool,
        repository=repository,
        category=repository.category,
        star_bucket="MID",
        age_cohort="MATURE",
        activity_level="LOW",
        selection_reason="coverage",
    )

    assert determine_monitoring_tier(repository, now=NOW) == MonitoringTier.NORMAL


@pytest.mark.django_db
def test_active_model_high_percentile_promotes_dormant_repository() -> None:
    from apps.forecasts.models import MLModel, ModelStatus, RepositoryForecast

    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            created_at="2020-01-01T00:00:00Z",
            pushed_at="2025-01-01T00:00:00Z",
        )
    )
    model = MLModel.objects.create(
        model_name="star-growth",
        model_version="monitor-active-v1",
        feature_version="feature-v2.0.0",
        label_version="label-v2.0.0",
        algorithm="random_forest_regressor",
        training_start=NOW - timedelta(days=180),
        training_end=NOW - timedelta(days=30),
        artifact_path="/tmp/model.joblib",
        artifact_sha256="a" * 64,
        status=ModelStatus.ACTIVE,
    )
    RepositoryForecast.objects.create(
        repository=repository,
        model=model,
        model_version=model.model_version,
        sample_at=NOW,
        confidence=0.8,
        predicted_activity_percentile=90,
    )

    assert determine_monitoring_tier(repository, now=NOW) == MonitoringTier.RISING


@pytest.mark.django_db
def test_refresh_is_idempotent_and_does_not_slide_unchanged_schedule() -> None:
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            created_at="2020-01-01T00:00:00Z",
            pushed_at="2025-01-01T00:00:00Z",
        )
    )
    first = refresh_repository_monitoring(repository.id, now=NOW)
    repository.refresh_from_db()
    scheduled = repository.next_snapshot_at
    second = refresh_repository_monitoring(repository.id, now=NOW + timedelta(hours=1))
    repository.refresh_from_db()

    assert first.tier == second.tier == MonitoringTier.NORMAL
    assert repository.next_snapshot_at == scheduled


@pytest.mark.django_db(transaction=True)
def test_repository_is_protected_from_downsampling_before_60_observed_days() -> None:
    payload = github_repository_payload(
        created_at="2020-01-01T00:00:00Z",
        pushed_at="2025-01-01T00:00:00Z",
    )
    first = SnapshotService(FakeGitHubClient()).persist_payload(
        payload, observed_at=NOW - timedelta(days=59)
    )
    SnapshotService(FakeGitHubClient()).persist_payload(payload, observed_at=NOW)

    assert determine_monitoring_tier(first.snapshot.repository, now=NOW) == MonitoringTier.NORMAL


@pytest.mark.django_db(transaction=True)
def test_repository_can_downsample_after_60_observed_days() -> None:
    from apps.activities.models import RepositoryActivityMetric

    payload = github_repository_payload(
        created_at="2020-01-01T00:00:00Z",
        pushed_at="2025-01-01T00:00:00Z",
    )
    first = SnapshotService(FakeGitHubClient()).persist_payload(
        payload, observed_at=NOW - timedelta(days=60)
    )
    SnapshotService(FakeGitHubClient()).persist_payload(payload, observed_at=NOW)
    RepositoryActivityMetric.objects.create(
        repository=first.snapshot.repository,
        metric_date=NOW.date(),
        commits_30d=3,
        prs_created_30d=1,
        active_contributors_30d=1,
        releases_30d=0,
    )

    assert determine_monitoring_tier(first.snapshot.repository, now=NOW) == MonitoringTier.DORMANT


@pytest.mark.django_db(transaction=True)
def test_missing_activity_or_recent_release_prevents_downsampling() -> None:
    from apps.activities.models import RepositoryActivityMetric

    payload = github_repository_payload(
        created_at="2020-01-01T00:00:00Z",
        pushed_at="2025-01-01T00:00:00Z",
    )
    first = SnapshotService(FakeGitHubClient()).persist_payload(
        payload, observed_at=NOW - timedelta(days=60)
    )
    SnapshotService(FakeGitHubClient()).persist_payload(payload, observed_at=NOW)
    repository = first.snapshot.repository

    assert determine_monitoring_tier(repository, now=NOW) == MonitoringTier.NORMAL

    RepositoryActivityMetric.objects.create(
        repository=repository,
        metric_date=NOW.date(),
        commits_30d=3,
        prs_created_30d=1,
        active_contributors_30d=1,
        releases_30d=1,
    )
    assert determine_monitoring_tier(repository, now=NOW) == MonitoringTier.NORMAL
