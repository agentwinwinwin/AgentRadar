from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import MetricsQuerySerializer, ProjectDiscoverQuerySerializer
from .api_services import RepositoryReadService
from .models import Repository


class ProjectPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class DashboardView(APIView):
    def get(self, request):
        return Response(RepositoryReadService.dashboard())


class ProjectListView(APIView):
    pagination_class = ProjectPagination

    def get(self, request):
        serializer = ProjectDiscoverQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = RepositoryReadService.discover(serializer.validated_data)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [RepositoryReadService.summary(repository) for repository in page]
        )


class ProjectDetailView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryReadService.detail(repository_id, request.user))


class ProjectMetricsView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        serializer = MetricsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        days = int(serializer.validated_data["range"][:-1])
        return Response(RepositoryReadService.metrics(repository_id, days))


class ProjectTrendView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryReadService.trend(repository_id))


class ProjectPotentialView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryReadService.potential(repository_id))


class ProjectForecastView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryReadService.forecast(repository_id))


class ProjectLearningView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryReadService.learning(repository_id))


class ProjectEnterpriseView(APIView):
    def get(self, request, repository_id: int):
        get_object_or_404(Repository, pk=repository_id, is_disabled=False)
        return Response(RepositoryReadService.enterprise(repository_id))
