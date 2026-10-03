from django.conf import settings
from django.db import models


class RepositoryLike(models.Model):
    repository = models.ForeignKey(
        "repositories.Repository", on_delete=models.CASCADE, related_name="community_likes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="repository_likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "repository_likes"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "user"), name="unique_repository_like_user"
            )
        ]
        indexes = [models.Index(fields=("repository", "-created_at"), name="repo_like_time_idx")]

    def __str__(self) -> str:
        return f"{self.user_id} likes {self.repository_id}"


class RepositoryComment(models.Model):
    repository = models.ForeignKey(
        "repositories.Repository", on_delete=models.CASCADE, related_name="community_comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="repository_comments"
    )
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repository_comments"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("repository", "-created_at"), name="repo_comment_time_idx")
        ]

    def __str__(self) -> str:
        return f"{self.author_id} commented on {self.repository_id}"
