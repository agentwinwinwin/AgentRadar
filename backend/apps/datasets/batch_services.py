from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.utils import timezone

from apps.activities.services import ContributorStatisticsPendingError
from apps.github.client import (
    GitHubClientError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubResponse,
    RealGitHubClient,
)
from apps.repositories.models import Repository

from .models import (
    BackfillBatchStatus,
    BackfillItemStatus,
    HistoricalBackfillBatch,
    HistoricalBackfillBatchItem,
)
from .services import HistoricalBackfillService, PreparedRepositoryHistory


def sample_dates(start: date, end: date, interval_days: int) -> list[date]:
    if interval_days < 1 or start > end:
        raise ValueError("invalid sample date range")
    values = []
    current = start
    while current <= end:
        values.append(current)
        current += timedelta(days=interval_days)
    return values


class MeteredRateLimitedGitHubClient(RealGitHubClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.request_counts: Counter[str] = Counter()
        self.rate_limit_waits = 0
        self.transport_retries = 0
        self.rate_limit_state: dict[str, dict[str, int | None]] = {}

    def _request(self, path: str, *, params=None) -> GitHubResponse:
        endpoint = self._endpoint_name(path, params or {})
        self.request_counts[endpoint] += 1
        for attempt in range(3):
            try:
                response = super()._request(path, params=params)
                break
            except GitHubRateLimitError as exc:
                if attempt == 2:
                    raise
                self._wait_for_reset(exc.reset_at)
                self.request_counts[endpoint] += 1
            except GitHubNotFoundError:
                raise
            except GitHubClientError:
                if attempt == 2:
                    raise
                self.transport_retries += 1
                self.request_counts[endpoint] += 1
                time.sleep(2**attempt)
        remaining = self._header_int(response.headers, "x-ratelimit-remaining")
        reset_at = self._header_int(response.headers, "x-ratelimit-reset")
        resource = self._header_value(response.headers, "x-ratelimit-resource") or endpoint
        self.rate_limit_state[resource] = {"remaining": remaining, "reset": reset_at}
        if resource == "search" and remaining is not None and remaining <= 2:
            self._wait_for_reset(reset_at)
        elif remaining == 0:
            self._wait_for_reset(reset_at)
        return response

    def _wait_for_reset(self, reset_at: int | None) -> None:
        seconds = max((reset_at or int(time.time()) + 60) - int(time.time()) + 1, 1)
        self.rate_limit_waits += 1
        time.sleep(min(seconds, 120))

    @staticmethod
    def _header_int(headers: Any, name: str) -> int | None:
        for key, value in headers.items():
            if key.casefold() == name and str(value).isdigit():
                return int(value)
        return None

    @staticmethod
    def _header_value(headers: Any, name: str) -> str | None:
        for key, value in headers.items():
            if key.casefold() == name:
                return str(value)
        return None

    @staticmethod
    def _endpoint_name(path: str, params: dict[str, Any]) -> str:
        if path == "/search/commits":
            return "commit_search"
        if path == "/search/issues":
            query = str(params.get("q", ""))
            if "type:pr" in query:
                return "pr_search"
            return "issue_search"
        if path.endswith("/stats/contributors"):
            return "contributor_statistics"
        if "/releases" in path:
            return "releases"
        return "other"


@dataclass(frozen=True)
class BatchExecutionResult:
    batch: HistoricalBackfillBatch
    processed_items: int


class HistoricalBackfillBatchService:
    contributor_stats_max_attempts = 3

    def create_or_resume(
        self,
        *,
        name: str,
        repositories: list[Repository],
        dates: list[date],
        configuration: dict[str, Any],
    ) -> HistoricalBackfillBatch:
        batch, created = HistoricalBackfillBatch.objects.get_or_create(
            name=name,
            defaults={"configuration": configuration},
        )
        if not created and batch.configuration != configuration:
            raise ValueError("existing batch configuration does not match")
        HistoricalBackfillBatchItem.objects.bulk_create(
            [
                HistoricalBackfillBatchItem(
                    batch=batch, repository=repository, sample_date=sample_date
                )
                for repository in repositories
                for sample_date in dates
            ],
            ignore_conflicts=True,
        )
        return batch

    def run(
        self,
        batch: HistoricalBackfillBatch,
        *,
        max_items: int | None = None,
        max_attempts: int = 3,
    ) -> BatchExecutionResult:
        client = MeteredRateLimitedGitHubClient(timeout=45)
        service = HistoricalBackfillService(client)
        batch.status = BackfillBatchStatus.RUNNING
        batch.started_at = batch.started_at or timezone.now()
        batch.save(update_fields=("status", "started_at", "updated_at"))
        items = list(
            batch.items.filter(
                status__in=(
                    BackfillItemStatus.PENDING,
                    BackfillItemStatus.FAILED,
                    BackfillItemStatus.RUNNING,
                ),
                attempts__lt=max_attempts,
            )
            .select_related("repository")
            .order_by("repository_id", "sample_date")
        )
        if max_items is not None:
            items = items[:max_items]
        processed = 0
        grouped: dict[int, list[HistoricalBackfillBatchItem]] = {}
        for item in items:
            grouped.setdefault(item.repository_id, []).append(item)
        for repository_items in grouped.values():
            repository = repository_items[0].repository
            prepared = None
            for item in repository_items:
                before = Counter(client.request_counts)
                item.status = BackfillItemStatus.RUNNING
                item.attempts += 1
                item.started_at = timezone.now()
                item.save(update_fields=("status", "attempts", "started_at", "updated_at"))
                try:
                    result = service.existing_result(repository, item.sample_date)
                    if result is None:
                        if prepared is None:
                            prepared = self._prepare_with_retry(service, repository, client)
                        result = service.collect_prepared(repository, item.sample_date, prepared)
                except (ContributorStatisticsPendingError, GitHubClientError) as exc:
                    item.status = BackfillItemStatus.FAILED
                    item.last_error = str(exc)[:500]
                    batch.retry_count += 1
                else:
                    item.status = BackfillItemStatus.SUCCEEDED
                    item.windows_created = result.created
                    item.last_error = ""
                item.finished_at = timezone.now()
                item.endpoint_request_counts = dict(Counter(client.request_counts) - before)
                item.save(
                    update_fields=(
                        "status",
                        "attempts",
                        "windows_created",
                        "last_error",
                        "finished_at",
                        "endpoint_request_counts",
                        "updated_at",
                    )
                )
                processed += 1
                if item.status == BackfillItemStatus.FAILED and prepared is None:
                    break
        batch.retry_count += client.rate_limit_waits + client.transport_retries
        batch.endpoint_request_counts = dict(client.request_counts)
        batch.rate_limit_state = client.rate_limit_state
        pending = batch.items.exclude(status=BackfillItemStatus.SUCCEEDED).exists()
        batch.status = BackfillBatchStatus.PARTIAL if pending else BackfillBatchStatus.COMPLETED
        batch.finished_at = timezone.now() if not pending else None
        batch.save(
            update_fields=(
                "status",
                "endpoint_request_counts",
                "rate_limit_state",
                "retry_count",
                "finished_at",
                "updated_at",
            )
        )
        return BatchExecutionResult(batch, processed)

    def _prepare_with_retry(
        self,
        service: HistoricalBackfillService,
        repository: Repository,
        client: MeteredRateLimitedGitHubClient,
    ) -> PreparedRepositoryHistory:
        for attempt in range(1, self.contributor_stats_max_attempts + 1):
            try:
                return service.prepare(repository)
            except ContributorStatisticsPendingError as exc:
                if attempt == self.contributor_stats_max_attempts:
                    raise
                client.rate_limit_waits += 1
                retry_after = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 5
                time.sleep(min(max(retry_after, 1), 60))
        raise AssertionError("unreachable")

    @staticmethod
    def report(batch: HistoricalBackfillBatch) -> dict[str, Any]:
        statuses = Counter(batch.items.values_list("status", flat=True))
        repositories = batch.items.values("repository_id").distinct().count()
        successful_repositories = sum(
            not batch.items.filter(repository_id=repository_id)
            .exclude(status=BackfillItemStatus.SUCCEEDED)
            .exists()
            for repository_id in batch.items.values_list("repository_id", flat=True).distinct()
        )
        failed_repositories = (
            batch.items.filter(status=BackfillItemStatus.FAILED)
            .values("repository_id")
            .distinct()
            .count()
        )
        counts = Counter()
        for value in batch.items.values_list("endpoint_request_counts", flat=True):
            counts.update(value)
        return {
            "batch": batch.name,
            "status": batch.status,
            "repositories": repositories,
            "successful_repositories": successful_repositories,
            "failed_repositories": failed_repositories,
            "items": batch.items.count(),
            "succeeded": statuses[BackfillItemStatus.SUCCEEDED],
            "failed": statuses[BackfillItemStatus.FAILED],
            "pending": statuses[BackfillItemStatus.PENDING],
            "running": statuses[BackfillItemStatus.RUNNING],
            "retry_count": batch.retry_count,
            "endpoint_request_counts": dict(counts),
            "rate_limit_state": batch.rate_limit_state,
        }
