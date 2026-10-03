from apps.repositories.api_services import RepositoryReadService

from .models import Alert, ScheduledReport


def watchlist_item(item):
    return {
        "repository": RepositoryReadService.summary(
            RepositoryReadService.with_current_trend(
                item.repository.__class__.objects.filter(pk=item.repository_id)
            ).get()
        ),
        "added_at": item.added_at,
    }


def alert_data(alert: Alert, status=None):
    return {
        "id": alert.id,
        "repository": {
            "id": alert.repository_id,
            "full_name": alert.repository.full_name,
        },
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "evidence": alert.evidence,
        "detected_at": alert.detected_at,
        "status": status,
        "rule_version": alert.rule_version,
    }


def report_data(report: ScheduledReport):
    return {
        "id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "content": report.content,
        "rule_version": report.rule_version,
        "generated_at": report.generated_at,
    }
