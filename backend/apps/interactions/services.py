from django.db import transaction

from apps.repositories.models import Repository

from .models import RepositoryComment, RepositoryLike


class RepositoryCommunityService:
    @staticmethod
    def comments(repository: Repository):
        return RepositoryComment.objects.filter(repository=repository).select_related("author")

    @staticmethod
    def summary(repository: Repository, user=None) -> dict:
        liked = (
            RepositoryLike.objects.filter(repository=repository, user=user).exists()
            if user is not None and user.is_authenticated
            else False
        )
        comments = RepositoryCommunityService.comments(repository)
        return {
            "repository_id": repository.id,
            "like_count": RepositoryLike.objects.filter(repository=repository).count(),
            "liked_by_me": liked,
            "comment_count": comments.count(),
            "comments": [
                RepositoryCommunityService.serialize_comment(item) for item in comments[:3]
            ],
        }

    @staticmethod
    @transaction.atomic
    def like(repository: Repository, user) -> tuple[RepositoryLike, bool]:
        return RepositoryLike.objects.get_or_create(repository=repository, user=user)

    @staticmethod
    def unlike(repository: Repository, user) -> bool:
        deleted, _ = RepositoryLike.objects.filter(repository=repository, user=user).delete()
        return deleted > 0

    @staticmethod
    def add_comment(repository: Repository, user, content: str) -> RepositoryComment:
        return RepositoryComment.objects.create(
            repository=repository, author=user, content=content.strip()
        )

    @staticmethod
    def serialize_comment(comment: RepositoryComment) -> dict:
        return {
            "id": comment.id,
            "author": {"id": comment.author_id, "username": comment.author.username},
            "content": comment.content,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
        }
