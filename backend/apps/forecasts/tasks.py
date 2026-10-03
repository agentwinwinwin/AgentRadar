from celery import shared_task
from django.utils import timezone

from .locks import RedisPredictionRolloutLock, RedisTrainingLock
from .models import MLModel, ModelTrainingRun, PredictionRolloutStatus, TrainingRunStatus
from .services import (
    ForecastService,
    ForecastTrainingService,
    StarPercentileRolloutService,
    TrainingBlockedError,
)


@shared_task(name="forecasts.train_models", soft_time_limit=6900, time_limit=7200)
def train_models(run_id: int | None = None) -> dict:
    if run_id is None:
        result = ForecastTrainingService().train()
        return {
            "model_versions": [model.model_version for model in result["models"]],
            "selected_model_version": result["selected_model_version"],
            "forecast_status": result["forecast_status"],
        }
    run = ModelTrainingRun.objects.get(pk=run_id)
    if run.status != TrainingRunStatus.QUEUED:
        return {"run_id": run.id, "status": run.status, **run.result}
    with RedisTrainingLock() as lock:
        if not lock.acquired:
            run.status = TrainingRunStatus.FAILED
            run.error_code = "TRAINING_LOCK_BUSY"
            run.error_message = "训练锁被占用，请稍后重新发起。"
            run.finished_at = timezone.now()
            run.save(update_fields=("status", "error_code", "error_message", "finished_at"))
            return {"run_id": run.id, "status": run.status}
        run.status = TrainingRunStatus.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=("status", "started_at"))
        try:
            result = ForecastTrainingService(label_version=run.label_version).train()
        except TrainingBlockedError as exc:
            run.status = TrainingRunStatus.BLOCKED
            run.error_code = "DATASET_GATE_BLOCKED"
            run.error_message = "训练开始前 Dataset Quality Gate 已不再满足。"
            run.dataset_gate_snapshot = {
                "passed": False,
                "checks": exc.gate.checks,
                "quality": exc.gate.report,
            }
        except Exception:
            run.status = TrainingRunStatus.FAILED
            run.error_code = "TRAINING_FAILED"
            run.error_message = "模型训练失败，请管理员检查 ML Worker 日志。"
        else:
            run.status = TrainingRunStatus.COMPLETED
            run.result = {
                "model_versions": [model.model_version for model in result["models"]],
                "selected_model_version": result["selected_model_version"],
                "model_status_ceiling": "VALIDATED",
                "forecast_status": "NOT_READY",
                "automatic_activation": False,
            }
        run.finished_at = timezone.now()
        run.save(
            update_fields=(
                "status", "dataset_gate_snapshot", "result", "error_code",
                "error_message", "finished_at",
            )
        )
        return {"run_id": run.id, "status": run.status, **run.result}


@shared_task(name="forecasts.run_forecast")
def run_forecast(repository_id: int) -> dict:
    forecast = ForecastService().run(repository_id)
    return {"forecast_id": forecast.id, "model_version": forecast.model_version}


@shared_task(
    name="forecasts.dispatch_star_percentile_rollout", soft_time_limit=6900, time_limit=7200
)
def dispatch_star_percentile_rollout(model_version: str) -> dict:
    model = MLModel.objects.get(model_version=model_version)
    if model.prediction_rollout_status == PredictionRolloutStatus.COMPLETED:
        return {"model_version": model_version, **model.prediction_rollout}
    with RedisPredictionRolloutLock(model_version) as lock:
        if not lock.acquired:
            return {"model_version": model_version, "status": "LOCKED"}
        model.prediction_rollout_status = PredictionRolloutStatus.RUNNING
        model.prediction_rollout = {
            **model.prediction_rollout,
            "started_at": timezone.now().isoformat(),
        }
        model.save(update_fields=("prediction_rollout_status", "prediction_rollout"))
        try:
            counts = StarPercentileRolloutService().run(model_version)
        except Exception as exc:
            model.prediction_rollout_status = PredictionRolloutStatus.FAILED
            model.prediction_rollout = {
                **model.prediction_rollout,
                "finished_at": timezone.now().isoformat(),
                "error": type(exc).__name__,
            }
        else:
            model.prediction_rollout_status = (
                PredictionRolloutStatus.COMPLETED
                if counts["failed"] == 0
                else PredictionRolloutStatus.PARTIAL
            )
            model.prediction_rollout = {
                **model.prediction_rollout,
                **counts,
                "finished_at": timezone.now().isoformat(),
            }
        model.save(update_fields=("prediction_rollout_status", "prediction_rollout"))
        return {
            "model_version": model_version,
            "status": model.prediction_rollout_status,
            **model.prediction_rollout,
        }


@shared_task(name="forecasts.predict_newly_eligible_star_repositories")
def predict_newly_eligible_star_repositories(model_version: str) -> dict:
    """Predict each newly eligible repository once for the current ACTIVE model."""
    model = MLModel.objects.filter(
        model_version=model_version,
        status="ACTIVE",
        feature_version=StarPercentileRolloutService.FEATURE_VERSION,
    ).first()
    if model is None:
        return {"model_version": model_version, "status": "SKIPPED", "reason": "MODEL_NOT_ACTIVE"}
    with RedisPredictionRolloutLock(model_version) as lock:
        if not lock.acquired:
            return {"model_version": model_version, "status": "LOCKED"}
        counts = StarPercentileRolloutService().run(
            model_version,
            only_missing=True,
            limit=200,
        )
    return {"model_version": model_version, "status": "COMPLETED", **counts}
