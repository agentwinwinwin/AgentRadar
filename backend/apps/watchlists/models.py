from django.conf import settings
from django.db import models

from apps.repositories.models import Repository


class Watchlist(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, default="default")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "watchlists"
        constraints = [
            models.UniqueConstraint(fields=("owner", "name"), name="unique_owner_watchlist")
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.name}"


class WatchlistItem(models.Model):
    watchlist = models.ForeignKey(Watchlist, on_delete=models.CASCADE, related_name="items")
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "watchlist_items"
        constraints = [
            models.UniqueConstraint(
                fields=("watchlist", "repository"), name="unique_watchlist_repository"
            )
        ]

    def __str__(self) -> str:
        return f"{self.watchlist}:{self.repository.full_name}"


class WatchlistEvent(models.Model):
    class Action(models.TextChoices):
        ADDED = "ADDED", "Added"
        REMOVED = "REMOVED", "Removed"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=Action.choices)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "watchlist_events"

    def __str__(self) -> str:
        return f"{self.action}:{self.repository.full_name}"


class Alert(models.Model):
    class Type(models.TextChoices):
        STAR_GROWTH_SPIKE = "STAR_GROWTH_SPIKE", "Star growth spike"
        FORK_GROWTH_SPIKE = "FORK_GROWTH_SPIKE", "Fork growth spike"
        TREND_CHANGE = "TREND_CHANGE", "Trend change"
        POTENTIAL_CHANGE = "POTENTIAL_CHANGE", "Potential change"
        NEW_RELEASE = "NEW_RELEASE", "New release"
        ACTIVITY_SURGE = "ACTIVITY_SURGE", "Activity surge"
        PROJECT_DORMANT = "PROJECT_DORMANT", "Project dormant"
        NEW_HIGH_POTENTIAL_PROJECT = "NEW_HIGH_POTENTIAL_PROJECT", "High potential"

    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        UNREAD = "UNREAD", "Unread"
        READ = "READ", "Read"
        DISMISSED = "DISMISSED", "Dismissed"

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="alerts")
    alert_type = models.CharField(max_length=40, choices=Type.choices, db_index=True)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=255)
    evidence = models.JSONField(default=dict)
    detected_at = models.DateTimeField(db_index=True)
    rule_version = models.CharField(max_length=50)
    event_bucket = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alerts"
        ordering = ("-detected_at", "-id")
        indexes = [
            models.Index(
                fields=("repository", "-detected_at"), name="alert_repo_detected_idx"
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "alert_type", "rule_version", "event_bucket"),
                name="unique_repository_alert_event",
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}:{self.alert_type}"


class ScheduledReport(models.Model):
    class Type(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    report_type = models.CharField(max_length=10, choices=Type.choices, db_index=True)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    content = models.JSONField(default=dict)
    rule_version = models.CharField(max_length=50)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduled_reports"
        ordering = ("-period_end",)
        indexes = [
            models.Index(
                fields=("owner", "report_type", "-period_end"),
                name="report_owner_type_period_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "report_type", "period_start", "period_end", "rule_version"),
                name="unique_scheduled_report_period",
            )
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.report_type}:{self.period_end}"


class AlertReceipt(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="receipts")
    status = models.CharField(
        max_length=12, choices=Alert.Status.choices, default=Alert.Status.UNREAD, db_index=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alert_receipts"
        indexes = [
            models.Index(fields=("owner", "status"), name="receipt_owner_status_idx")
        ]
        constraints = [
            models.UniqueConstraint(fields=("owner", "alert"), name="unique_owner_alert_receipt")
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.alert_id}:{self.status}"
