from datetime import UTC, date, datetime

import pytest

from apps.datasets.models import DataOrigin, HistoricalActivityWindow
from apps.datasets.services import HistoricalBackfillService
from apps.datasets.tests.fakes import FakeBackfillGitHubClient
from apps.github.fakes import FakeGitHubClient
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot


def create_repository(index: int = 1):
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            id=80_000 + index,
            full_name=f"dataset/project-{index}",
            name=f"project-{index}",
            created_at="2025-01-01T00:00:00Z",
        )
    )
    return repository


@pytest.mark.django_db
def test_backfill_writes_three_provenanced_windows_idempotently() -> None:
    repository = create_repository()
    service = HistoricalBackfillService(FakeBackfillGitHubClient())

    first = service.collect(repository, date(2026, 6, 1))
    second = service.collect(repository, date(2026, 6, 1))

    assert first.created == 3
    assert second.created == 0
    assert HistoricalActivityWindow.objects.filter(repository=repository).count() == 3
    assert all(item.data_origin == DataOrigin.BACKFILLED for item in first.windows)
    assert all(item.source_metadata["star_snapshot_backfilled"] is False for item in first.windows)
    assert RepositorySnapshot.objects.filter(repository=repository).count() == 0


@pytest.mark.django_db
def test_incomplete_search_is_null_but_real_zero_is_preserved() -> None:
    repository = create_repository()
    result = HistoricalBackfillService(FakeBackfillGitHubClient(incomplete_commits=True)).collect(
        repository, date(2026, 6, 1)
    )

    feature_7d = result.windows[0]
    assert feature_7d.commits is None
    assert feature_7d.releases == 0
    assert feature_7d.data_completeness < 1
    assert feature_7d.source_metadata["search_incomplete_fields"] == ["commits"]


@pytest.mark.django_db
def test_backfill_rejects_unfinished_label_window() -> None:
    repository = create_repository()
    with pytest.raises(ValueError, match="fully in the past"):
        HistoricalBackfillService(FakeBackfillGitHubClient()).collect(repository, date.today())


def test_contributor_window_without_weekly_coverage_is_null_not_zero() -> None:
    contributors = [
        {
            "weeks": [
                {"w": int(datetime(2026, 6, 1, tzinfo=UTC).timestamp()), "c": 0},
            ]
        }
    ]

    assert (
        HistoricalBackfillService._active_contributors(
            contributors, date(2026, 5, 1), date(2026, 5, 31)
        )
        is None
    )
