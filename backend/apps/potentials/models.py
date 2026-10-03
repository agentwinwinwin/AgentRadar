from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class RepositoryPotentialScore(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="potential_scores"
    )
    potential_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    confidence = models.FloatField(validators=(MinValueValidator(0.0), MaxValueValidator(1.0)))
    algorithm_version = models.CharField(max_length=50)
    evidence = models.JSONField(default=dict)
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "repository_potential_scores"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "algorithm_version"),
                name="unique_repository_potential_algorithm",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0),
                name="potential_confidence_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.algorithm_version}"
