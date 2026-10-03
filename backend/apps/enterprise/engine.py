from dataclasses import dataclass

ALGORITHM_VERSION = "enterprise-v1.1.0"
WEIGHTS = {
    "maintenance": 20,
    "community": 15,
    "delivery": 15,
    "security": 15,
    "license": 10,
    "documentation": 10,
    "architecture_operations": 10,
    "risk": 5,
}


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    confidence: float
    recommendation: str


def calculate(values: dict[str, float | None], hype_risk: float | None) -> ScoreResult:
    available = [(WEIGHTS[key], value) for key, value in values.items() if value is not None]
    available_weight = sum(weight for weight, _ in available)
    if not available_weight:
        return ScoreResult(None, 0.0, "WATCH")
    score = sum(weight * float(value) for weight, value in available) / available_weight
    if hype_risk is not None:
        score -= min(max(hype_risk, 0), 100) * 0.1
    score = round(min(max(score, 0), 100), 2)
    recommendation = (
        "ADOPT" if score >= 80 else "POC" if score >= 65 else "WATCH" if score >= 40 else "AVOID"
    )
    return ScoreResult(score, available_weight / 100, recommendation)
