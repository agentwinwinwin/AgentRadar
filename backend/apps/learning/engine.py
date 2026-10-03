from dataclasses import dataclass

ALGORITHM_VERSION = "learning-v1.1.0"
WEIGHTS = {
    "development_activity": 25,
    "documentation": 25,
    "architecture_learning": 20,
    "community": 15,
    "delivery": 10,
    "maintenance": 5,
}


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    confidence: float


def calculate(values: dict[str, float | None]) -> ScoreResult:
    available = [(WEIGHTS[key], value) for key, value in values.items() if value is not None]
    available_weight = sum(weight for weight, _ in available)
    if not available_weight:
        return ScoreResult(None, 0.0)
    score = sum(weight * float(value) for weight, value in available) / available_weight
    return ScoreResult(round(min(max(score, 0), 100), 2), available_weight / 100)
