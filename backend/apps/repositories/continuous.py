from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.datasets.acquisition_services import repository_stratum
from apps.datasets.models import (
    RepositoryPool,
    RepositoryPoolMembership,
    RepositoryPoolStatus,
    RepositoryPoolType,
)
from apps.github.client import GitHubClientProtocol

from .models import GitHubDiscoveryQuery, MonitoringTier, Repository
from .services import RepositoryService


@dataclass(frozen=True)
class ContinuousDiscoveryResult:
    queries: int
    seen: int
    created: int
    reused: int
    skipped: int
    incomplete_queries: int


class GitHubBudgetUnavailable(RuntimeError):
    pass


class ContinuousDiscoveryService:
    REQUIRED_QUALIFIERS = "archived:false fork:false stars:>10"

    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client
        self.repository_service = RepositoryService(client)

    def discover(
        self,
        *,
        mode: str,
        now=None,
        max_queries: int | None = None,
        per_query: int | None = None,
    ) -> ContinuousDiscoveryResult:
        if mode not in {"new", "recent"}:
            raise ValueError("mode must be new or recent")
        now = now or timezone.now()
        self._ensure_budget()
        qualifier = (
            f"created:>={(now - timedelta(days=7)).date().isoformat()}"
            if mode == "new"
            else f"pushed:>={(now - timedelta(days=30)).date().isoformat()}"
        )
        seen_ids: set[int] = set()
        created = reused = skipped = incomplete = 0
        query_rows = GitHubDiscoveryQuery.objects.filter(is_active=True).order_by("id")
        queries = list(query_rows[:max_queries] if max_queries is not None else query_rows)
        for query_row in queries:
            result = self.client.search_repositories(
                f"{query_row.query} {qualifier} {self.REQUIRED_QUALIFIERS}",
                sort="updated",
                order="desc",
                per_page=per_query or settings.CONTINUOUS_DISCOVERY_PER_QUERY,
                page=1,
            )
            incomplete += int(result.incomplete_results)
            for item in result.items:
                github_id = item.get("id")
                if not isinstance(github_id, int) or github_id in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(github_id)
                if item.get("fork") or item.get("archived"):
                    skipped += 1
                    continue
                repository = Repository.objects.filter(github_id=github_id).first()
                if repository is not None:
                    reused += 1
                    continue
                payload = self.client.get_repository(item["full_name"])
                with transaction.atomic():
                    repository, was_created = self.repository_service.upsert_from_github(payload)
                    if not was_created:
                        reused += 1
                        continue
                    Repository.objects.filter(pk=repository.pk).update(
                        monitoring_tier=MonitoringTier.NEW,
                        monitoring_enabled=True,
                        next_snapshot_at=now,
                    )
                    self._add_candidate(repository, now=now)
                    from apps.enterprise.tasks import calculate_repository_enterprise
                    from apps.learning.tasks import calculate_repository_learning
                    from apps.snapshots.tasks import create_repository_snapshot

                    transaction.on_commit(
                        lambda repo_id=repository.id: create_repository_snapshot.delay(repo_id)
                    )
                    transaction.on_commit(
                        lambda repo_id=repository.id: calculate_repository_learning.delay(repo_id)
                    )
                    transaction.on_commit(
                        lambda repo_id=repository.id: calculate_repository_enterprise.delay(repo_id)
                    )
                    created += 1
        return ContinuousDiscoveryResult(
            queries=len(queries),
            seen=len(seen_ids),
            created=created,
            reused=reused,
            skipped=skipped,
            incomplete_queries=incomplete,
        )

    def _ensure_budget(self) -> None:
        resources = self.client.get_rate_limit()["resources"]
        search_remaining = int(resources.get("search", {}).get("remaining", 0))
        core_remaining = int(resources.get("core", {}).get("remaining", 0))
        if search_remaining <= settings.GITHUB_SEARCH_MIN_REMAINING:
            raise GitHubBudgetUnavailable("GitHub search budget is below the safety threshold")
        if core_remaining <= settings.GITHUB_CORE_MIN_REMAINING:
            raise GitHubBudgetUnavailable("GitHub core budget is below the safety threshold")

    @staticmethod
    def _add_candidate(repository: Repository, *, now) -> None:
        pool = RepositoryPool.objects.filter(
            name="sprint8-candidate-v2",
            pool_type=RepositoryPoolType.CANDIDATE,
            status=RepositoryPoolStatus.CONFIRMED,
        ).first()
        if pool is None:
            pool = RepositoryPool.objects.create(
                name="continuous-candidate-v1",
                pool_type=RepositoryPoolType.CANDIDATE,
                status=RepositoryPoolStatus.CONFIRMED,
                selection_version="continuous-discovery-v1.0.0",
                selection_config={"purpose": "new repository candidates"},
                confirmed_at=now,
            )
        stratum = repository_stratum(repository, now.date())
        RepositoryPoolMembership.objects.get_or_create(
            pool=pool,
            repository=repository,
            defaults={
                "category": stratum.category,
                "star_bucket": stratum.star_bucket,
                "age_cohort": stratum.age_cohort,
                "activity_level": stratum.activity_level,
                "selection_reason": "continuous_discovery_candidate",
            },
        )
