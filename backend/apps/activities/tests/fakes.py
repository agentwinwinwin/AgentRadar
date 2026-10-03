from copy import deepcopy
from typing import Any

from apps.github.client import ContributorStatisticsResult, SearchCountResult


class FakeActivityGitHubClient:
    def __init__(self, *, incomplete: bool = False, stats_ready: bool = True) -> None:
        self.incomplete = incomplete
        self.stats_ready = stats_ready

    def _count(self, count: int) -> SearchCountResult:
        return SearchCountResult(
            count=None if self.incomplete else count,
            incomplete_results=self.incomplete,
            reported_total_count=count,
        )

    def count_commits(self, full_name: str, *, start: str, end: str) -> SearchCountResult:
        del full_name, start, end
        return self._count(11)

    def count_pull_requests(
        self, full_name: str, *, start: str, end: str, merged: bool = False
    ) -> SearchCountResult:
        del full_name, start, end
        return self._count(3 if merged else 5)

    def count_issues(
        self, full_name: str, *, start: str, end: str, closed: bool = False
    ) -> SearchCountResult:
        del full_name, start, end
        return self._count(7 if closed else 9)

    def get_contributor_statistics(self, full_name: str) -> ContributorStatisticsResult:
        del full_name
        if not self.stats_ready:
            return ContributorStatisticsResult(False, [], retry_after=17)
        return ContributorStatisticsResult(
            True,
            [{"author": {"id": 501}, "weeks": [{"w": 1786233600, "c": 2}]}],
        )

    def get_contributors(self, full_name: str) -> list[dict[str, Any]]:
        del full_name
        return [{"id": 501, "login": "dev", "avatar_url": None, "contributions": 12}]

    def get_releases(self, full_name: str) -> list[dict[str, Any]]:
        del full_name
        return [
            {
                "id": 701,
                "tag_name": "v1.0",
                "name": None,
                "author": {"login": "dev"},
                "draft": False,
                "prerelease": False,
                "created_at": "2026-08-10T00:00:00Z",
                "published_at": "2026-08-10T00:00:00Z",
                "body": "release",
            }
        ]

    def get_community_profile(self, full_name: str) -> dict[str, Any]:
        del full_name
        return {"health_percentage": 87}

    def get_repository(self, full_name: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected repository fetch: {full_name}")

    def search_repositories(self, *args, **kwargs):
        return deepcopy([])
