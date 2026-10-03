from datetime import date
from unittest.mock import patch

import pytest
from django.conf import settings

from apps.datasets.tasks import backfill_repository_activity, build_training_samples
from apps.datasets.tests.test_backfill import create_repository


def test_dataset_tasks_use_backfill_queue() -> None:
    assert settings.CELERY_TASK_ROUTES["datasets.*"]["queue"] == "github_backfill"


@pytest.mark.django_db
def test_backfill_task_uses_github_client_boundary() -> None:
    repository = create_repository()
    with (
        patch("apps.datasets.tasks.RealGitHubClient") as client_class,
        patch("apps.datasets.tasks.HistoricalBackfillService.collect") as collect,
    ):
        collect.return_value.windows = (1, 2, 3)
        collect.return_value.created = 3
        result = backfill_repository_activity.run(repository.id, "2026-06-01")

    client_class.assert_called_once_with()
    collect.assert_called_once_with(repository, date(2026, 6, 1))
    assert result["windows"] == 3


@pytest.mark.django_db
def test_build_task_runs_database_builder() -> None:
    with patch("apps.datasets.tasks.DatasetBuilder.build", return_value={"created": 0}) as build:
        result = build_training_samples.run("2026-06-01")

    build.assert_called_once_with(date(2026, 6, 1))
    assert result == {"created": 0}
