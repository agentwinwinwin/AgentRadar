from django.urls import path

from .views import (
    AdminControlCenterView,
    AdminModelActivationView,
    AdminTrainingReadinessView,
    AdminTrainingRunView,
    AdminTrainingStartView,
    HealthView,
    LivenessView,
    OperationsStatusView,
    ReadinessView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/live", LivenessView.as_view(), name="health-live"),
    path("health/ready", ReadinessView.as_view(), name="health-ready"),
    path("operations/status", OperationsStatusView.as_view(), name="operations-status"),
    path("operations/control-center", AdminControlCenterView.as_view(), name="control-center"),
    path("operations/training/check", AdminTrainingReadinessView.as_view(), name="training-check"),
    path("operations/training/start", AdminTrainingStartView.as_view(), name="training-start"),
    path(
        "operations/training/runs/<int:run_id>",
        AdminTrainingRunView.as_view(),
        name="training-run",
    ),
    path(
        "operations/models/<str:model_version>/activate",
        AdminModelActivationView.as_view(),
        name="control-center-model-activate",
    ),
]
