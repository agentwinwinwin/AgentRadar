from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operations.models import RepositoryScoreHistory
from apps.operations.services import record_score_history
from apps.potentials.models import RepositoryPotentialScore
from apps.watchlists.models import Alert
from apps.watchlists.services import AlertService
from apps.watchlists.tests.test_services import repository


@pytest.mark.django_db
def test_score_history_is_bucket_idempotent_and_never_backfills():
    score = RepositoryPotentialScore.objects.create(
        repository=repository(),
        potential_score=50,
        confidence=0.8,
        algorithm_version="potential-test",
        calculated_at=timezone.now(),
    )
    first = record_score_history(score, RepositoryScoreHistory.ScoreType.POTENTIAL)
    score.potential_score = 55
    score.save(update_fields=("potential_score",))
    second = record_score_history(score, RepositoryScoreHistory.ScoreType.POTENTIAL)
    assert first.id == second.id
    assert RepositoryScoreHistory.objects.count() == 1
    assert float(second.score) == 55


@pytest.mark.django_db
def test_change_alert_requires_two_real_history_rows():
    repo = repository()
    now = timezone.now()
    RepositoryScoreHistory.objects.create(
        repository=repo,
        score_type=RepositoryScoreHistory.ScoreType.POTENTIAL,
        algorithm_version="potential-test",
        score=50,
        confidence=0.8,
        evidence={},
        history_bucket="20260817-00",
        calculated_at=now - timedelta(days=1),
    )
    assert AlertService.evaluate_repository(repo.id)["created"] == 0
    RepositoryScoreHistory.objects.create(
        repository=repo,
        score_type=RepositoryScoreHistory.ScoreType.POTENTIAL,
        algorithm_version="potential-test",
        score=70,
        confidence=0.8,
        evidence={},
        history_bucket="20260818-00",
        calculated_at=now,
    )
    assert AlertService.evaluate_repository(repo.id)["created"] == 1
    assert Alert.objects.get().alert_type == Alert.Type.POTENTIAL_CHANGE
