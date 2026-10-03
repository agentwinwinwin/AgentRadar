from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CapabilityName(models.TextChoices):
    STAR_GROWTH_7D = "STAR_GROWTH_7D", "Star growth 7d"
    STAR_GROWTH_30D = "STAR_GROWTH_30D", "Star growth 30d"
    FORK_GROWTH_7D = "FORK_GROWTH_7D", "Fork growth 7d"
    FORK_GROWTH_30D = "FORK_GROWTH_30D", "Fork growth 30d"
    MOMENTUM = "MOMENTUM", "Momentum"
    HYPE_RISK = "HYPE_RISK", "Hype risk"
    CATEGORY_TREND = "CATEGORY_TREND", "Category trend"
    TREND_CHANGE_ALERT = "TREND_CHANGE_ALERT", "Trend change alert"
    POTENTIAL_CHANGE_ALERT = "POTENTIAL_CHANGE_ALERT", "Potential change alert"
    FORECAST_V2_DATA_READINESS = "FORECAST_V2_DATA_READINESS", "Forecast V2 data readiness"


class CapabilityStatus(models.TextChoices):
    ACCUMULATING = "ACCUMULATING", "Accumulating"
    READY = "READY", "Ready"
    DEGRADED = "DEGRADED", "Degraded"
    DISABLED = "DISABLED", "Disabled"


class DataCapability(models.Model):
    name = models.CharField(max_length=50, choices=CapabilityName.choices, unique=True)
    status = models.CharField(
        max_length=20, choices=CapabilityStatus.choices, default=CapabilityStatus.ACCUMULATING
    )
    data_coverage = models.FloatField(
        default=0.0, validators=(MinValueValidator(0.0), MaxValueValidator(1.0))
    )
    algorithm_version = models.CharField(  # noqa: DJ001 - absence is meaningful
        max_length=50, null=True, blank=True
    )
    reason = models.TextField()
    metrics = models.JSONField(default=dict)
    data_as_of = models.DateTimeField(null=True, blank=True)
    first_ready_at = models.DateTimeField(null=True, blank=True)
    last_evaluated_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "data_capabilities"
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(data_coverage__gte=0.0) & models.Q(data_coverage__lte=1.0),
                name="capability_coverage_between_zero_and_one",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name}: {self.status}"


class CategoryTrendMetric(models.Model):
    category = models.CharField(max_length=50)
    algorithm_version = models.CharField(max_length=50)
    trend_score = models.DecimalField(max_digits=5, decimal_places=2)
    repository_count = models.PositiveIntegerField()
    eligible_repository_count = models.PositiveIntegerField()
    data_coverage = models.FloatField(validators=(MinValueValidator(0.0), MaxValueValidator(1.0)))
    data_as_of = models.DateTimeField()
    evidence = models.JSONField(default=dict)
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "category_trend_metrics"
        constraints = [
            models.UniqueConstraint(
                fields=("category", "algorithm_version"),
                name="unique_category_trend_algorithm",
            ),
            models.CheckConstraint(
                condition=models.Q(data_coverage__gte=0.0) & models.Q(data_coverage__lte=1.0),
                name="category_trend_coverage_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category}: {self.algorithm_version}"
