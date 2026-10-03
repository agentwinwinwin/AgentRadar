from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.github.client import GitHubClientProtocol
from apps.repositories.models import Repository, RepositoryCategory
from apps.repositories.services import RepositoryService
from apps.trends.engine import age_cohort

from .models import (
    AcquisitionQueryShard,
    RepositoryPool,
    RepositoryPoolMembership,
    RepositoryPoolStatus,
    RepositoryPoolType,
)

SAMPLING_VERSION = "sampling-v1.0.0"
SAMPLING_VERSION_V2 = "sampling-v2.0.0"
STAR_BUCKETS = ("STAR_0_99", "STAR_100_999", "STAR_1K_9K", "STAR_10K_PLUS", "UNKNOWN")
ACTIVITY_LEVELS = ("HIGH", "MEDIUM", "LOW", "INACTIVE", "UNKNOWN")
MAJOR_CATEGORY_QUERIES = {
    RepositoryCategory.AGENT_FRAMEWORK: '"agent framework"',
    RepositoryCategory.CODING_AGENT: '"coding agent"',
    RepositoryCategory.BROWSER_AGENT: '"browser agent"',
    RepositoryCategory.RESEARCH_AGENT: '"research agent"',
    RepositoryCategory.MULTI_AGENT: '"multi agent"',
    RepositoryCategory.AGENT_MEMORY: '"agent memory"',
    RepositoryCategory.MCP_TOOL: '"MCP agent"',
    RepositoryCategory.COMPUTER_USE: '"computer use"',
    RepositoryCategory.AGENT_OBSERVABILITY: '"agent observability"',
    RepositoryCategory.AGENT_SECURITY: '"agent security"',
}


def star_bucket(stars: int | None) -> str:
    if stars is None:
        return "UNKNOWN"
    if stars < 100:
        return "STAR_0_99"
    if stars < 1_000:
        return "STAR_100_999"
    if stars < 10_000:
        return "STAR_1K_9K"
    return "STAR_10K_PLUS"


def activity_level(repository: Repository) -> str:
    metric = repository.activity_metrics.order_by("-metric_date").first()
    if metric is None:
        return "UNKNOWN"
    values = (metric.commits_30d, metric.prs_created_30d, metric.issues_closed_30d)
    if all(value is None for value in values):
        return "UNKNOWN"
    score = sum(value or 0 for value in values)
    if score >= 50:
        return "HIGH"
    if score >= 10:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "INACTIVE"


@dataclass(frozen=True)
class RepositoryStratum:
    category: str
    star_bucket: str
    age_cohort: str
    activity_level: str


def repository_stratum(repository: Repository, as_of: date) -> RepositoryStratum:
    return RepositoryStratum(
        category=repository.category,
        star_bucket=star_bucket(repository.stars),
        age_cohort=age_cohort(repository.github_created_at.date(), as_of),
        activity_level=activity_level(repository),
    )


class CoverageAuditService:
    def report(self, *, as_of: date | None = None) -> dict[str, Any]:
        as_of = as_of or timezone.now().date()
        repositories = list(Repository.objects.all().prefetch_related("activity_metrics"))
        strata = {
            repository.id: repository_stratum(repository, as_of) for repository in repositories
        }
        combined = Counter(
            (item.category, item.star_bucket, item.age_cohort) for item in strata.values()
        )
        nonzero = sorted(combined.values())
        median = nonzero[len(nonzero) // 2] if nonzero else 0
        underrepresented = [
            {"category": key[0], "star_bucket": key[1], "age_cohort": key[2], "count": count}
            for key, count in sorted(combined.items())
            if count < 5
        ]
        overrepresented = [
            {"category": key[0], "star_bucket": key[1], "age_cohort": key[2], "count": count}
            for key, count in sorted(combined.items())
            if median and count > median * 2
        ]
        return {
            "as_of": as_of.isoformat(),
            "repository_total": len(repositories),
            "category_distribution": dict(Counter(item.category for item in strata.values())),
            "star_bucket_distribution": dict(Counter(item.star_bucket for item in strata.values())),
            "age_cohort_distribution": dict(Counter(item.age_cohort for item in strata.values())),
            "activity_level_distribution": dict(
                Counter(item.activity_level for item in strata.values())
            ),
            "combined_strata": {"|".join(key): value for key, value in sorted(combined.items())},
            "underrepresented_strata": underrepresented,
            "overrepresented_strata": overrepresented,
        }


class HeadCoverageService:
    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client
        self.repository_service = RepositoryService(client)

    def ensure(self, *, top_n: int = 10) -> dict[str, Any]:
        if not 1 <= top_n <= 100:
            raise ValueError("top_n must be between 1 and 100")
        categories: dict[str, Any] = {}
        created_ids: list[int] = []
        repository_ids: list[int] = []
        for category, phrase in MAJOR_CATEGORY_QUERIES.items():
            result = self.client.search_repositories(
                f"{phrase} archived:false fork:false stars:>10",
                sort="stars",
                order="desc",
                per_page=top_n,
                page=1,
            )
            existing = created = 0
            for payload in result.items:
                repository = Repository.objects.filter(github_id=payload.get("id")).first()
                if repository is None:
                    repository = Repository.objects.filter(
                        full_name=payload.get("full_name")
                    ).first()
                if repository is None:
                    repository, _ = self.repository_service.upsert_from_github(payload)
                    created += 1
                    created_ids.append(repository.id)
                else:
                    existing += 1
                repository_ids.append(repository.id)
            observed = len(result.items)
            categories[str(category)] = {
                "top_n": top_n,
                "observed": observed,
                "existing": existing,
                "created": created,
                "coverage_rate": round(existing / observed, 6) if observed else None,
                "incomplete_results": result.incomplete_results,
            }
        return {
            "categories": categories,
            "repository_ids": sorted(set(repository_ids)),
            "created_repository_ids": sorted(set(created_ids)),
        }


class RepositoryPoolService:
    @staticmethod
    def _v2_tracked_repositories() -> list[Repository]:
        return [
            repository
            for repository in Repository.objects.all().prefetch_related(
                "activity_metrics", "topics"
            )
            if not repository.is_fork
            and not repository.is_archived
            and not repository.is_disabled
            and repository.category != RepositoryCategory.OTHER_AGENT
            and repository.github_pushed_at is not None
            and (repository.description or repository.topics.exists())
        ]

    @transaction.atomic
    def build(
        self,
        *,
        training_target: int = 300,
        head_repository_ids: list[int] | None = None,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        if training_target < 1:
            raise ValueError("training_target must be positive")
        as_of = as_of or timezone.now().date()
        head_repository_ids = head_repository_ids or []
        all_repositories = list(Repository.objects.all().prefetch_related("activity_metrics"))
        eligible = [
            repository
            for repository in all_repositories
            if not repository.is_fork and not repository.is_archived and not repository.is_disabled
        ]
        tracked = [
            repository
            for repository in eligible
            if repository.category != RepositoryCategory.OTHER_AGENT
            or repository.id in head_repository_ids
        ]
        candidate_pool = self._replace_pool(
            "sprint8-candidate-v1",
            RepositoryPoolType.CANDIDATE,
            all_repositories,
            as_of,
            reason="existing_repository_candidate",
            status=RepositoryPoolStatus.CONFIRMED,
        )
        tracked_pool = self._replace_pool(
            "sprint8-tracked-v1",
            RepositoryPoolType.TRACKED,
            tracked,
            as_of,
            reason="eligible_ai_agent_or_head_coverage",
            status=RepositoryPoolStatus.CONFIRMED,
        )
        selected = self._stratified_select(tracked, training_target, as_of)
        training_pool = self._replace_pool(
            "sprint8-training-v1",
            RepositoryPoolType.TRAINING,
            selected,
            as_of,
            reason="category_star_age_stratified",
            status=RepositoryPoolStatus.DRAFT,
            selection_config={"target": training_target, "as_of": as_of.isoformat()},
        )
        return {
            "candidate_pool": candidate_pool.memberships.count(),
            "tracked_pool": tracked_pool.memberships.count(),
            "training_pool": training_pool.memberships.count(),
            "training_pool_status": training_pool.status,
            "training_strata": self.pool_distribution(training_pool),
        }

    @transaction.atomic
    def build_v2(self, *, training_target: int = 800, as_of: date | None = None) -> dict[str, Any]:
        if not 600 <= training_target <= 1_000:
            raise ValueError("v2 training target must be between 600 and 1000")
        as_of = as_of or timezone.now().date()
        all_repositories = list(Repository.objects.all().prefetch_related("activity_metrics"))
        tracked = self._v2_tracked_repositories()
        candidate_pool = self._replace_pool(
            "sprint8-candidate-v2",
            RepositoryPoolType.CANDIDATE,
            all_repositories,
            as_of,
            reason="discovery_expansion_candidate",
            status=RepositoryPoolStatus.CONFIRMED,
            selection_version=SAMPLING_VERSION_V2,
        )
        tracked_pool = self._replace_pool(
            "sprint8-tracked-v2",
            RepositoryPoolType.TRACKED,
            tracked,
            as_of,
            reason="classified_nonfork_active_metadata",
            status=RepositoryPoolStatus.CONFIRMED,
            selection_version=SAMPLING_VERSION_V2,
        )
        selected = self._stratified_select(tracked, training_target, as_of)
        training_pool = self._replace_pool(
            "sprint8-training-v2",
            RepositoryPoolType.TRAINING,
            selected,
            as_of,
            reason="category_star_age_stratified_v2",
            status=RepositoryPoolStatus.DRAFT,
            selection_config={"target": training_target, "as_of": as_of.isoformat()},
            selection_version=SAMPLING_VERSION_V2,
        )
        return {
            "candidate_pool": candidate_pool.memberships.count(),
            "tracked_pool": tracked_pool.memberships.count(),
            "training_pool": training_pool.memberships.count(),
            "training_pool_status": training_pool.status,
            "training_strata": self.pool_distribution(training_pool),
        }

    def simulate_training_sizes(
        self,
        *,
        targets: tuple[int, ...],
        sample_dates: tuple[date, ...],
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """Simulate larger stratified pools without creating or replacing a pool."""
        if not targets or any(target < 1 for target in targets):
            raise ValueError("targets must be positive")
        as_of = as_of or timezone.now().date()
        tracked = self._v2_tracked_repositories()
        simulations = {}
        for target in targets:
            selected = self._stratified_select(tracked, target, as_of)
            category_counts = Counter(repository.category for repository in selected)
            matrix = {}
            thresholds = {20: 0, 50: 0, 80: 0}
            for sample_date in sample_dates:
                counts = Counter(
                    repository.category
                    for repository in selected
                    if repository.github_created_at.date() <= sample_date
                )
                matrix[sample_date.isoformat()] = dict(sorted(counts.items()))
                for threshold in thresholds:
                    thresholds[threshold] += sum(count >= threshold for count in counts.values())
            simulations[str(target)] = {
                "selected": len(selected),
                "category_count": len(category_counts),
                "category_distribution": dict(sorted(category_counts.items())),
                "sample_at_cohort_sizes": matrix,
                "cohorts_gte_20": thresholds[20],
                "cohorts_gte_50": thresholds[50],
                "cohorts_gte_80": thresholds[80],
            }
        return {
            "candidate_count": Repository.objects.count(),
            "eligible_tracked_count": len(tracked),
            "sample_dates": [value.isoformat() for value in sample_dates],
            "simulations": simulations,
        }

    @staticmethod
    def _stratified_select(
        repositories: list[Repository], target: int, as_of: date
    ) -> list[Repository]:
        groups: dict[tuple[str, str, str], list[Repository]] = defaultdict(list)
        levels = {repository.id: activity_level(repository) for repository in repositories}
        level_order = {level: index for index, level in enumerate(ACTIVITY_LEVELS)}
        for repository in repositories:
            item = repository_stratum(repository, as_of)
            groups[(item.category, item.star_bucket, item.age_cohort)].append(repository)
        for values in groups.values():
            values.sort(
                key=lambda repository: (
                    level_order[levels[repository.id]],
                    hashlib.sha256(repository.full_name.encode()).hexdigest(),
                )
            )
        selected: list[Repository] = []
        keys = sorted(groups)
        round_index = 0
        while len(selected) < min(target, len(repositories)):
            added = False
            for key in keys:
                if round_index < len(groups[key]):
                    selected.append(groups[key][round_index])
                    added = True
                    if len(selected) == min(target, len(repositories)):
                        break
            if not added:
                break
            round_index += 1
        return selected

    @staticmethod
    def _replace_pool(
        name: str,
        pool_type: str,
        repositories: list[Repository],
        as_of: date,
        *,
        reason: str,
        status: str,
        selection_config: dict[str, Any] | None = None,
        selection_version: str = SAMPLING_VERSION,
    ) -> RepositoryPool:
        pool, _ = RepositoryPool.objects.update_or_create(
            name=name,
            defaults={
                "pool_type": pool_type,
                "status": status,
                "selection_version": selection_version,
                "selection_config": selection_config or {"as_of": as_of.isoformat()},
                "confirmed_at": (
                    timezone.now() if status == RepositoryPoolStatus.CONFIRMED else None
                ),
            },
        )
        pool.memberships.all().delete()
        ranks: Counter[tuple[str, str, str]] = Counter()
        memberships = []
        for repository in repositories:
            item = repository_stratum(repository, as_of)
            key = (item.category, item.star_bucket, item.age_cohort)
            ranks[key] += 1
            memberships.append(
                RepositoryPoolMembership(
                    pool=pool,
                    repository=repository,
                    category=item.category,
                    star_bucket=item.star_bucket,
                    age_cohort=item.age_cohort,
                    activity_level=item.activity_level,
                    selection_reason=reason,
                    stratum_rank=ranks[key],
                )
            )
        RepositoryPoolMembership.objects.bulk_create(memberships)
        return pool

    @staticmethod
    def pool_distribution(pool: RepositoryPool) -> dict[str, int]:
        values = pool.memberships.values_list("category", "star_bucket", "age_cohort")
        return {"|".join(key): count for key, count in sorted(Counter(values).items())}


class QueryShardingService:
    STAR_QUALIFIERS = {
        "STAR_0_99": "stars:11..99",
        "STAR_100_999": "stars:100..999",
        "STAR_1K_9K": "stars:1000..9999",
        "STAR_10K_PLUS": "stars:>=10000",
    }

    def __init__(self, client: GitHubClientProtocol | None = None) -> None:
        self.client = client
        self.repository_service = RepositoryService(client) if client is not None else None

    def plan(self, report: dict[str, Any]) -> list[AcquisitionQueryShard]:
        as_of = date.fromisoformat(report["as_of"])
        AcquisitionQueryShard.objects.update(is_active=False)
        shards = []
        for item in report["underrepresented_strata"]:
            phrase = MAJOR_CATEGORY_QUERIES.get(item["category"])
            stars = self.STAR_QUALIFIERS.get(item["star_bucket"])
            if phrase is None or stars is None:
                continue
            created = self._age_qualifier(item["age_cohort"], as_of)
            query = f"{phrase} {stars} {created} archived:false fork:false"
            shard, _ = AcquisitionQueryShard.objects.update_or_create(
                query=query,
                defaults={
                    "category": item["category"],
                    "star_bucket": item["star_bucket"],
                    "age_cohort": item["age_cohort"],
                    "shortage": 5 - item["count"],
                    "is_active": True,
                },
            )
            shards.append(shard)
        return shards

    def execute(self, *, limit_shards: int = 10, per_shard: int = 10) -> dict[str, int]:
        if self.client is None or self.repository_service is None:
            raise ValueError("GitHub client is required to execute query shards")
        if limit_shards < 1 or not 1 <= per_shard <= 100:
            raise ValueError("invalid shard limits")
        seen = created = reused = 0
        shards = list(
            AcquisitionQueryShard.objects.filter(is_active=True).order_by("-shortage", "id")[
                :limit_shards
            ]
        )
        for shard in shards:
            result = self.client.search_repositories(
                shard.query, sort="stars", order="desc", per_page=per_shard, page=1
            )
            shard_seen = shard_created = 0
            for payload in result.items:
                seen += 1
                shard_seen += 1
                repository = Repository.objects.filter(github_id=payload.get("id")).first()
                if repository is None:
                    repository = Repository.objects.filter(
                        full_name=payload.get("full_name")
                    ).first()
                if repository is None:
                    self.repository_service.upsert_from_github(payload)
                    created += 1
                    shard_created += 1
                else:
                    reused += 1
            shard.last_executed_at = timezone.now()
            shard.repositories_seen += shard_seen
            shard.repositories_created += shard_created
            shard.save(
                update_fields=(
                    "last_executed_at",
                    "repositories_seen",
                    "repositories_created",
                    "updated_at",
                )
            )
        return {
            "shards_executed": len(shards),
            "repositories_seen": seen,
            "repositories_created": created,
            "repositories_reused": reused,
        }

    @staticmethod
    def _age_qualifier(value: str, as_of: date) -> str:
        if value == "AGE_0_30":
            return f"created:>={as_of - timedelta(days=30)}"
        if value == "AGE_31_180":
            return f"created:{as_of - timedelta(days=180)}..{as_of - timedelta(days=31)}"
        if value == "AGE_181_730":
            return f"created:{as_of - timedelta(days=730)}..{as_of - timedelta(days=181)}"
        return f"created:<{as_of - timedelta(days=730)}"
