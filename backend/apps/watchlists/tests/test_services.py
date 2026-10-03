from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.activities.models import RepositoryRelease
from apps.potentials.engine import ALGORITHM_VERSION as POTENTIAL_VERSION
from apps.potentials.models import RepositoryPotentialScore
from apps.repositories.models import Repository
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import ALGORITHM_VERSION as TREND_VERSION
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore

from ..models import Alert, ScheduledReport, Watchlist, WatchlistEvent, WatchlistItem
from ..services import AlertService, ReportService, WatchlistService


def repository(github_id=1):
    now = timezone.now()
    return Repository.objects.create(
        github_id=github_id,
        owner="acme",
        name=f"agent-{github_id}",
        full_name=f"acme/agent-{github_id}",
        default_branch="main",
        github_created_at=now - timedelta(days=400),
        github_updated_at=now,
        last_synced_at=now,
    )


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(username="owner", password="test-password")


@pytest.mark.django_db
def test_watchlist_add_is_idempotent_and_remove_is_audited(owner):
    repo = repository()
    first, created = WatchlistService.add(repo.id, owner)
    second, repeated = WatchlistService.add(repo.id, owner)
    assert created is True and repeated is False and first.id == second.id
    assert WatchlistItem.objects.count() == 1
    assert WatchlistEvent.objects.filter(action=WatchlistEvent.Action.ADDED).count() == 1
    assert WatchlistService.remove(repo.id, owner) is True
    assert WatchlistService.remove(repo.id, owner) is False
    assert WatchlistEvent.objects.filter(action=WatchlistEvent.Action.REMOVED).count() == 1


@pytest.mark.django_db
def test_empty_watchlist_read_does_not_create_a_watchlist(owner):
    assert list(WatchlistService.list(owner)) == []
    assert Watchlist.objects.count() == 0


@pytest.mark.django_db
def test_snapshot_alert_requires_real_seven_day_history_and_is_idempotent():
    repo = repository()
    now = timezone.now()
    RepositorySnapshot.objects.create(
        repository=repo,
        snapshot_at=now,
        snapshot_date=now.date(),
        snapshot_bucket="2026-08-18T00",
        stars=300,
        forks=50,
        data_completeness=1,
    )
    assert AlertService.evaluate_repository(repo.id)["created"] == 0
    baseline_at = now - timedelta(days=8)
    RepositorySnapshot.objects.create(
        repository=repo,
        snapshot_at=baseline_at,
        snapshot_date=baseline_at.date(),
        snapshot_bucket="2026-08-10T00",
        stars=100,
        forks=10,
        data_completeness=1,
    )
    assert AlertService.evaluate_repository(repo.id)["created"] == 2
    assert AlertService.evaluate_repository(repo.id)["created"] == 0
    assert Alert.objects.count() == 2


@pytest.mark.django_db
def test_high_potential_requires_confidence_and_trend_completeness():
    repo = repository()
    now = timezone.now()
    trend = RepositoryTrendScore.objects.create(
        repository=repo,
        trend_score=85,
        hype_risk_status=HypeRiskStatus.INSUFFICIENT_HISTORY,
        lifecycle_stage=LifecycleStage.GROWING,
        data_completeness=0.8,
        algorithm_version=TREND_VERSION,
        calculated_at=now,
    )
    potential = RepositoryPotentialScore.objects.create(
        repository=repo,
        potential_score=90,
        confidence=0.2,
        algorithm_version=POTENTIAL_VERSION,
        calculated_at=now,
    )
    assert AlertService.evaluate_repository(repo.id)["created"] == 0
    potential.confidence = 0.8
    potential.save(update_fields=("confidence",))
    assert AlertService.evaluate_repository(repo.id)["created"] == 1
    alert = Alert.objects.get(alert_type=Alert.Type.NEW_HIGH_POTENTIAL_PROJECT)
    assert alert.evidence["potential_algorithm_version"] == POTENTIAL_VERSION
    assert alert.evidence["trend_algorithm_version"] == trend.algorithm_version


@pytest.mark.django_db
def test_recent_real_release_creates_one_idempotent_alert():
    repo = repository()
    published_at = timezone.now() - timedelta(days=8)
    RepositoryRelease.objects.create(
        repository=repo,
        github_release_id=99,
        tag_name="v1.0",
        is_draft=False,
        published_at=published_at,
        content_hash="a" * 64,
    )
    assert AlertService.evaluate_repository(repo.id)["created"] == 1
    assert AlertService.evaluate_repository(repo.id)["created"] == 0
    alert = Alert.objects.get(alert_type=Alert.Type.NEW_RELEASE)
    assert alert.evidence["published_at"] == published_at.isoformat()


@pytest.mark.django_db
def test_dormant_uses_real_repository_push_timestamp_when_activity_is_missing():
    repo = repository()
    repo.github_pushed_at = timezone.now() - timedelta(days=100)
    repo.save(update_fields=("github_pushed_at",))
    assert AlertService.evaluate_repository(repo.id)["created"] == 1
    alert = Alert.objects.get(alert_type=Alert.Type.PROJECT_DORMANT)
    assert alert.evidence["source"] == "repositories.github_pushed_at"


@pytest.mark.django_db
def test_daily_and_weekly_reports_are_structured_and_idempotent(owner):
    repo = repository()
    WatchlistService.add(repo.id, owner)
    now = timezone.now()
    daily = ReportService.generate(ScheduledReport.Type.DAILY, owner, now=now)
    repeated = ReportService.generate(ScheduledReport.Type.DAILY, owner, now=now)
    weekly = ReportService.generate(ScheduledReport.Type.WEEKLY, owner, now=now)
    assert daily.id == repeated.id
    assert weekly.report_type == ScheduledReport.Type.WEEKLY
    assert daily.content["facts_source"] == "STRUCTURED_DATABASE_AND_EXISTING_EVIDENCE"
    assert daily.content["llm_used"] is False
    assert daily.content["insufficient_evidence"][0]["reason"] == "7D_SNAPSHOT_HISTORY"
