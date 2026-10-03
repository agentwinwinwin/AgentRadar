import io
import json
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from apps.github.client import GitHubClientError, GitHubRateLimitError, RealGitHubClient


class FakeResponse:
    def __init__(self, payload: dict | list, *, status: int = 200, headers=None) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_real_client_uses_versioned_github_endpoint() -> None:
    payload = {"id": 1, "full_name": "owner/repo"}
    with patch("apps.github.client.urlopen", return_value=FakeResponse(payload)) as request:
        result = RealGitHubClient(token="secret").get_repository("owner/repo")

    assert result == payload
    built_request = request.call_args.args[0]
    assert built_request.full_url == "https://api.github.com/repos/owner/repo"
    assert built_request.headers["Authorization"] == "Bearer secret"
    assert built_request.headers["X-github-api-version"] == "2022-11-28"


def test_search_validates_github_result_cap() -> None:
    with pytest.raises(ValueError, match="1,000 result cap"):
        RealGitHubClient(token="").search_repositories("topic:ai-agent", page=11)


def test_rate_limit_error_preserves_reset_time() -> None:
    error = HTTPError(
        "https://api.github.com/search/repositories",
        403,
        "Forbidden",
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "12345"},
        io.BytesIO(b"{}"),
    )
    with patch("apps.github.client.urlopen", side_effect=error):
        with pytest.raises(GitHubRateLimitError) as exc_info:
            RealGitHubClient(token="").search_repositories("topic:ai-agent")

    assert exc_info.value.reset_at == 12345


def test_rate_limit_uses_unified_client() -> None:
    payload = {"resources": {"core": {"remaining": 4999}, "search": {"remaining": 29}}}
    with patch("apps.github.client.urlopen", return_value=FakeResponse(payload)) as request:
        result = RealGitHubClient(token="secret").get_rate_limit()

    assert result == payload
    assert request.call_args.args[0].full_url == "https://api.github.com/rate_limit"


def test_commit_search_uses_verified_qualifiers_and_nulls_incomplete_count() -> None:
    payload = {"total_count": 42, "incomplete_results": True, "items": []}
    with patch("apps.github.client.urlopen", return_value=FakeResponse(payload)) as request:
        result = RealGitHubClient(token="secret").count_commits(
            "owner/repo", start="2026-08-01", end="2026-08-16"
        )

    assert result.count is None
    assert result.reported_total_count == 42
    assert result.incomplete_results is True
    assert "q=repo%3Aowner%2Frepo+committer-date%3A2026-08-01..2026-08-16" in (
        request.call_args.args[0].full_url
    )


def test_contributor_statistics_exposes_202_as_pending() -> None:
    response = FakeResponse({}, status=202, headers={"Retry-After": "30"})
    with patch("apps.github.client.urlopen", return_value=response):
        result = RealGitHubClient(token="secret").get_contributor_statistics("owner/repo")

    assert result.ready is False
    assert result.retry_after == 30
    assert result.contributors == []


def test_incomplete_http_response_is_wrapped_as_retryable_client_error() -> None:
    response = FakeResponse([])
    response.read = lambda: (_ for _ in ()).throw(IncompleteRead(b"partial", 10))

    with patch("apps.github.client.urlopen", return_value=response):
        with pytest.raises(GitHubClientError, match="request failed"):
            RealGitHubClient(token="secret").get_contributor_statistics("owner/repo")
