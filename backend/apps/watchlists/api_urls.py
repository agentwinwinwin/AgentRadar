from django.urls import path

from .api_views import (
    AlertDetailView,
    AlertListView,
    ReportDetailView,
    ReportListView,
    WatchlistItemView,
    WatchlistView,
)

urlpatterns = [
    path("watchlist", WatchlistView.as_view(), name="watchlist"),
    path("watchlist/<int:repository_id>", WatchlistItemView.as_view(), name="watchlist-item"),
    path("alerts", AlertListView.as_view(), name="alert-list"),
    path("alerts/<int:alert_id>", AlertDetailView.as_view(), name="alert-detail"),
    path("reports", ReportListView.as_view(), name="report-list"),
    path("reports/<int:report_id>", ReportDetailView.as_view(), name="report-detail"),
]
