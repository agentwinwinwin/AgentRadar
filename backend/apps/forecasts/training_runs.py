from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.datasets.models import TrainingSample
from apps.datasets.services import FEATURE_VERSION, PERCENTILE_LABEL_VERSION

from .models import ModelTrainingRun, TrainingRunStatus
from .services import DatasetEarlyStopService

TRAINING_LABEL_VERSION = PERCENTILE_LABEL_VERSION
TRAINING_CONFIRMATION = f"START TRAINING {TRAINING_LABEL_VERSION}"
STALE_AFTER = timedelta(hours=2)


def serialize_run(run: ModelTrainingRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "feature_version": run.feature_version,
        "label_version": run.label_version,
        "celery_task_id": run.celery_task_id,
        "requested_by": run.requested_by.get_username(),
        "requested_at": run.requested_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "dataset_gate_snapshot": run.dataset_gate_snapshot,
        "split_readiness_snapshot": run.split_readiness_snapshot,
        "result": run.result,
        "error_code": run.error_code or None,
        "error_message": run.error_message or None,
    }


class TrainingRunService:
    @staticmethod
    def _queryset():
        return TrainingSample.objects.filter(
            feature_version=FEATURE_VERSION,
            label_version=TRAINING_LABEL_VERSION,
        )

    @classmethod
    def recover_stale(cls) -> None:
        cutoff = timezone.now() - STALE_AFTER
        ModelTrainingRun.objects.filter(
            status=TrainingRunStatus.RUNNING,
            started_at__lt=cutoff,
        ).update(
            status=TrainingRunStatus.FAILED,
            error_code="STALE_RUN",
            error_message="训练 Worker 未在时限内完成，请检查 ML Worker 后重新发起。",
            finished_at=timezone.now(),
        )

    @classmethod
    def readiness(cls) -> dict[str, Any]:
        cls.recover_stale()
        evaluation = DatasetEarlyStopService(label_version=TRAINING_LABEL_VERSION).evaluate(
            cls._queryset()
        )
        active = ModelTrainingRun.objects.filter(
            status__in=(TrainingRunStatus.QUEUED, TrainingRunStatus.RUNNING)
        ).first()
        return {
            **evaluation,
            "can_start": bool(evaluation["early_stop"] and active is None),
            "blocking_run_id": active.id if active else None,
            "feature_version": FEATURE_VERSION,
            "label_version": TRAINING_LABEL_VERSION,
            "confirmation_text": TRAINING_CONFIRMATION,
            "evaluated_at": timezone.now().isoformat(),
        }

    @classmethod
    def request(cls, *, user, confirmation: str) -> ModelTrainingRun:
        if confirmation != TRAINING_CONFIRMATION:
            raise ValueError("请输入完整训练确认文本")
        readiness = cls.readiness()
        if not readiness["early_stop"]:
            raise RuntimeError("Dataset Quality Gate 或 Time-based Split 尚未通过")
        if readiness["blocking_run_id"]:
            raise RuntimeError("已有训练任务正在排队或运行")
        task_id = uuid4().hex
        try:
            with transaction.atomic():
                run = ModelTrainingRun.objects.create(
                    requested_by=user,
                    feature_version=FEATURE_VERSION,
                    label_version=TRAINING_LABEL_VERSION,
                    celery_task_id=task_id,
                    dataset_gate_snapshot={
                        "passed": readiness["quality_gate_passed"],
                        "checks": readiness["checks"],
                        "quality": readiness["quality"],
                        "evaluated_at": readiness["evaluated_at"],
                    },
                    split_readiness_snapshot={
                        "passed": readiness["time_split_ready"],
                        "counts": readiness["split_counts"],
                    },
                )
                from .tasks import train_models

                transaction.on_commit(
                    lambda: train_models.apply_async(args=(run.id,), task_id=task_id, queue="ml")
                )
        except IntegrityError as exc:
            raise RuntimeError("已有训练任务正在排队或运行") from exc
        return run

    @classmethod
    def dashboard(cls) -> dict[str, Any]:
        readiness = cls.readiness()
        runs = ModelTrainingRun.objects.select_related("requested_by")[:10]
        return {"readiness": readiness, "runs": [serialize_run(run) for run in runs]}
