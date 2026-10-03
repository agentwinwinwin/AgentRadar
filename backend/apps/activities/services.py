import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.github.client import GitHubClientProtocol, SearchCountResult
from apps.repositories.models import Repository

from .models import Contributor, RepositoryActivityMetric, RepositoryContributor, RepositoryRelease


class ContributorStatisticsPendingError(RuntimeError):
    def __init__(self, retry_after: int | None = None) -> None:
        super().__init__("GitHub contributor statistics are still being generated")
        self.retry_after = retry_after


@dataclass(frozen=True)
class ActivityCollectionResult:
    metric: RepositoryActivityMetric
    created: bool


def _window(metric_date: date, days: int) -> tuple[str, str]:
    return ((metric_date - timedelta(days=days - 1)).isoformat(), metric_date.isoformat())


def _count(result: SearchCountResult) -> int | None:
    return None if result.incomplete_results else result.count


class ActivityService:
    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client

    def collect(
        self, repository: Repository, *, metric_date: date | None = None
    ) -> ActivityCollectionResult:
        metric_date = metric_date or timezone.now().astimezone(UTC).date()
        full_name = repository.full_name

        contributor_stats = self.client.get_contributor_statistics(full_name)
        if not contributor_stats.ready:
            raise ContributorStatisticsPendingError(contributor_stats.retry_after)

        windows = {days: _window(metric_date, days) for days in (7, 30, 90)}
        values: dict[str, int | None] = {
            "commits_7d": _count(
                self.client.count_commits(full_name, start=windows[7][0], end=windows[7][1])
            ),
            "commits_30d": _count(
                self.client.count_commits(full_name, start=windows[30][0], end=windows[30][1])
            ),
            "commits_90d": _count(
                self.client.count_commits(full_name, start=windows[90][0], end=windows[90][1])
            ),
        }
        for days in (7, 30):
            start, end = windows[days]
            values[f"prs_created_{days}d"] = _count(
                self.client.count_pull_requests(full_name, start=start, end=end)
            )
            values[f"prs_merged_{days}d"] = _count(
                self.client.count_pull_requests(full_name, start=start, end=end, merged=True)
            )
            values[f"issues_created_{days}d"] = _count(
                self.client.count_issues(full_name, start=start, end=end)
            )
            values[f"issues_closed_{days}d"] = _count(
                self.client.count_issues(full_name, start=start, end=end, closed=True)
            )

        contributors = self.client.get_contributors(full_name)
        releases = self.client.get_releases(full_name)
        community = self.client.get_community_profile(full_name)
        values["active_contributors_30d"] = self._active_contributors(
            contributor_stats.contributors, metric_date
        )
        release_dates = [
            parsed
            for release in releases
            if not release.get("draft")
            and (parsed := self._timestamp(release.get("published_at"))) is not None
        ]
        values["releases_30d"] = self._recent_count(release_dates, metric_date, 30)
        values["releases_90d"] = self._recent_count(release_dates, metric_date, 90)
        values["days_since_last_push"] = self._days_since(repository.github_pushed_at, metric_date)
        values["days_since_last_release"] = self._days_since(
            max(release_dates, default=None), metric_date
        )

        return self._persist(
            repository,
            metric_date,
            values,
            contributors=contributors,
            releases=releases,
            community=community,
        )

    @transaction.atomic
    def _persist(
        self,
        repository: Repository,
        metric_date: date,
        values: dict[str, int | None],
        *,
        contributors: list[dict[str, Any]],
        releases: list[dict[str, Any]],
        community: dict[str, Any],
    ) -> ActivityCollectionResult:
        observed_at = timezone.now()
        for payload in contributors:
            github_user_id = payload.get("id")
            login = payload.get("login")
            if not isinstance(github_user_id, int) or not isinstance(login, str):
                continue
            contributor, _ = Contributor.objects.update_or_create(
                github_user_id=github_user_id,
                defaults={"login": login, "avatar_url": payload.get("avatar_url")},
            )
            total = payload.get("contributions")
            RepositoryContributor.objects.update_or_create(
                repository=repository,
                contributor=contributor,
                defaults={
                    "contributions_total": total if isinstance(total, int) and total >= 0 else None,
                    "last_observed_at": observed_at,
                },
            )
        for payload in releases:
            self._upsert_release(repository, payload)

        health = community.get("health_percentage")
        repository.community_health = (
            health if isinstance(health, int) and 0 <= health <= 100 else None
        )
        repository.save(update_fields=("community_health", "updated_at"))
        metric, created = RepositoryActivityMetric.objects.update_or_create(
            repository=repository,
            metric_date=metric_date,
            defaults=values,
        )
        return ActivityCollectionResult(metric=metric, created=created)

    @classmethod
    def _upsert_release(cls, repository: Repository, payload: dict[str, Any]) -> None:
        release_id = payload.get("id")
        tag_name = payload.get("tag_name")
        if not isinstance(release_id, int) or not isinstance(tag_name, str):
            return
        body = payload.get("body") if isinstance(payload.get("body"), str) else None
        author = payload.get("author")
        RepositoryRelease.objects.update_or_create(
            github_release_id=release_id,
            defaults={
                "repository": repository,
                "tag_name": tag_name,
                "name": payload.get("name") if isinstance(payload.get("name"), str) else None,
                "author_login": author.get("login") if isinstance(author, dict) else None,
                "is_draft": bool(payload.get("draft", False)),
                "is_prerelease": bool(payload.get("prerelease", False)),
                "github_created_at": cls._timestamp(payload.get("created_at")),
                "published_at": cls._timestamp(payload.get("published_at")),
                "body": body,
                "content_hash": hashlib.sha256((body or "").encode()).hexdigest(),
            },
        )

    @staticmethod
    def _active_contributors(stats: list[dict[str, Any]], metric_date: date) -> int:
        threshold = datetime.combine(
            metric_date - timedelta(days=29), datetime.min.time(), tzinfo=UTC
        ).timestamp()
        active = 0
        for contributor in stats:
            weeks = contributor.get("weeks", [])
            if isinstance(weeks, list) and any(
                isinstance(week, dict)
                and isinstance(week.get("w"), int)
                and week["w"] >= threshold
                and isinstance(week.get("c"), int)
                and week["c"] > 0
                for week in weeks
            ):
                active += 1
        return active

    @staticmethod
    def _recent_count(values: list[datetime], metric_date: date, days: int) -> int:
        start = metric_date - timedelta(days=days - 1)
        return sum(start <= value.astimezone(UTC).date() <= metric_date for value in values)

    @staticmethod
    def _days_since(value: datetime | None, metric_date: date) -> int | None:
        if value is None:
            return None
        return max((metric_date - value.astimezone(UTC).date()).days, 0)

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        return parse_datetime(value)
