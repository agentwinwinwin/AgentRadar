from unittest.mock import patch

import pytest
from django.conf import settings

from apps.potentials.models import RepositoryPotentialScore
from apps.potentials.tasks import calculate_all_potential_scores, calculate_potential_score
from apps.potentials.tests.test_services import create_trend


@pytest.mark.django_db
def test_potential_task_is_idempotent() -> None:
    repository, _ = create_trend()

    with patch("apps.potentials.tasks.dispatch_unique_repository_task") as alert_dispatch:
        first = calculate_potential_score.run(repository.id)
        second = calculate_potential_score.run(repository.id)

    assert first["created"] is True
    assert second["created"] is False
    assert RepositoryPotentialScore.objects.filter(repository=repository).count() == 1
    assert alert_dispatch.call_count == 2


@pytest.mark.django_db
def test_potential_dispatcher_uses_persisted_trends() -> None:
    repository, _ = create_trend()
    with patch("apps.potentials.tasks.dispatch_potential_score", return_value=True) as dispatch:
        result = calculate_all_potential_scores.run()

    assert result == {"dispatched": 1}
    dispatch.assert_called_once_with(repository.id)


def test_potential_tasks_use_scoring_queue() -> None:
    assert settings.CELERY_TASK_ROUTES["potentials.*"]["queue"] == "scoring"
