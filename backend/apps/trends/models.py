from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class HypeRiskStatus(models.TextChoices):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY", "Insufficient history"
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class LifecycleStage(models.TextChoices):
    EMERGING = "EMERGING", "Emerging"
    ACCELERATING = "ACCELERATING", "Accelerating"
    BREAKOUT = "BREAKOUT", "Breakout"
    GROWING = "GROWING", "Growing"
    MATURE = "MATURE", "Mature"
    COOLING = "COOLING", "Cooling"
    DORMANT = "DORMANT", "Dormant"


class RepositoryTrendScore(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="trend_scores"
    )
    trend_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    momentum_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    development_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    community_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    delivery_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    adoption_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    topic_momentum_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    maintenance_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hype_risk = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hype_risk_status = models.CharField(max_length=30, choices=HypeRiskStatus.choices)
    lifecycle_stage = models.CharField(max_length=20, choices=LifecycleStage.choices)
    data_completeness = models.FloatField(
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0))
    )
    algorithm_version = models.CharField(max_length=50)
    calculated_at = models.DateTimeField()
    evidence = models.JSONField(default=dict)

    class Meta:
        db_table = "repository_trend_scores"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "algorithm_version"),
                name="unique_repository_trend_algorithm",
            ),
            models.CheckConstraint(
                condition=models.Q(data_completeness__gte=0.0)
                & models.Q(data_completeness__lte=1.0),
                name="trend_completeness_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.algorithm_version}"
