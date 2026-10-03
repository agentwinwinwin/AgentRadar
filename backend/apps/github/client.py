import json
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class GitHubClientError(RuntimeError):
    """Base error raised for GitHub API failures."""


class GitHubNotFoundError(GitHubClientError):
    pass


class GitHubRateLimitError(GitHubClientError):
    def __init__(self, message: str, *, reset_at: int | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


@dataclass(frozen=True)
class RepositorySearchResult:
    total_count: int
    incomplete_results: bool
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class SearchCountResult:
    count: int | None
    incomplete_results: bool
    reported_total_count: int


@dataclass(frozen=True)
class ContributorStatisticsResult:
    ready: bool
    contributors: list[dict[str, Any]]
    retry_after: int | None = None


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    payload: Any
    headers: Mapping[str, str]


class GitHubClientProtocol(Protocol):
    def get_repository(self, full_name: str) -> dict[str, Any]: ...

    def search_repositories(
        self,
        query: str,
        *,
        sort: str | None = None,
        order: str = "desc",
        per_page: int = 100,
        page: int = 1,
    ) -> RepositorySearchResult: ...

    def count_commits(self, full_name: str, *, start: str, end: str) -> SearchCountResult: ...

    def count_pull_requests(
        self, full_name: str, *, start: str, end: str, merged: bool = False
    ) -> SearchCountResult: ...

    def count_issues(
        self, full_name: str, *, start: str, end: str, closed: bool = False
    ) -> SearchCountResult: ...

    def get_contributors(self, full_name: str) -> list[dict[str, Any]]: ...

    def get_contributor_statistics(self, full_name: str) -> ContributorStatisticsResult: ...

    def get_releases(self, full_name: str) -> list[dict[str, Any]]: ...

    def get_community_profile(self, full_name: str) -> dict[str, Any]: ...

    def get_rate_limit(self) -> dict[str, Any]: ...

    def get_readme(self, full_name: str) -> dict[str, Any]: ...

    def get_contents(
        self, full_name: str, path: str = ""
    ) -> dict[str, Any] | list[dict[str, Any]]: ...

    def search_issues(self, query: str, *, per_page: int = 20) -> RepositorySearchResult: ...

    def get_recent_releases(self, full_name: str, *, limit: int = 5) -> list[dict[str, Any]]: ...


class RealGitHubClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.token = settings.GITHUB_TOKEN if token is None else token
        self.base_url = (base_url or settings.GITHUB_API_URL).rstrip("/")
        self.timeout = timeout
        self.request_count = 0
        self.search_request_count = 0

    def get_repository(self, full_name: str) -> dict[str, Any]:
        owner, name = self._parse_full_name(full_name)
        payload = self._get(f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}")
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub repository response must be an object")
        return payload

    def search_repositories(
        self,
        query: str,
        *,
        sort: str | None = None,
        order: str = "desc",
        per_page: int = 100,
        page: int = 1,
    ) -> RepositorySearchResult:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        if page < 1 or page > 10:
            raise ValueError("page must be between 1 and 10 due to GitHub's 1,000 result cap")

        params: dict[str, str | int] = {
            "q": query,
            "order": order,
            "per_page": per_page,
            "page": page,
        }
        if sort:
            params["sort"] = sort
        payload = self._get("/search/repositories", params=params)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise GitHubClientError("GitHub repository search response is malformed")
        return RepositorySearchResult(
            total_count=int(payload.get("total_count", 0)),
            incomplete_results=bool(payload.get("incomplete_results", False)),
            items=payload["items"],
        )

    def count_commits(self, full_name: str, *, start: str, end: str) -> SearchCountResult:
        return self._search_count(
            "/search/commits", f"repo:{full_name} committer-date:{start}..{end}"
        )

    def count_pull_requests(
        self, full_name: str, *, start: str, end: str, merged: bool = False
    ) -> SearchCountResult:
        date_qualifier = "merged" if merged else "created"
        state = " is:merged" if merged else ""
        return self._search_count(
            "/search/issues",
            f"repo:{full_name} type:pr{state} {date_qualifier}:{start}..{end}",
        )

    def count_issues(
        self, full_name: str, *, start: str, end: str, closed: bool = False
    ) -> SearchCountResult:
        date_qualifier = "closed" if closed else "created"
        state = " is:closed" if closed else ""
        return self._search_count(
            "/search/issues",
            f"repo:{full_name} type:issue{state} {date_qualifier}:{start}..{end}",
        )

    def get_contributors(self, full_name: str) -> list[dict[str, Any]]:
        return self._get_paginated(full_name, "contributors")

    def get_releases(self, full_name: str) -> list[dict[str, Any]]:
        return self._get_paginated(full_name, "releases")

    def get_contributor_statistics(self, full_name: str) -> ContributorStatisticsResult:
        owner, name = self._parse_full_name(full_name)
        response = self._request(
            f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/stats/contributors"
        )
        if response.status == 202:
            retry_after = response.headers.get("Retry-After")
            return ContributorStatisticsResult(
                ready=False,
                contributors=[],
                retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        if not isinstance(response.payload, list):
            raise GitHubClientError("GitHub contributor statistics response is malformed")
        return ContributorStatisticsResult(ready=True, contributors=response.payload)

    def get_community_profile(self, full_name: str) -> dict[str, Any]:
        owner, name = self._parse_full_name(full_name)
        payload = self._get(
            f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/community/profile"
        )
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub community profile response is malformed")
        return payload

    def get_rate_limit(self) -> dict[str, Any]:
        payload = self._get("/rate_limit")
        if not isinstance(payload, dict) or not isinstance(payload.get("resources"), dict):
            raise GitHubClientError("GitHub rate limit response is malformed")
        return payload

    def get_readme(self, full_name: str) -> dict[str, Any]:
        owner, name = self._parse_full_name(full_name)
        payload = self._get(f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/readme")
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub README response is malformed")
        return payload

    def get_contents(self, full_name: str, path: str = "") -> dict[str, Any] | list[dict[str, Any]]:
        owner, name = self._parse_full_name(full_name)
        suffix = f"/{quote(path.strip('/'), safe='/')}" if path.strip("/") else ""
        payload = self._get(
            f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/contents{suffix}"
        )
        if not isinstance(payload, dict | list):
            raise GitHubClientError("GitHub contents response is malformed")
        return payload

    def search_issues(self, query: str, *, per_page: int = 20) -> RepositorySearchResult:
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        payload = self._get("/search/issues", params={"q": query, "per_page": per_page, "page": 1})
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise GitHubClientError("GitHub issue search response is malformed")
        return RepositorySearchResult(
            total_count=int(payload.get("total_count", 0)),
            incomplete_results=bool(payload.get("incomplete_results", False)),
            items=payload["items"],
        )

    def get_recent_releases(self, full_name: str, *, limit: int = 5) -> list[dict[str, Any]]:
        owner, name = self._parse_full_name(full_name)
        payload = self._get(
            f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/releases",
            params={"per_page": min(max(limit, 1), 100), "page": 1},
        )
        if not isinstance(payload, list):
            raise GitHubClientError("GitHub releases response is malformed")
        return [item for item in payload if isinstance(item, dict) and not item.get("draft")][
            :limit
        ]

    def _search_count(self, path: str, query: str) -> SearchCountResult:
        payload = self._get(path, params={"q": query, "per_page": 1})
        if not isinstance(payload, dict) or "total_count" not in payload:
            raise GitHubClientError("GitHub search count response is malformed")
        total = int(payload["total_count"])
        incomplete = bool(payload.get("incomplete_results", False))
        return SearchCountResult(
            count=None if incomplete else total,
            incomplete_results=incomplete,
            reported_total_count=total,
        )

    def _get_paginated(self, full_name: str, resource: str) -> list[dict[str, Any]]:
        owner, name = self._parse_full_name(full_name)
        items: list[dict[str, Any]] = []
        for page in range(1, 11):
            payload = self._get(
                f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/{resource}",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                raise GitHubClientError(f"GitHub {resource} response is malformed")
            items.extend(payload)
            if len(payload) < 100:
                break
        return items

    @staticmethod
    def _parse_full_name(full_name: str) -> tuple[str, str]:
        parts = full_name.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("full_name must use the owner/repository format")
        return parts[0], parts[1]

    def _get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> Any:
        return self._request(path, params=params).payload

    def _request(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> GitHubResponse:
        self.request_count += 1
        if path.startswith("/search/"):
            self.search_request_count += 1
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "agentGitHub/1.0",
            "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
                payload = json.loads(body) if body else None
                status = getattr(response, "status", 200)
                headers = getattr(response, "headers", {})
                return GitHubResponse(status, payload, dict(headers.items()))
        except HTTPError as exc:
            self._raise_http_error(exc)
        except (URLError, TimeoutError, HTTPException) as exc:
            raise GitHubClientError(f"GitHub request failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubClientError("GitHub returned an invalid JSON response") from exc

    @staticmethod
    def _raise_http_error(exc: HTTPError) -> None:
        if exc.code == 404:
            raise GitHubNotFoundError("GitHub repository was not found") from exc
        remaining = exc.headers.get("X-RateLimit-Remaining")
        if exc.code in {403, 429} and (remaining == "0" or exc.code == 429):
            reset = exc.headers.get("X-RateLimit-Reset")
            raise GitHubRateLimitError(
                "GitHub rate limit exceeded",
                reset_at=int(reset) if reset and reset.isdigit() else None,
            ) from exc
        raise GitHubClientError(f"GitHub request failed with HTTP {exc.code}") from exc
