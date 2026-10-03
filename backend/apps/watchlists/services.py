from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.capabilities.models import CapabilityName, CapabilityStatus, DataCapability
from apps.operations.models import RepositoryScoreHistory
from apps.potentials.engine import ALGORITHM_VERSION as POTENTIAL_VERSION
from apps.potentials.models import RepositoryPotentialScore
from apps.repositories.models import Repository
from apps.trends.engine import ALGORITHM_VERSION as TREND_VERSION
from apps.trends.models import RepositoryTrendScore

from .models import Alert, AlertReceipt, ScheduledReport, Watchlist, WatchlistEvent, WatchlistItem
from .rules import REPORT_VERSION, RULE_VERSION, THRESHOLDS


def _value(value: Decimal | int | float | None) -> float | int | None:
    return float(value) if isinstance(value, Decimal) else value


class WatchlistService:
    @staticmethod
    def get(owner) -> Watchlist:
        watchlist, _ = Watchlist.objects.get_or_create(owner=owner, name="default")
        return watchlist

    @classmethod
    @transaction.atomic
    def add(cls, repository_id: int, owner) -> tuple[WatchlistItem, bool]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        item, created = WatchlistItem.objects.get_or_create(
            watchlist=cls.get(owner), repository=repository
        )
        if created:
            WatchlistEvent.objects.create(
                owner=owner, repository=repository, action=WatchlistEvent.Action.ADDED
            )
            AlertReceipt.objects.bulk_create(
                [AlertReceipt(owner=owner, alert=alert) for alert in repository.alerts.all()],
                ignore_conflicts=True,
            )
            from apps.snapshots.monitoring import refresh_repository_monitoring

            refresh_repository_monitoring(repository.id)
        return item, created

    @classmethod
    @transaction.atomic
    def remove(cls, repository_id: int, owner) -> bool:
        item = (
            WatchlistItem.objects.filter(watchlist=cls.get(owner), repository_id=repository_id)
            .select_related("repository")
            .first()
        )
        if item is None:
            return False
        repository = item.repository
        item.delete()
        WatchlistEvent.objects.create(
            owner=owner, repository=repository, action=WatchlistEvent.Action.REMOVED
        )
        from apps.snapshots.monitoring import refresh_repository_monitoring

        refresh_repository_monitoring(repository.id)
        return True

    @classmethod
    def list(cls, owner):
        return (
            WatchlistItem.objects.filter(watchlist__owner=owner, watchlist__name="default")
            .select_related("repository")
            .order_by("-added_at")
        )


class AlertService:
    @staticmethod
    def _capability_allows(name: str) -> bool:
        capability = DataCapability.objects.filter(name=name).first()
        return capability is None or capability.status == CapabilityStatus.READY

    @classmethod
    def evaluate_repository(cls, repository_id: int) -> dict[str, int]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        now = timezone.now()
        created = 0
        created += cls._snapshot_growth(repository, now)
        created += cls._activity(repository, now)
        created += cls._release(repository, now)
        created += cls._dormant(repository, now)
        created += cls._high_potential(repository, now)
        created += cls._score_changes(repository)
        return {"created": created, "evaluated": 1}

    @staticmethod
    def _create(repository, alert_type, severity, title, evidence, detected_at, bucket) -> int:
        alert, created = Alert.objects.get_or_create(
            repository=repository,
            alert_type=alert_type,
            rule_version=RULE_VERSION,
            event_bucket=bucket,
            defaults={
                "severity": severity,
                "title": title,
                "evidence": evidence,
                "detected_at": detected_at,
            },
        )
        if created:
            owner_ids = WatchlistItem.objects.filter(repository=repository).values_list(
                "watchlist__owner_id", flat=True
            )
            AlertReceipt.objects.bulk_create(
                [AlertReceipt(owner_id=owner_id, alert=alert) for owner_id in owner_ids],
                ignore_conflicts=True,
            )
        return int(created)

    @classmethod
    def _snapshot_growth(cls, repository, now) -> int:
        latest = repository.snapshots.order_by("-snapshot_at").first()
        if latest is None or latest.data_completeness < THRESHOLDS.snapshot_min_completeness:
            return 0
        baseline = (
            repository.snapshots.filter(
                snapshot_at__lte=latest.snapshot_at - timedelta(days=7),
                data_completeness__gte=THRESHOLDS.snapshot_min_completeness,
            )
            .order_by("-snapshot_at")
            .first()
        )
        if baseline is None:
            return 0
        total = 0
        for field, kind, absolute, minimum_percent, title, capability in (
            (
                "stars",
                Alert.Type.STAR_GROWTH_SPIKE,
                THRESHOLDS.star_7d_absolute,
                THRESHOLDS.star_7d_percent,
                "Star 增长突增",
                CapabilityName.STAR_GROWTH_7D,
            ),
            (
                "forks",
                Alert.Type.FORK_GROWTH_SPIKE,
                THRESHOLDS.fork_7d_absolute,
                THRESHOLDS.fork_7d_percent,
                "Fork 增长突增",
                CapabilityName.FORK_GROWTH_7D,
            ),
        ):
            if not cls._capability_allows(capability):
                continue
            current, previous = getattr(latest, field), getattr(baseline, field)
            if current is None or previous is None:
                continue
            delta = current - previous
            percent = (delta / previous * 100) if previous > 0 else None
            if delta >= absolute and percent is not None and percent >= minimum_percent:
                total += cls._create(
                    repository,
                    kind,
                    Alert.Severity.WARNING,
                    title,
                    {
                        "current": current,
                        "baseline": previous,
                        "delta": delta,
                        "percent": round(percent, 2),
                        "window_days": 7,
                        "latest_snapshot_id": latest.id,
                        "baseline_snapshot_id": baseline.id,
                    },
                    latest.snapshot_at,
                    latest.snapshot_date.isoformat(),
                )
        return total

    @classmethod
    def _activity(cls, repository, now) -> int:
        latest = repository.activity_metrics.order_by("-metric_date").first()
        if latest is None or latest.commits_7d is None:
            return 0
        baseline = (
            repository.activity_metrics.filter(
                metric_date__lte=latest.metric_date - timedelta(days=7), commits_7d__isnull=False
            )
            .order_by("-metric_date")
            .first()
        )
        if baseline is None or baseline.commits_7d is None:
            return 0
        if latest.commits_7d < THRESHOLDS.activity_surge_min_commits:
            return 0
        if latest.commits_7d < max(1, baseline.commits_7d) * THRESHOLDS.activity_surge_multiplier:
            return 0
        return cls._create(
            repository,
            Alert.Type.ACTIVITY_SURGE,
            Alert.Severity.WARNING,
            "开发活跃度显著上升",
            {
                "commits_7d": latest.commits_7d,
                "baseline_commits_7d": baseline.commits_7d,
                "metric_id": latest.id,
                "baseline_metric_id": baseline.id,
            },
            now,
            latest.metric_date.isoformat(),
        )

    @classmethod
    def _release(cls, repository, now) -> int:
        release = (
            repository.releases.filter(
                is_draft=False,
                published_at__gte=now - timedelta(days=THRESHOLDS.release_lookback_days),
            )
            .order_by("-published_at")
            .first()
        )
        if release is None or release.published_at is None:
            return 0
        return cls._create(
            repository,
            Alert.Type.NEW_RELEASE,
            Alert.Severity.INFO,
            f"发布新版本 {release.tag_name}",
            {
                "release_id": release.id,
                "tag_name": release.tag_name,
                "published_at": release.published_at.isoformat(),
                "lookback_days": THRESHOLDS.release_lookback_days,
            },
            now,
            f"release:{release.github_release_id}",
        )

    @classmethod
    def _dormant(cls, repository, now) -> int:
        metric = repository.activity_metrics.order_by("-metric_date").first()
        if metric is not None and metric.days_since_last_push is not None:
            days_since_last_push = metric.days_since_last_push
            evidence = {
                "days_since_last_push": days_since_last_push,
                "metric_id": metric.id,
                "source": "repository_activity_metrics",
            }
            bucket = metric.metric_date.isoformat()
        elif repository.github_pushed_at is not None:
            days_since_last_push = max(0, (now - repository.github_pushed_at).days)
            evidence = {
                "days_since_last_push": days_since_last_push,
                "github_pushed_at": repository.github_pushed_at.isoformat(),
                "source": "repositories.github_pushed_at",
            }
            bucket = now.date().isoformat()
        else:
            return 0
        if days_since_last_push < THRESHOLDS.dormant_days:
            return 0
        return cls._create(
            repository,
            Alert.Type.PROJECT_DORMANT,
            Alert.Severity.WARNING,
            "项目可能进入低活跃状态",
            evidence,
            now,
            bucket,
        )

    @classmethod
    def _high_potential(cls, repository, now) -> int:
        score = RepositoryPotentialScore.objects.filter(
            repository=repository, algorithm_version=POTENTIAL_VERSION
        ).first()
        trend = RepositoryTrendScore.objects.filter(
            repository=repository, algorithm_version=TREND_VERSION
        ).first()
        if (
            score is None
            or score.potential_score is None
            or score.confidence < THRESHOLDS.potential_min_confidence
            or float(score.potential_score) < THRESHOLDS.high_potential_score
            or trend is None
            or trend.data_completeness < THRESHOLDS.trend_min_completeness
        ):
            return 0
        return cls._create(
            repository,
            Alert.Type.NEW_HIGH_POTENTIAL_PROJECT,
            Alert.Severity.INFO,
            "项目达到高潜力信号门槛",
            {
                "potential_score": _value(score.potential_score),
                "potential_confidence": score.confidence,
                "potential_algorithm_version": score.algorithm_version,
                "trend_completeness": trend.data_completeness,
                "trend_algorithm_version": trend.algorithm_version,
            },
            score.calculated_at,
            score.calculated_at.date().isoformat(),
        )

    @classmethod
    def _score_changes(cls, repository) -> int:
        total = 0
        rules = (
            (
                RepositoryScoreHistory.ScoreType.TREND,
                Alert.Type.TREND_CHANGE,
                THRESHOLDS.trend_change,
                THRESHOLDS.trend_min_completeness,
                "趋势评分发生显著变化",
                CapabilityName.TREND_CHANGE_ALERT,
            ),
            (
                RepositoryScoreHistory.ScoreType.POTENTIAL,
                Alert.Type.POTENTIAL_CHANGE,
                THRESHOLDS.potential_change,
                THRESHOLDS.potential_min_confidence,
                "潜力评分发生显著变化",
                CapabilityName.POTENTIAL_CHANGE_ALERT,
            ),
        )
        for score_type, alert_type, threshold, minimum_confidence, title, capability in rules:
            if not cls._capability_allows(capability):
                continue
            history = list(
                RepositoryScoreHistory.objects.filter(
                    repository=repository, score_type=score_type, score__isnull=False
                ).order_by("-calculated_at")[:2]
            )
            if len(history) < 2 or history[0].confidence is None:
                continue
            if history[0].confidence < minimum_confidence:
                continue
            delta = float(history[0].score) - float(history[1].score)
            if abs(delta) < threshold:
                continue
            total += cls._create(
                repository,
                alert_type,
                Alert.Severity.WARNING,
                title,
                {
                    "current_score": _value(history[0].score),
                    "previous_score": _value(history[1].score),
                    "delta": round(delta, 2),
                    "current_history_id": history[0].id,
                    "previous_history_id": history[1].id,
                    "algorithm_version": history[0].algorithm_version,
                    "confidence": history[0].confidence,
                },
                history[0].calculated_at,
                history[0].history_bucket,
            )
        return total


class ReportService:
    @classmethod
    def generate(cls, report_type: str, owner, now=None):
        now = now or timezone.now()
        period_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if report_type == ScheduledReport.Type.WEEKLY:
            period_end -= timedelta(days=period_end.weekday())
        days = 1 if report_type == ScheduledReport.Type.DAILY else 7
        start = period_end - timedelta(days=days)
        watchlist_items = WatchlistService.list(owner)
        watched_ids = list(watchlist_items.values_list("repository_id", flat=True))
        alerts = Alert.objects.filter(detected_at__gte=start, detected_at__lt=period_end)
        watched_alerts = alerts.filter(repository_id__in=watched_ids)
        events = WatchlistEvent.objects.filter(
            owner=owner, occurred_at__gte=start, occurred_at__lt=period_end
        ).select_related("repository")
        insufficient = []
        for item in watchlist_items:
            repository = item.repository
            if not repository.snapshots.filter(
                snapshot_at__lte=period_end - timedelta(days=7)
            ).exists():
                insufficient.append(
                    {
                        "repository_id": repository.id,
                        "repository": repository.full_name,
                        "reason": "7D_SNAPSHOT_HISTORY",
                    }
                )
        content = {
            "period": {"start": start.isoformat(), "end": period_end.isoformat()},
            "new_repositories": list(
                Repository.objects.filter(created_at__gte=start, created_at__lt=period_end).values(
                    "id", "full_name", "category", "stars"
                )[:100]
            ),
            "watchlist_changes": [
                {
                    "repository_id": event.repository_id,
                    "repository": event.repository.full_name,
                    "action": event.action,
                    "occurred_at": event.occurred_at.isoformat(),
                }
                for event in events
            ],
            "alerts": list(
                watched_alerts.values(
                    "id", "repository_id", "alert_type", "severity", "title", "detected_at"
                )[:100]
            ),
            "trend_changes": list(
                watched_alerts.filter(alert_type=Alert.Type.TREND_CHANGE).values(
                    "id", "repository_id", "evidence"
                )
            ),
            "potential_changes": list(
                watched_alerts.filter(alert_type=Alert.Type.POTENTIAL_CHANGE).values(
                    "id", "repository_id", "evidence"
                )
            ),
            "new_releases": list(
                watched_alerts.filter(alert_type=Alert.Type.NEW_RELEASE).values(
                    "id", "repository_id", "evidence"
                )
            ),
            "activity_changes": list(
                watched_alerts.filter(alert_type=Alert.Type.ACTIVITY_SURGE).values(
                    "id", "repository_id", "evidence"
                )
            ),
            "insufficient_evidence": insufficient,
            "facts_source": "STRUCTURED_DATABASE_AND_EXISTING_EVIDENCE",
            "llm_used": False,
        }
        report, _ = ScheduledReport.objects.update_or_create(
            owner=owner,
            report_type=report_type,
            period_start=start,
            period_end=period_end,
            rule_version=REPORT_VERSION,
            defaults={"content": content},
        )
        return report
