from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import F, FloatField, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.activities.models import RepositoryActivityMetric
from apps.capabilities.models import (
    CapabilityName,
    CapabilityStatus,
    CategoryTrendMetric,
    DataCapability,
)
from apps.capabilities.services import CATEGORY_TREND_VERSION
from apps.enterprise.engine import ALGORITHM_VERSION as ENTERPRISE_ALGORITHM_VERSION
from apps.enterprise.models import RepositoryEnterpriseScore
from apps.forecasts.models import ModelStatus, RepositoryForecast
from apps.forecasts.services import ForecastService
from apps.learning.engine import ALGORITHM_VERSION as LEARNING_ALGORITHM_VERSION
from apps.learning.models import RepositoryLearningScore
from apps.potentials.engine import ALGORITHM_VERSION as POTENTIAL_ALGORITHM_VERSION
from apps.potentials.engine import candidate_flags
from apps.potentials.models import RepositoryPotentialScore
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import ALGORITHM_VERSION
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore

from .models import Repository, Topic


def _number(value: Decimal | int | float | None) -> float | int | None:
    if isinstance(value, Decimal):
        return float(value)
    return value


class RepositoryReadService:
    MIN_TREND_RANKING_COMPLETENESS = 0.50
    MIN_POTENTIAL_RANKING_CONFIDENCE = 0.45
    TREND_FIELDS = (
        "trend_score",
        "momentum_score",
        "development_score",
        "community_score",
        "delivery_score",
        "adoption_score",
        "topic_momentum_score",
        "maintenance_score",
        "hype_risk",
        "hype_risk_status",
        "lifecycle_stage",
        "data_completeness",
        "algorithm_version",
        "calculated_at",
    )

    @classmethod
    def with_current_trend(cls, queryset: QuerySet[Repository]) -> QuerySet[Repository]:
        trend = RepositoryTrendScore.objects.filter(
            repository_id=OuterRef("pk"), algorithm_version=ALGORITHM_VERSION
        )
        activity = RepositoryActivityMetric.objects.filter(repository_id=OuterRef("pk")).order_by(
            "-metric_date"
        )
        potential = RepositoryPotentialScore.objects.filter(
            repository_id=OuterRef("pk"), algorithm_version=POTENTIAL_ALGORITHM_VERSION
        )
        learning = RepositoryLearningScore.objects.filter(
            repository_id=OuterRef("pk"), algorithm_version=LEARNING_ALGORITHM_VERSION
        )
        enterprise = RepositoryEnterpriseScore.objects.filter(
            repository_id=OuterRef("pk"), algorithm_version=ENTERPRISE_ALGORITHM_VERSION
        )
        active_model_forecast = RepositoryForecast.objects.filter(
            repository_id=OuterRef("pk"),
            model__status=ModelStatus.ACTIVE,
            model__feature_version="feature-v2.0.0",
            predicted_activity_percentile__isnull=False,
        ).order_by("-sample_at", "-created_at")
        annotations = {
            f"current_{field}": Subquery(trend.values(field)[:1]) for field in cls.TREND_FIELDS
        }
        for field in (
            "commits_30d",
            "prs_created_30d",
            "issues_created_30d",
            "releases_30d",
        ):
            annotations[f"current_{field}"] = Subquery(activity.values(field)[:1])
        for field in ("potential_score", "confidence", "algorithm_version", "calculated_at"):
            annotations[f"current_potential_{field}"] = Subquery(potential.values(field)[:1])
        for prefix, score_query in (("learning", learning), ("enterprise", enterprise)):
            for field in ("score", "confidence", "algorithm_version", "calculated_at"):
                annotations[f"current_{prefix}_{field}"] = Subquery(score_query.values(field)[:1])
        annotations.update(
            {
                "current_forecast_percentile": Subquery(
                    active_model_forecast.values("predicted_activity_percentile")[:1]
                ),
                "current_forecast_confidence": Subquery(
                    active_model_forecast.values("confidence")[:1]
                ),
                "current_forecast_model_version": Subquery(
                    active_model_forecast.values("model_version")[:1]
                ),
                "current_forecast_sample_at": Subquery(
                    active_model_forecast.values("sample_at")[:1]
                ),
            }
        )
        annotated = queryset.annotate(**annotations)
        return annotated.annotate(
            current_display_potential_score=Coalesce(
                "current_forecast_percentile",
                "current_potential_potential_score",
                output_field=FloatField(),
            ),
            current_display_potential_confidence=Coalesce(
                "current_forecast_confidence", "current_potential_confidence"
            ),
        )

    @classmethod
    def discover(cls, filters: dict[str, Any]) -> QuerySet[Repository]:
        queryset = cls.with_current_trend(
            Repository.objects.filter(is_disabled=False, is_fork=False)
        ).prefetch_related("topics")
        if query := filters.get("q"):
            queryset = queryset.filter(full_name__icontains=query) | queryset.filter(
                description__icontains=query
            )
        if category := filters.get("category"):
            queryset = queryset.filter(category=category)
        if language := filters.get("language"):
            queryset = queryset.filter(primary_language__iexact=language)
        if license_key := filters.get("license"):
            queryset = queryset.filter(license_spdx__iexact=license_key)
        if filters.get("min_stars") is not None:
            queryset = queryset.filter(stars__gte=filters["min_stars"])
        if filters.get("max_stars") is not None:
            queryset = queryset.filter(stars__lte=filters["max_stars"])
        if filters.get("trend_min") is not None:
            queryset = queryset.filter(current_trend_score__gte=filters["trend_min"])
        if filters.get("potential_min") is not None:
            queryset = queryset.filter(
                current_display_potential_score__gte=filters["potential_min"],
                current_display_potential_confidence__gte=cls.MIN_POTENTIAL_RANKING_CONFIDENCE,
            )
        if filters.get("learning_min") is not None:
            queryset = queryset.filter(
                current_learning_score__gte=filters["learning_min"],
                current_learning_confidence__gte=settings.LEARNING_RANKING_MIN_CONFIDENCE,
            )
        if filters.get("enterprise_min") is not None:
            queryset = queryset.filter(
                current_enterprise_score__gte=filters["enterprise_min"],
                current_enterprise_confidence__gte=settings.ENTERPRISE_RANKING_MIN_CONFIDENCE,
            )
        if lifecycle := filters.get("lifecycle"):
            queryset = queryset.filter(current_lifecycle_stage=lifecycle)
        ordering = {
            "trend": "current_trend_score",
            "-trend": "-current_trend_score",
            "potential": "current_display_potential_score",
            "-potential": "-current_display_potential_score",
            "learning": "current_learning_score",
            "-learning": "-current_learning_score",
            "enterprise": "current_enterprise_score",
            "-enterprise": "-current_enterprise_score",
            "stars": "stars",
            "-stars": "-stars",
            "updated": "github_updated_at",
            "-updated": "-github_updated_at",
        }[filters.get("sort", "-trend")]
        field = ordering.removeprefix("-")
        if field == "current_trend_score":
            queryset = queryset.filter(
                current_trend_score__isnull=False,
                current_data_completeness__gte=cls.MIN_TREND_RANKING_COMPLETENESS,
            )
        elif field == "current_display_potential_score":
            queryset = queryset.filter(
                current_display_potential_score__isnull=False,
                current_display_potential_confidence__gte=cls.MIN_POTENTIAL_RANKING_CONFIDENCE,
            )
        elif field == "current_learning_score":
            queryset = queryset.filter(
                current_learning_score__isnull=False,
                current_learning_confidence__gte=settings.LEARNING_RANKING_MIN_CONFIDENCE,
            )
        elif field == "current_enterprise_score":
            queryset = queryset.filter(
                current_enterprise_score__isnull=False,
                current_enterprise_confidence__gte=settings.ENTERPRISE_RANKING_MIN_CONFIDENCE,
            )
        order_expression = (
            F(field).desc(nulls_last=True)
            if ordering.startswith("-")
            else F(field).asc(nulls_last=True)
        )
        return queryset.order_by(order_expression, "full_name")

    @classmethod
    def dashboard(cls) -> dict[str, Any]:
        repositories = list(
            cls.with_current_trend(Repository.objects.filter(is_disabled=False, is_fork=False))
            .prefetch_related("topics")
            .order_by("-current_trend_score", "full_name")
        )
        active = sum(
            any(
                (getattr(repository, f"current_{field}", None) or 0) > 0
                for field in (
                    "commits_30d",
                    "prs_created_30d",
                    "issues_created_30d",
                    "releases_30d",
                )
            )
            for repository in repositories
        )
        lifecycle = Counter(
            repository.current_lifecycle_stage
            for repository in repositories
            if repository.current_lifecycle_stage
        )
        category_scores: dict[str, list[float]] = defaultdict(list)
        category_counts = Counter(repository.category for repository in repositories)
        for repository in repositories:
            if repository.current_trend_score is not None:
                category_scores[repository.category].append(float(repository.current_trend_score))
        high_potential = [
            repository
            for repository in repositories
            if cls._candidate_flags(repository)["high_potential"]
        ]
        breakout_candidates = [
            repository
            for repository in repositories
            if cls._candidate_flags(repository)["breakout_candidate"]
        ]
        ranked_trend = [
            repository
            for repository in repositories
            if repository.current_trend_score is not None
            and repository.current_data_completeness is not None
            and repository.current_data_completeness >= cls.MIN_TREND_RANKING_COMPLETENESS
        ]
        ranked_trend.sort(
            key=lambda repository: (
                cls._sort_number(repository.current_trend_score),
                cls._sort_number(repository.current_data_completeness),
            ),
            reverse=True,
        )
        high_potential.sort(
            key=lambda repository: (
                cls._sort_number(repository.current_display_potential_score),
                cls._sort_number(repository.current_display_potential_confidence),
                cls._sort_number(repository.current_trend_score),
            ),
            reverse=True,
        )
        categories = [
            {
                "category": category,
                "repository_count": count,
                "average_trend": (
                    round(sum(category_scores[category]) / len(category_scores[category]), 2)
                    if category_scores[category]
                    else None
                ),
            }
            for category, count in sorted(category_counts.items())
        ]
        category_capability = DataCapability.objects.filter(
            name=CapabilityName.CATEGORY_TREND
        ).first()
        category_ready = bool(
            category_capability and category_capability.status == CapabilityStatus.READY
        )
        category_trends = (
            [
                {
                    "category": row.category,
                    "trend_score": _number(row.trend_score),
                    "repository_count": row.repository_count,
                    "eligible_repository_count": row.eligible_repository_count,
                    "data_coverage": row.data_coverage,
                }
                for row in CategoryTrendMetric.objects.filter(
                    algorithm_version=CATEGORY_TREND_VERSION
                ).order_by("-trend_score")
            ]
            if category_ready
            else []
        )
        return {
            "statistics": {
                "tracked_projects": len(repositories),
                "active_projects": active,
                "emerging_projects": lifecycle[LifecycleStage.EMERGING],
                "breakout_projects": lifecycle[LifecycleStage.BREAKOUT],
                "high_hype_projects": sum(
                    repository.current_hype_risk_status == HypeRiskStatus.HIGH
                    for repository in repositories
                ),
                "high_potential_projects": len(high_potential),
                "breakout_candidates": len(breakout_candidates),
            },
            "top_trend_projects": [cls.summary(item) for item in ranked_trend[:10]],
            "breakout_projects": [
                cls.summary(item)
                for item in repositories
                if item.current_lifecycle_stage == LifecycleStage.BREAKOUT
            ][:10],
            "high_hype_projects": [
                cls.summary(item)
                for item in repositories
                if item.current_hype_risk_status == HypeRiskStatus.HIGH
            ][:10],
            "high_potential_projects": [cls.summary(item) for item in high_potential[:10]],
            "high_potential_ranking": {
                "source": (
                    "STAR_FORECAST_V2"
                    if any(
                        getattr(item, "current_forecast_percentile", None) is not None
                        for item in repositories
                    )
                    else "DETERMINISTIC_POTENTIAL"
                ),
                "fallback": "DETERMINISTIC_POTENTIAL",
                "algorithm_version": (
                    next(
                        (
                            getattr(item, "current_forecast_model_version", None)
                            for item in repositories
                            if getattr(item, "current_forecast_percentile", None) is not None
                        ),
                        None,
                    )
                    or POTENTIAL_ALGORITHM_VERSION
                ),
            },
            "breakout_candidates": [cls.summary(item) for item in breakout_candidates[:10]],
            "lifecycle_distribution": [
                {"stage": stage, "count": lifecycle[stage]} for stage in LifecycleStage.values
            ],
            "category_summary": categories,
            "category_trend": {
                "status": (
                    category_capability.status
                    if category_capability
                    else CapabilityStatus.ACCUMULATING
                ),
                "fallback": None if category_ready else "CATEGORY_DISTRIBUTION",
                "data_as_of": category_capability.data_as_of if category_capability else None,
                "data_coverage": (
                    category_capability.data_coverage if category_capability else 0.0
                ),
                "algorithm_version": (
                    category_capability.algorithm_version if category_capability else None
                ),
                "reason": (
                    category_capability.reason
                    if category_capability
                    else "Data maturity has not been evaluated yet"
                ),
                "results": category_trends,
            },
        }

    @staticmethod
    def summary(repository: Repository) -> dict[str, Any]:
        flags = RepositoryReadService._candidate_flags(repository)
        return {
            "id": repository.id,
            "full_name": repository.full_name,
            "description": repository.description,
            "category": repository.category,
            "primary_language": repository.primary_language,
            "stars": repository.stars,
            "forks": repository.forks,
            "trend_score": _number(getattr(repository, "current_trend_score", None)),
            "data_completeness": getattr(repository, "current_data_completeness", None),
            "hype_risk": _number(getattr(repository, "current_hype_risk", None)),
            "hype_risk_status": getattr(repository, "current_hype_risk_status", None),
            "lifecycle_stage": getattr(repository, "current_lifecycle_stage", None),
            "algorithm_version": getattr(repository, "current_algorithm_version", None),
            "potential_score": _number(
                getattr(repository, "current_display_potential_score", None)
            ),
            "potential_confidence": getattr(
                repository, "current_display_potential_confidence", None
            ),
            "potential_algorithm_version": (
                getattr(repository, "current_forecast_model_version", None)
                or getattr(repository, "current_potential_algorithm_version", None)
            ),
            "potential_score_source": (
                "STAR_FORECAST_V2"
                if getattr(repository, "current_forecast_percentile", None) is not None
                else "DETERMINISTIC_POTENTIAL"
            ),
            "deterministic_potential_score": _number(
                getattr(repository, "current_potential_potential_score", None)
            ),
            "forecast_percentile": _number(
                getattr(repository, "current_forecast_percentile", None)
            ),
            "forecast_sample_at": getattr(repository, "current_forecast_sample_at", None),
            "learning_score": _number(getattr(repository, "current_learning_score", None)),
            "learning_confidence": getattr(repository, "current_learning_confidence", None),
            "learning_algorithm_version": getattr(
                repository, "current_learning_algorithm_version", None
            ),
            "enterprise_score": _number(getattr(repository, "current_enterprise_score", None)),
            "enterprise_confidence": getattr(repository, "current_enterprise_confidence", None),
            "enterprise_algorithm_version": getattr(
                repository, "current_enterprise_algorithm_version", None
            ),
            **flags,
            "topics": [topic.normalized_name for topic in repository.topics.all()],
        }

    @classmethod
    def detail(cls, repository_id: int, user=None) -> dict[str, Any]:
        from apps.repositories.localization import RepositoryLocalizationService
        from apps.watchlists.models import WatchlistItem

        repository = (
            cls.with_current_trend(Repository.objects.all())
            .prefetch_related(
                Prefetch("topics", queryset=Topic.objects.order_by("normalized_name")),
                Prefetch(
                    "snapshots",
                    queryset=RepositorySnapshot.objects.order_by("-snapshot_at")[:1],
                    to_attr="latest_snapshots",
                ),
                Prefetch(
                    "activity_metrics",
                    queryset=RepositoryActivityMetric.objects.order_by("-metric_date")[:1],
                    to_attr="latest_activities",
                ),
            )
            .get(pk=repository_id, is_disabled=False)
        )
        latest_snapshot = repository.latest_snapshots[0] if repository.latest_snapshots else None
        latest_activity = repository.latest_activities[0] if repository.latest_activities else None
        response = cls.summary(repository)
        localization = RepositoryLocalizationService().cached_or_pending(repository)
        response.update(
            {
                "owner": repository.owner,
                "name": repository.name,
                "github_url": f"https://github.com/{repository.full_name}",
                "homepage": repository.homepage,
                "subscribers": repository.subscribers,
                "open_issues": repository.open_issues,
                "license_key": repository.license_key,
                "license_spdx": repository.license_spdx,
                "default_branch": repository.default_branch,
                "is_archived": repository.is_archived,
                "community_health": repository.community_health,
                "github_created_at": repository.github_created_at,
                "github_updated_at": repository.github_updated_at,
                "github_pushed_at": repository.github_pushed_at,
                "last_synced_at": repository.last_synced_at,
                "latest_snapshot": cls._snapshot(latest_snapshot),
                "latest_activity": cls._activity(latest_activity),
                "is_watchlisted": WatchlistItem.objects.filter(
                    watchlist__owner=user, repository_id=repository_id
                ).exists()
                if user is not None and user.is_authenticated
                else False,
                **localization,
            }
        )
        return response

    @classmethod
    def metrics(cls, repository_id: int, days: int) -> dict[str, Any]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        start = timezone.now().date() - timedelta(days=days - 1)
        snapshots = repository.snapshots.filter(snapshot_date__gte=start).order_by("snapshot_at")
        activities = repository.activity_metrics.filter(metric_date__gte=start).order_by(
            "metric_date"
        )
        releases = repository.releases.filter(published_at__date__gte=start).order_by(
            "published_at"
        )
        trends = repository.trend_scores.order_by("calculated_at")
        potentials = repository.potential_scores.order_by("calculated_at")
        return {
            "repository_id": repository.id,
            "range": f"{days}d",
            "snapshots": [cls._snapshot(snapshot) for snapshot in snapshots],
            "activity": [cls._activity(activity) for activity in activities],
            "releases": [
                {
                    "tag_name": release.tag_name,
                    "name": release.name,
                    "published_at": release.published_at,
                    "is_prerelease": release.is_prerelease,
                }
                for release in releases
            ],
            "trend_history": [cls._trend_summary(trend) for trend in trends],
            "potential_history": [cls._potential_summary(item) for item in potentials],
        }

    @classmethod
    def trend(cls, repository_id: int) -> dict[str, Any]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        trend = repository.trend_scores.order_by("-calculated_at").first()
        if trend is None:
            return {
                "repository_id": repository.id,
                "status": "NOT_AVAILABLE",
                "data_completeness": 0.0,
                "hype_risk": None,
                "hype_risk_status": HypeRiskStatus.INSUFFICIENT_HISTORY,
                "evidence": None,
            }
        response = cls._trend_summary(trend)
        response.update(
            {
                "repository_id": repository.id,
                "status": "AVAILABLE",
                "evidence": trend.evidence,
            }
        )
        return response

    @classmethod
    def potential(cls, repository_id: int) -> dict[str, Any]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        potential = repository.potential_scores.filter(
            algorithm_version=POTENTIAL_ALGORITHM_VERSION
        ).first()
        if potential is None:
            return {
                "repository_id": repository.id,
                "status": "NOT_AVAILABLE",
                "potential_score": None,
                "confidence": 0.0,
                "algorithm_version": POTENTIAL_ALGORITHM_VERSION,
                "evidence": None,
                "high_potential": False,
                "potential_candidate": False,
                "breakout_candidate": False,
            }
        response = cls._potential_summary(potential)
        response.update(
            {
                "repository_id": repository.id,
                "status": "AVAILABLE",
                "evidence": potential.evidence,
                **potential.evidence.get("candidate_flags", {}),
            }
        )
        return response

    @staticmethod
    def forecast(repository_id: int) -> dict[str, Any]:
        Repository.objects.get(pk=repository_id, is_disabled=False)
        return ForecastService().status(repository_id)

    @staticmethod
    def learning(repository_id: int) -> dict[str, Any]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        score = repository.learning_scores.filter(
            algorithm_version=LEARNING_ALGORITHM_VERSION
        ).first()
        if score is None:
            return {
                "repository_id": repository.id,
                "status": "NOT_AVAILABLE",
                "score": None,
                "confidence": 0.0,
                "algorithm_version": LEARNING_ALGORITHM_VERSION,
                "ranking_eligible": False,
                "evidence": None,
            }
        return {
            "repository_id": repository.id,
            "status": "AVAILABLE",
            "score": _number(score.score),
            "confidence": score.confidence,
            "algorithm_version": score.algorithm_version,
            "calculated_at": score.calculated_at,
            "ranking_eligible": score.confidence >= settings.LEARNING_RANKING_MIN_CONFIDENCE,
            "evidence": score.evidence,
        }

    @staticmethod
    def enterprise(repository_id: int) -> dict[str, Any]:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        score = repository.enterprise_scores.filter(
            algorithm_version=ENTERPRISE_ALGORITHM_VERSION
        ).first()
        if score is None:
            return {
                "repository_id": repository.id,
                "status": "NOT_AVAILABLE",
                "score": None,
                "confidence": 0.0,
                "recommendation": None,
                "algorithm_version": ENTERPRISE_ALGORITHM_VERSION,
                "ranking_eligible": False,
                "evidence": None,
            }
        return {
            "repository_id": repository.id,
            "status": "AVAILABLE",
            "score": _number(score.score),
            "confidence": score.confidence,
            "recommendation": score.recommendation,
            "algorithm_version": score.algorithm_version,
            "calculated_at": score.calculated_at,
            "ranking_eligible": score.confidence >= settings.ENTERPRISE_RANKING_MIN_CONFIDENCE,
            "evidence": score.evidence,
        }

    @staticmethod
    def _snapshot(snapshot: RepositorySnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        return {
            "snapshot_at": snapshot.snapshot_at,
            "stars": snapshot.stars,
            "forks": snapshot.forks,
            "subscribers": snapshot.subscribers,
            "open_issues": snapshot.open_issues,
            "data_completeness": snapshot.data_completeness,
        }

    @staticmethod
    def _activity(activity: RepositoryActivityMetric | None) -> dict[str, Any] | None:
        if activity is None:
            return None
        return {
            "metric_date": activity.metric_date,
            "commits_7d": activity.commits_7d,
            "commits_30d": activity.commits_30d,
            "prs_created_7d": activity.prs_created_7d,
            "prs_created_30d": activity.prs_created_30d,
            "prs_merged_7d": activity.prs_merged_7d,
            "prs_merged_30d": activity.prs_merged_30d,
            "issues_created_7d": activity.issues_created_7d,
            "issues_created_30d": activity.issues_created_30d,
            "issues_closed_7d": activity.issues_closed_7d,
            "issues_closed_30d": activity.issues_closed_30d,
            "active_contributors_30d": activity.active_contributors_30d,
            "releases_30d": activity.releases_30d,
            "releases_90d": activity.releases_90d,
            "days_since_last_push": activity.days_since_last_push,
            "days_since_last_release": activity.days_since_last_release,
        }

    @staticmethod
    def _trend_summary(trend: RepositoryTrendScore) -> dict[str, Any]:
        return {
            "trend_score": _number(trend.trend_score),
            "momentum_score": _number(trend.momentum_score),
            "development_score": _number(trend.development_score),
            "community_score": _number(trend.community_score),
            "delivery_score": _number(trend.delivery_score),
            "adoption_score": _number(trend.adoption_score),
            "topic_momentum_score": _number(trend.topic_momentum_score),
            "maintenance_score": _number(trend.maintenance_score),
            "hype_risk": _number(trend.hype_risk),
            "hype_risk_status": trend.hype_risk_status,
            "lifecycle_stage": trend.lifecycle_stage,
            "data_completeness": trend.data_completeness,
            "algorithm_version": trend.algorithm_version,
            "calculated_at": trend.calculated_at,
        }

    @staticmethod
    def _potential_summary(potential: RepositoryPotentialScore) -> dict[str, Any]:
        return {
            "potential_score": _number(potential.potential_score),
            "confidence": potential.confidence,
            "algorithm_version": potential.algorithm_version,
            "calculated_at": potential.calculated_at,
        }

    @staticmethod
    def _candidate_flags(repository: Repository) -> dict[str, bool]:
        forecast_percentile = _number(
            getattr(repository, "current_forecast_percentile", None)
        )
        if forecast_percentile is not None:
            confidence = float(getattr(repository, "current_forecast_confidence", 0.0) or 0.0)
            return {
                "high_potential": forecast_percentile >= 80 and confidence >= 0.45,
                "potential_candidate": forecast_percentile >= 65 and confidence >= 0.45,
                "breakout_candidate": False,
            }
        return candidate_flags(
            potential=_number(getattr(repository, "current_potential_potential_score", None)),
            confidence=float(getattr(repository, "current_potential_confidence", 0.0) or 0.0),
            momentum=_number(getattr(repository, "current_momentum_score", None)),
            community=_number(getattr(repository, "current_community_score", None)),
            delivery=_number(getattr(repository, "current_delivery_score", None)),
            hype_status=getattr(repository, "current_hype_risk_status", "") or "",
        )

    @staticmethod
    def _sort_number(value: Any) -> float:
        return float(value) if value is not None else -1.0
