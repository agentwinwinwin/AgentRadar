from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class ModelStatus(models.TextChoices):
    TRAINED = "TRAINED", "Trained"
    VALIDATED = "VALIDATED", "Validated"
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired"


class PredictionRolloutStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not started"
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    PARTIAL = "PARTIAL", "Partial"
    FAILED = "FAILED", "Failed"


class TrainingRunStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    BLOCKED = "BLOCKED", "Blocked"


class ModelTrainingRun(models.Model):
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="model_training_runs",
    )
    singleton_key = models.CharField(max_length=50, default="forecast-v1-training", editable=False)
    status = models.CharField(
        max_length=20, choices=TrainingRunStatus.choices, default=TrainingRunStatus.QUEUED
    )
    feature_version = models.CharField(max_length=50)
    label_version = models.CharField(max_length=50)
    celery_task_id = models.CharField(max_length=255, unique=True)
    dataset_gate_snapshot = models.JSONField(default=dict)
    split_readiness_snapshot = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "model_training_runs"
        ordering = ("-requested_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("singleton_key",),
                condition=models.Q(
                    status__in=(TrainingRunStatus.QUEUED, TrainingRunStatus.RUNNING)
                ),
                name="unique_inflight_forecast_training",
            )
        ]
        indexes = [models.Index(fields=("status", "-requested_at"))]

    def __str__(self) -> str:
        return f"training run {self.pk}: {self.status}"


class MLModel(models.Model):
    model_name = models.CharField(max_length=100)
    model_version = models.CharField(max_length=100, unique=True)
    feature_version = models.CharField(max_length=50)
    label_version = models.CharField(max_length=50)
    algorithm = models.CharField(max_length=50)
    training_start = models.DateTimeField()
    training_end = models.DateTimeField()
    validation_metrics = models.JSONField(default=dict)
    test_metrics = models.JSONField(default=dict)
    dataset_quality = models.JSONField(default=dict)
    feature_importance = models.JSONField(default=dict)
    artifact_path = models.CharField(max_length=1000)
    artifact_sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20, choices=ModelStatus.choices, default=ModelStatus.TRAINED
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    prediction_rollout_status = models.CharField(
        max_length=20,
        choices=PredictionRolloutStatus.choices,
        default=PredictionRolloutStatus.NOT_STARTED,
    )
    prediction_rollout = models.JSONField(default=dict)
    retraining_targets = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ml_models"
        constraints = [
            models.UniqueConstraint(
                fields=("model_name", "model_version"), name="unique_ml_model_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.model_version} ({self.status})"


class RepositoryForecast(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="forecasts")
    model = models.ForeignKey(MLModel, on_delete=models.PROTECT, related_name="forecasts")
    model_version = models.CharField(max_length=100)
    sample_at = models.DateTimeField()
    forecast_horizon_days = models.PositiveSmallIntegerField(default=30)
    high_growth_probability = models.FloatField(
        null=True,
        blank=True,
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0)),
    )
    prediction = models.PositiveSmallIntegerField(null=True, blank=True)
    confidence = models.FloatField(validators=(MinValueValidator(0.0), MaxValueValidator(1.0)))
    predicted_activity_percentile = models.FloatField(
        null=True,
        blank=True,
        validators=(MinValueValidator(0.0), MaxValueValidator(100.0)),
    )
    percentile_model_version = models.CharField(max_length=100, blank=True, default="")
    feature_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "repository_forecasts"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "model_version", "sample_at"),
                name="unique_repository_forecast_model_sample",
            ),
            models.CheckConstraint(
                condition=models.Q(prediction__isnull=True) | models.Q(prediction__in=(0, 1)),
                name="forecast_binary_prediction",
            ),
            models.CheckConstraint(
                condition=models.Q(predicted_activity_percentile__isnull=True)
                | (
                    models.Q(predicted_activity_percentile__gte=0.0)
                    & models.Q(predicted_activity_percentile__lte=100.0)
                ),
                name="forecast_percentile_between_zero_and_hundred",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.model_version}"
