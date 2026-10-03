from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.watchlists.models import Alert, ScheduledReport, WatchlistEvent


def retention_counts(*, apply: bool = False) -> dict[str, int | bool]:
    now = timezone.now()
    querysets = {
        "alerts": Alert.objects.filter(
            detected_at__lt=now - timedelta(days=settings.ALERT_RETENTION_DAYS)
        ),
        "reports": ScheduledReport.objects.filter(
            period_end__lt=now - timedelta(days=settings.REPORT_RETENTION_DAYS)
        ),
        "watchlist_events": WatchlistEvent.objects.filter(
            occurred_at__lt=now - timedelta(days=settings.WATCHLIST_EVENT_RETENTION_DAYS)
        ),
    }
    result: dict[str, int | bool] = {name: queryset.count() for name, queryset in querysets.items()}
    result["applied"] = apply
    if apply:
        for queryset in querysets.values():
            queryset.delete()
    return result
