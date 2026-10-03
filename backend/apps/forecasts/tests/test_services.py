from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.datasets.models import DataOrigin, TrainingSample
from apps.datasets.services import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    LABEL_VERSION,
    PERCENTILE_LABEL_VERSION,
)
from apps.datasets.tests.test_backfill import create_repository
from apps.forecasts.models import MLModel, ModelStatus, RepositoryForecast
from apps.forecasts.services import (
    DatasetEarlyStopService,
    DatasetQualityGate,
    ForecastService,
    ForecastTrainingService,
    ModelActivationService,
    PercentileRegressionService,
    StarPercentileRolloutService,
    TrainingBlockedError,
)
from apps.repositories.models import RepositoryCategory


def create_sample(repository, index: int) -> TrainingSample:
    sample_date = date(2025, 1, 1) + timedelta(days=index)
    category = RepositoryCategory.BROWSER_AGENT if index % 2 else RepositoryCategory.CODING_AGENT
    features = {name: (category if name == "category" else index % 17) for name in FEATURE_NAMES}
    features["_provenance"] = {
        "data_origin": DataOrigin.BACKFILLED,
        "feature_timestamps": [
            datetime.combine(sample_date, datetime.max.time(), tzinfo=UTC).isoformat()
        ],
    }
    return TrainingSample.objects.create(
        repository=repository,
        sample_at=datetime.combine(sample_date, datetime.max.time(), tzinfo=UTC),
        feature_window_start=sample_date - timedelta(days=29),
        feature_window_end=sample_date,
        label_window_start=sample_date + timedelta(days=1),
        label_window_end=sample_date + timedelta(days=30),
        category=category,
        age_cohort="AGE_31_180" if index % 2 else "AGE_181_730",
        features=features,
        label=int(index % 5 == 0),
        label_score=100 if index % 5 == 0 else 0,
        feature_version=FEATURE_VERSION,
        label_version=LABEL_VERSION,
        data_origin=DataOrigin.BACKFILLED,
    )


@pytest.mark.django_db
def test_quality_gate_rejects_smoke_dataset() -> None:
    repository = create_repository()
    create_sample(repository, 1)

    gate = DatasetQualityGate().evaluate()

    assert gate.passed is False
    assert gate.checks["total_samples"]["passed"] is False
    with pytest.raises(TrainingBlockedError):
        ForecastTrainingService().train()
    assert MLModel.objects.count() == 0


@pytest.mark.django_db
def test_quality_gate_empty_dataset_reports_missingness_failure() -> None:
    gate = DatasetQualityGate().evaluate()

    assert gate.passed is False
    assert gate.checks["maximum_feature_missing_rate"]["actual"] == 1.0
    assert gate.checks["maximum_feature_missing_rate"]["passed"] is False


@pytest.mark.django_db
def test_time_based_training_compares_three_models_and_never_auto_activates(tmp_path) -> None:
    repository = create_repository()
    for index in range(210):
        create_sample(repository, index)

    with override_settings(ML_ARTIFACT_ROOT=tmp_path):
        result = ForecastTrainingService().train()
        repeated = ForecastTrainingService().train()

    assert {model.algorithm for model in result["models"]} == {
        "logistic_regression",
        "random_forest",
        "xgboost",
    }
    assert result["forecast_status"] == "NOT_READY"
    assert MLModel.objects.filter(status=ModelStatus.ACTIVE).count() == 0
    assert MLModel.objects.count() == 3
    assert repeated["selected_model_version"] == result["selected_model_version"]
    for model in result["models"]:
        assert model.training_start < model.training_end
        assert model.feature_version == FEATURE_VERSION
        assert model.label_version == LABEL_VERSION
        assert set(model.validation_metrics) >= {
            "accuracy",
            "precision",
            "recall",
            "f1",
            "roc_auc",
            "pr_auc",
            "confusion_matrix",
        }
        assert model.feature_importance


@pytest.mark.django_db
def test_early_stop_requires_gate_and_all_time_splits_with_both_classes() -> None:
    repository = create_repository()
    assert DatasetEarlyStopService().evaluate()["early_stop"] is False
    for index in range(210):
        create_sample(repository, index)

    result = DatasetEarlyStopService().evaluate()

    assert result["quality_gate_passed"] is True
    assert result["time_split_ready"] is True
    assert result["early_stop"] is True
    assert all(
        values["positive"] > 0 and values["negative"] > 0
        for values in result["split_counts"].values()
    )


@pytest.mark.django_db
def test_v1_2_classification_regression_and_learning_curve(tmp_path) -> None:
    repository = create_repository()
    for index in range(210):
        sample = create_sample(repository, index)
        sample.label_version = PERCENTILE_LABEL_VERSION
        sample.future_activity_percentile = 100.0 if sample.label else 0.0
        sample.binary_top20_label = sample.label
        sample.label_cohort_size = 30
        sample.save(
            update_fields=(
                "label_version",
                "future_activity_percentile",
                "binary_top20_label",
                "label_cohort_size",
                "updated_at",
            )
        )

    with override_settings(ML_ARTIFACT_ROOT=tmp_path):
        service = ForecastTrainingService(label_version=PERCENTILE_LABEL_VERSION)
        result = service.train()
        regression = PercentileRegressionService().train()
        curve = service.learning_curve(
            list(
                TrainingSample.objects.filter(label_version=PERCENTILE_LABEL_VERSION).order_by(
                    "sample_at", "id"
                )
            ),
            algorithm="logistic_regression",
        )

    assert all(model.label_version == PERCENTILE_LABEL_VERSION for model in result["models"])
    assert all(
        all("__x" not in name for name in model.feature_importance) for model in result["models"]
    )
    assert set(regression["validation_metrics"]) >= {"mae", "rmse", "r2"}
    assert regression["model"].status == ModelStatus.VALIDATED
    assert {point["fraction"] for point in curve["points"]} == {0.25, 0.5, 0.75, 1.0}
    assert curve["assessment"] in {
        "MORE_DATA_LIKELY_BENEFICIAL",
        "DATASET_SIZE_CURRENTLY_SUFFICIENT",
    }


@pytest.mark.django_db
def test_activation_rejects_bad_metrics_and_forecast_falls_back() -> None:
    repository = create_repository()
    model = MLModel.objects.create(
        model_name="activity-growth-30d",
        model_version="bad-v1",
        feature_version=FEATURE_VERSION,
        label_version=LABEL_VERSION,
        algorithm="logistic_regression",
        training_start=datetime(2025, 1, 1, tzinfo=UTC),
        training_end=datetime(2025, 6, 1, tzinfo=UTC),
        validation_metrics={"precision": 0.1, "recall": 0.1, "f1": 0.1, "pr_auc": 0.1},
        test_metrics={"precision": 0.1, "recall": 0.1, "f1": 0.1, "pr_auc": 0.1},
        dataset_quality={"passed": True},
        artifact_path="unused",
        artifact_sha256="0" * 64,
        status=ModelStatus.VALIDATED,
    )

    with pytest.raises(ValueError, match="below activation"):
        ModelActivationService().activate(model.model_version)
    response = ForecastService().status(repository.id)
    assert response["status"] == "NOT_READY"
    assert response["fallback"] == "POTENTIAL_SCORE"


@pytest.mark.django_db
def test_star_percentile_activation_uses_regression_gate_and_declared_features() -> None:
    model = MLModel.objects.create(
        model_name="star-growth-percentile-30d",
        model_version="star-v2-candidate",
        feature_version="feature-v2.0.0",
        label_version="label-v2.0.0",
        algorithm="random_forest_regressor",
        training_start=datetime(2025, 1, 1, tzinfo=UTC),
        training_end=datetime(2025, 6, 1, tzinfo=UTC),
        validation_metrics={"mae": 12.0, "r2": 0.5},
        test_metrics={"mae": 15.0, "r2": 0.4},
        dataset_quality={"passed": True, "feature_names": ["star_growth_30d"]},
        artifact_path="unused",
        artifact_sha256="0" * 64,
        status=ModelStatus.VALIDATED,
    )

    eligible, reasons = ModelActivationService.eligibility(model)

    assert eligible is True
    assert reasons == []

    model.dataset_quality = {"passed": True, "feature_names": ["repository_id"]}
    model.save(update_fields=("dataset_quality",))
    eligible, reasons = ModelActivationService.eligibility(model)
    assert eligible is False
    assert "repository_id 禁止作为模型 Feature" in reasons


@pytest.mark.django_db
def test_binary_forecast_is_scheduled_on_demand_once_when_features_exist() -> None:
    repository = create_repository()
    create_sample(repository, 1)
    now = datetime.now(tz=UTC)
    MLModel.objects.create(
        model_name="activity-growth-30d",
        model_version="binary-active-on-demand",
        feature_version=FEATURE_VERSION,
        label_version=LABEL_VERSION,
        algorithm="random_forest",
        training_start=now - timedelta(days=180),
        training_end=now - timedelta(days=30),
        validation_metrics={},
        test_metrics={},
        dataset_quality={"passed": True},
        artifact_path="unused",
        artifact_sha256="0" * 64,
        status=ModelStatus.ACTIVE,
    )

    redis_client = type("RedisClient", (), {"set": lambda *args, **kwargs: True})()
    with (
        patch("apps.forecasts.services.Redis.from_url", return_value=redis_client),
        patch("apps.forecasts.tasks.run_forecast.delay") as dispatch,
    ):
        result = ForecastService().status(repository.id)

    assert result["status"] == "PENDING"
    assert result["model_version"] == "binary-active-on-demand"
    dispatch.assert_called_once_with(repository.id)


@pytest.mark.django_db
def test_star_percentile_only_missing_predicts_newly_eligible_once(tmp_path) -> None:
    existing_repository = create_repository()
    new_repository = create_repository(2)
    existing_sample = create_sample(existing_repository, 2)
    new_sample = create_sample(new_repository, 3)
    for sample in (existing_sample, new_sample):
        sample.feature_version = "feature-v2.0.0"
        sample.label_version = "label-v2.0.0"
        sample.save(update_fields=("feature_version", "label_version", "updated_at"))
    artifact = tmp_path / "star.joblib"
    artifact.write_bytes(b"star-model")
    import hashlib

    model = MLModel.objects.create(
        model_name="star-growth-percentile-30d",
        model_version="star-v2-active-eligibility",
        feature_version="feature-v2.0.0",
        label_version="label-v2.0.0",
        algorithm="random_forest_regressor",
        training_start=datetime(2025, 1, 1, tzinfo=UTC),
        training_end=datetime(2025, 6, 1, tzinfo=UTC),
        validation_metrics={"mae": 10, "r2": 0.5},
        test_metrics={"mae": 12, "r2": 0.4},
        dataset_quality={"passed": True, "feature_names": ["commit_30d"]},
        artifact_path=str(artifact),
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        status=ModelStatus.ACTIVE,
    )
    RepositoryForecast.objects.create(
        repository=existing_repository,
        model=model,
        model_version=model.model_version,
        sample_at=existing_sample.sample_at,
        confidence=0.8,
        predicted_activity_percentile=42,
        percentile_model_version=model.model_version,
    )
    pipeline = type("Pipeline", (), {"predict": lambda self, matrix: [77.0]})()

    with patch("apps.forecasts.services.joblib.load", return_value=pipeline):
        first = StarPercentileRolloutService().run(model.model_version, only_missing=True)
        second = StarPercentileRolloutService().run(model.model_version, only_missing=True)

    assert first == {"total": 1, "predicted": 1, "skipped": 0, "failed": 0}
    assert second == {"total": 0, "predicted": 0, "skipped": 0, "failed": 0}
    frozen = RepositoryForecast.objects.get(repository=existing_repository, model=model)
    assert frozen.predicted_activity_percentile == 42
    predicted = RepositoryForecast.objects.get(repository=new_repository, model=model)
    assert predicted.predicted_activity_percentile == 77
    assert predicted.feature_snapshot["prediction_policy"] == "FROZEN_UNTIL_NEXT_MODEL_ACTIVATION"
