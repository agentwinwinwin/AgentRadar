from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.repositories.models import Repository

from .api_serializers import RepositoryCommentCreateSerializer
from .services import RepositoryCommunityService


class RepositoryCommunityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, repository_id: int):
        repository = get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryCommunityService.summary(repository, request.user))


class RepositoryLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, repository_id: int):
        repository = get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        _, created = RepositoryCommunityService.like(repository, request.user)
        return Response(
            RepositoryCommunityService.summary(repository, request.user),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, repository_id: int):
        repository = get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        RepositoryCommunityService.unlike(repository, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RepositoryCommentView(APIView):
    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def get(self, request, repository_id: int):
        repository = get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(
            RepositoryCommunityService.comments(repository), request, view=self
        )
        return paginator.get_paginated_response(
            [RepositoryCommunityService.serialize_comment(comment) for comment in page]
        )

    def post(self, request, repository_id: int):
        repository = get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        serializer = RepositoryCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = RepositoryCommunityService.add_comment(
            repository, request.user, serializer.validated_data["content"]
        )
        return Response(
            RepositoryCommunityService.serialize_comment(comment),
            status=status.HTTP_201_CREATED,
        )
