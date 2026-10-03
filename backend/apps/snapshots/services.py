from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.github.client import GitHubClientProtocol
from apps.repositories.models import Repository
from apps.repositories.services import RepositoryService

from .models import RepositorySnapshot


class InvalidSnapshotPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotResult:
    snapshot: RepositorySnapshot
    created: bool


def snapshot_bucket(snapshot_at: datetime, *, bucket_hours: int | None = None) -> str:
    hours = bucket_hours or settings.REPOSITORY_SNAPSHOT_BUCKET_HOURS
    if hours <= 0 or 24 % hours != 0:
        raise ValueError("bucket_hours must be a positive divisor of 24")
    if timezone.is_naive(snapshot_at):
        raise ValueError("snapshot_at must be timezone-aware")
    utc_value = snapshot_at.astimezone(UTC)
    bucket_hour = utc_value.hour - (utc_value.hour % hours)
    bucket_start = utc_value.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
    return bucket_start.strftime("%Y-%m-%dT%H")


class SnapshotService:
    COUNT_FIELDS = (
        "stargazers_count",
        "forks_count",
        "subscribers_count",
        "watchers_count",
        "open_issues_count",
    )
    SNAPSHOT_FIELDS = (
        "stargazers_count",
        "forks_count",
        "subscribers_count",
        "open_issues_count",
        "pushed_at",
    )

    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client
        self.repository_service = RepositoryService(client)

    def sync_and_snapshot(
        self,
        repository: Repository,
        *,
        observed_at: datetime | None = None,
        on_committed: Callable[[int], None] | None = None,
    ) -> SnapshotResult:
        payload = self.client.get_repository(repository.full_name)
        return self.persist_payload(
            payload,
            observed_at=observed_at,
            on_committed=on_committed,
        )

    @transaction.atomic
    def persist_payload(
        self,
        payload: dict[str, Any],
        *,
        observed_at: datetime | None = None,
        on_committed: Callable[[int], None] | None = None,
    ) -> SnapshotResult:
        observed_at = observed_at or timezone.now()
        if timezone.is_naive(observed_at):
            raise InvalidSnapshotPayloadError("observed_at must be timezone-aware")
        self._validate_snapshot_values(payload)
        repository, _ = self.repository_service.upsert_from_github(payload)
        pushed_at = self._parse_optional_timestamp(payload.get("pushed_at"))
        updated_at = self._parse_optional_timestamp(payload.get("updated_at"))
        values = {
            "snapshot_at": observed_at,
            "snapshot_date": observed_at.astimezone(UTC).date(),
            "stars": payload.get("stargazers_count"),
            "forks": payload.get("forks_count"),
            "subscribers": payload.get("subscribers_count"),
            "watchers": payload.get("watchers_count"),
            "open_issues": payload.get("open_issues_count"),
            "github_pushed_at": pushed_at,
            "github_updated_at": updated_at,
            "is_archived": bool(payload.get("archived", False)),
            "data_origin": "OBSERVED",
            "data_completeness": self._data_completeness(payload),
        }
        snapshot, created = RepositorySnapshot.objects.update_or_create(
            repository=repository,
            snapshot_bucket=snapshot_bucket(observed_at),
            defaults=values,
        )
        if on_committed is not None:
            transaction.on_commit(lambda: on_committed(snapshot.id))
        return SnapshotResult(snapshot=snapshot, created=created)

    @classmethod
    def _data_completeness(cls, payload: dict[str, Any]) -> float:
        present = sum(payload.get(field) is not None for field in cls.SNAPSHOT_FIELDS)
        return present / len(cls.SNAPSHOT_FIELDS)

    @staticmethod
    def _parse_optional_timestamp(value: Any):
        if value is None:
            return None
        if not isinstance(value, str) or (parsed := parse_datetime(value)) is None:
            raise InvalidSnapshotPayloadError("pushed_at must be an ISO-8601 timestamp or null")
        return parsed

    @classmethod
    def _validate_snapshot_values(cls, payload: dict[str, Any]) -> None:
        for field in cls.COUNT_FIELDS:
            value = payload.get(field)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise InvalidSnapshotPayloadError(f"{field} must be a non-negative integer or null")
