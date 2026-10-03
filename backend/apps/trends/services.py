from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.activities.models import RepositoryActivityMetric, RepositoryContributor
from apps.repositories.models import Repository
from apps.snapshots.models import RepositorySnapshot

from .engine import (
    ALGORITHM_VERSION,
    ComponentResult,
    age_cohort,
    hype_risk,
    lifecycle_stage,
    percentile_ranks,
    weighted_component,
)
from .models import RepositoryTrendScore

MOMENTUM_WEIGHTS = {
    "star_delta_7d": 0.25,
    "star_growth_7d": 0.15,
    "fork_delta_7d": 0.10,
    "star_delta_30d": 0.20,
    "star_growth_30d": 0.10,
    "fork_delta_30d": 0.10,
    "star_acceleration": 0.10,
}
DEVELOPMENT_WEIGHTS = {
    "commits_30d": 0.30,
    "prs_created_30d": 0.20,
    "prs_merged_30d": 0.20,
    "active_contributors_30d": 0.30,
}
COMMUNITY_WEIGHTS = {
    "issues_closed_30d": 0.25,
    "issue_close_ratio": 0.25,
    "pr_participation": 0.20,
    "active_contributors_30d": 0.15,
    "community_health": 0.15,
}
DELIVERY_WEIGHTS = {
    "releases_30d": 0.45,
    "releases_90d": 0.25,
    "release_recency": 0.30,
}
ADOPTION_WEIGHTS = {"stars": 0.65, "forks": 0.35}
MAINTENANCE_WEIGHTS = {
    "push_recency": 0.35,
    "release_recency": 0.20,
    "community_health": 0.25,
    "contributor_diversity": 0.20,
}
TREND_WEIGHTS = {
    "momentum": 0.25,
    "development": 0.20,
    "community": 0.15,
    "delivery": 0.10,
    "adoption": 0.10,
    "topic_momentum": 0.10,
    "maintenance": 0.10,
}
PERCENTILE_FEATURES = (
    "star_delta_7d",
    "star_growth_7d",
    "fork_delta_7d",
    "star_delta_30d",
    "star_growth_30d",
    "fork_delta_30d",
    "star_acceleration",
    "commits_30d",
    "prs_created_30d",
    "prs_merged_30d",
    "active_contributors_30d",
    "issues_closed_30d",
    "releases_30d",
    "releases_90d",
    "stars",
    "forks",
)


@dataclass(frozen=True)
class RepositoryFeatures:
    repository: Repository
    calculation_date: date
    cohort: str
    values: dict[str, float | int | None]


@dataclass(frozen=True)
class TrendCalculationResult:
    trend: RepositoryTrendScore
    created: bool


class TrendService:
    def calculate_repository(
        self, repository_id: int, *, calculation_date: date | None = None
    ) -> TrendCalculationResult:
        calculation_date = calculation_date or timezone.now().astimezone(UTC).date()
        features = self._load_features(calculation_date)
        try:
            target = next(item for item in features if item.repository.id == repository_id)
        except StopIteration as exc:
            raise Repository.DoesNotExist from exc
        percentiles, cohort_size = self._percentiles(features, target)
        return self._calculate_and_persist(target, percentiles, cohort_size)

    def _load_features(self, calculation_date: date) -> list[RepositoryFeatures]:
        end = datetime.combine(calculation_date + timedelta(days=1), time.min, tzinfo=UTC)
        repositories = Repository.objects.filter(is_disabled=False).prefetch_related(
            Prefetch(
                "snapshots",
                queryset=RepositorySnapshot.objects.filter(snapshot_at__lt=end).order_by(
                    "snapshot_at"
                ),
                to_attr="trend_snapshots",
            ),
            Prefetch(
                "activity_metrics",
                queryset=RepositoryActivityMetric.objects.filter(
                    metric_date__lte=calculation_date
                ).order_by("metric_date"),
                to_attr="trend_activities",
            ),
            Prefetch(
                "repositorycontributor_set",
                queryset=RepositoryContributor.objects.all(),
                to_attr="trend_contributors",
            ),
        )
        return [self._features(repository, calculation_date) for repository in repositories]

    def _features(self, repository: Repository, calculation_date: date) -> RepositoryFeatures:
        snapshots = list(repository.trend_snapshots)
        current = snapshots[-1] if snapshots else None
        baseline_7 = self._baseline(snapshots, current, 7)
        baseline_30 = self._baseline(snapshots, current, 30)
        activity = repository.trend_activities[-1] if repository.trend_activities else None

        star_delta_7 = self._delta(current, baseline_7, "stars")
        star_delta_30 = self._delta(current, baseline_30, "stars")
        fork_delta_7 = self._delta(current, baseline_7, "forks")
        fork_delta_30 = self._delta(current, baseline_30, "forks")
        acceleration = None
        if star_delta_7 is not None and star_delta_30 is not None:
            acceleration = star_delta_7 / 7 - (star_delta_30 - star_delta_7) / 23

        values: dict[str, float | int | None] = {
            "stars": current.stars if current else None,
            "forks": current.forks if current else None,
            "star_delta_7d": star_delta_7,
            "star_growth_7d": self._growth(current, baseline_7, "stars"),
            "fork_delta_7d": fork_delta_7,
            "star_delta_30d": star_delta_30,
            "star_growth_30d": self._growth(current, baseline_30, "stars"),
            "fork_delta_30d": fork_delta_30,
            "star_acceleration": acceleration,
            "commits_30d": self._activity(activity, "commits_30d"),
            "prs_created_30d": self._activity(activity, "prs_created_30d"),
            "prs_merged_30d": self._activity(activity, "prs_merged_30d"),
            "active_contributors_30d": self._activity(activity, "active_contributors_30d"),
            "issues_created_30d": self._activity(activity, "issues_created_30d"),
            "issues_closed_30d": self._activity(activity, "issues_closed_30d"),
            "releases_30d": self._activity(activity, "releases_30d"),
            "releases_90d": self._activity(activity, "releases_90d"),
            "days_since_last_push": self._activity(activity, "days_since_last_push"),
            "days_since_last_release": self._activity(activity, "days_since_last_release"),
            "community_health": repository.community_health,
            "contributor_diversity": self._contributor_diversity(repository.trend_contributors),
        }
        return RepositoryFeatures(
            repository=repository,
            calculation_date=calculation_date,
            cohort=age_cohort(
                repository.github_created_at.astimezone(UTC).date(), calculation_date
            ),
            values=values,
        )

    @staticmethod
    def _baseline(
        snapshots: list[RepositorySnapshot],
        current: RepositorySnapshot | None,
        days: int,
    ) -> RepositorySnapshot | None:
        if current is None:
            return None
        target = current.snapshot_at - timedelta(days=days)
        eligible = [snapshot for snapshot in snapshots if snapshot.snapshot_at <= target]
        if not eligible:
            return None
        candidate = eligible[-1]
        if target - candidate.snapshot_at > timedelta(days=2):
            return None
        return candidate

    @staticmethod
    def _delta(
        current: RepositorySnapshot | None,
        baseline: RepositorySnapshot | None,
        field: str,
    ) -> int | None:
        if current is None or baseline is None:
            return None
        current_value = getattr(current, field)
        baseline_value = getattr(baseline, field)
        if current_value is None or baseline_value is None:
            return None
        return current_value - baseline_value

    @staticmethod
    def _growth(
        current: RepositorySnapshot | None,
        baseline: RepositorySnapshot | None,
        field: str,
    ) -> float | None:
        delta = TrendService._delta(current, baseline, field)
        if delta is None or baseline is None:
            return None
        baseline_value = getattr(baseline, field)
        return delta / max(baseline_value, 10) * 100

    @staticmethod
    def _activity(activity: RepositoryActivityMetric | None, field: str) -> int | None:
        return getattr(activity, field) if activity is not None else None

    @staticmethod
    def _contributor_diversity(contributors: list[RepositoryContributor]) -> float | None:
        values = [
            item.contributions_total
            for item in contributors
            if item.contributions_total is not None
        ]
        total = sum(values)
        if not values or total == 0:
            return None
        return (1 - max(values) / total) * 100

    @staticmethod
    def _percentiles(
        features: list[RepositoryFeatures], target: RepositoryFeatures
    ) -> tuple[dict[str, float | None], int]:
        cohort = [
            item
            for item in features
            if item.repository.category == target.repository.category
            and item.cohort == target.cohort
        ]
        output: dict[str, float | None] = {}
        for field in PERCENTILE_FEATURES:
            ranks = percentile_ranks(
                {item.repository.id: item.values.get(field) for item in cohort}
            )
            output[field] = ranks[target.repository.id]
        return output, len(cohort)

    @transaction.atomic
    def _calculate_and_persist(
        self,
        target: RepositoryFeatures,
        percentiles: dict[str, float | None],
        cohort_size: int,
    ) -> TrendCalculationResult:
        raw = target.values
        momentum = weighted_component(
            {key: percentiles[key] for key in MOMENTUM_WEIGHTS}, MOMENTUM_WEIGHTS
        )
        development = weighted_component(
            {key: percentiles[key] for key in DEVELOPMENT_WEIGHTS}, DEVELOPMENT_WEIGHTS
        )
        close_ratio = self._close_ratio(raw["issues_created_30d"], raw["issues_closed_30d"])
        community = weighted_component(
            {
                "issues_closed_30d": percentiles["issues_closed_30d"],
                "issue_close_ratio": close_ratio,
                "pr_participation": percentiles["prs_created_30d"],
                "active_contributors_30d": percentiles["active_contributors_30d"],
                "community_health": raw["community_health"],
            },
            COMMUNITY_WEIGHTS,
        )
        release_recency = self._recency(raw["days_since_last_release"], 90)
        delivery = weighted_component(
            {
                "releases_30d": percentiles["releases_30d"],
                "releases_90d": percentiles["releases_90d"],
                "release_recency": release_recency,
            },
            DELIVERY_WEIGHTS,
        )
        adoption = weighted_component(
            {key: percentiles[key] for key in ADOPTION_WEIGHTS}, ADOPTION_WEIGHTS
        )
        maintenance = self._maintenance(target, release_recency)
        topic_momentum = ComponentResult(None, 0.0, {"topic_momentum": None})
        components = {
            "momentum": momentum,
            "development": development,
            "community": community,
            "delivery": delivery,
            "adoption": adoption,
            "topic_momentum": topic_momentum,
            "maintenance": maintenance,
        }
        trend = weighted_component(
            {name: component.score for name, component in components.items()}, TREND_WEIGHTS
        )
        completeness = round(
            sum(
                TREND_WEIGHTS[name] * component.completeness
                for name, component in components.items()
            ),
            6,
        )
        hype = hype_risk(
            star_growth_30d_percentile=percentiles["star_growth_30d"],
            fork_delta_30d_percentile=percentiles["fork_delta_30d"],
            development_score=(development.score if development.completeness == 1.0 else None),
            community_score=(community.score if community.completeness == 1.0 else None),
        )
        age_days = max(
            (
                target.calculation_date - target.repository.github_created_at.astimezone(UTC).date()
            ).days,
            0,
        )
        lifecycle = lifecycle_stage(
            repository_age_days=age_days,
            archived=target.repository.is_archived,
            trend_score=trend.score,
            momentum_score=momentum.score,
            development_score=development.score,
            maintenance_score=maintenance.score,
            hype=hype,
        )
        evidence = {
            "calculation_date": target.calculation_date.isoformat(),
            "cohort": {"category": target.repository.category, "age": target.cohort},
            "cohort_size": cohort_size,
            "raw_features": raw,
            "percentiles": percentiles,
            "components": {
                name: {
                    "score": component.score,
                    "completeness": component.completeness,
                    "inputs": component.inputs,
                }
                for name, component in components.items()
            },
            "trend_weights": TREND_WEIGHTS,
            "missing_inputs": sorted(key for key, value in raw.items() if value is None),
            "hype_risk_status": hype.status,
            "lifecycle_stage": lifecycle,
        }
        defaults: dict[str, Any] = {
            "trend_score": trend.score,
            "momentum_score": momentum.score,
            "development_score": development.score,
            "community_score": community.score,
            "delivery_score": delivery.score,
            "adoption_score": adoption.score,
            "topic_momentum_score": None,
            "maintenance_score": maintenance.score,
            "hype_risk": hype.score,
            "hype_risk_status": hype.status,
            "lifecycle_stage": lifecycle,
            "data_completeness": completeness,
            "calculated_at": timezone.now(),
            "evidence": evidence,
        }
        score, created = RepositoryTrendScore.objects.update_or_create(
            repository=target.repository,
            algorithm_version=ALGORITHM_VERSION,
            defaults=defaults,
        )
        score.refresh_from_db()
        from apps.operations.models import RepositoryScoreHistory
        from apps.operations.services import record_score_history

        record_score_history(score, RepositoryScoreHistory.ScoreType.TREND)
        return TrendCalculationResult(score, created)

    @staticmethod
    def _close_ratio(opened: float | int | None, closed: float | int | None) -> float | None:
        if opened is None or closed is None:
            return None
        if opened == 0:
            return 100.0 if closed == 0 else 100.0
        return min(float(closed) / float(opened) * 100, 100.0)

    @staticmethod
    def _recency(days: float | int | None, horizon: int) -> float | None:
        if days is None:
            return None
        return max(100.0 * (1 - float(days) / horizon), 0.0)

    @staticmethod
    def _maintenance(
        target: RepositoryFeatures, release_recency_90d: float | None
    ) -> ComponentResult:
        if target.repository.is_archived:
            return ComponentResult(0.0, 1.0, {"archived": 1.0})
        raw = target.values
        return weighted_component(
            {
                "push_recency": TrendService._recency(raw["days_since_last_push"], 90),
                "release_recency": (
                    TrendService._recency(raw["days_since_last_release"], 180)
                    if release_recency_90d is not None
                    else None
                ),
                "community_health": raw["community_health"],
                "contributor_diversity": raw["contributor_diversity"],
            },
            MAINTENANCE_WEIGHTS,
        )
