from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.github.client import GitHubClientProtocol

from .classifiers import classify_repository
from .models import GitHubDiscoveryQuery, Repository, RepositoryTopic, Topic


class InvalidGitHubRepositoryError(ValueError):
    pass


@dataclass(frozen=True)
class DiscoveryResult:
    queries_executed: int
    repositories_seen: int
    repositories_created: int
    repositories_updated: int
    repositories_skipped: int
    incomplete_queries: int
    truncated_queries: int


class RepositoryService:
    VERIFIED_RAW_FIELDS = (
        "id",
        "node_id",
        "name",
        "full_name",
        "description",
        "homepage",
        "private",
        "visibility",
        "fork",
        "archived",
        "disabled",
        "size",
        "stargazers_count",
        "forks_count",
        "subscribers_count",
        "open_issues_count",
        "language",
        "topics",
        "license",
        "default_branch",
        "created_at",
        "updated_at",
        "pushed_at",
    )

    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client

    def sync_by_full_name(self, full_name: str) -> tuple[Repository, bool]:
        return self.upsert_from_github(self.client.get_repository(full_name))

    @transaction.atomic
    def upsert_from_github(self, payload: dict[str, Any]) -> tuple[Repository, bool]:
        self._validate_payload(payload)
        topics = self._normalize_topics(payload.get("topics", []))
        license_data = payload.get("license") or {}
        owner_data = payload["owner"]
        now = timezone.now()
        defaults = {
            "owner": owner_data["login"],
            "name": payload["name"],
            "full_name": payload["full_name"],
            "description": payload.get("description"),
            "homepage": payload.get("homepage"),
            "stars": payload.get("stargazers_count"),
            "forks": payload.get("forks_count"),
            "subscribers": payload.get("subscribers_count"),
            "open_issues": payload.get("open_issues_count"),
            "primary_language": payload.get("language"),
            "license_key": license_data.get("key"),
            "license_spdx": license_data.get("spdx_id"),
            "default_branch": payload["default_branch"],
            "repo_size": payload.get("size", 0),
            "is_fork": payload.get("fork", False),
            "is_archived": payload.get("archived", False),
            "is_disabled": payload.get("disabled", False),
            "github_created_at": self._parse_timestamp(payload["created_at"], "created_at"),
            "github_updated_at": self._parse_timestamp(payload["updated_at"], "updated_at"),
            "github_pushed_at": self._parse_optional_timestamp(payload.get("pushed_at")),
            "last_synced_at": now,
            "raw_metadata": {
                field: payload.get(field) for field in self.VERIFIED_RAW_FIELDS if field in payload
            },
        }
        repository = Repository.objects.filter(github_id=payload["id"]).first()
        created = repository is None
        if created:
            defaults["category"] = classify_repository(
                topics=topics,
                description=payload.get("description"),
            )
            repository = Repository.objects.create(github_id=payload["id"], **defaults)
        else:
            for field, value in defaults.items():
                setattr(repository, field, value)
            repository.save(update_fields=(*defaults.keys(), "updated_at"))

        self._replace_topics(repository, topics)
        return repository, created

    @staticmethod
    def _replace_topics(repository: Repository, topic_names: list[str]) -> None:
        topic_ids: list[int] = []
        for normalized_name in topic_names:
            topic, _ = Topic.objects.get_or_create(
                normalized_name=normalized_name,
                defaults={"name": normalized_name},
            )
            topic_ids.append(topic.id)
        RepositoryTopic.objects.filter(repository=repository).exclude(
            topic_id__in=topic_ids
        ).delete()
        RepositoryTopic.objects.bulk_create(
            [RepositoryTopic(repository=repository, topic_id=topic_id) for topic_id in topic_ids],
            ignore_conflicts=True,
        )

    @staticmethod
    def _normalize_topics(value: Any) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise InvalidGitHubRepositoryError("topics must be a list of strings")
        return sorted({item.strip().casefold() for item in value if item.strip()})

    @staticmethod
    def _parse_timestamp(value: Any, field: str):
        if not isinstance(value, str) or (parsed := parse_datetime(value)) is None:
            raise InvalidGitHubRepositoryError(f"{field} must be an ISO-8601 timestamp")
        return parsed

    @classmethod
    def _parse_optional_timestamp(cls, value: Any):
        return None if value is None else cls._parse_timestamp(value, "pushed_at")

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        required = (
            "id",
            "owner",
            "name",
            "full_name",
            "default_branch",
            "created_at",
            "updated_at",
        )
        missing = [field for field in required if payload.get(field) in (None, "")]
        if missing:
            message = f"missing required GitHub fields: {', '.join(missing)}"
            raise InvalidGitHubRepositoryError(message)
        if not isinstance(payload["id"], int) or not isinstance(payload["owner"], dict):
            raise InvalidGitHubRepositoryError("id and owner have invalid types")
        if not payload["owner"].get("login"):
            raise InvalidGitHubRepositoryError("owner.login is required")


class RepositoryDiscoveryService:
    REQUIRED_QUALIFIERS = "archived:false fork:false stars:>10"

    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client
        self.repository_service = RepositoryService(client)

    def discover(
        self,
        *,
        per_query: int = 100,
        pages_per_query: int = 10,
        start_page: int = 1,
    ) -> DiscoveryResult:
        if not 1 <= per_query <= 100:
            raise ValueError("per_query must be between 1 and 100")
        if not 1 <= pages_per_query <= 10:
            raise ValueError("pages_per_query must be between 1 and 10")
        if not 1 <= start_page <= 10 or start_page + pages_per_query - 1 > 10:
            raise ValueError("requested pages must stay within GitHub's first 10 pages")
        seen = created = updated = skipped = 0
        incomplete_query_ids: set[int] = set()
        truncated_query_ids: set[int] = set()
        queries = list(GitHubDiscoveryQuery.objects.filter(is_active=True))
        for discovery_query in queries:
            query = f"{discovery_query.query} {self.REQUIRED_QUALIFIERS}"
            for page in range(start_page, start_page + pages_per_query):
                result = self.client.search_repositories(query, per_page=per_query, page=page)
                if result.incomplete_results:
                    incomplete_query_ids.add(discovery_query.id)
                if result.total_count > 1000:
                    truncated_query_ids.add(discovery_query.id)
                if not result.items:
                    break
                for payload in result.items:
                    seen += 1
                    if payload.get("fork") or payload.get("archived"):
                        skipped += 1
                        continue
                    _, was_created = self.repository_service.upsert_from_github(payload)
                    created += int(was_created)
                    updated += int(not was_created)
                if len(result.items) < per_query:
                    break
        return DiscoveryResult(
            queries_executed=len(queries),
            repositories_seen=seen,
            repositories_created=created,
            repositories_updated=updated,
            repositories_skipped=skipped,
            incomplete_queries=len(incomplete_query_ids),
            truncated_queries=len(truncated_query_ids),
        )
