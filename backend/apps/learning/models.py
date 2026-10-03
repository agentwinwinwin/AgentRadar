from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class RepositoryLearningScore(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="learning_scores"
    )
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    confidence = models.FloatField(validators=(MinValueValidator(0), MaxValueValidator(1)))
    algorithm_version = models.CharField(max_length=50)
    evidence = models.JSONField(default=dict)
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "repository_learning_scores"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "algorithm_version"),
                name="unique_repository_learning_algorithm",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0) & models.Q(confidence__lte=1),
                name="learning_confidence_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.algorithm_version}"


class RepositoryAssessmentEvidence(models.Model):
    class Status(models.TextChoices):
        NOT_CHECKED = "NOT_CHECKED", "Not checked"
        PARTIAL = "PARTIAL", "Partial"
        COMPLETE = "COMPLETE", "Complete"
        FAILED = "FAILED", "Failed"

    repository = models.OneToOneField(
        Repository, on_delete=models.CASCADE, related_name="assessment_evidence"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_CHECKED)
    readme = models.BooleanField(null=True, blank=True)
    docs = models.BooleanField(null=True, blank=True)
    getting_started = models.BooleanField(null=True, blank=True)
    examples = models.BooleanField(null=True, blank=True)
    architecture = models.BooleanField(null=True, blank=True)
    contributing = models.BooleanField(null=True, blank=True)
    security = models.BooleanField(null=True, blank=True)
    testing = models.BooleanField(null=True, blank=True)
    deployment = models.BooleanField(null=True, blank=True)
    container = models.BooleanField(null=True, blank=True)
    matched_paths = models.JSONField(default=list)
    source = models.CharField(max_length=40, default="GITHUB_CONTENTS_WHITELIST")
    request_count = models.PositiveSmallIntegerField(default=0)
    checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repository_assessment_evidence"

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.status}"
