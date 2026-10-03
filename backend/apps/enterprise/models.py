from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class RepositoryEnterpriseScore(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="enterprise_scores"
    )
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    confidence = models.FloatField(validators=(MinValueValidator(0), MaxValueValidator(1)))
    recommendation = models.CharField(max_length=10)
    algorithm_version = models.CharField(max_length=50)
    evidence = models.JSONField(default=dict)
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "repository_enterprise_scores"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "algorithm_version"),
                name="unique_repository_enterprise_algorithm",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0) & models.Q(confidence__lte=1),
                name="enterprise_confidence_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.algorithm_version}"
