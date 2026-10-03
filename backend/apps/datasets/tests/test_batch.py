from datetime import date

import pytest
from django.conf import settings

from apps.activities.services import ContributorStatisticsPendingError
from apps.datasets.batch_services import (
    HistoricalBackfillBatchService,
    MeteredRateLimitedGitHubClient,
    sample_dates,
)
from apps.datasets.models import BackfillItemStatus, HistoricalBackfillBatchItem
from apps.datasets.services import DatasetBuilder, PreparedRepositoryHistory
from apps.datasets.tests.test_backfill import create_repository
from apps.github.client import GitHubClientError, GitHubResponse


def test_production_cohort_threshold_and_fourteen_day_dates() -> None:
    assert settings.DATASET_MIN_LABEL_COHORT_SIZE == 20
    assert DatasetBuilder().minimum_cohort_size == 20
    assert sample_dates(date(2026, 3, 1), date(2026, 3, 29), 14) == [
        date(2026, 3, 1),
        date(2026, 3, 15),
        date(2026, 3, 29),
    ]


@pytest.mark.django_db
def test_batch_checkpoint_creation_is_idempotent() -> None:
    repositories = [create_repository(1), create_repository(2)]
    dates = [date(2026, 3, 1), date(2026, 3, 15)]
    service = HistoricalBackfillBatchService()
    config = {"repository_ids": [item.id for item in repositories]}

    first = service.create_or_resume(
        name="batch-test", repositories=repositories, dates=dates, configuration=config
    )
    second = service.create_or_resume(
        name="batch-test", repositories=repositories, dates=dates, configuration=config
    )

    assert first.id == second.id
    assert HistoricalBackfillBatchItem.objects.count() == 4
    assert service.report(first)["pending"] == 4
    assert service.report(first)["running"] == 0


@pytest.mark.django_db
def test_interrupted_running_item_is_selected_for_resume(monkeypatch) -> None:
    repository = create_repository(1)
    service = HistoricalBackfillBatchService()
    batch = service.create_or_resume(
        name="interrupted-batch",
        repositories=[repository],
        dates=[date(2026, 3, 1)],
        configuration={"repository_ids": [repository.id]},
    )
    item = batch.items.get()
    item.status = BackfillItemStatus.RUNNING
    item.save(update_fields=("status",))

    monkeypatch.setattr(
        "apps.datasets.batch_services.HistoricalBackfillService.prepare",
        lambda _service, _repository: PreparedRepositoryHistory([], []),
    )
    monkeypatch.setattr(
        "apps.datasets.batch_services.HistoricalBackfillService.collect_prepared",
        lambda _service, _repository, _date, _prepared: type("Result", (), {"created": 0})(),
    )

    result = service.run(batch)

    assert result.processed_items == 1
    item.refresh_from_db()
    assert item.status == BackfillItemStatus.SUCCEEDED


def test_endpoint_request_classification() -> None:
    classify = MeteredRateLimitedGitHubClient._endpoint_name
    assert classify("/search/commits", {}) == "commit_search"
    assert classify("/search/issues", {"q": "type:pr"}) == "pr_search"
    assert classify("/search/issues", {"q": "type:issue"}) == "issue_search"
    assert classify("/repos/a/b/stats/contributors", {}) == "contributor_statistics"
    assert classify("/repos/a/b/releases", {}) == "releases"


def test_contributor_statistics_202_is_retried(monkeypatch) -> None:
    class PendingThenReady:
        calls = 0

        def prepare(self, repository):
            self.calls += 1
            if self.calls < 3:
                raise ContributorStatisticsPendingError(1)
            return PreparedRepositoryHistory([], [])

    service = PendingThenReady()
    client = MeteredRateLimitedGitHubClient(token="test-token")
    monkeypatch.setattr("apps.datasets.batch_services.time.sleep", lambda _seconds: None)

    result = HistoricalBackfillBatchService()._prepare_with_retry(service, object(), client)

    assert result == PreparedRepositoryHistory([], [])
    assert service.calls == 3
    assert client.rate_limit_waits == 2


def test_transient_transport_error_is_retried(monkeypatch) -> None:
    responses = iter(
        (
            GitHubClientError("transient TLS failure"),
            GitHubResponse(
                200,
                {"total_count": 1, "incomplete_results": False},
                {"x-ratelimit-resource": "search", "x-ratelimit-remaining": "29"},
            ),
        )
    )

    def request(_client, _path, *, params=None):
        del params
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr("apps.github.client.RealGitHubClient._request", request)
    monkeypatch.setattr("apps.datasets.batch_services.time.sleep", lambda _seconds: None)
    client = MeteredRateLimitedGitHubClient(token="test-token")

    response = client._request("/search/commits", params={"q": "repo:a/b"})

    assert response.status == 200
    assert client.transport_retries == 1
    assert client.request_counts["commit_search"] == 2
    assert client.rate_limit_state["search"]["remaining"] == 29
