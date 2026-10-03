from datetime import date

import pytest

from apps.trends.engine import (
    HypeResult,
    age_cohort,
    hype_risk,
    lifecycle_stage,
    percentile_ranks,
    weighted_component,
)
from apps.trends.models import HypeRiskStatus, LifecycleStage


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [
        (0, "AGE_0_30"),
        (30, "AGE_0_30"),
        (31, "AGE_31_180"),
        (180, "AGE_31_180"),
        (181, "AGE_181_730"),
        (730, "AGE_181_730"),
        (731, "AGE_731_PLUS"),
    ],
)
def test_age_cohort_boundaries(age_days: int, expected: str) -> None:
    calculation_date = date(2026, 8, 16)
    created_at = calculation_date.fromordinal(calculation_date.toordinal() - age_days)
    assert age_cohort(created_at, calculation_date) == expected


def test_percentile_is_tie_aware_order_independent_and_excludes_null() -> None:
    first = percentile_ranks({"a": 10, "b": 20, "c": 20, "missing": None, "d": 40})
    second = percentile_ranks({"d": 40, "c": 20, "b": 20, "a": 10, "missing": None})

    assert first == second
    assert first == {"a": 0.0, "b": 50.0, "c": 50.0, "missing": None, "d": 100.0}
    assert percentile_ranks({"only": 7})["only"] == 50.0


def test_weighted_component_distinguishes_null_from_zero_and_clamps_extremes() -> None:
    result = weighted_component(
        {"zero": 0, "missing": None, "extreme": 10_000},
        {"zero": 0.25, "missing": 0.25, "extreme": 0.50},
    )

    assert result.score == pytest.approx(66.666667)
    assert result.completeness == 0.75
    assert result.inputs["zero"] == 0.0
    assert result.inputs["missing"] is None


def test_hype_requires_all_inputs_and_has_stable_boundaries() -> None:
    insufficient = hype_risk(
        star_growth_30d_percentile=None,
        fork_delta_30d_percentile=10,
        development_score=10,
        community_score=10,
    )
    low = hype_risk(
        star_growth_30d_percentile=40,
        fork_delta_30d_percentile=10,
        development_score=10,
        community_score=10,
    )
    high = hype_risk(
        star_growth_30d_percentile=100,
        fork_delta_30d_percentile=0,
        development_score=0,
        community_score=0,
    )

    assert insufficient == HypeResult(None, HypeRiskStatus.INSUFFICIENT_HISTORY)
    assert low == HypeResult(30.0, HypeRiskStatus.LOW)
    assert high == HypeResult(100.0, HypeRiskStatus.HIGH)


def test_lifecycle_rules_are_ordered_and_deterministic() -> None:
    hype = HypeResult(20, HypeRiskStatus.LOW)
    assert (
        lifecycle_stage(
            repository_age_days=100,
            archived=False,
            trend_score=90,
            momentum_score=90,
            development_score=80,
            maintenance_score=90,
            hype=hype,
        )
        == LifecycleStage.BREAKOUT
    )
    assert (
        lifecycle_stage(
            repository_age_days=100,
            archived=True,
            trend_score=100,
            momentum_score=100,
            development_score=100,
            maintenance_score=100,
            hype=hype,
        )
        == LifecycleStage.DORMANT
    )
