from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class RepositoryScoreHistory(models.Model):
    class ScoreType(models.TextChoices):
        TREND = "TREND", "Trend"
        POTENTIAL = "POTENTIAL", "Potential"

    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="score_history"
    )
    score_type = models.CharField(max_length=16, choices=ScoreType.choices)
    algorithm_version = models.CharField(max_length=50)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    confidence = models.FloatField(
        null=True, blank=True, validators=(MinValueValidator(0), MaxValueValidator(1))
    )
    evidence = models.JSONField(default=dict)
    history_bucket = models.CharField(max_length=13)
    calculated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "repository_score_history"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "score_type", "algorithm_version", "history_bucket"),
                name="unique_repository_score_history_bucket",
            )
        ]
        indexes = [
            models.Index(
                fields=("repository", "score_type", "-calculated_at"),
                name="score_history_repo_type_at_idx",
            ),
            models.Index(fields=("score_type", "-calculated_at"), name="score_history_type_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.repository_id}:{self.score_type}:{self.history_bucket}"
