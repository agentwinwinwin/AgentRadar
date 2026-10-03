from datetime import UTC, datetime

import pytest
from django.db import IntegrityError

from apps.github.fakes import FakeGitHubClient
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot
from apps.snapshots.services import (
    InvalidSnapshotPayloadError,
    SnapshotService,
    snapshot_bucket,
)

OBSERVED_AT = datetime(2026, 8, 16, 11, 45, tzinfo=UTC)


def test_snapshot_bucket_uses_six_hour_utc_window() -> None:
    assert snapshot_bucket(OBSERVED_AT) == "2026-08-16T06"


@pytest.mark.django_db(transaction=True)
def test_repeating_same_snapshot_ten_times_upserts_one_row() -> None:
    payload = github_repository_payload()
    service = SnapshotService(FakeGitHubClient())

    results = [service.persist_payload(payload, observed_at=OBSERVED_AT) for _ in range(10)]

    assert results[0].created is True
    assert all(result.created is False for result in results[1:])
    assert RepositorySnapshot.objects.count() == 1
    assert RepositorySnapshot.objects.get().snapshot_bucket == "2026-08-16T06"


@pytest.mark.django_db(transaction=True)
def test_null_snapshot_values_remain_null_not_zero() -> None:
    payload = github_repository_payload(
        stargazers_count=None,
        forks_count=None,
        subscribers_count=None,
        open_issues_count=None,
        pushed_at=None,
    )

    result = SnapshotService(FakeGitHubClient()).persist_payload(
        payload,
        observed_at=OBSERVED_AT,
    )

    result.snapshot.refresh_from_db()
    assert result.snapshot.stars is None
    assert result.snapshot.forks is None
    assert result.snapshot.subscribers is None
    assert result.snapshot.open_issues is None
    assert result.snapshot.github_pushed_at is None
    assert result.snapshot.data_completeness == 0.0
    assert result.snapshot.repository.stars is None


@pytest.mark.django_db(transaction=True)
def test_follow_up_callback_runs_only_after_successful_commit() -> None:
    committed: list[int] = []

    result = SnapshotService(FakeGitHubClient()).persist_payload(
        github_repository_payload(),
        observed_at=OBSERVED_AT,
        on_committed=committed.append,
    )

    assert committed == [result.snapshot.id]

    with pytest.raises(InvalidSnapshotPayloadError):
        SnapshotService(FakeGitHubClient()).persist_payload(
            github_repository_payload(stargazers_count=-1),
            observed_at=OBSERVED_AT,
            on_committed=committed.append,
        )
    assert committed == [result.snapshot.id]


@pytest.mark.django_db(transaction=True)
def test_database_constraint_is_second_duplicate_defense() -> None:
    snapshot = (
        SnapshotService(FakeGitHubClient())
        .persist_payload(
            github_repository_payload(),
            observed_at=OBSERVED_AT,
        )
        .snapshot
    )

    with pytest.raises(IntegrityError):
        RepositorySnapshot.objects.create(
            repository=snapshot.repository,
            snapshot_at=OBSERVED_AT,
            snapshot_date=OBSERVED_AT.date(),
            snapshot_bucket=snapshot.snapshot_bucket,
            data_completeness=1.0,
        )
