import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.datasets.models import RepositoryPool, RepositoryPoolStatus, RepositoryPoolType
from apps.github.client import RealGitHubClient
from apps.knowledge.models import KnowledgeDocument, KnowledgeSyncState
from apps.knowledge.services import IngestionStats, KnowledgeIngestionService


class Command(BaseCommand):
    help = "Synchronize a bounded, category-balanced subset of the confirmed Tracked Pool."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--repository", action="append", default=[])
        parser.add_argument("--include-pr-issue", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not 0 <= options["offset"] <= 3000:
            raise ValueError("offset must be between 0 and 3000")
        if options["repository"]:
            from apps.repositories.models import Repository

            repositories = list(Repository.objects.filter(full_name__in=options["repository"]))
        else:
            pool = (
                RepositoryPool.objects.filter(
                    pool_type=RepositoryPoolType.TRACKED,
                    status=RepositoryPoolStatus.CONFIRMED,
                )
                .order_by("-selection_version")
                .first()
            )
            if pool is None:
                raise ValueError("confirmed Tracked Pool is required")
            synced_ids = set(
                KnowledgeDocument.objects.filter(is_active=True).values_list(
                    "repository_id", flat=True
                )
            ) | set(KnowledgeSyncState.objects.values_list("repository_id", flat=True))
            groups = defaultdict(list)
            for membership in pool.memberships.select_related("repository").order_by(
                "category", "star_bucket", "stratum_rank", "repository_id"
            ):
                if membership.repository_id not in synced_ids:
                    groups[membership.category].append(membership.repository)
            candidates = []
            target = options["limit"] + options["offset"]
            while groups and len(candidates) < target:
                for category in list(groups):
                    if groups[category] and len(candidates) < target:
                        candidates.append(groups[category].pop(0))
                    if not groups[category]:
                        groups.pop(category)
            repositories = candidates[options["offset"] : target]
        total = IngestionStats()
        failures = []
        client = RealGitHubClient()
        service = KnowledgeIngestionService(client, include_pr_issue=options["include_pr_issue"])
        for repository in repositories:
            request_start = client.request_count
            search_start = client.search_request_count
            try:
                stats = service.sync_repository(repository)
                stats["github_api_calls"] = client.request_count - request_start
                stats["github_search_calls"] = client.search_request_count - search_start
                KnowledgeSyncState.objects.update_or_create(
                    repository=repository,
                    defaults={
                        "last_synced_at": timezone.now(),
                        "last_status": "COMPLETED",
                        "last_stats": stats,
                    },
                )
                for field in total.__dataclass_fields__:
                    setattr(total, field, getattr(total, field) + int(stats[field]))
            except Exception as exc:  # command isolates repository failures
                failures.append({"repository": repository.full_name, "error": type(exc).__name__})
                failed_stats = {
                    "error": type(exc).__name__,
                    "github_api_calls": client.request_count - request_start,
                    "github_search_calls": client.search_request_count - search_start,
                }
                total.github_api_calls += failed_stats["github_api_calls"]
                KnowledgeSyncState.objects.update_or_create(
                    repository=repository,
                    defaults={
                        "last_synced_at": timezone.now(),
                        "last_status": "FAILED",
                        "last_stats": failed_stats,
                    },
                )
        self.stdout.write(
            json.dumps(
                {"selected": len(repositories), "stats": total.__dict__, "failures": failures},
                sort_keys=True,
            )
        )
