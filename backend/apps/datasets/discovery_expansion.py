from __future__ import annotations

from calendar import monthrange
from collections import Counter
from dataclasses import dataclass
from math import ceil

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.github.client import GitHubClientProtocol
from apps.repositories.models import Repository, RepositoryCategory
from apps.repositories.services import RepositoryService

from .models import AcquisitionQueryShard, RepositoryDiscoveryEvidence

DISCOVERY_VERSION = "discovery-shards-v2.0.0"
KEYWORDS = (
    ("topic:ai-agent", RepositoryCategory.AGENT_FRAMEWORK),
    ("topic:ai-agents", RepositoryCategory.AGENT_FRAMEWORK),
    ("topic:autonomous-agent", RepositoryCategory.AGENT_FRAMEWORK),
    ("topic:llm-agent", RepositoryCategory.AGENT_FRAMEWORK),
    ("topic:agentic-ai", RepositoryCategory.AGENT_FRAMEWORK),
    ('"agent framework"', RepositoryCategory.AGENT_FRAMEWORK),
    ('"multi agent"', RepositoryCategory.MULTI_AGENT),
    ('"agent orchestration"', RepositoryCategory.MULTI_AGENT),
    ('"coding agent"', RepositoryCategory.CODING_AGENT),
    ('"coding assistant"', RepositoryCategory.CODING_AGENT),
    ('"computer use"', RepositoryCategory.COMPUTER_USE),
    ('"browser agent"', RepositoryCategory.BROWSER_AGENT),
    ('"browser automation" ai', RepositoryCategory.BROWSER_AGENT),
    ('"research agent"', RepositoryCategory.RESEARCH_AGENT),
    ('"deep research" ai', RepositoryCategory.RESEARCH_AGENT),
    ('"agent memory"', RepositoryCategory.AGENT_MEMORY),
    ('"memory agent"', RepositoryCategory.AGENT_MEMORY),
    ('"model context protocol"', RepositoryCategory.MCP_TOOL),
    ('"mcp server" ai', RepositoryCategory.MCP_TOOL),
    ('"agent tool"', RepositoryCategory.MCP_TOOL),
    ('"agent workflow"', RepositoryCategory.AGENT_WORKFLOW),
    ('"agent security"', RepositoryCategory.AGENT_SECURITY),
    ('"agent observability"', RepositoryCategory.AGENT_OBSERVABILITY),
    ('"ai assistant" agent', RepositoryCategory.OTHER_AGENT),
    ('"autonomous ai"', RepositoryCategory.OTHER_AGENT),
    ("agentic", RepositoryCategory.OTHER_AGENT),
)
STAR_SHARDS = (
    ("STAR_0_9", "stars:0..9"),
    ("STAR_10_49", "stars:10..49"),
    ("STAR_50_99", "stars:50..99"),
    ("STAR_100_499", "stars:100..499"),
    ("STAR_500_999", "stars:500..999"),
    ("STAR_1K_4K", "stars:1000..4999"),
    ("STAR_5K_9K", "stars:5000..9999"),
    ("STAR_10K_PLUS", "stars:>=10000"),
)
CREATED_SHARDS = (
    ("CREATED_PRE_2023", "created:<2023-01-01"),
    ("CREATED_2023", "created:2023-01-01..2023-12-31"),
    ("CREATED_2024", "created:2024-01-01..2024-12-31"),
    ("CREATED_2025", "created:2025-01-01..2025-12-31"),
    ("CREATED_2026", "created:2026-01-01..2026-12-31"),
)


@dataclass(frozen=True)
class DiscoveryExpansionResult:
    target: int
    repository_total: int
    shards_executed: int
    requests: int
    seen: int
    created: int
    updated: int
    skipped: int
    incomplete: int
    truncated: int
    endpoint_request_counts: dict[str, int]


class DiscoveryExpansionService:
    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client
        self.repository_service = RepositoryService(client)

    def plan(self) -> int:
        rows = []
        for priority, (keyword, category) in enumerate(KEYWORDS):
            for star_index, (star_key, star_query) in enumerate(STAR_SHARDS):
                for created_index, (created_key, created_query) in enumerate(CREATED_SHARDS):
                    query = f"{keyword} {star_query} {created_query} archived:false fork:false"
                    rows.append(
                        AcquisitionQueryShard(
                            query=query,
                            category=category,
                            star_bucket=star_key,
                            age_cohort=created_key,
                            shortage=10_000 - (priority * 100 + star_index * 10 + created_index),
                            shard_metadata={
                                "version": DISCOVERY_VERSION,
                                "keyword": keyword,
                                "star": star_query,
                                "created": created_query,
                                "priority": priority * 100 + star_index * 10 + created_index,
                            },
                        )
                    )
        AcquisitionQueryShard.objects.bulk_create(rows, ignore_conflicts=True)
        return AcquisitionQueryShard.objects.filter(
            shard_metadata__version=DISCOVERY_VERSION
        ).count()

    def execute(self, *, target: int, max_shards: int = 500) -> DiscoveryExpansionResult:
        if target < 1 or max_shards < 1:
            raise ValueError("target and max_shards must be positive")
        totals: Counter[str] = Counter()
        shards = AcquisitionQueryShard.objects.filter(
            shard_metadata__version=DISCOVERY_VERSION,
            is_active=True,
            last_executed_at__isnull=True,
        ).order_by("-shortage", "id")
        for shard in shards[:max_shards]:
            if Repository.objects.count() >= target:
                break
            try:
                first = self.client.search_repositories(
                    shard.query, sort="stars", order="desc", per_page=100, page=1
                )
            except Exception as exc:
                shard.last_error = str(exc)[:500]
                shard.execution_count += 1
                shard.save(update_fields=("last_error", "execution_count", "updated_at"))
                raise
            totals["requests"] += 1
            totals["shards"] += 1
            totals["incomplete"] += int(first.incomplete_results)
            truncated = first.total_count > 1_000
            totals["truncated"] += int(truncated)
            if truncated:
                self._split_truncated(shard)
            pages = min(10, ceil(first.total_count / 100))
            results = [first]
            if not truncated:
                for page in range(2, pages + 1):
                    results.append(
                        self.client.search_repositories(
                            shard.query,
                            sort="stars",
                            order="desc",
                            per_page=100,
                            page=page,
                        )
                    )
                    totals["requests"] += 1
            shard_created = 0
            for result in results:
                for payload in result.items:
                    totals["seen"] += 1
                    if payload.get("fork") or payload.get("archived"):
                        totals["skipped"] += 1
                        continue
                    repository, was_created = self.repository_service.upsert_from_github(payload)
                    totals["created" if was_created else "updated"] += 1
                    shard_created += int(was_created)
                    self._record_evidence(repository, shard)
            shard.last_total_count = first.total_count
            shard.last_incomplete_results = first.incomplete_results
            shard.last_truncated = truncated
            shard.last_executed_at = timezone.now()
            shard.execution_count += 1
            shard.repositories_seen += sum(len(result.items) for result in results)
            shard.repositories_created += shard_created
            shard.is_active = not truncated
            shard.last_error = ""
            shard.save(
                update_fields=(
                    "last_total_count",
                    "last_incomplete_results",
                    "last_truncated",
                    "last_executed_at",
                    "execution_count",
                    "repositories_seen",
                    "repositories_created",
                    "last_error",
                    "is_active",
                    "updated_at",
                )
            )
        request_counts = getattr(self.client, "request_counts", {})
        return DiscoveryExpansionResult(
            target=target,
            repository_total=Repository.objects.count(),
            shards_executed=totals["shards"],
            requests=totals["requests"],
            seen=totals["seen"],
            created=totals["created"],
            updated=totals["updated"],
            skipped=totals["skipped"],
            incomplete=totals["incomplete"],
            truncated=totals["truncated"],
            endpoint_request_counts=dict(request_counts),
        )

    @staticmethod
    def _split_truncated(shard: AcquisitionQueryShard) -> None:
        metadata = shard.shard_metadata
        created = str(metadata.get("created", ""))
        ranges = []
        if created == "created:<2023-01-01":
            ranges = [
                (f"CREATED_{year}", f"created:{year}-01-01..{year}-12-31")
                for year in range(2008, 2023)
            ]
        elif created.startswith("created:") and ".." in created:
            first = created.removeprefix("created:").split("..", 1)[0]
            year = int(first[:4])
            ranges = [
                (
                    f"CREATED_{year}_{month:02d}",
                    f"created:{year}-{month:02d}-01..{year}-{month:02d}-"
                    f"{monthrange(year, month)[1]:02d}",
                )
                for month in range(1, 13)
            ]
        rows = []
        for created_key, created_query in ranges:
            query = (
                f"{metadata['keyword']} {metadata['star']} {created_query} "
                "archived:false fork:false"
            )
            rows.append(
                AcquisitionQueryShard(
                    query=query,
                    category=shard.category,
                    star_bucket=shard.star_bucket,
                    age_cohort=created_key,
                    shortage=shard.shortage + 1,
                    shard_metadata={
                        **metadata,
                        "created": created_query,
                        "parent_shard_id": shard.id,
                        "dynamic_split": True,
                    },
                )
            )
        AcquisitionQueryShard.objects.bulk_create(rows, ignore_conflicts=True)

    @staticmethod
    @transaction.atomic
    def _record_evidence(repository: Repository, shard: AcquisitionQueryShard) -> None:
        evidence, created = RepositoryDiscoveryEvidence.objects.get_or_create(
            repository=repository, shard=shard
        )
        if not created:
            RepositoryDiscoveryEvidence.objects.filter(pk=evidence.pk).update(
                times_seen=F("times_seen") + 1,
                last_seen_at=timezone.now(),
            )
