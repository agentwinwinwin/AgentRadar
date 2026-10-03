from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.activities.models import RepositoryActivityMetric
from apps.datasets.models import TrainingSample
from apps.forecasts.models import MLModel, ModelStatus
from apps.operations.models import RepositoryScoreHistory
from apps.repositories.models import Repository
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import ALGORITHM_VERSION as TREND_ALGORITHM_VERSION
from apps.trends.models import RepositoryTrendScore

from .models import CapabilityName, CapabilityStatus, CategoryTrendMetric, DataCapability

CATEGORY_TREND_VERSION = "category-trend-v1.0.0"
MATURITY_VERSION = "data-maturity-v1.0.0"


@dataclass(frozen=True)
class Evaluation:
    ready: bool
    coverage: float
    reason: str
    metrics: dict[str, Any]
    algorithm_version: str | None = MATURITY_VERSION


class DataMaturityService:
    ACTIVITY_FIELDS = (
        "commits_30d",
        "prs_created_30d",
        "prs_merged_30d",
        "active_contributors_30d",
        "issues_created_30d",
        "issues_closed_30d",
    )

    def evaluate(self) -> dict[str, Any]:
        now = timezone.now()
        repository_ids = list(
            Repository.objects.filter(
                is_disabled=False, is_fork=False, monitoring_enabled=True
            ).values_list("id", flat=True)
        )
        snapshots = self._snapshots(repository_ids)
        latest_activity = self._latest_activity(repository_ids)
        data_as_of = max(
            (row.snapshot_at for rows in snapshots.values() for row in rows), default=None
        )
        eligible_count = len(repository_ids)
        growth = {
            (field, days): self._growth_evaluation(
                snapshots, repository_ids, field, days, eligible_count
            )
            for field in ("stars", "forks")
            for days in (7, 30)
        }
        activity = self._activity_evaluation(latest_activity, repository_ids)
        category_eval, category_rows = self._category_evaluation(
            repository_ids, snapshots, eligible_count
        )
        score_evaluations = {
            CapabilityName.TREND_CHANGE_ALERT: self._score_history_evaluation(
                repository_ids, RepositoryScoreHistory.ScoreType.TREND
            ),
            CapabilityName.POTENTIAL_CHANGE_ALERT: self._score_history_evaluation(
                repository_ids, RepositoryScoreHistory.ScoreType.POTENTIAL
            ),
        }
        dependencies_7_30 = [
            growth[("stars", 7)],
            growth[("forks", 7)],
            growth[("stars", 30)],
            growth[("forks", 30)],
            activity,
        ]
        evaluations = {
            CapabilityName.STAR_GROWTH_7D: growth[("stars", 7)],
            CapabilityName.STAR_GROWTH_30D: growth[("stars", 30)],
            CapabilityName.FORK_GROWTH_7D: growth[("forks", 7)],
            CapabilityName.FORK_GROWTH_30D: growth[("forks", 30)],
            CapabilityName.MOMENTUM: self._dependencies("Momentum", dependencies_7_30),
            CapabilityName.HYPE_RISK: self._dependencies(
                "Hype Risk",
                [growth[("stars", 30)], growth[("forks", 30)], activity],
            ),
            CapabilityName.CATEGORY_TREND: category_eval,
            **score_evaluations,
            CapabilityName.FORECAST_V2_DATA_READINESS: self._forecast_v2(repository_ids, snapshots),
        }
        transitioned: list[str] = []
        for name, evaluation in evaluations.items():
            if self._persist(name, evaluation, now, data_as_of):
                transitioned.append(name)
        if category_eval.ready:
            self._persist_category_trends(category_rows, now, data_as_of or now)
        return {
            "evaluated": len(evaluations),
            "transitioned_to_ready": transitioned,
            "ready": sum(item.ready for item in evaluations.values()),
        }

    @staticmethod
    def _snapshots(repository_ids: list[int]) -> dict[int, list[RepositorySnapshot]]:
        grouped: dict[int, list[RepositorySnapshot]] = defaultdict(list)
        rows = RepositorySnapshot.objects.filter(
            repository_id__in=repository_ids,
            data_origin="OBSERVED",
            data_completeness__gte=0.8,
        ).order_by("repository_id", "snapshot_at")
        for row in rows.iterator(chunk_size=1000):
            grouped[row.repository_id].append(row)
        return grouped

    @staticmethod
    def _latest_activity(repository_ids: list[int]) -> dict[int, RepositoryActivityMetric]:
        output: dict[int, RepositoryActivityMetric] = {}
        rows = RepositoryActivityMetric.objects.filter(repository_id__in=repository_ids).order_by(
            "repository_id", "-metric_date"
        )
        for row in rows.iterator(chunk_size=1000):
            output.setdefault(row.repository_id, row)
        return output

    def _growth_evaluation(
        self,
        snapshots: dict[int, list[RepositorySnapshot]],
        repository_ids: list[int],
        field: str,
        days: int,
        eligible_count: int,
    ) -> Evaluation:
        qualified = sum(
            self._has_baseline(snapshots.get(repository_id, []), field, days)
            for repository_id in repository_ids
        )
        coverage = qualified / eligible_count if eligible_count else 0.0
        ready = (
            qualified >= settings.CAPABILITY_MIN_REPOSITORIES
            and coverage >= settings.CAPABILITY_MIN_COVERAGE
        )
        reason = (
            f"{qualified}/{eligible_count} repositories have {days}d OBSERVED {field} history; "
            f"requires {settings.CAPABILITY_MIN_REPOSITORIES} and "
            f"{settings.CAPABILITY_MIN_COVERAGE:.0%} coverage"
        )
        return Evaluation(
            ready,
            coverage,
            reason,
            {"qualified_repositories": qualified, "eligible_repositories": eligible_count},
        )

    @staticmethod
    def _has_baseline(snapshots: list[RepositorySnapshot], field: str, days: int) -> bool:
        valid = [item for item in snapshots if getattr(item, field) is not None]
        if len(valid) < 2:
            return False
        current = valid[-1]
        target = current.snapshot_at - timedelta(days=days)
        candidates = [item for item in valid[:-1] if item.snapshot_at <= target]
        return bool(candidates and target - candidates[-1].snapshot_at <= timedelta(days=2))

    def _activity_evaluation(
        self, activities: dict[int, RepositoryActivityMetric], repository_ids: list[int]
    ) -> Evaluation:
        qualified = sum(
            row is not None
            and all(getattr(row, field) is not None for field in self.ACTIVITY_FIELDS)
            for row in (activities.get(repository_id) for repository_id in repository_ids)
        )
        total = len(repository_ids)
        coverage = qualified / total if total else 0.0
        ready = (
            qualified >= settings.CAPABILITY_MIN_REPOSITORIES
            and coverage >= settings.CAPABILITY_MIN_COVERAGE
        )
        return Evaluation(
            ready,
            coverage,
            f"{qualified}/{total} repositories have complete development activity inputs",
            {"qualified_repositories": qualified, "eligible_repositories": total},
        )

    @staticmethod
    def _dependencies(label: str, dependencies: list[Evaluation]) -> Evaluation:
        ready = all(item.ready for item in dependencies)
        coverage = min((item.coverage for item in dependencies), default=0.0)
        return Evaluation(
            ready,
            coverage,
            f"{label} dependencies are {'ready' if ready else 'still accumulating'}",
            {"dependency_coverages": [item.coverage for item in dependencies]},
            TREND_ALGORITHM_VERSION,
        )

    def _category_evaluation(
        self,
        repository_ids: list[int],
        snapshots: dict[int, list[RepositorySnapshot]],
        eligible_count: int,
    ) -> tuple[Evaluation, list[dict[str, Any]]]:
        repositories = list(
            Repository.objects.filter(id__in=repository_ids).values("id", "category")
        )
        scores = {
            row.repository_id: row
            for row in RepositoryTrendScore.objects.filter(
                repository_id__in=repository_ids,
                algorithm_version=TREND_ALGORITHM_VERSION,
                trend_score__isnull=False,
                data_completeness__gte=0.5,
            )
        }
        grouped: dict[str, list[int]] = defaultdict(list)
        for repository in repositories:
            grouped[repository["category"]].append(repository["id"])
        rows = []
        for category, ids in grouped.items():
            eligible = [
                repository_id
                for repository_id in ids
                if repository_id in scores
                and self._has_baseline(snapshots.get(repository_id, []), "stars", 30)
            ]
            coverage = len(eligible) / len(ids) if ids else 0.0
            if (
                len(eligible) >= settings.CATEGORY_TREND_MIN_REPOSITORIES
                and coverage >= settings.CATEGORY_TREND_MIN_COVERAGE
            ):
                rows.append(
                    {
                        "category": category,
                        "repository_count": len(ids),
                        "eligible_ids": eligible,
                        "coverage": coverage,
                        "score": sum(float(scores[item].trend_score) for item in eligible)
                        / len(eligible),
                    }
                )
        ready = len(rows) >= settings.CATEGORY_TREND_MIN_CATEGORIES
        qualified_repositories = sum(len(row["eligible_ids"]) for row in rows)
        coverage = qualified_repositories / eligible_count if eligible_count else 0.0
        return (
            Evaluation(
                ready,
                coverage,
                f"{len(rows)} categories meet repository and coverage gates",
                {
                    "qualified_categories": len(rows),
                    "required_categories": settings.CATEGORY_TREND_MIN_CATEGORIES,
                },
                CATEGORY_TREND_VERSION,
            ),
            rows,
        )

    @staticmethod
    def _score_history_evaluation(repository_ids: list[int], score_type: str) -> Evaluation:
        counts: dict[int, int] = defaultdict(int)
        rows = RepositoryScoreHistory.objects.filter(
            repository_id__in=repository_ids, score_type=score_type
        ).values_list("repository_id", "history_bucket")
        seen = set(rows)
        for repository_id, _ in seen:
            counts[repository_id] += 1
        qualified = sum(count >= 2 for count in counts.values())
        total = len(repository_ids)
        coverage = qualified / total if total else 0.0
        ready = (
            qualified >= settings.CAPABILITY_MIN_REPOSITORIES
            and coverage >= settings.CAPABILITY_MIN_COVERAGE
        )
        return Evaluation(
            ready,
            coverage,
            f"{qualified}/{total} repositories have at least two real score history buckets",
            {"qualified_repositories": qualified, "eligible_repositories": total},
            "alerts-v1.0.0",
        )

    def _forecast_v2(
        self, repository_ids: list[int], snapshots: dict[int, list[RepositorySnapshot]]
    ) -> Evaluation:
        active_model = (
            MLModel.objects.filter(
                status=ModelStatus.ACTIVE, feature_version="feature-v2.0.0"
            )
            .order_by("-activated_at", "-created_at")
            .first()
        )
        targets = active_model.retraining_targets if active_model else {}
        phase = "NEXT_RETRAINING" if active_model else "FIRST_ACTIVATION"
        required_span = int(targets.get("observed_span_days") or 60)
        required_repositories = int(
            targets.get("observed_repositories") or settings.FORECAST_V2_MIN_REPOSITORIES
        )
        required_samples = int(
            targets.get("training_samples") or settings.FORECAST_V2_MIN_TRAINING_SAMPLES
        )
        required_categories = int(
            targets.get("categories") or settings.FORECAST_V2_MIN_CATEGORIES
        )
        qualified_ids = [
            repository_id
            for repository_id in repository_ids
            if self._has_baseline(snapshots.get(repository_id, []), "stars", required_span)
        ]
        categories = (
            Repository.objects.filter(id__in=qualified_ids).values("category").distinct().count()
        )
        sample_count = TrainingSample.objects.filter(
            feature_version="feature-v2.0.0",
            label_version="label-v2.0.0",
            binary_top20_label__isnull=False,
        ).count()
        spans = [
            (rows[-1].snapshot_at - rows[0].snapshot_at).days
            for rows in snapshots.values()
            if len(rows) >= 2
        ]
        max_span = max(spans, default=0)
        first_observed_at = min(
            (rows[0].snapshot_at for rows in snapshots.values() if rows), default=None
        )
        earliest_label_ready_at = (
            first_observed_at + timedelta(days=90) if first_observed_at else None
        )
        ready = (
            len(qualified_ids) >= required_repositories
            and sample_count >= required_samples
            and categories >= required_categories
        )
        coverage = len(qualified_ids) / len(repository_ids) if repository_ids else 0.0
        return Evaluation(
            ready,
            coverage,
            "Forecast V2 data is ready for candidate dataset generation"
            if ready
            else "Observed 60d history, samples or category coverage is insufficient",
            {
                "observed_60d_repositories": len(qualified_ids),
                "observed_target_span_repositories": len(qualified_ids),
                "required_observed_repositories": required_repositories,
                "star_enhanced_training_samples": sample_count,
                "required_training_samples": required_samples,
                "qualified_categories": categories,
                "required_categories": required_categories,
                "maximum_observed_span_days": max_span,
                "required_observed_span_days": required_span,
                "required_future_label_days": 30,
                "earliest_label_ready_at": (
                    earliest_label_ready_at.isoformat() if earliest_label_ready_at else None
                ),
                "feature_version": "feature-v2.0.0",
                "label_version": "label-v2.0.0",
                "data_readiness": "DATA_READY" if ready else "ACCUMULATING",
                "readiness_phase": phase,
                "active_star_model_version": active_model.model_version if active_model else None,
                "collection_continues_after_activation": True,
            },
            "forecast-v2-readiness-v1.1.0",
        )

    @staticmethod
    @transaction.atomic
    def _persist(name: str, evaluation: Evaluation, now, data_as_of) -> bool:
        capability, _ = DataCapability.objects.select_for_update().get_or_create(
            name=name,
            defaults={"reason": "Initial evaluation pending", "last_evaluated_at": now},
        )
        if capability.status == CapabilityStatus.DISABLED:
            capability.last_evaluated_at = now
            capability.save(update_fields=("last_evaluated_at", "updated_at"))
            return False
        old_status = capability.status
        is_retraining_cycle = (
            name == CapabilityName.FORECAST_V2_DATA_READINESS
            and evaluation.metrics.get("readiness_phase") == "NEXT_RETRAINING"
        )
        status = (
            CapabilityStatus.READY
            if evaluation.ready
            else CapabilityStatus.ACCUMULATING
            if is_retraining_cycle
            else CapabilityStatus.DEGRADED
            if capability.first_ready_at
            else CapabilityStatus.ACCUMULATING
        )
        capability.status = status
        capability.data_coverage = round(evaluation.coverage, 6)
        capability.reason = evaluation.reason
        capability.metrics = evaluation.metrics
        capability.algorithm_version = evaluation.algorithm_version
        capability.data_as_of = data_as_of
        capability.last_evaluated_at = now
        if status == CapabilityStatus.READY and capability.first_ready_at is None:
            capability.first_ready_at = now
        capability.save()
        return status == CapabilityStatus.READY and old_status != CapabilityStatus.READY

    @staticmethod
    @transaction.atomic
    def _persist_category_trends(rows: list[dict[str, Any]], now, data_as_of) -> None:
        active_categories = [row["category"] for row in rows]
        CategoryTrendMetric.objects.filter(algorithm_version=CATEGORY_TREND_VERSION).exclude(
            category__in=active_categories
        ).delete()
        for row in rows:
            CategoryTrendMetric.objects.update_or_create(
                category=row["category"],
                algorithm_version=CATEGORY_TREND_VERSION,
                defaults={
                    "trend_score": round(row["score"], 2),
                    "repository_count": row["repository_count"],
                    "eligible_repository_count": len(row["eligible_ids"]),
                    "data_coverage": row["coverage"],
                    "data_as_of": data_as_of,
                    "calculated_at": now,
                    "evidence": {"repository_ids": row["eligible_ids"]},
                },
            )
