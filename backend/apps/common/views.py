from django.conf import settings
from django.db import connection
from django.utils import timezone
from redis import Redis
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activities.models import RepositoryActivityMetric
from apps.capabilities.models import DataCapability
from apps.forecasts.models import MLModel, ModelTrainingRun
from apps.forecasts.training_runs import TrainingRunService, serialize_run
from apps.snapshots.models import RepositorySnapshot

from .admin_serializers import ModelActivationSerializer, TrainingStartSerializer
from .admin_services import AdminControlCenterService


class HealthView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        return Response({"service": "agentradar-backend", "status": "ok"})


class LivenessView(HealthView):
    pass


def _dependency_state() -> tuple[dict, bool]:
    dependencies: dict[str, dict[str, str]] = {}
    ready = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        dependencies["postgresql"] = {"status": "ok"}
    except Exception as exc:  # pragma: no cover - exercised in deployment smoke
        dependencies["postgresql"] = {"status": "failed", "error": type(exc).__name__}
        ready = False
    try:
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1).ping()
        dependencies["redis"] = {"status": "ok"}
    except Exception as exc:  # pragma: no cover - exercised in deployment smoke
        dependencies["redis"] = {"status": "failed", "error": type(exc).__name__}
        ready = False
    unsafe_secret = settings.SECRET_KEY == "unsafe-development-key"
    production_config_ok = settings.DEBUG or not unsafe_secret
    dependencies["configuration"] = {
        "status": "ok" if production_config_ok else "failed",
    }
    ready = ready and production_config_ok
    dependencies["github"] = {"status": "configured" if bool(settings.GITHUB_TOKEN) else "degraded"}
    dependencies["llm"] = {"status": "configured" if bool(settings.LLM_API_KEY) else "degraded"}
    return dependencies, ready


class ReadinessView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        dependencies, ready = _dependency_state()
        return Response(
            {
                "service": "agentradar-backend",
                "status": "ready" if ready else "not_ready",
                "dependencies": dependencies,
            },
            status=200 if ready else 503,
        )


class OperationsStatusView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        dependencies, ready = _dependency_state()
        latest_snapshot = RepositorySnapshot.objects.order_by("-snapshot_at").first()
        latest_activity = RepositoryActivityMetric.objects.order_by("-updated_at").first()
        return Response(
            {
                "status": "ok" if ready else "degraded",
                "checked_at": timezone.now().isoformat(),
                "dependencies": dependencies,
                "data_freshness": {
                    "latest_snapshot_at": (
                        latest_snapshot.snapshot_at.isoformat() if latest_snapshot else None
                    ),
                    "latest_activity_at": (
                        latest_activity.updated_at.isoformat() if latest_activity else None
                    ),
                },
                "capabilities": [
                    {
                        "name": item.name,
                        "status": item.status,
                        "coverage": item.data_coverage,
                        "first_ready_at": (
                            item.first_ready_at.isoformat() if item.first_ready_at else None
                        ),
                        "last_evaluated_at": item.last_evaluated_at.isoformat(),
                        "reason": item.reason,
                        "algorithm_version": item.algorithm_version,
                        "metrics": item.metrics,
                    }
                    for item in DataCapability.objects.all()
                ],
            }
        )


class AdminControlCenterView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        dependencies, ready = _dependency_state()
        capabilities = [
            {
                "name": item.name,
                "status": item.status,
                "coverage": item.data_coverage,
                "first_ready_at": (
                    item.first_ready_at.isoformat() if item.first_ready_at else None
                ),
                "last_evaluated_at": item.last_evaluated_at.isoformat(),
                "reason": item.reason,
                "algorithm_version": item.algorithm_version,
                "metrics": item.metrics,
            }
            for item in DataCapability.objects.all()
        ]
        return Response(
            {
                "status": "READY" if ready else "DEGRADED",
                "checked_at": timezone.now().isoformat(),
                "dependencies": dependencies,
                "product": AdminControlCenterService.product_status(),
                "capabilities": capabilities,
                "models": AdminControlCenterService.models(),
                "training": AdminControlCenterService.training(),
            }
        )


class AdminTrainingReadinessView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request: Request) -> Response:
        return Response(TrainingRunService.readiness())


class AdminTrainingStartView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request: Request) -> Response:
        serializer = TrainingStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = TrainingRunService.request(
                user=request.user,
                confirmation=serializer.validated_data["confirmation"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(serialize_run(run), status=202)


class AdminTrainingRunView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request: Request, run_id: int) -> Response:
        try:
            run = ModelTrainingRun.objects.select_related("requested_by").get(pk=run_id)
        except ModelTrainingRun.DoesNotExist:
            return Response({"detail": "训练记录不存在"}, status=404)
        return Response(serialize_run(run))


class AdminModelActivationView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request: Request, model_version: str) -> Response:
        serializer = ModelActivationSerializer(
            data=request.data,
            context={"model_version": model_version},
        )
        serializer.is_valid(raise_exception=True)
        try:
            model = AdminControlCenterService.activate(model_version=model_version)
        except MLModel.DoesNotExist:
            return Response({"detail": "候选模型不存在"}, status=404)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(
            {
                "model_version": model.model_version,
                "status": model.status,
                "activated_by": request.user.get_username(),
            }
        )
