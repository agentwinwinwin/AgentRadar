from django.db import transaction

from apps.forecasts.models import MLModel, ModelStatus
from apps.forecasts.services import ModelActivationService
from apps.forecasts.training_runs import TrainingRunService


class AdminControlCenterService:
    @staticmethod
    def models() -> list[dict]:
        results = []
        for model in MLModel.objects.order_by("-created_at"):
            eligible, reasons = ModelActivationService.eligibility(model)
            results.append(
                {
                    "id": model.id,
                    "model_name": model.model_name,
                    "model_version": model.model_version,
                    "feature_version": model.feature_version,
                    "label_version": model.label_version,
                    "algorithm": model.algorithm,
                    "status": model.status,
                    "training_start": model.training_start.isoformat(),
                    "training_end": model.training_end.isoformat(),
                    "validation_metrics": model.validation_metrics,
                    "test_metrics": model.test_metrics,
                    "dataset_quality": model.dataset_quality,
                    "feature_importance": model.feature_importance,
                    "artifact_sha256": model.artifact_sha256,
                    "activation_eligible": eligible,
                    "activation_blockers": reasons,
                    "activated_at": model.activated_at.isoformat() if model.activated_at else None,
                    "prediction_rollout_status": model.prediction_rollout_status,
                    "prediction_rollout": model.prediction_rollout,
                    "retraining_targets": model.retraining_targets,
                    "created_at": model.created_at.isoformat(),
                }
            )
        return results

    @staticmethod
    @transaction.atomic
    def activate(*, model_version: str) -> MLModel:
        return ModelActivationService().activate(model_version)

    @staticmethod
    def product_status() -> dict:
        active = MLModel.objects.filter(status=ModelStatus.ACTIVE).order_by("-created_at").first()
        validated_count = MLModel.objects.filter(status=ModelStatus.VALIDATED).count()
        return {
            "forecast_status": "READY" if active else "NOT_READY",
            "active_model_version": active.model_version if active else None,
            "validated_model_count": validated_count,
            "forecast_definition": "未来30天进入同 Category 高开发活跃增长组的概率",
            "automatic_activation": False,
        }

    @staticmethod
    def training() -> dict:
        return TrainingRunService.dashboard()
