from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.activities.services import ContributorStatisticsPendingError
from apps.github.client import GitHubClientProtocol, SearchCountResult
from apps.repositories.models import Repository
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import age_cohort, percentile_ranks
from apps.trends.models import RepositoryTrendScore

from .models import DataOrigin, HistoricalActivityWindow, TrainingSample

FEATURE_VERSION = "feature-v1.0.0"
LEGACY_LABEL_VERSION = "label-v1.0.0"
LABEL_VERSION = "label-v1.1.0"
PERCENTILE_LABEL_VERSION = "label-v1.2.0"
FEATURE_NAMES = (
    "repo_age_days",
    "category",
    "current_stars",
    "current_forks",
    "commit_7d",
    "commit_30d",
    "pr_created_7d",
    "pr_created_30d",
    "pr_merged_30d",
    "issue_created_30d",
    "issue_closed_30d",
    "active_contributors_30d",
    "release_count_30d",
    "days_since_last_push",
    "days_since_last_release",
    "community_health",
    "topic_momentum",
)
LABEL_SIGNALS = (
    "commit_activity",
    "pr_activity",
    "contributor_activity",
    "release_activity",
    "issue_resolution_activity",
)


def _count(result: SearchCountResult) -> int | None:
    return None if result.incomplete_results else result.count


def _sample_at(sample_date: date) -> datetime:
    return datetime.combine(sample_date, time.max, tzinfo=UTC)


@dataclass(frozen=True)
class BackfillResult:
    windows: tuple[HistoricalActivityWindow, ...]
    created: int


@dataclass(frozen=True)
class PreparedRepositoryHistory:
    contributor_stats: list[dict[str, Any]]
    releases: list[dict[str, Any]]


class HistoricalBackfillService:
    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client

    def collect(self, repository: Repository, sample_date: date) -> BackfillResult:
        if sample_date + timedelta(days=30) > timezone.now().astimezone(UTC).date():
            raise ValueError("label window must be fully in the past")
        prepared = self.prepare(repository)
        return self.collect_prepared(repository, sample_date, prepared)

    def prepare(self, repository: Repository) -> PreparedRepositoryHistory:
        stats = self.client.get_contributor_statistics(repository.full_name)
        if not stats.ready:
            raise ContributorStatisticsPendingError(stats.retry_after)
        releases = self.client.get_releases(repository.full_name)
        return PreparedRepositoryHistory(stats.contributors, releases)

    def collect_prepared(
        self,
        repository: Repository,
        sample_date: date,
        prepared: PreparedRepositoryHistory,
    ) -> BackfillResult:
        if sample_date + timedelta(days=30) > timezone.now().astimezone(UTC).date():
            raise ValueError("label window must be fully in the past")
        existing = self.existing_result(repository, sample_date)
        if existing is not None:
            return existing
        ranges = self._ranges(sample_date)

        windows: list[HistoricalActivityWindow] = []
        created_count = 0
        for start, end in ranges:
            window, created = self._collect_window(
                repository,
                start,
                end,
                prepared.contributor_stats,
                prepared.releases,
            )
            windows.append(window)
            created_count += int(created)
        return BackfillResult(tuple(windows), created_count)

    @staticmethod
    def _ranges(sample_date: date) -> tuple[tuple[date, date], ...]:
        return (
            (sample_date - timedelta(days=6), sample_date),
            (sample_date - timedelta(days=29), sample_date),
            (sample_date + timedelta(days=1), sample_date + timedelta(days=30)),
        )

    def existing_result(self, repository: Repository, sample_date: date) -> BackfillResult | None:
        windows = []
        for start, end in self._ranges(sample_date):
            window = HistoricalActivityWindow.objects.filter(
                repository=repository,
                window_start=start,
                window_end=end,
                data_origin=DataOrigin.BACKFILLED,
            ).first()
            if window is None:
                return None
            windows.append(window)
        return BackfillResult(tuple(windows), 0)

    @transaction.atomic
    def _collect_window(
        self,
        repository: Repository,
        start: date,
        end: date,
        contributor_stats: list[dict[str, Any]],
        releases: list[dict[str, Any]],
    ) -> tuple[HistoricalActivityWindow, bool]:
        full_name = repository.full_name
        results = {
            "commits": self.client.count_commits(
                full_name, start=start.isoformat(), end=end.isoformat()
            ),
            "prs_created": self.client.count_pull_requests(
                full_name, start=start.isoformat(), end=end.isoformat()
            ),
            "prs_merged": self.client.count_pull_requests(
                full_name, start=start.isoformat(), end=end.isoformat(), merged=True
            ),
            "issues_created": self.client.count_issues(
                full_name, start=start.isoformat(), end=end.isoformat()
            ),
            "issues_closed": self.client.count_issues(
                full_name, start=start.isoformat(), end=end.isoformat(), closed=True
            ),
        }
        values: dict[str, int | None] = {key: _count(result) for key, result in results.items()}
        values["active_contributors"] = self._active_contributors(contributor_stats, start, end)
        release_dates = self._release_dates(releases)
        values["releases"] = sum(start <= item.date() <= end for item in release_dates)
        eligible_releases = [item for item in release_dates if item.date() <= end]
        values["days_since_last_release"] = (
            (end - max(eligible_releases).date()).days if eligible_releases else None
        )
        core_fields = (
            "commits",
            "prs_created",
            "prs_merged",
            "issues_created",
            "issues_closed",
            "active_contributors",
            "releases",
        )
        completeness = sum(values[field] is not None for field in core_fields) / len(core_fields)
        incomplete_fields = [key for key, result in results.items() if result.incomplete_results]
        window, created = HistoricalActivityWindow.objects.update_or_create(
            repository=repository,
            window_start=start,
            window_end=end,
            data_origin=DataOrigin.BACKFILLED,
            defaults={
                **values,
                "data_completeness": round(completeness, 6),
                "source_metadata": {
                    "source": "github_rest_api",
                    "data_origin": DataOrigin.BACKFILLED,
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "search_incomplete_fields": incomplete_fields,
                    "contributor_stats_scope": "weekly_default_branch_recent_10000_commits",
                    "release_scope": "retained_github_releases",
                    "star_snapshot_backfilled": False,
                },
            },
        )
        return window, created

    @staticmethod
    def _active_contributors(
        contributors: list[dict[str, Any]], start: date, end: date
    ) -> int | None:
        observed_week_dates = [
            datetime.fromtimestamp(week["w"], tz=UTC).date()
            for contributor in contributors
            for week in contributor.get("weeks", [])
            if isinstance(week, dict) and isinstance(week.get("w"), int)
        ]
        if (
            not observed_week_dates
            or start < min(observed_week_dates)
            or end > max(observed_week_dates) + timedelta(days=6)
        ):
            return None
        active = 0
        for contributor in contributors:
            weeks = contributor.get("weeks", [])
            if isinstance(weeks, list) and any(
                isinstance(week, dict)
                and isinstance(week.get("w"), int)
                and start <= datetime.fromtimestamp(week["w"], tz=UTC).date() <= end
                and isinstance(week.get("c"), int)
                and week["c"] > 0
                for week in weeks
            ):
                active += 1
        return active

    @staticmethod
    def _release_dates(releases: list[dict[str, Any]]) -> list[datetime]:
        values = []
        for release in releases:
            published = release.get("published_at")
            if release.get("draft") or not isinstance(published, str):
                continue
            try:
                values.append(datetime.fromisoformat(published.replace("Z", "+00:00")))
            except ValueError:
                continue
        return values


@dataclass(frozen=True)
class SampleCandidate:
    repository: Repository
    sample_at: datetime
    age_cohort: str
    feature_7d: HistoricalActivityWindow
    feature_30d: HistoricalActivityWindow
    label_30d: HistoricalActivityWindow
    features: dict[str, Any]
    label_values: dict[str, float | int | None]


class DataLeakageError(ValueError):
    pass


class DataLeakageGuard:
    @staticmethod
    def validate(candidate: SampleCandidate) -> None:
        sample_date = candidate.sample_at.date()
        if candidate.feature_7d.window_end > sample_date:
            raise DataLeakageError("7d feature window contains future data")
        if candidate.feature_30d.window_end > sample_date:
            raise DataLeakageError("30d feature window contains future data")
        if candidate.label_30d.window_start <= sample_date:
            raise DataLeakageError("label window overlaps feature time")
        provenance = candidate.features.get("_provenance", {})
        for timestamp in provenance.get("feature_timestamps", []):
            if datetime.fromisoformat(timestamp) > candidate.sample_at:
                raise DataLeakageError("feature provenance contains future timestamp")
        if "repository_id" in candidate.features:
            raise DataLeakageError("repository_id must not be a model feature")


class DatasetBuilder:
    def __init__(
        self,
        *,
        minimum_cohort_size: int | None = None,
        label_version: str = LABEL_VERSION,
    ) -> None:
        self.minimum_cohort_size = (
            settings.DATASET_MIN_LABEL_COHORT_SIZE
            if minimum_cohort_size is None
            else minimum_cohort_size
        )
        if self.minimum_cohort_size < 2:
            raise ValueError("minimum_cohort_size must be at least 2")
        if label_version not in {
            LEGACY_LABEL_VERSION,
            LABEL_VERSION,
            PERCENTILE_LABEL_VERSION,
        }:
            raise ValueError("unsupported label version")
        self.label_version = label_version

    def build(
        self,
        sample_date: date,
        repositories: QuerySet[Repository] | None = None,
    ) -> dict[str, int]:
        if sample_date + timedelta(days=30) > timezone.now().astimezone(UTC).date():
            raise ValueError("label window must be fully in the past")
        repositories = repositories or Repository.objects.filter(is_disabled=False)
        candidates = [
            candidate
            for repository in repositories
            if (candidate := self._candidate(repository, sample_date)) is not None
        ]
        complete = [
            candidate
            for candidate in candidates
            if all(value is not None for value in candidate.label_values.values())
        ]
        cohort_counts = Counter(self._cohort_key(candidate) for candidate in complete)
        valid = [
            candidate
            for candidate in complete
            if cohort_counts[self._cohort_key(candidate)] >= self.minimum_cohort_size
        ]
        invalid_repository_ids = [
            candidate.repository.id for candidate in complete if candidate not in valid
        ]
        if invalid_repository_ids:
            TrainingSample.objects.filter(
                repository_id__in=invalid_repository_ids,
                sample_at=_sample_at(sample_date),
                feature_version=FEATURE_VERSION,
                label_version=self.label_version,
            ).delete()
        scores = self._label_scores(valid)
        created = 0
        updated = 0
        with transaction.atomic():
            for candidate in valid:
                DataLeakageGuard.validate(candidate)
                score = scores[candidate.repository.id]
                binary_label = int(score >= 80.0)
                _, was_created = TrainingSample.objects.update_or_create(
                    repository=candidate.repository,
                    sample_at=candidate.sample_at,
                    feature_version=FEATURE_VERSION,
                    label_version=self.label_version,
                    defaults={
                        "feature_window_start": candidate.feature_30d.window_start,
                        "feature_window_end": candidate.feature_30d.window_end,
                        "label_window_start": candidate.label_30d.window_start,
                        "label_window_end": candidate.label_30d.window_end,
                        "category": candidate.repository.category,
                        "age_cohort": candidate.age_cohort,
                        "features": candidate.features,
                        "label": binary_label,
                        "label_score": score,
                        "future_activity_percentile": (
                            score if self.label_version == PERCENTILE_LABEL_VERSION else None
                        ),
                        "binary_top20_label": (
                            binary_label if self.label_version == PERCENTILE_LABEL_VERSION else None
                        ),
                        "label_cohort_size": (
                            cohort_counts[self._cohort_key(candidate)]
                            if self.label_version == PERCENTILE_LABEL_VERSION
                            else None
                        ),
                        "data_origin": DataOrigin.BACKFILLED,
                        "label_evidence": {
                            "raw_signals": candidate.label_values,
                            "percentiles": self._candidate_percentiles(valid, candidate),
                            "cohort": self._cohort_evidence(candidate),
                            "threshold": 80.0,
                            "minimum_cohort_size": self.minimum_cohort_size,
                            "cohort_size": cohort_counts[self._cohort_key(candidate)],
                            "window_start": candidate.label_30d.window_start.isoformat(),
                            "window_end": candidate.label_30d.window_end.isoformat(),
                        },
                    },
                )
                created += int(was_created)
                updated += int(not was_created)
        return {
            "eligible": len(candidates),
            "skipped_incomplete_label": len(candidates) - len(complete),
            "skipped_small_cohort": len(complete) - len(valid),
            "created": created,
            "updated": updated,
        }

    def _candidate(self, repository: Repository, sample_date: date) -> SampleCandidate | None:
        feature_7d = self._window(repository, sample_date - timedelta(days=6), sample_date)
        feature_30d = self._window(repository, sample_date - timedelta(days=29), sample_date)
        label_30d = self._window(
            repository, sample_date + timedelta(days=1), sample_date + timedelta(days=30)
        )
        if not all((feature_7d, feature_30d, label_30d)):
            return None
        sample_at = _sample_at(sample_date)
        cohort = age_cohort(repository.github_created_at.astimezone(UTC).date(), sample_date)
        features = self._features(repository, sample_at, feature_7d, feature_30d)
        label_values = {
            "commit_activity": label_30d.commits,
            "pr_activity": self._sum_nullable(label_30d.prs_created, label_30d.prs_merged),
            "contributor_activity": label_30d.active_contributors,
            "release_activity": label_30d.releases,
            "issue_resolution_activity": label_30d.issues_closed,
        }
        return SampleCandidate(
            repository,
            sample_at,
            cohort,
            feature_7d,
            feature_30d,
            label_30d,
            features,
            label_values,
        )

    @staticmethod
    def _window(repository: Repository, start: date, end: date) -> HistoricalActivityWindow | None:
        return HistoricalActivityWindow.objects.filter(
            repository=repository,
            window_start=start,
            window_end=end,
            data_origin=DataOrigin.BACKFILLED,
        ).first()

    @staticmethod
    def _features(
        repository: Repository,
        sample_at: datetime,
        feature_7d: HistoricalActivityWindow,
        feature_30d: HistoricalActivityWindow,
    ) -> dict[str, Any]:
        snapshot = (
            RepositorySnapshot.objects.filter(repository=repository, snapshot_at__lte=sample_at)
            .order_by("-snapshot_at")
            .first()
        )
        trend = (
            RepositoryTrendScore.objects.filter(repository=repository, calculated_at__lte=sample_at)
            .order_by("-calculated_at")
            .first()
        )
        timestamps = [
            _sample_at(feature_7d.window_end).isoformat(),
            _sample_at(feature_30d.window_end).isoformat(),
        ]
        if snapshot:
            timestamps.append(snapshot.snapshot_at.isoformat())
        if trend:
            timestamps.append(trend.calculated_at.isoformat())
        return {
            "repo_age_days": max((sample_at.date() - repository.github_created_at.date()).days, 0),
            "category": repository.category,
            "current_stars": snapshot.stars if snapshot else None,
            "current_forks": snapshot.forks if snapshot else None,
            "commit_7d": feature_7d.commits,
            "commit_30d": feature_30d.commits,
            "pr_created_7d": feature_7d.prs_created,
            "pr_created_30d": feature_30d.prs_created,
            "pr_merged_30d": feature_30d.prs_merged,
            "issue_created_30d": feature_30d.issues_created,
            "issue_closed_30d": feature_30d.issues_closed,
            "active_contributors_30d": feature_30d.active_contributors,
            "release_count_30d": feature_30d.releases,
            "days_since_last_push": None,
            "days_since_last_release": feature_30d.days_since_last_release,
            "community_health": None,
            "topic_momentum": (
                float(trend.topic_momentum_score)
                if trend and trend.topic_momentum_score is not None
                else None
            ),
            "_provenance": {
                "data_origin": DataOrigin.BACKFILLED,
                "feature_timestamps": sorted(timestamps),
                "snapshot_origin": DataOrigin.OBSERVED if snapshot else None,
                "category_source": "current_classification",
                "historical_star_backfilled": False,
            },
        }

    @staticmethod
    def _sum_nullable(first: int | None, second: int | None) -> int | None:
        return None if first is None or second is None else first + second

    def _cohort_key(self, candidate: SampleCandidate) -> tuple[str, ...]:
        if self.label_version == LEGACY_LABEL_VERSION:
            return candidate.repository.category, candidate.age_cohort
        return (candidate.repository.category,)

    def _cohort_evidence(self, candidate: SampleCandidate) -> dict[str, str]:
        evidence = {
            "category": candidate.repository.category,
            "sample_at": candidate.sample_at.date().isoformat(),
            "label_version": self.label_version,
        }
        if self.label_version == LEGACY_LABEL_VERSION:
            evidence["age"] = candidate.age_cohort
        return evidence

    def _label_scores(self, candidates: list[SampleCandidate]) -> dict[int, float]:
        output: dict[int, float] = {}
        cohorts: dict[tuple[str, ...], list[SampleCandidate]] = defaultdict(list)
        for candidate in candidates:
            cohorts[self._cohort_key(candidate)].append(candidate)
        for cohort in cohorts.values():
            ranks = {
                signal: percentile_ranks(
                    {
                        candidate.repository.id: candidate.label_values[signal]
                        for candidate in cohort
                    }
                )
                for signal in LABEL_SIGNALS
            }
            for candidate in cohort:
                values = [ranks[signal][candidate.repository.id] for signal in LABEL_SIGNALS]
                output[candidate.repository.id] = round(
                    mean(float(value) for value in values if value is not None), 6
                )
        return output

    def _candidate_percentiles(
        self, candidates: list[SampleCandidate], target: SampleCandidate
    ) -> dict[str, float | None]:
        cohort = [item for item in candidates if self._cohort_key(item) == self._cohort_key(target)]
        return {
            signal: percentile_ranks(
                {item.repository.id: item.label_values[signal] for item in cohort}
            )[target.repository.id]
            for signal in LABEL_SIGNALS
        }


class DatasetQualityService:
    def report(self, queryset: QuerySet[TrainingSample] | None = None) -> dict[str, Any]:
        samples = list(TrainingSample.objects.all() if queryset is None else queryset)
        positives = sum(sample.label == 1 for sample in samples)
        total = len(samples)
        missing = Counter()
        for sample in samples:
            for feature in FEATURE_NAMES:
                if sample.features.get(feature) is None:
                    missing[feature] += 1
        dates = [sample.sample_at for sample in samples]
        return {
            "total_samples": total,
            "positive_samples": positives,
            "negative_samples": total - positives,
            "positive_ratio": round(positives / total, 6) if total else None,
            "negative_ratio": round((total - positives) / total, 6) if total else None,
            "category_distribution": dict(Counter(sample.category for sample in samples)),
            "age_cohort_distribution": dict(Counter(sample.age_cohort for sample in samples)),
            "sample_at_distribution": dict(
                sorted(Counter(sample.sample_at.date().isoformat() for sample in samples).items())
            ),
            "sample_time_range": {
                "start": min(dates).isoformat() if dates else None,
                "end": max(dates).isoformat() if dates else None,
            },
            "missing_features": {
                feature: {
                    "count": missing[feature],
                    "rate": round(missing[feature] / total, 6) if total else None,
                }
                for feature in FEATURE_NAMES
            },
            "feature_versions": dict(Counter(sample.feature_version for sample in samples)),
            "label_versions": dict(Counter(sample.label_version for sample in samples)),
        }
