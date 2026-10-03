from django.urls import path

from .api_views import RepositoryCommentView, RepositoryCommunityView, RepositoryLikeView

urlpatterns = [
    path(
        "projects/<int:repository_id>/community",
        RepositoryCommunityView.as_view(),
        name="repository-community",
    ),
    path(
        "projects/<int:repository_id>/like",
        RepositoryLikeView.as_view(),
        name="repository-like",
    ),
    path(
        "projects/<int:repository_id>/comments",
        RepositoryCommentView.as_view(),
        name="repository-comment",
    ),
]

