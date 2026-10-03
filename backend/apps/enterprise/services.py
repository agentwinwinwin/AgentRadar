from typing import Any

from django.utils import timezone

from apps.activities.models import RepositoryContributor
from apps.learning.services import (
    _average,
    assessment_signals,
    knowledge_signals,
    recency_score,
)
from apps.repositories.models import Repository
from apps.trends.engine import ALGORITHM_VERSION as TREND_VERSION

from .engine import ALGORITHM_VERSION, WEIGHTS, calculate
from .models import RepositoryEnterpriseScore


def _item(value: Any, *, missing_status: str = "MISSING") -> dict[str, Any]:
    return {"value": value, "status": "VALUE" if value is not None else missing_status}


class EnterpriseService:
    def calculate_repository(self, repository_id: int) -> RepositoryEnterpriseScore:
        repository = Repository.objects.get(pk=repository_id)
        trend = repository.trend_scores.filter(algorithm_version=TREND_VERSION).first()
        activity = repository.activity_metrics.order_by("-metric_date").first()
        knowledge = knowledge_signals(repository)
        signals = assessment_signals(repository, knowledge)
        standard_license = repository.license_spdx not in (None, "", "NOASSERTION", "OTHER")
        license_score = 100.0 if standard_license else None
        docs_known = any(
            signals[key] is not None
            for key in ("readme", "docs", "getting_started", "contributing")
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
        architecture_known = any(
            signals[key] is not None for key in ("architecture", "deployment", "container")
        )
        architecture_operations = (
            min(
                100.0,
                (40 if signals["architecture"] else 0)
                + (35 if signals["deployment"] else 0)
                + (25 if signals["container"] else 0),
            )
            if architecture_known
            else None
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
        maintenance = (
            0.0
            if repository.is_archived
            else _average(
                [
                    float(trend.maintenance_score)
                    if trend and trend.maintenance_score is not None
                    else None,
                    recency_score(repository),
                ]
            )
        )
        security = (
            100.0 if signals["security"] is True else 0.0 if signals["security"] is False else None
        )
        risk = 0.0 if repository.is_archived else 100.0 if repository.github_pushed_at else None
        values = {
            "maintenance": maintenance,
            "community": community,
            "delivery": delivery,
            "security": security,
            "license": license_score,
            "documentation": documentation,
            "architecture_operations": architecture_operations,
            "risk": risk,
        }
        hype = float(trend.hype_risk) if trend and trend.hype_risk is not None else None
        result = calculate(values, hype)
        component_missing_status = {
            key: "INSUFFICIENT_HISTORY" for key in ("maintenance", "community", "delivery")
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
            "archived": repository.is_archived,
            "license": repository.license_spdx,
            "contributors": contributor_count,
            "releases": release_count,
            "hype_risk": hype,
            "hype_penalty": round(hype * 0.1, 2) if hype is not None else None,
            "missing_inputs": [key for key, value in values.items() if value is None],
            "source_trend_version": trend.algorithm_version if trend else None,
        }
        score, _ = RepositoryEnterpriseScore.objects.update_or_create(
            repository=repository,
            algorithm_version=ALGORITHM_VERSION,
            defaults={
                "score": result.score,
                "confidence": result.confidence,
                "recommendation": result.recommendation,
                "evidence": evidence,
                "calculated_at": timezone.now(),
            },
        )
        return score
