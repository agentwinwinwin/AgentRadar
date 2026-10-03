from copy import deepcopy
from typing import Any

from .client import GitHubNotFoundError, RepositorySearchResult


class FakeGitHubClient:
    def __init__(self, repositories: list[dict[str, Any]] | None = None) -> None:
        self.repositories = {
            item["full_name"].casefold(): deepcopy(item) for item in (repositories or [])
        }
        self.search_calls: list[str] = []
        self.get_calls: list[str] = []

    def get_repository(self, full_name: str) -> dict[str, Any]:
        self.get_calls.append(full_name)
        try:
            return deepcopy(self.repositories[full_name.casefold()])
        except KeyError as exc:
            raise GitHubNotFoundError("GitHub repository was not found") from exc

    def search_repositories(
        self,
        query: str,
        *,
        sort: str | None = None,
        order: str = "desc",
        per_page: int = 100,
        page: int = 1,
    ) -> RepositorySearchResult:
        del sort, order
        self.search_calls.append(query)
        items = list(self.repositories.values())
        start = (page - 1) * per_page
        return RepositorySearchResult(
            total_count=len(items),
            incomplete_results=False,
            items=deepcopy(items[start : start + per_page]),
        )
