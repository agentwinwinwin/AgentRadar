from datetime import UTC, datetime

from apps.github.client import ContributorStatisticsResult, SearchCountResult


class FakeBackfillGitHubClient:
    def __init__(self, *, incomplete_commits: bool = False) -> None:
        self.incomplete_commits = incomplete_commits

    @staticmethod
    def _complete(value: int) -> SearchCountResult:
        return SearchCountResult(value, False, value)

    def count_commits(self, full_name: str, *, start: str, end: str) -> SearchCountResult:
        del full_name, start, end
        if self.incomplete_commits:
            return SearchCountResult(None, True, 99)
        return self._complete(12)

    def count_pull_requests(
        self, full_name: str, *, start: str, end: str, merged: bool = False
    ) -> SearchCountResult:
        del full_name, start, end
        return self._complete(3 if merged else 5)

    def count_issues(
        self, full_name: str, *, start: str, end: str, closed: bool = False
    ) -> SearchCountResult:
        del full_name, start, end
        return self._complete(4 if closed else 6)

    def get_contributor_statistics(self, full_name: str) -> ContributorStatisticsResult:
        del full_name
        weeks = [
            {"w": int(datetime(2026, 5, 10, tzinfo=UTC).timestamp()), "c": 1},
            {"w": int(datetime(2026, 6, 10, tzinfo=UTC).timestamp()), "c": 2},
        ]
        return ContributorStatisticsResult(True, [{"weeks": weeks}])

    def get_releases(self, full_name: str):
        del full_name
        return [
            {"draft": False, "published_at": "2026-05-20T00:00:00Z"},
            {"draft": False, "published_at": "2026-06-15T00:00:00Z"},
        ]
