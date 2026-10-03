from django.db import models

from apps.repositories.models import Repository


class RepositoryActivityMetric(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="activity_metrics"
    )
    metric_date = models.DateField()
    commits_7d = models.PositiveIntegerField(null=True, blank=True)
    commits_30d = models.PositiveIntegerField(null=True, blank=True)
    commits_90d = models.PositiveIntegerField(null=True, blank=True)
    prs_created_7d = models.PositiveIntegerField(null=True, blank=True)
    prs_created_30d = models.PositiveIntegerField(null=True, blank=True)
    prs_merged_7d = models.PositiveIntegerField(null=True, blank=True)
    prs_merged_30d = models.PositiveIntegerField(null=True, blank=True)
    issues_created_7d = models.PositiveIntegerField(null=True, blank=True)
    issues_created_30d = models.PositiveIntegerField(null=True, blank=True)
    issues_closed_7d = models.PositiveIntegerField(null=True, blank=True)
    issues_closed_30d = models.PositiveIntegerField(null=True, blank=True)
    active_contributors_30d = models.PositiveIntegerField(null=True, blank=True)
    releases_30d = models.PositiveIntegerField(null=True, blank=True)
    releases_90d = models.PositiveIntegerField(null=True, blank=True)
    days_since_last_push = models.PositiveIntegerField(null=True, blank=True)
    days_since_last_release = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repository_activity_metrics"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "metric_date"), name="unique_repository_activity_date"
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.metric_date}"


class Contributor(models.Model):
    github_user_id = models.BigIntegerField(unique=True)
    login = models.CharField(max_length=255)
    avatar_url = models.URLField(  # noqa: DJ001 - GitHub null is meaningful
        max_length=500, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contributors"

    def __str__(self) -> str:
        return self.login


class RepositoryContributor(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE)
    contributions_total = models.PositiveIntegerField(null=True, blank=True)
    last_observed_at = models.DateTimeField()

    class Meta:
        db_table = "repository_contributors"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "contributor"), name="unique_repository_contributor"
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.contributor.login}"


class RepositoryRelease(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="releases")
    github_release_id = models.BigIntegerField(unique=True)
    tag_name = models.CharField(max_length=255)
    name = models.TextField(null=True, blank=True)  # noqa: DJ001 - GitHub null is meaningful
    author_login = models.CharField(  # noqa: DJ001 - GitHub null is meaningful
        max_length=255, null=True, blank=True
    )
    is_draft = models.BooleanField(default=False)
    is_prerelease = models.BooleanField(default=False)
    github_created_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    body = models.TextField(null=True, blank=True)  # noqa: DJ001 - GitHub null is meaningful
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repository_releases"

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.tag_name}"
