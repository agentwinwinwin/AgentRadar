from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.activities.services import ContributorStatisticsPendingError
from apps.github.client import GitHubClientProtocol, SearchCountResult
from apps.repositories.models import Repository

from .models import (
    DataOrigin,
    HistoricalActivityBucket,
    HistoricalActivityWindow,
    HistoricalBucketKind,
    HistoricalContributorWeek,
    HistoricalSourceCache,
)

ACQUISITION_VERSION = "activity-bucket-v1.0.0"
SAMPLING_VERSION = "monthly-sampling-v1.0.0"


def sparse_sample_dates(start: date, end: date, interval_days: int = 30) -> list[date]:
    if interval_days != 30:
        raise ValueError("monthly sampling v1 requires an exact 30-day interval")
    if start > end:
        raise ValueError("invalid sample date range")
    values = []
    current = start
    while current <= end:
        values.append(current)
        current += timedelta(days=interval_days)
    return values


def estimate_requests(sample_count: int) -> dict[str, int | float]:
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    legacy_search = sample_count * 15
    bucket_search = (sample_count + 1) * 5 + sample_count * 2
    legacy_total = legacy_search + 2
    bucket_total = bucket_search + 2
    return {
        "samples_per_repository": sample_count,
        "legacy_requests_per_repository": legacy_total,
        "bucket_requests_per_repository": bucket_total,
        "legacy_requests_100_repositories": legacy_total * 100,
        "bucket_requests_100_repositories": bucket_total * 100,
        "estimated_reduction_percent": round((legacy_total - bucket_total) / legacy_total * 100, 2),
    }


def _count(result: SearchCountResult) -> int | None:
    return None if result.incomplete_results else result.count


@dataclass(frozen=True)
class MaterializationResult:
    buckets_created: int
    windows_created: int
    buckets_reused: int


class HistoricalBucketMaterializer:
    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client

    def materialize(
        self, repository: Repository, sample_dates: list[date]
    ) -> MaterializationResult:
        if not sample_dates:
            raise ValueError("sample_dates must not be empty")
        if any(
            sample_date + timedelta(days=30) > timezone.now().date() for sample_date in sample_dates
        ):
            raise ValueError("label windows must be fully in the past")
        cache = self._source_cache(repository)
        ranges: dict[tuple[date, date, str], None] = {}
        for sample_date in sample_dates:
            ranges[
                (
                    sample_date - timedelta(days=29),
                    sample_date,
                    HistoricalBucketKind.ACTIVITY_30D,
                )
            ] = None
            ranges[
                (
                    sample_date + timedelta(days=1),
                    sample_date + timedelta(days=30),
                    HistoricalBucketKind.ACTIVITY_30D,
                )
            ] = None
            ranges[
                (
                    sample_date - timedelta(days=6),
                    sample_date,
                    HistoricalBucketKind.FEATURE_TAIL_7D,
                )
            ] = None
        created = reused = windows_created = 0
        for start, end, kind in sorted(ranges):
            bucket = HistoricalActivityBucket.objects.filter(
                repository=repository,
                bucket_start=start,
                bucket_end=end,
                bucket_kind=kind,
                acquisition_version=ACQUISITION_VERSION,
            ).first()
            if bucket is None:
                bucket = self._collect_bucket(repository, start, end, kind, cache)
                created += 1
            else:
                reused += 1
            windows_created += int(self._materialize_window(bucket))
        return MaterializationResult(created, windows_created, reused)

    @transaction.atomic
    def _source_cache(self, repository: Repository) -> HistoricalSourceCache:
        cache = HistoricalSourceCache.objects.filter(
            repository=repository,
            acquisition_version=ACQUISITION_VERSION,
            contributor_stats_fetched_at__isnull=False,
            releases_fetched_at__isnull=False,
        ).first()
        if cache is not None:
            return cache
        stats = self.client.get_contributor_statistics(repository.full_name)
        if not stats.ready:
            raise ContributorStatisticsPendingError(stats.retry_after)
        releases = self.client.get_releases(repository.full_name)
        week_rows = []
        week_dates = []
        for index, contributor in enumerate(stats.contributors):
            author = contributor.get("author") or {}
            key = str(author.get("id") or author.get("login") or f"anonymous-{index}")
            for week in contributor.get("weeks", []):
                if not isinstance(week, dict) or not isinstance(week.get("w"), int):
                    continue
                week_start = datetime.fromtimestamp(week["w"], tz=UTC).date()
                week_dates.append(week_start)
                week_rows.append(
                    HistoricalContributorWeek(
                        repository=repository,
                        contributor_key=key,
                        week_start=week_start,
                        commits=max(int(week.get("c") or 0), 0),
                        additions=(
                            max(int(week["a"]), 0) if isinstance(week.get("a"), int) else None
                        ),
                        deletions=(
                            max(int(week["d"]), 0) if isinstance(week.get("d"), int) else None
                        ),
                        data_origin=DataOrigin.BACKFILLED,
                    )
                )
        HistoricalContributorWeek.objects.bulk_create(
            week_rows,
            update_conflicts=True,
            unique_fields=("repository", "contributor_key", "week_start"),
            update_fields=("commits", "additions", "deletions", "data_origin"),
        )
        release_dates = sorted(
            value.isoformat()
            for release in releases
            if (value := self._release_date(release)) is not None
        )
        cache, _ = HistoricalSourceCache.objects.update_or_create(
            repository=repository,
            defaults={
                "contributor_stats_fetched_at": timezone.now(),
                "contributor_week_start": min(week_dates) if week_dates else None,
                "contributor_week_end": max(week_dates) if week_dates else None,
                "contributor_stats_empty": not week_dates,
                "releases_fetched_at": timezone.now(),
                "release_dates": release_dates,
                "acquisition_version": ACQUISITION_VERSION,
            },
        )
        return cache

    def _collect_bucket(
        self,
        repository: Repository,
        start: date,
        end: date,
        kind: str,
        cache: HistoricalSourceCache,
    ) -> HistoricalActivityBucket:
        full_name = repository.full_name
        results = {
            "commits": self.client.count_commits(
                full_name, start=start.isoformat(), end=end.isoformat()
            ),
            "prs_created": self.client.count_pull_requests(
                full_name, start=start.isoformat(), end=end.isoformat()
            ),
        }
        if kind == HistoricalBucketKind.ACTIVITY_30D:
            results.update(
                {
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
            )
        values: dict[str, int | None] = {key: _count(value) for key, value in results.items()}
        release_dates = [datetime.fromisoformat(value).date() for value in cache.release_dates]
        if kind == HistoricalBucketKind.ACTIVITY_30D:
            values["active_contributors"] = self._active_contributors(repository, cache, start, end)
            values["releases"] = sum(start <= value <= end for value in release_dates)
            prior = [value for value in release_dates if value <= end]
            values["days_since_last_release"] = (end - max(prior)).days if prior else None
        expected_fields = (
            (
                "commits",
                "prs_created",
                "prs_merged",
                "issues_created",
                "issues_closed",
                "active_contributors",
                "releases",
            )
            if kind == HistoricalBucketKind.ACTIVITY_30D
            else ("commits", "prs_created")
        )
        completeness = sum(values.get(field) is not None for field in expected_fields) / len(
            expected_fields
        )
        return HistoricalActivityBucket.objects.create(
            repository=repository,
            bucket_start=start,
            bucket_end=end,
            bucket_kind=kind,
            acquisition_version=ACQUISITION_VERSION,
            data_completeness=round(completeness, 6),
            source_metadata={
                "source": "github_rest_api_materialized_bucket",
                "data_origin": DataOrigin.BACKFILLED,
                "acquisition_version": ACQUISITION_VERSION,
                "search_incomplete_fields": [
                    key for key, result in results.items() if result.incomplete_results
                ],
                "star_snapshot_backfilled": False,
            },
            **values,
        )

    @staticmethod
    def _active_contributors(
        repository: Repository, cache: HistoricalSourceCache, start: date, end: date
    ) -> int | None:
        if (
            cache.contributor_week_start is None
            or cache.contributor_week_end is None
            or start < cache.contributor_week_start
            or end > cache.contributor_week_end + timedelta(days=6)
        ):
            return None
        return (
            HistoricalContributorWeek.objects.filter(
                repository=repository,
                week_start__gte=start,
                week_start__lte=end,
                commits__gt=0,
            )
            .values("contributor_key")
            .distinct()
            .count()
        )

    @staticmethod
    def _materialize_window(bucket: HistoricalActivityBucket) -> bool:
        _, created = HistoricalActivityWindow.objects.update_or_create(
            repository=bucket.repository,
            window_start=bucket.bucket_start,
            window_end=bucket.bucket_end,
            data_origin=DataOrigin.BACKFILLED,
            defaults={
                "commits": bucket.commits,
                "prs_created": bucket.prs_created,
                "prs_merged": bucket.prs_merged,
                "issues_created": bucket.issues_created,
                "issues_closed": bucket.issues_closed,
                "active_contributors": bucket.active_contributors,
                "releases": bucket.releases,
                "days_since_last_release": bucket.days_since_last_release,
                "data_completeness": bucket.data_completeness,
                "source_metadata": {
                    **bucket.source_metadata,
                    "materialized_from_bucket_id": bucket.id,
                },
            },
        )
        return created

    @staticmethod
    def _release_date(release: dict[str, Any]) -> datetime | None:
        value = release.get("published_at")
        if release.get("draft") or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
