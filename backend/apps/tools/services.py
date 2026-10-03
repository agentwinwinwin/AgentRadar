from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q

from apps.activities.models import RepositoryActivityMetric
from apps.common.actor import ActorRequired, actor_user_id
from apps.datasets.models import (
    RepositoryPoolMembership,
    RepositoryPoolStatus,
    RepositoryPoolType,
)
from apps.knowledge.models import KnowledgeDocument, KnowledgeSourceType, KnowledgeSyncState
from apps.knowledge.services import RetrievalService
from apps.repositories.api_services import RepositoryReadService
from apps.repositories.models import Repository, RepositoryCategory
from apps.snapshots.models import RepositorySnapshot
from apps.watchlists.api_services import alert_data, report_data
from apps.watchlists.models import ScheduledReport
from apps.watchlists.services import WatchlistService


class ToolDataService:
    """Minimal read service used by tools; it never mutates domain data."""

    @staticmethod
    def resolve_repository(value: int | str) -> Repository:
        query = Q(pk=value) if isinstance(value, int) else Q(full_name__iexact=value.strip())
        return Repository.objects.get(query, is_disabled=False)

    @classmethod
    def project(cls, value: int | str) -> dict[str, Any]:
        return RepositoryReadService.detail(cls.resolve_repository(value).id)

    @classmethod
    def search(cls, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return [
            RepositoryReadService.summary(repo)
            for repo in RepositoryReadService.discover(filters)[:limit]
        ]

    @classmethod
    def scores(cls, value: int | str) -> dict[str, Any]:
        repository = cls.resolve_repository(value)
        return {
            "repository": repository.full_name,
            "trend": RepositoryReadService.trend(repository.id),
            "potential": RepositoryReadService.potential(repository.id),
            "learning": RepositoryReadService.learning(repository.id),
            "enterprise": RepositoryReadService.enterprise(repository.id),
            "forecast": RepositoryReadService.forecast(repository.id),
        }

    @classmethod
    def compare(cls, values: list[int | str]) -> dict[str, Any]:
        ids = [value for value in values if isinstance(value, int)]
        names = [value.strip() for value in values if isinstance(value, str)]
        lookup = Q(pk__in=ids)
        for name in names:
            lookup |= Q(full_name__iexact=name)
        resolved = list(
            Repository.objects.filter(lookup, is_disabled=False).prefetch_related(
                Prefetch(
                    "snapshots",
                    queryset=RepositorySnapshot.objects.order_by("-snapshot_at")[:1],
                    to_attr="comparison_snapshots",
                ),
                Prefetch(
                    "activity_metrics",
                    queryset=RepositoryActivityMetric.objects.order_by("-metric_date")[:1],
                    to_attr="comparison_activities",
                ),
            )
        )
        by_id = {repository.id: repository for repository in resolved}
        by_name = {repository.full_name.lower(): repository for repository in resolved}
        repositories = [
            by_id[value] if isinstance(value, int) else by_name[value.strip().lower()]
            for value in values
        ]
        document_rows = (
            KnowledgeDocument.objects.filter(repository__in=repositories, is_active=True)
            .values("repository_id", "source_type")
            .annotate(count=Count("id"))
        )
        document_counts = defaultdict(int)
        for row in document_rows:
            document_counts[row["repository_id"]] += row["count"]
        projects = []
        for repository in repositories:
            latest_snapshot = (
                repository.comparison_snapshots[0] if repository.comparison_snapshots else None
            )
            latest_activity = (
                repository.comparison_activities[0] if repository.comparison_activities else None
            )
            projects.append(
                {
                    "repository_id": repository.id,
                    "full_name": repository.full_name,
                    "category": repository.category,
                    "stars": repository.stars,
                    "forks": repository.forks,
                    "activity": RepositoryReadService._activity(latest_activity),
                    "snapshot": RepositoryReadService._snapshot(latest_snapshot),
                    **{
                        key: value
                        for key, value in {
                            "trend": RepositoryReadService.trend(repository.id),
                            "potential": RepositoryReadService.potential(repository.id),
                            "learning": RepositoryReadService.learning(repository.id),
                            "enterprise": RepositoryReadService.enterprise(repository.id),
                            "forecast": RepositoryReadService.forecast(repository.id),
                        }.items()
                    },
                    "knowledge_status": (
                        "INGESTED" if document_counts[repository.id] else "NOT_INGESTED"
                    ),
                }
            )
        numeric = ("stars", "forks")
        differences = {
            field: {item["full_name"]: item[field] for item in projects} for field in numeric
        }
        return {"projects": projects, "differences": differences}

    @classmethod
    def retrieve_knowledge(cls, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        repository_id = arguments.get("repository_id")
        if repository_id is not None:
            repository_id = cls.resolve_repository(repository_id).id
        rows = RetrievalService().retrieve(
            arguments["query"],
            repository_id=repository_id,
            category=arguments.get("category"),
            source_types=[arguments["source_type"]] if arguments.get("source_type") else None,
            limit=arguments.get("top_k", 5),
        )
        for row in rows:
            row["similarity"] = row.pop("score")
        return rows

    @classmethod
    def knowledge_summary(cls, value: int | str) -> dict[str, Any]:
        repository = cls.resolve_repository(value)
        documents = KnowledgeDocument.objects.filter(repository=repository, is_active=True)
        types = Counter(documents.values_list("source_type", flat=True))
        state = KnowledgeSyncState.objects.filter(repository=repository).first()
        status = (
            "INGESTED"
            if documents.exists()
            else (
                "DOCUMENT_NOT_FOUND"
                if state and state.last_status == "COMPLETED"
                else "NOT_INGESTED"
            )
        )
        return {
            "repository_id": repository.id,
            "repository": repository.full_name,
            "status": status,
            "readme_exists": bool(types[KnowledgeSourceType.README]),
            "docs_count": types[KnowledgeSourceType.DOC],
            "architecture_count": types[KnowledgeSourceType.ARCHITECTURE]
            + types[KnowledgeSourceType.DESIGN],
            "security_count": types[KnowledgeSourceType.SECURITY],
            "contributing_count": types[KnowledgeSourceType.CONTRIBUTING],
            "release_count": types[KnowledgeSourceType.RELEASE],
            "evidence": {"document_count": sum(types.values()), "source_type_counts": dict(types)},
        }

    @staticmethod
    def categories() -> list[dict[str, Any]]:
        repository_counts = dict(
            Repository.objects.filter(is_disabled=False, is_fork=False)
            .values_list("category")
            .annotate(count=Count("id"))
        )
        pool_counts: dict[str, dict[str, int]] = defaultdict(dict)
        rows = (
            RepositoryPoolMembership.objects.filter(pool__status=RepositoryPoolStatus.CONFIRMED)
            .values("category", "pool__pool_type")
            .annotate(count=Count("repository_id", distinct=True))
        )
        for row in rows:
            pool_counts[row["category"]][row["pool__pool_type"]] = row["count"]
        output = []
        for category, _ in RepositoryCategory.choices:
            projects = RepositoryReadService.with_current_trend(
                Repository.objects.filter(category=category, is_disabled=False, is_fork=False)
            )
            stars = [repo.stars for repo in projects if repo.stars is not None]
            trends = [
                float(repo.current_trend_score)
                for repo in projects
                if repo.current_trend_score is not None
            ]
            output.append(
                {
                    "category": category,
                    "repository_count": repository_counts.get(category, 0),
                    "tracked_count": pool_counts[category].get(RepositoryPoolType.TRACKED, 0),
                    "training_count": pool_counts[category].get(RepositoryPoolType.TRAINING, 0),
                    "average_stars": round(mean(stars), 2) if stars else None,
                    "average_trend": round(mean(trends), 2) if trends else None,
                }
            )
        return output

    @classmethod
    def category_trend(cls, category: str) -> dict[str, Any]:
        rows = list(
            RepositoryReadService.with_current_trend(
                Repository.objects.filter(category=category, is_disabled=False, is_fork=False)
            )
        )
        trends = [
            float(row.current_trend_score) for row in rows if row.current_trend_score is not None
        ]
        potentials = [
            float(row.current_potential_potential_score)
            for row in rows
            if row.current_potential_potential_score is not None
        ]
        activity = [
            sum(
                value or 0
                for value in (
                    row.current_commits_30d,
                    row.current_prs_created_30d,
                    row.current_issues_created_30d,
                    row.current_releases_30d,
                )
            )
            for row in rows
            if any(
                value is not None
                for value in (
                    row.current_commits_30d,
                    row.current_prs_created_30d,
                    row.current_issues_created_30d,
                    row.current_releases_30d,
                )
            )
        ]
        return {
            "status": "NO_DEDICATED_CATEGORY_TREND_MODEL",
            "category": category,
            "repository_count": len(rows),
            "active_count": sum(value > 0 for value in activity),
            "trend_distribution": cls._distribution(trends),
            "potential_distribution": cls._distribution(potentials),
            "total_stars": sum(row.stars or 0 for row in rows),
            "activity_total": sum(activity) if activity else None,
        }

    @staticmethod
    def watchlist() -> dict[str, Any]:
        owner = ToolDataService._actor()
        return {
            "projects": [
                {
                    "repository_id": item.repository_id,
                    "full_name": item.repository.full_name,
                    "added_at": item.added_at,
                }
                for item in WatchlistService.list(owner)
            ]
        }

    @classmethod
    def alerts(cls, value: int | str, limit: int = 20) -> dict[str, Any]:
        owner = cls._actor()
        repository = cls.resolve_repository(value)
        receipts = (
            repository.alerts.filter(receipts__owner=owner)
            .select_related("repository")
            .prefetch_related("receipts")[:limit]
        )
        return {
            "repository": repository.full_name,
            "alerts": [
                alert_data(
                    row,
                    next(item.status for item in row.receipts.all() if item.owner_id == owner.id),
                )
                for row in receipts
            ],
        }

    @staticmethod
    def latest_report(report_type: str) -> dict[str, Any]:
        owner = ToolDataService._actor()
        report = ScheduledReport.objects.filter(owner=owner, report_type=report_type).first()
        return (
            {"status": "AVAILABLE", "report": report_data(report)}
            if report
            else {
                "status": "NOT_AVAILABLE",
                "report": None,
            }
        )

    @staticmethod
    def _actor():
        owner_id = actor_user_id.get()
        if owner_id is None:
            raise ActorRequired("Authenticated user context is required.")
        return get_user_model().objects.get(pk=owner_id, is_active=True)

    @staticmethod
    def _distribution(values: list[float]) -> dict[str, Any]:
        return {
            "count": len(values),
            "minimum": min(values) if values else None,
            "average": round(mean(values), 2) if values else None,
            "maximum": max(values) if values else None,
        }
