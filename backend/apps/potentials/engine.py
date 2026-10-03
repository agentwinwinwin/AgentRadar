from dataclasses import dataclass

ALGORITHM_VERSION = "potential-v1.0.0"
POTENTIAL_WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.20,
    "topic_momentum": 0.20,
    "community": 0.15,
    "delivery": 0.10,
    "novelty": 0.10,
}
HYPE_PENALTY_WEIGHT = 0.15
MISSING_HYPE_CONFIDENCE_FACTOR = 0.85


@dataclass(frozen=True)
class PotentialResult:
    score: float | None
    confidence: float
    base_score: float | None
    hype_penalty: float


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return min(max(value, lower), upper)


def calculate_potential(
    values: dict[str, float | None],
    completeness: dict[str, float],
    hype_risk: float | None,
) -> PotentialResult:
    available = {key: value for key, value in values.items() if value is not None}
    available_weight = sum(POTENTIAL_WEIGHTS[key] for key in available)
    base_score = None
    if available_weight:
        base_score = (
            sum(float(value) * POTENTIAL_WEIGHTS[key] for key, value in available.items())
            / available_weight
        )
    confidence = sum(
        POTENTIAL_WEIGHTS[key] * min(max(completeness.get(key, 0.0), 0.0), 1.0)
        for key in POTENTIAL_WEIGHTS
    )
    hype_penalty = 0.0
    if hype_risk is None:
        confidence *= MISSING_HYPE_CONFIDENCE_FACTOR
    else:
        hype_penalty = clamp(float(hype_risk)) * HYPE_PENALTY_WEIGHT
    score = None if base_score is None else clamp(base_score - hype_penalty)
    return PotentialResult(
        None if score is None else round(score, 6),
        round(min(max(confidence, 0.0), 1.0), 6),
        None if base_score is None else round(base_score, 6),
        round(hype_penalty, 6),
    )


def candidate_flags(
    *,
    potential: float | None,
    confidence: float,
    momentum: float | None,
    community: float | None,
    delivery: float | None,
    hype_status: str,
) -> dict[str, bool]:
    high = potential is not None and potential >= 75 and confidence >= 0.55
    candidate = potential is not None and potential >= 65 and confidence >= 0.45
    breakout = (
        potential is not None
        and potential >= 80
        and confidence >= 0.65
        and momentum is not None
        and momentum >= 75
        and community is not None
        and community >= 60
        and delivery is not None
        and delivery >= 50
        and hype_status not in {"HIGH", "INSUFFICIENT_HISTORY"}
    )
    return {
        "high_potential": high,
        "potential_candidate": candidate,
        "breakout_candidate": breakout,
    }
