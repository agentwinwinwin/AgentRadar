from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import TypeVar

from .models import HypeRiskStatus, LifecycleStage

ALGORITHM_VERSION = "trend-v1.0.0"

T = TypeVar("T")


@dataclass(frozen=True)
class ComponentResult:
    score: float | None
    completeness: float
    inputs: dict[str, float | None]


@dataclass(frozen=True)
class HypeResult:
    score: float | None
    status: str


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return min(max(value, lower), upper)


def age_cohort(created_at: date, calculation_date: date) -> str:
    age_days = max((calculation_date - created_at).days, 0)
    if age_days <= 30:
        return "AGE_0_30"
    if age_days <= 180:
        return "AGE_31_180"
    if age_days <= 730:
        return "AGE_181_730"
    return "AGE_731_PLUS"


def percentile_ranks(values: dict[T, float | int | None]) -> dict[T, float | None]:
    observed = [(key, float(value)) for key, value in values.items() if value is not None]
    if not observed:
        return {key: None for key in values}
    sorted_values = sorted(value for _, value in observed)
    if len(sorted_values) == 1:
        ranks = {sorted_values[0]: 50.0}
    else:
        ranks = {}
        for value in set(sorted_values):
            positions = [index + 1 for index, item in enumerate(sorted_values) if item == value]
            average_rank = mean(positions)
            ranks[value] = (average_rank - 1) / (len(sorted_values) - 1) * 100
    return {
        key: None if value is None else round(ranks[float(value)], 6)
        for key, value in values.items()
    }


def weighted_component(
    inputs: dict[str, float | int | None], weights: dict[str, float]
) -> ComponentResult:
    total_weight = sum(weights.values())
    available = {
        key: clamp(float(value))
        for key, value in inputs.items()
        if value is not None and key in weights
    }
    available_weight = sum(weights[key] for key in available)
    score = None
    if available_weight:
        score = sum(available[key] * weights[key] for key in available) / available_weight
        score = round(clamp(score), 6)
    return ComponentResult(
        score=score,
        completeness=round(available_weight / total_weight, 6) if total_weight else 0.0,
        inputs={key: None if value is None else float(value) for key, value in inputs.items()},
    )


def hype_risk(
    *,
    star_growth_30d_percentile: float | None,
    fork_delta_30d_percentile: float | None,
    development_score: float | None,
    community_score: float | None,
) -> HypeResult:
    required = (
        star_growth_30d_percentile,
        fork_delta_30d_percentile,
        development_score,
        community_score,
    )
    if any(value is None for value in required):
        return HypeResult(None, HypeRiskStatus.INSUFFICIENT_HISTORY)
    comparison = mean(float(value) for value in required[1:] if value is not None)
    score = round(clamp(float(star_growth_30d_percentile) - comparison), 6)
    if score <= 30:
        status = HypeRiskStatus.LOW
    elif score <= 60:
        status = HypeRiskStatus.MEDIUM
    else:
        status = HypeRiskStatus.HIGH
    return HypeResult(score, status)


def lifecycle_stage(
    *,
    repository_age_days: int,
    archived: bool,
    trend_score: float | None,
    momentum_score: float | None,
    development_score: float | None,
    maintenance_score: float | None,
    hype: HypeResult,
) -> str:
    if archived or (maintenance_score is not None and maintenance_score < 20):
        return LifecycleStage.DORMANT
    if trend_score is None:
        return LifecycleStage.MATURE
    if (
        trend_score >= 88
        and momentum_score is not None
        and momentum_score >= 88
        and development_score is not None
        and development_score >= 70
        and hype.score is not None
        and hype.score <= 40
    ):
        return LifecycleStage.BREAKOUT
    if trend_score >= 75 and momentum_score is not None and momentum_score >= 80:
        return LifecycleStage.ACCELERATING
    if repository_age_days < 180 and trend_score >= 65:
        return LifecycleStage.EMERGING
    if trend_score >= 60:
        return LifecycleStage.GROWING
    if trend_score < 45 and momentum_score is not None and momentum_score < 40:
        return LifecycleStage.COOLING
    return LifecycleStage.MATURE
