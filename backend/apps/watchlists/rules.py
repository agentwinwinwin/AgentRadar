from dataclasses import dataclass

RULE_VERSION = "alerts-v1.0.0"
REPORT_VERSION = "reports-v1.0.0"


@dataclass(frozen=True)
class AlertThresholds:
    snapshot_min_completeness: float = 0.8
    trend_min_completeness: float = 0.5
    potential_min_confidence: float = 0.45
    star_7d_absolute: int = 100
    star_7d_percent: float = 20.0
    fork_7d_absolute: int = 20
    fork_7d_percent: float = 20.0
    trend_change: float = 15.0
    potential_change: float = 15.0
    activity_surge_multiplier: float = 2.0
    activity_surge_min_commits: int = 20
    release_lookback_days: int = 30
    dormant_days: int = 90
    high_potential_score: float = 80.0


THRESHOLDS = AlertThresholds()
