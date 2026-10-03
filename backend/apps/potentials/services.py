from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.repositories.models import Repository
from apps.trends.engine import ALGORITHM_VERSION as TREND_ALGORITHM_VERSION
from apps.trends.models import RepositoryTrendScore

from .engine import (
    ALGORITHM_VERSION,
    POTENTIAL_WEIGHTS,
    calculate_potential,
    candidate_flags,
)
from .models import RepositoryPotentialScore


@dataclass(frozen=True)
class PotentialCalculationResult:
    potential: RepositoryPotentialScore
    created: bool


def _number(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)


class PotentialService:
    @transaction.atomic
    def calculate_repository(self, repository_id: int) -> PotentialCalculationResult:
        repository = Repository.objects.get(pk=repository_id, is_disabled=False)
        trend = RepositoryTrendScore.objects.get(
            repository=repository, algorithm_version=TREND_ALGORITHM_VERSION
        )
        components = trend.evidence.get("components", {})
        values = {
            "trend": _number(trend.trend_score),
            "momentum": _number(trend.momentum_score),
            "topic_momentum": _number(trend.topic_momentum_score),
            "community": _number(trend.community_score),
            "delivery": _number(trend.delivery_score),
            "novelty": None,
        }
        completeness = {
            "trend": trend.data_completeness,
            "momentum": self._component_completeness(components, "momentum"),
            "topic_momentum": self._component_completeness(components, "topic_momentum"),
            "community": self._component_completeness(components, "community"),
            "delivery": self._component_completeness(components, "delivery"),
            "novelty": 0.0,
        }
        result = calculate_potential(values, completeness, _number(trend.hype_risk))
        flags = candidate_flags(
            potential=result.score,
            confidence=result.confidence,
            momentum=values["momentum"],
            community=values["community"],
            delivery=values["delivery"],
            hype_status=trend.hype_risk_status,
        )
        missing = sorted(key for key, value in values.items() if value is None)
        if trend.hype_risk is None:
            missing.append("hype_risk")
        evidence: dict[str, Any] = {
            "source_trend": {
                "id": trend.id,
                "algorithm_version": trend.algorithm_version,
                "calculated_at": trend.calculated_at.isoformat(),
            },
            "inputs": values,
            "weights": POTENTIAL_WEIGHTS,
            "component_completeness": completeness,
            "base_potential": result.base_score,
            "hype_risk": _number(trend.hype_risk),
            "hype_risk_status": trend.hype_risk_status,
            "hype_penalty": result.hype_penalty,
            "missing_inputs": sorted(missing),
            "candidate_flags": flags,
            "candidate_thresholds": {
                "high_potential": {"potential": 75, "confidence": 0.55},
                "potential_candidate": {"potential": 65, "confidence": 0.45},
                "breakout_candidate": {
                    "potential": 80,
                    "confidence": 0.65,
                    "momentum": 75,
                    "community": 60,
                    "delivery": 50,
                    "requires_known_non_high_hype": True,
                },
            },
        }
        potential, created = RepositoryPotentialScore.objects.update_or_create(
            repository=repository,
            algorithm_version=ALGORITHM_VERSION,
            defaults={
                "potential_score": result.score,
                "confidence": result.confidence,
                "evidence": evidence,
                "calculated_at": timezone.now(),
            },
        )
        potential.refresh_from_db()
        from apps.operations.models import RepositoryScoreHistory
        from apps.operations.services import record_score_history

        record_score_history(potential, RepositoryScoreHistory.ScoreType.POTENTIAL)
        return PotentialCalculationResult(potential, created)

    @staticmethod
    def _component_completeness(components: dict[str, Any], name: str) -> float:
        value = components.get(name, {}).get("completeness", 0.0)
        return float(value) if value is not None else 0.0
