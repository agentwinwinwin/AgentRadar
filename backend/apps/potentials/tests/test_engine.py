import pytest

from apps.potentials.engine import calculate_potential, candidate_flags


def test_potential_is_deterministic_and_missing_values_reduce_confidence() -> None:
    values = {
        "trend": 80.0,
        "momentum": 90.0,
        "topic_momentum": None,
        "community": 70.0,
        "delivery": 60.0,
        "novelty": None,
    }
    completeness = {
        "trend": 0.8,
        "momentum": 1.0,
        "topic_momentum": 0.0,
        "community": 1.0,
        "delivery": 1.0,
        "novelty": 0.0,
    }

    first = calculate_potential(values, completeness, None)
    second = calculate_potential(values, completeness, None)

    assert first == second
    assert first.score == pytest.approx(77.857143)
    assert first.hype_penalty == 0.0
    assert first.confidence == pytest.approx(0.5525)


def test_real_zero_is_not_missing_and_hype_penalty_is_applied() -> None:
    values = {key: 0.0 for key in ("trend", "momentum", "community", "delivery")}
    values.update({"topic_momentum": None, "novelty": None})
    completeness = {key: 1.0 if value is not None else 0.0 for key, value in values.items()}

    result = calculate_potential(values, completeness, 40.0)

    assert result.base_score == 0.0
    assert result.hype_penalty == 6.0
    assert result.score == 0.0
    assert result.confidence == pytest.approx(0.7)


def test_small_project_cannot_rank_from_momentum_alone() -> None:
    result = calculate_potential(
        {
            "trend": 20.0,
            "momentum": 100.0,
            "topic_momentum": None,
            "community": 10.0,
            "delivery": 10.0,
            "novelty": None,
        },
        {
            "trend": 0.8,
            "momentum": 1.0,
            "topic_momentum": 0.0,
            "community": 1.0,
            "delivery": 1.0,
            "novelty": 0.0,
        },
        None,
    )
    flags = candidate_flags(
        potential=result.score,
        confidence=result.confidence,
        momentum=100.0,
        community=10.0,
        delivery=10.0,
        hype_status="INSUFFICIENT_HISTORY",
    )

    assert result.score == pytest.approx(39.285714)
    assert flags == {
        "high_potential": False,
        "potential_candidate": False,
        "breakout_candidate": False,
    }


def test_breakout_requires_multiple_signals_and_known_non_high_hype() -> None:
    assert (
        candidate_flags(
            potential=90,
            confidence=0.7,
            momentum=90,
            community=80,
            delivery=70,
            hype_status="LOW",
        )["breakout_candidate"]
        is True
    )
    assert (
        candidate_flags(
            potential=90,
            confidence=0.7,
            momentum=90,
            community=80,
            delivery=70,
            hype_status="INSUFFICIENT_HISTORY",
        )["breakout_candidate"]
        is False
    )
