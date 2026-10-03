from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.datasets.services import FEATURE_VERSION, PERCENTILE_LABEL_VERSION

from ..models import ModelTrainingRun, TrainingRunStatus
from ..tasks import train_models
from ..training_runs import TRAINING_CONFIRMATION, TrainingRunService

LABEL_VERSION = PERCENTILE_LABEL_VERSION


def ready_state() -> dict:
    return {
        "early_stop": True,
        "quality_gate_passed": True,
        "time_split_ready": True,
        "split_counts": {"training": {"samples": 200, "positive": 30, "negative": 170}},
        "checks": {"total_samples": {"actual": 255, "required": 200, "passed": True}},
        "quality": {"total_samples": 255},
        "can_start": True,
        "blocking_run_id": None,
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
        "confirmation_text": TRAINING_CONFIRMATION,
        "evaluated_at": "2026-08-19T00:00:00+00:00",
    }


@pytest.mark.django_db(transaction=True)
def test_training_request_is_persisted_and_dispatched_to_ml_queue(monkeypatch) -> None:
    user = get_user_model().objects.create_user(username="trainer", password="password123")
    dispatched = {}
    monkeypatch.setattr(TrainingRunService, "readiness", classmethod(lambda cls: ready_state()))
    monkeypatch.setattr(
        train_models,
        "apply_async",
        lambda *, args, task_id, queue: dispatched.update(
            {"args": args, "task_id": task_id, "queue": queue}
        ),
    )

    run = TrainingRunService.request(user=user, confirmation=TRAINING_CONFIRMATION)

    assert run.status == TrainingRunStatus.QUEUED
    assert dispatched == {"args": (run.id,), "task_id": run.celery_task_id, "queue": "ml"}
    with pytest.raises(RuntimeError, match="正在排队或运行"):
        TrainingRunService.request(user=user, confirmation=TRAINING_CONFIRMATION)


@pytest.mark.django_db
def test_database_allows_only_one_inflight_training() -> None:
    user = get_user_model().objects.create_user(username="trainer2", password="password123")
    common = {
        "requested_by": user,
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
        "dataset_gate_snapshot": {},
        "split_readiness_snapshot": {},
    }
    ModelTrainingRun.objects.create(celery_task_id="first", **common)

    with pytest.raises(IntegrityError):
        ModelTrainingRun.objects.create(celery_task_id="second", **common)


@pytest.mark.django_db
def test_training_task_completes_without_automatic_activation(monkeypatch) -> None:
    user = get_user_model().objects.create_user(username="trainer3", password="password123")
    run = ModelTrainingRun.objects.create(
        requested_by=user,
        feature_version=FEATURE_VERSION,
        label_version=LABEL_VERSION,
        celery_task_id="task-success",
    )

    class Lock:
        acquired = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    models = [SimpleNamespace(model_version="forecast-v1-real", status="VALIDATED")]
    monkeypatch.setattr("apps.forecasts.tasks.RedisTrainingLock", Lock)
    monkeypatch.setattr(
        "apps.forecasts.tasks.ForecastTrainingService.train",
        lambda self: {
            "models": models,
            "selected_model_version": "forecast-v1-real",
            "forecast_status": "NOT_READY",
        },
    )

    result = train_models.run(run.id)
    run.refresh_from_db()

    assert result["status"] == TrainingRunStatus.COMPLETED
    assert run.result["model_status_ceiling"] == "VALIDATED"
    assert run.result["automatic_activation"] is False
    assert run.result["forecast_status"] == "NOT_READY"
