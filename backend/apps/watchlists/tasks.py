from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from redis import Redis

from apps.common.task_dispatch import dispatch_unique_repository_task
from apps.repositories.models import Repository

from .models import ScheduledReport
from .services import AlertService, ReportService


@shared_task(name="alerts.evaluate_repository_alerts")
def evaluate_repository_alerts(repository_id: int):
    return AlertService.evaluate_repository(repository_id)


@shared_task(name="alerts.dispatch_alert_evaluation")
def dispatch_alert_evaluation():
    client = Redis.from_url(settings.CELERY_BROKER_URL)
    backlog = int(client.llen("scoring"))
    if backlog > settings.ALERT_FULL_SCAN_BACKLOG_THRESHOLD:
        return {
            "dispatched": 0,
            "status": "SKIPPED_BACKLOG",
            "scoring_backlog": backlog,
        }
    key = "agentradar:celery:pending:alert-full-scan"
    if not client.set(
        key,
        "1",
        nx=True,
        ex=settings.ALERT_FULL_SCAN_COALESCE_TTL_SECONDS,
    ):
        return {
            "dispatched": 0,
            "status": "SKIPPED_DUPLICATE",
            "scoring_backlog": backlog,
        }
    repository_ids = Repository.objects.filter(is_disabled=False).values_list("id", flat=True)
    dispatched = 0
    for repository_id in repository_ids.iterator(chunk_size=500):
        dispatched += int(
            dispatch_unique_repository_task(
                evaluate_repository_alerts,
                repository_id,
                purpose="alert-evaluation",
            )
        )
    return {
        "dispatched": dispatched,
        "status": "DISPATCHED",
        "scoring_backlog": backlog,
    }


@shared_task(name="reports.generate_daily_report")
def generate_daily_report():
    report_ids = [
        ReportService.generate(ScheduledReport.Type.DAILY, owner).id
        for owner in get_user_model().objects.filter(is_active=True).iterator()
    ]
    return {"report_ids": report_ids, "generated": len(report_ids)}


@shared_task(name="reports.generate_weekly_report")
def generate_weekly_report():
    report_ids = [
        ReportService.generate(ScheduledReport.Type.WEEKLY, owner).id
        for owner in get_user_model().objects.filter(is_active=True).iterator()
    ]
    return {"report_ids": report_ids, "generated": len(report_ids)}
