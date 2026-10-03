from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, transaction

from apps.github.fakes import FakeGitHubClient
from apps.potentials.engine import ALGORITHM_VERSION
from apps.potentials.models import RepositoryPotentialScore
from apps.potentials.services import PotentialService
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.trends.engine import ALGORITHM_VERSION as TREND_ALGORITHM_VERSION
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore


def create_trend(*, hype_risk=None, hype_status=HypeRiskStatus.INSUFFICIENT_HISTORY):
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload()
    )
    trend = RepositoryTrendScore.objects.create(
        repository=repository,
        trend_score=80,
        momentum_score=90,
        development_score=70,
        community_score=70,
        delivery_score=60,
        adoption_score=50,
        topic_momentum_score=None,
        maintenance_score=60,
        hype_risk=hype_risk,
        hype_risk_status=hype_status,
        lifecycle_stage=LifecycleStage.GROWING,
        data_completeness=0.8,
        algorithm_version=TREND_ALGORITHM_VERSION,
        calculated_at=datetime(2026, 8, 16, tzinfo=UTC),
        evidence={
            "components": {
                "momentum": {"completeness": 1.0},
                "topic_momentum": {"completeness": 0.0},
                "community": {"completeness": 1.0},
                "delivery": {"completeness": 1.0},
            }
        },
    )
    return repository, trend


@pytest.mark.django_db
def test_service_upserts_versioned_score_and_explains_missing_hype() -> None:
    repository, trend = create_trend()
    service = PotentialService()

    first = service.calculate_repository(repository.id)
    second = service.calculate_repository(repository.id)

    assert first.created is True
    assert second.created is False
    assert RepositoryPotentialScore.objects.filter(repository=repository).count() == 1
    assert second.potential.algorithm_version == ALGORITHM_VERSION
    assert float(second.potential.potential_score) == pytest.approx(77.86)
    assert second.potential.confidence == pytest.approx(0.5525)
    assert second.potential.evidence["source_trend"]["id"] == trend.id
    assert second.potential.evidence["hype_penalty"] == 0.0
    assert "hype_risk" in second.potential.evidence["missing_inputs"]
    assert second.potential.evidence["candidate_flags"]["high_potential"] is True
    assert second.potential.evidence["candidate_flags"]["breakout_candidate"] is False


@pytest.mark.django_db
def test_known_hype_applies_penalty_without_confidence_reduction() -> None:
    repository, _ = create_trend(hype_risk=20, hype_status=HypeRiskStatus.LOW)

    result = PotentialService().calculate_repository(repository.id).potential

    assert float(result.potential_score) == pytest.approx(74.86)
    assert result.confidence == pytest.approx(0.65)
    assert result.evidence["hype_penalty"] == 3.0


@pytest.mark.django_db
def test_database_rejects_confidence_outside_unit_interval() -> None:
    repository, _ = create_trend()

    with pytest.raises(IntegrityError), transaction.atomic():
        RepositoryPotentialScore.objects.create(
            repository=repository,
            potential_score=50,
            confidence=1.1,
            algorithm_version="invalid",
            calculated_at=datetime(2026, 8, 16, tzinfo=UTC),
        )
