from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository


class RepositorySnapshot(models.Model):
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    snapshot_at = models.DateTimeField()
    snapshot_date = models.DateField(db_index=True)
    snapshot_bucket = models.CharField(max_length=13)
    stars = models.PositiveBigIntegerField(null=True, blank=True)
    forks = models.PositiveBigIntegerField(null=True, blank=True)
    subscribers = models.PositiveBigIntegerField(null=True, blank=True)
    watchers = models.PositiveBigIntegerField(null=True, blank=True)
    open_issues = models.PositiveBigIntegerField(null=True, blank=True)
    github_pushed_at = models.DateTimeField(null=True, blank=True)
    github_updated_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    data_origin = models.CharField(max_length=20, default="OBSERVED")
    data_completeness = models.FloatField(
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0))
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "repository_snapshots"
        ordering = ("-snapshot_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "snapshot_bucket"),
                name="unique_repository_snapshot_bucket",
            ),
            models.CheckConstraint(
                condition=models.Q(data_completeness__gte=0.0)
                & models.Q(data_completeness__lte=1.0),
                name="snapshot_completeness_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}@{self.snapshot_bucket}"
