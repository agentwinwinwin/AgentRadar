from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from apps.activities.models import RepositoryContributor
from apps.knowledge.models import KnowledgeDocument, KnowledgeSourceType, KnowledgeSyncState
from apps.repositories.models import Repository
from apps.trends.engine import ALGORITHM_VERSION as TREND_VERSION

from .engine import ALGORITHM_VERSION, WEIGHTS, calculate
from .models import RepositoryAssessmentEvidence, RepositoryLearningScore


@dataclass(frozen=True)
class KnowledgeSignals:
    status: str
    docs_count: int | None
    readme: bool | None
    architecture: bool | None
    contributing: bool | None
    getting_started: bool | None
    examples: bool | None
    testing: bool | None
    deployment: bool | None
    security: bool | None
    latest_updated_at: str | None


def knowledge_signals(repository: Repository) -> KnowledgeSignals:
    documents = KnowledgeDocument.objects.filter(repository=repository, is_active=True)
    if documents.exists():
        paths = [f"{doc.source_path} {doc.title}".casefold() for doc in documents]
        types = set(documents.values_list("source_type", flat=True))
        latest = documents.order_by("-github_updated_at").first()
        return KnowledgeSignals(
            "INGESTED",
            documents.filter(
                source_type__in=(
                    KnowledgeSourceType.DOC,
                    KnowledgeSourceType.ARCHITECTURE,
                    KnowledgeSourceType.DESIGN,
                    KnowledgeSourceType.SECURITY,
                    KnowledgeSourceType.CONTRIBUTING,
                )
            ).count(),
            KnowledgeSourceType.README in types,
            bool(types & {KnowledgeSourceType.ARCHITECTURE, KnowledgeSourceType.DESIGN})
            or any("architect" in path or "design.md" in path for path in paths),
            KnowledgeSourceType.CONTRIBUTING in types or any("contribut" in path for path in paths),
            any("getting-started" in path or "getting_started" in path for path in paths),
            any("example" in path or "tutorial" in path for path in paths),
            any("test" in path for path in paths),
            any("deploy" in path or "operations" in path for path in paths),
            KnowledgeSourceType.SECURITY in types or any("security" in path for path in paths),
            latest.github_updated_at.isoformat() if latest and latest.github_updated_at else None,
        )
    status = (
        "DOCUMENT_NOT_FOUND"
        if KnowledgeSyncState.objects.filter(
            repository=repository, last_status="COMPLETED"
        ).exists()
        else "NOT_INGESTED"
    )
    missing = None if status == "NOT_INGESTED" else False
    return KnowledgeSignals(
        status,
        0 if missing is False else None,
        missing,
        missing,
        missing,
        missing,
        missing,
        missing,
        missing,
        missing,
        None,
    )


def _knowledge_value(signals: KnowledgeSignals, value: float) -> float | None:
    return None if signals.status == "NOT_INGESTED" else value


def _item(
    value: Any, *, missing_status: str = "MISSING", reason: str | None = None
) -> dict[str, Any]:
    status = "VALUE" if value is not None else missing_status
    return {"value": value, "status": status, "reason": reason}


def recency_score(repository: Repository, now=None) -> float | None:
    if repository.is_archived:
        return 0.0
    if repository.github_pushed_at is None:
        return None
    days = ((now or timezone.now()) - repository.github_pushed_at).days
    return (
        100.0
        if days <= 7
        else 80.0
        if days <= 30
        else 55.0
        if days <= 90
        else 30.0
        if days <= 180
        else 10.0
    )


def _average(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def assessment_signals(
    repository: Repository, knowledge: KnowledgeSignals
) -> dict[str, bool | None | str]:
    evidence = RepositoryAssessmentEvidence.objects.filter(repository=repository).first()
    fields = (
        "readme",
        "docs",
        "getting_started",
        "examples",
        "architecture",
        "contributing",
        "security",
        "testing",
        "deployment",
        "container",
    )
    result: dict[str, bool | None | str] = {
        key: getattr(evidence, key) if evidence else None for key in fields
    }
    if knowledge.status == "INGESTED":
        for key in fields:
            knowledge_value = getattr(knowledge, key, None)
            if result[key] is None and knowledge_value is not None:
                result[key] = knowledge_value
    result["evidence_status"] = evidence.status if evidence else "NOT_CHECKED"
    result["knowledge_status"] = knowledge.status
    return result


class LearningService:
    def calculate_repository(self, repository_id: int) -> RepositoryLearningScore:
        repository = Repository.objects.get(pk=repository_id)
        trend = repository.trend_scores.filter(algorithm_version=TREND_VERSION).first()
        activity = repository.activity_metrics.order_by("-metric_date").first()
        knowledge = knowledge_signals(repository)
        signals = assessment_signals(repository, knowledge)
        docs_known = any(
            signals[key] is not None
            for key in ("readme", "docs", "getting_started", "contributing")
        )
        architecture_known = any(
            signals[key] is not None for key in ("architecture", "examples", "testing")
        )
        documentation = (
            min(
                100.0,
                (40 if signals["readme"] else 0)
                + (20 if signals["docs"] else 0)
                + (20 if signals["getting_started"] else 0)
                + (20 if signals["contributing"] else 0),
            )
            if docs_known
            else None
        )
        architecture_learning = (
            min(
                100.0,
                (50 if signals["architecture"] else 0)
                + (30 if signals["examples"] else 0)
                + (20 if signals["testing"] else 0),
            )
            if architecture_known
            else None
        )
        development_activity = _average(
            [
                min(activity.commits_30d / 30 * 100, 100)
                if activity and activity.commits_30d is not None
                else None,
                min(activity.prs_merged_30d / 10 * 100, 100)
                if activity and activity.prs_merged_30d is not None
                else None,
                recency_score(repository),
            ]
        )
        contributor_count = RepositoryContributor.objects.filter(repository=repository).count()
        community = _average(
            [
                float(trend.community_score)
                if trend and trend.community_score is not None
                else None,
                min(contributor_count / 10 * 100, 100) if contributor_count else None,
                min(activity.active_contributors_30d / 10 * 100, 100)
                if activity and activity.active_contributors_30d is not None
                else None,
            ]
        )
        release_count = repository.releases.filter(is_draft=False).count()
        delivery = _average(
            [
                float(trend.delivery_score) if trend and trend.delivery_score is not None else None,
                min(release_count / 5 * 100, 100) if release_count else None,
            ]
        )
        values = {
            "development_activity": development_activity,
            "documentation": documentation,
            "architecture_learning": architecture_learning,
            "community": community,
            "delivery": delivery,
            "maintenance": _average(
                [
                    float(trend.maintenance_score)
                    if trend and trend.maintenance_score is not None
                    else None,
                    recency_score(repository),
                ]
            ),
        }
        result = calculate(values)
        component_missing_status = {
            key: "INSUFFICIENT_HISTORY"
            for key in ("development_activity", "community", "delivery", "maintenance")
        }
        evidence = {
            "weights": WEIGHTS,
            "components": {
                key: _item(value, missing_status=component_missing_status.get(key, "MISSING"))
                for key, value in values.items()
            },
            "knowledge_status": knowledge.status,
            "knowledge": knowledge.__dict__,
            "assessment": signals,
            "repository_current_state": {
                "archived": repository.is_archived,
                "github_pushed_at": repository.github_pushed_at.isoformat()
                if repository.github_pushed_at
                else None,
                "contributors": contributor_count,
                "releases": release_count,
            },
            "missing_inputs": [key for key, value in values.items() if value is None],
            "source_trend_version": trend.algorithm_version if trend else None,
        }
        score, _ = RepositoryLearningScore.objects.update_or_create(
            repository=repository,
            algorithm_version=ALGORITHM_VERSION,
            defaults={
                "score": result.score,
                "confidence": result.confidence,
                "evidence": evidence,
                "calculated_at": timezone.now(),
            },
        )
        return score
