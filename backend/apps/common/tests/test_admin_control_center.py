from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.forecasts.models import MLModel, ModelStatus
from apps.forecasts.training_runs import TRAINING_CONFIRMATION


def create_validated_model() -> MLModel:
    now = timezone.now()
    metrics = {
        "accuracy": 0.70,
        "precision": 0.60,
        "recall": 0.55,
        "f1": 0.57,
        "roc_auc": 0.72,
        "pr_auc": 0.51,
        "confusion_matrix": [[8, 2], [3, 7]],
    }
    return MLModel.objects.create(
        model_name="activity-growth-30d",
        model_version="forecast-v1-admin-test",
        feature_version="feature-v1",
        label_version="label-v1.2.0",
        algorithm="logistic_regression",
        training_start=now - timedelta(days=180),
        training_end=now - timedelta(days=30),
        validation_metrics=metrics,
        test_metrics=metrics,
        dataset_quality={"passed": True, "fingerprint": "test"},
        feature_importance={"commit_30d": 0.4},
        artifact_path="/not/executed/model.joblib",
        artifact_sha256="a" * 64,
        status=ModelStatus.VALIDATED,
    )


@pytest.mark.django_db
def test_control_center_is_invisible_to_regular_users() -> None:
    user = get_user_model().objects.create_user(username="regular", password="password123")
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/v1/operations/control-center")

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_can_read_model_gate_without_artifact_path() -> None:
    model = create_validated_model()
    staff = get_user_model().objects.create_user(
        username="operator", password="password123", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(staff)

    response = client.get("/api/v1/operations/control-center")

    assert response.status_code == 200
    candidate = response.data["models"][0]
    assert candidate["model_version"] == model.model_version
    assert candidate["activation_eligible"] is True
    assert "artifact_path" not in candidate
    assert response.data["product"]["automatic_activation"] is False


@pytest.mark.django_db
def test_activation_requires_staff_and_exact_model_version_confirmation() -> None:
    model = create_validated_model()
    staff = get_user_model().objects.create_user(
        username="operator", password="password123", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(staff)
    url = f"/api/v1/operations/models/{model.model_version}/activate"

    rejected = client.post(url, {"confirmation": "wrong"}, format="json")
    accepted = client.post(url, {"confirmation": model.model_version}, format="json")

    assert rejected.status_code == 400
    assert accepted.status_code == 200
    assert accepted.data["status"] == ModelStatus.ACTIVE
    model.refresh_from_db()
    assert model.status == ModelStatus.ACTIVE


@pytest.mark.django_db
def test_training_start_requires_staff() -> None:
    user = get_user_model().objects.create_user(username="regular2", password="password123")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/v1/operations/training/start",
        {"confirmation": TRAINING_CONFIRMATION},
        format="json",
    )

    assert response.status_code == 403
