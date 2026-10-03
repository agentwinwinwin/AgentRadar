from datetime import UTC, date, datetime, timedelta

import pytest

from apps.datasets.bucket_services import (
    ACQUISITION_VERSION,
    HistoricalBucketMaterializer,
    estimate_requests,
    sparse_sample_dates,
)
from apps.datasets.models import (
    HistoricalActivityBucket,
    HistoricalActivityWindow,
    HistoricalContributorWeek,
    HistoricalSourceCache,
)
from apps.datasets.tests.fakes import FakeBackfillGitHubClient
from apps.github.client import ContributorStatisticsResult
from apps.snapshots.models import RepositorySnapshot

from .test_backfill import create_repository


class CountingBucketClient(FakeBackfillGitHubClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = {
            "commits": 0,
            "prs": 0,
            "issues": 0,
            "contributor_statistics": 0,
            "releases": 0,
        }

    def count_commits(self, full_name: str, *, start: str, end: str):
        self.calls["commits"] += 1
        return super().count_commits(full_name, start=start, end=end)

    def count_pull_requests(self, full_name: str, *, start: str, end: str, merged=False):
        self.calls["prs"] += 1
        return super().count_pull_requests(full_name, start=start, end=end, merged=merged)

    def count_issues(self, full_name: str, *, start: str, end: str, closed=False):
        self.calls["issues"] += 1
        return super().count_issues(full_name, start=start, end=end, closed=closed)

    def get_contributor_statistics(self, full_name: str):
        del full_name
        self.calls["contributor_statistics"] += 1
        weeks = []
        current = date(2026, 3, 1)
        while current <= date(2026, 7, 31):
            weeks.append(
                {
                    "w": int(
                        datetime.combine(current, datetime.min.time(), tzinfo=UTC).timestamp()
                    ),
                    "c": 1,
                }
            )
            current += timedelta(days=7)
        return ContributorStatisticsResult(True, [{"author": {"id": 1}, "weeks": weeks}])

    def get_releases(self, full_name: str):
        self.calls["releases"] += 1
        return super().get_releases(full_name)


def test_monthly_sampling_and_request_estimate() -> None:
    dates = sparse_sample_dates(date(2025, 9, 30), date(2026, 6, 27))

    assert len(dates) == 10
    assert all((right - left).days == 30 for left, right in zip(dates, dates[1:], strict=False))
    assert estimate_requests(10) == {
        "samples_per_repository": 10,
        "legacy_requests_per_repository": 152,
        "bucket_requests_per_repository": 77,
        "legacy_requests_100_repositories": 15_200,
        "bucket_requests_100_repositories": 7_700,
        "estimated_reduction_percent": 49.34,
    }


@pytest.mark.django_db
def test_materialized_buckets_are_reused_without_new_api_calls() -> None:
    repository = create_repository()
    client = CountingBucketClient()
    materializer = HistoricalBucketMaterializer(client)
    dates = sparse_sample_dates(date(2026, 4, 1), date(2026, 5, 31))

    first = materializer.materialize(repository, dates)
    calls_after_first = dict(client.calls)
    second = materializer.materialize(repository, dates)

    assert first.buckets_created == 7
    assert first.windows_created == 7
    assert second.buckets_created == 0
    assert second.buckets_reused == 7
    assert client.calls == calls_after_first
    assert sum(calls_after_first.values()) == 28
    assert HistoricalActivityBucket.objects.count() == 7
    assert HistoricalActivityWindow.objects.count() == 7
    assert HistoricalContributorWeek.objects.exists()
    assert HistoricalSourceCache.objects.get().acquisition_version == ACQUISITION_VERSION
    assert RepositorySnapshot.objects.count() == 0
