from django.urls import path

from .api_views import (
    DashboardView,
    ProjectDetailView,
    ProjectEnterpriseView,
    ProjectForecastView,
    ProjectLearningView,
    ProjectListView,
    ProjectMetricsView,
    ProjectPotentialView,
    ProjectTrendView,
)

urlpatterns = [
    path("dashboard", DashboardView.as_view(), name="dashboard"),
    path("projects", ProjectListView.as_view(), name="project-list"),
    path("projects/<int:repository_id>", ProjectDetailView.as_view(), name="project-detail"),
    path(
        "projects/<int:repository_id>/metrics",
        ProjectMetricsView.as_view(),
        name="project-metrics",
    ),
    path(
        "projects/<int:repository_id>/trend",
        ProjectTrendView.as_view(),
        name="project-trend",
    ),
    path(
        "projects/<int:repository_id>/potential",
        ProjectPotentialView.as_view(),
        name="project-potential",
    ),
    path(
        "projects/<int:repository_id>/forecast",
        ProjectForecastView.as_view(),
        name="project-forecast",
    ),
    path(
        "projects/<int:repository_id>/learning",
        ProjectLearningView.as_view(),
        name="project-learning",
    ),
    path(
        "projects/<int:repository_id>/enterprise",
        ProjectEnterpriseView.as_view(),
        name="project-enterprise",
    ),
]
