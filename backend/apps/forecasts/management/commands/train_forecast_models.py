import json

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.models import TrainingSample
from apps.datasets.services import PERCENTILE_LABEL_VERSION
from apps.forecasts.services import (
    ForecastTrainingService,
    PercentileRegressionService,
    TrainingBlockedError,
)


class Command(BaseCommand):
    help = "Train and evaluate Forecast V1 models after enforcing the dataset gate."

    def add_arguments(self, parser):
        parser.add_argument("--label-version", default=PERCENTILE_LABEL_VERSION)

    def handle(self, *args, **options):
        service = ForecastTrainingService(label_version=options["label_version"])
        try:
            result = service.train()
        except TrainingBlockedError as exc:
            payload = {
                "forecast_status": "NOT_READY",
                "quality_gate": {
                    "passed": exc.gate.passed,
                    "checks": exc.gate.checks,
                    "report": exc.gate.report,
                },
            }
            raise CommandError(json.dumps(payload, sort_keys=True)) from exc
        samples = list(
            TrainingSample.objects.filter(label_version=options["label_version"]).order_by(
                "sample_at", "id"
            )
        )
        selected = next(
            model
            for model in result["models"]
            if model.model_version == result["selected_model_version"]
        )
        regression = (
            PercentileRegressionService().train()
            if options["label_version"] == PERCENTILE_LABEL_VERSION
            else None
        )
        learning_curve = service.learning_curve(samples, algorithm=selected.algorithm)
        self.stdout.write(
            json.dumps(
                {
                    "forecast_status": result["forecast_status"],
                    "selected_model_version": result["selected_model_version"],
                    "models": [
                        {
                            "algorithm": model.algorithm,
                            "model_version": model.model_version,
                            "status": model.status,
                            "validation_metrics": model.validation_metrics,
                            "test_metrics": model.test_metrics,
                        }
                        for model in result["models"]
                    ],
                    "regression": (
                        {
                            "model_version": regression["model"].model_version,
                            "status": regression["model"].status,
                            "validation_metrics": regression["validation_metrics"],
                            "test_metrics": regression["test_metrics"],
                        }
                        if regression
                        else None
                    ),
                    "learning_curve": learning_curve,
                },
                sort_keys=True,
            )
        )
