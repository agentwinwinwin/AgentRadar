from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.activities.models import RepositoryActivityMetric
from apps.forecasts.models import MLModel, ModelStatus
from apps.github.fakes import FakeGitHubClient
from apps.operations.models import RepositoryScoreHistory
from apps.repositories.models import RepositoryCategory
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import ALGORITHM_VERSION
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore
from apps.watchlists.models import Alert
from apps.watchlists.services import AlertService

from ..models import CapabilityName, CapabilityStatus, CategoryTrendMetric, DataCapability
from ..services import CATEGORY_TREND_VERSION, DataMaturityService
from ..tasks import evaluate_data_maturity, recalculate_mature_scores


class AcquiredLock:
    acquired = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def repository(index: int, category=RepositoryCategory.CODING_AGENT):
    item, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            id=770_000 + index,
            full_name=f"maturity/repo-{index}",
            name=f"repo-{index}",
        )
    )
    item.category = category
    item.save(update_fields=("category", "updated_at"))
    return item


def snapshot(item, at, *, stars=100, forks=10):
    return RepositorySnapshot.objects.create(
        repository=item,
        snapshot_at=at,
        snapshot_date=at.date(),
        snapshot_bucket=at.strftime("%Y-%m-%dT%H"),
        stars=stars,
        forks=forks,
        data_origin="OBSERVED",
        data_completeness=1.0,
    )


def activity(item, at):
    return RepositoryActivityMetric.objects.create(
        repository=item,
        metric_date=at.date(),
        commits_30d=10,
        prs_created_30d=4,
        prs_merged_30d=3,
        active_contributors_30d=2,
        issues_created_30d=2,
        issues_closed_30d=2,
    )


BASE_GATES = override_settings(
    CAPABILITY_MIN_REPOSITORIES=1,
    CAPABILITY_MIN_COVERAGE=1.0,
    CATEGORY_TREND_MIN_REPOSITORIES=1,
    CATEGORY_TREND_MIN_COVERAGE=1.0,
    CATEGORY_TREND_MIN_CATEGORIES=2,
    FORECAST_V2_MIN_REPOSITORIES=1,
    FORECAST_V2_MIN_TRAINING_SAMPLES=1,
    FORECAST_V2_MIN_CATEGORIES=1,
)


@pytest.mark.django_db
@BASE_GATES
@pytest.mark.parametrize(
    ("span_days", "capability", "expected"),
    [
        (6, CapabilityName.STAR_GROWTH_7D, CapabilityStatus.ACCUMULATING),
        (7, CapabilityName.STAR_GROWTH_7D, CapabilityStatus.READY),
        (29, CapabilityName.STAR_GROWTH_30D, CapabilityStatus.ACCUMULATING),
        (30, CapabilityName.STAR_GROWTH_30D, CapabilityStatus.READY),
    ],
)
def test_growth_readiness_uses_real_observed_span(span_days, capability, expected):
    item = repository(span_days)
    now = datetime(2026, 8, 18, tzinfo=UTC)
    snapshot(item, now - timedelta(days=span_days), stars=90, forks=9)
    snapshot(item, now, stars=100, forks=10)

    DataMaturityService().evaluate()

    assert DataCapability.objects.get(name=capability).status == expected


@pytest.mark.django_db
@BASE_GATES
def test_null_growth_is_not_treated_as_zero_and_hype_stays_accumulating():
    item = repository(40)
    now = datetime(2026, 8, 18, tzinfo=UTC)
    snapshot(item, now - timedelta(days=30), stars=None, forks=None)
    snapshot(item, now, stars=100, forks=10)

    DataMaturityService().evaluate()

    assert DataCapability.objects.get(name=CapabilityName.STAR_GROWTH_30D).data_coverage == 0
    assert (
        DataCapability.objects.get(name=CapabilityName.HYPE_RISK).status
        == CapabilityStatus.ACCUMULATING
    )


@pytest.mark.django_db
@BASE_GATES
def test_momentum_and_hype_become_ready_only_with_growth_and_activity():
    item = repository(50)
    now = datetime(2026, 8, 18, tzinfo=UTC)
    snapshot(item, now - timedelta(days=30), stars=50, forks=5)
    snapshot(item, now - timedelta(days=7), stars=80, forks=8)
    snapshot(item, now, stars=100, forks=10)
    DataMaturityService().evaluate()
    assert (
        DataCapability.objects.get(name=CapabilityName.MOMENTUM).status
        == CapabilityStatus.ACCUMULATING
    )

    activity(item, now)
    DataMaturityService().evaluate()
    assert DataCapability.objects.get(name=CapabilityName.MOMENTUM).status == CapabilityStatus.READY
    assert (
        DataCapability.objects.get(name=CapabilityName.HYPE_RISK).status == CapabilityStatus.READY
    )


@pytest.mark.django_db
@BASE_GATES
def test_category_trend_fallback_then_ready_and_versioned():
    now = datetime(2026, 8, 18, tzinfo=UTC)
    first = repository(61, RepositoryCategory.CODING_AGENT)
    snapshot(first, now - timedelta(days=30))
    snapshot(first, now)
    RepositoryTrendScore.objects.create(
        repository=first,
        trend_score=70,
        hype_risk_status=HypeRiskStatus.INSUFFICIENT_HISTORY,
        lifecycle_stage=LifecycleStage.GROWING,
        data_completeness=0.8,
        algorithm_version=ALGORITHM_VERSION,
        calculated_at=now,
    )
    DataMaturityService().evaluate()
    assert (
        DataCapability.objects.get(name=CapabilityName.CATEGORY_TREND).status
        == CapabilityStatus.ACCUMULATING
    )
    assert CategoryTrendMetric.objects.count() == 0

    second = repository(62, RepositoryCategory.BROWSER_AGENT)
    snapshot(second, now - timedelta(days=30))
    snapshot(second, now)
    RepositoryTrendScore.objects.create(
        repository=second,
        trend_score=80,
        hype_risk_status=HypeRiskStatus.INSUFFICIENT_HISTORY,
        lifecycle_stage=LifecycleStage.GROWING,
        data_completeness=0.8,
        algorithm_version=ALGORITHM_VERSION,
        calculated_at=now,
    )
    DataMaturityService().evaluate()
    capability = DataCapability.objects.get(name=CapabilityName.CATEGORY_TREND)
    assert capability.status == CapabilityStatus.READY
    assert capability.algorithm_version == CATEGORY_TREND_VERSION
    assert CategoryTrendMetric.objects.count() == 2


@pytest.mark.django_db
@BASE_GATES
def test_repeated_celery_evaluation_dispatches_recalculation_only_on_transition():
    item = repository(70)
    now = datetime(2026, 8, 18, tzinfo=UTC)
    snapshot(item, now - timedelta(days=7), stars=90, forks=9)
    snapshot(item, now, stars=100, forks=10)

    with (
        patch("apps.capabilities.tasks.RedisCapabilityLock", return_value=AcquiredLock()),
        patch("apps.capabilities.tasks.recalculate_mature_scores.delay") as dispatch,
    ):
        first = evaluate_data_maturity.run()
        second = evaluate_data_maturity.run()

    assert first["recalculation_dispatched"] is True
    assert second["recalculation_dispatched"] is False
    dispatch.assert_called_once_with()


@pytest.mark.django_db
def test_forecast_v2_uses_larger_next_retraining_targets_after_activation():
    item = repository(75)
    now = datetime(2026, 8, 18, tzinfo=UTC)
    snapshot(item, now - timedelta(days=90), stars=50, forks=5)
    snapshot(item, now, stars=100, forks=10)
    MLModel.objects.create(
        model_name="star-growth-percentile-30d",
        model_version="star-v2-active",
        feature_version="feature-v2.0.0",
        label_version="label-v2.0.0",
        algorithm="random_forest_regressor",
        training_start=now - timedelta(days=180),
        training_end=now - timedelta(days=30),
        validation_metrics={"mae": 10, "r2": 0.5},
        test_metrics={"mae": 12, "r2": 0.4},
        dataset_quality={"passed": True},
        artifact_path="unused",
        artifact_sha256="0" * 64,
        status=ModelStatus.ACTIVE,
        activated_at=now,
        retraining_targets={
            "cycle": "NEXT_RETRAINING",
            "observed_span_days": 90,
            "observed_repositories": 400,
            "training_samples": 400,
            "categories": 5,
        },
    )

    DataMaturityService().evaluate()

    capability = DataCapability.objects.get(name=CapabilityName.FORECAST_V2_DATA_READINESS)
    assert capability.status == CapabilityStatus.ACCUMULATING
    assert capability.metrics["readiness_phase"] == "NEXT_RETRAINING"
    assert capability.metrics["required_observed_span_days"] == 90
    assert capability.metrics["required_observed_repositories"] == 400
    assert capability.metrics["required_training_samples"] == 400
    assert capability.metrics["collection_continues_after_activation"] is True


@pytest.mark.django_db
def test_daily_maturity_dispatches_newly_eligible_prediction_for_active_star_model():
    now = datetime(2026, 8, 18, tzinfo=UTC)
    model = MLModel.objects.create(
        model_name="star-growth-percentile-30d",
        model_version="star-v2-active-daily",
        feature_version="feature-v2.0.0",
        label_version="label-v2.0.0",
        algorithm="random_forest_regressor",
        training_start=now - timedelta(days=180),
        training_end=now - timedelta(days=30),
        validation_metrics={"mae": 10, "r2": 0.5},
        test_metrics={"mae": 12, "r2": 0.4},
        dataset_quality={"passed": True, "feature_names": ["star_growth_30d"]},
        artifact_path="unused",
        artifact_sha256="0" * 64,
        status=ModelStatus.ACTIVE,
        activated_at=now,
    )

    with (
        patch("apps.capabilities.tasks.RedisCapabilityLock", return_value=AcquiredLock()),
        patch(
            "apps.forecasts.tasks.predict_newly_eligible_star_repositories.delay"
        ) as dispatch,
    ):
        result = evaluate_data_maturity.run()

    assert result["star_eligibility_prediction_dispatched"] is True
    assert result["star_model_version"] == model.model_version
    dispatch.assert_called_once_with(model.model_version)


@pytest.mark.django_db
def test_change_alert_is_suppressed_while_capability_accumulates():
    item = repository(80)
    now = datetime(2026, 8, 18, tzinfo=UTC)
    DataCapability.objects.create(
        name=CapabilityName.TREND_CHANGE_ALERT,
        status=CapabilityStatus.ACCUMULATING,
        data_coverage=0.1,
        reason="score history insufficient",
        last_evaluated_at=now,
    )
    for offset, score in ((1, 40), (0, 80)):
        RepositoryScoreHistory.objects.create(
            repository=item,
            score_type=RepositoryScoreHistory.ScoreType.TREND,
            algorithm_version=ALGORITHM_VERSION,
            score=score,
            confidence=0.8,
            history_bucket=f"202608{18 - offset}-00",
            calculated_at=now - timedelta(days=offset),
        )

    AlertService.evaluate_repository(item.id)

    assert not Alert.objects.filter(alert_type=Alert.Type.TREND_CHANGE).exists()


def test_capability_tasks_use_operations_queue(settings):
    assert settings.CELERY_TASK_ROUTES["capabilities.*"]["queue"] == "operations"
    assert settings.CELERY_BEAT_SCHEDULE["evaluate-data-maturity-daily"]["options"] == {
        "queue": "operations"
    }


@pytest.mark.django_db
@override_settings(CAPABILITY_RECALC_BATCH_SIZE=2)
def test_score_recalculation_is_dispatched_in_bounded_batches():
    first, second, third = repository(91), repository(92), repository(93)
    with (
        patch("apps.trends.tasks.dispatch_trend_score") as score,
        patch("apps.capabilities.tasks.recalculate_mature_scores.apply_async") as next_batch,
    ):
        result = recalculate_mature_scores.run()

    assert result["dispatched"] == 2
    assert result["has_more"] is True
    assert result["next_after_id"] == second.id
    score.assert_any_call(first.id)
    score.assert_any_call(second.id)
    next_batch.assert_called_once_with(args=[second.id], countdown=5)
    assert third.id > result["next_after_id"]
