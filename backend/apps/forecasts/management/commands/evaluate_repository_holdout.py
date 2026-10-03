import json

import numpy as np
from django.core.management.base import BaseCommand
from sklearn.model_selection import GroupShuffleSplit

from apps.datasets.models import TrainingSample
from apps.datasets.services import FEATURE_VERSION, PERCENTILE_LABEL_VERSION
from apps.forecasts.services import ForecastTrainingService, _matrix, _metrics, _rows


class Command(BaseCommand):
    help = "Run an auxiliary repository-disjoint XGBoost evaluation without Registry writes."

    def handle(self, *args, **options):
        samples = list(
            TrainingSample.objects.filter(
                feature_version=FEATURE_VERSION,
                label_version=PERCENTILE_LABEL_VERSION,
            )
            .select_related("repository")
            .order_by("sample_at", "id")
        )
        if len(samples) < 200 or len({item.repository_id for item in samples}) < 40:
            self.stdout.write(json.dumps({"status": "INSUFFICIENT_DATA_FOR_REPOSITORY_HOLDOUT"}))
            return
        groups = np.asarray([item.repository_id for item in samples])
        indexes = np.arange(len(samples))
        split = None
        for seed in range(42, 62):
            candidate = next(
                GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(
                    indexes, groups=groups
                )
            )
            train_idx, test_idx = candidate
            if (
                len({samples[i].label for i in train_idx}) == 2
                and len({samples[i].label for i in test_idx}) == 2
            ):
                split = candidate
                break
        if split is None:
            self.stdout.write(json.dumps({"status": "INSUFFICIENT_DATA_FOR_REPOSITORY_HOLDOUT"}))
            return
        train_idx, test_idx = split
        train = [samples[i] for i in train_idx]
        test = [samples[i] for i in test_idx]
        pipeline = ForecastTrainingService._pipeline(
            ForecastTrainingService.ALGORITHMS["xgboost"]()
        )
        pipeline.fit(_matrix(_rows(train)), np.asarray([item.label for item in train]))
        metrics = _metrics(
            np.asarray([item.label for item in test]),
            pipeline.predict_proba(_matrix(_rows(test)))[:, 1],
        )
        train_repositories = {item.repository_id for item in train}
        test_repositories = {item.repository_id for item in test}
        result = {
            "status": "COMPLETED",
            "repository_overlap": len(train_repositories & test_repositories),
            "training_repositories": len(train_repositories),
            "holdout_repositories": len(test_repositories),
            "training_samples": len(train),
            "holdout_samples": len(test),
            "holdout_positive": sum(item.label == 1 for item in test),
            "holdout_negative": sum(item.label == 0 for item in test),
            "metrics": metrics,
        }
        self.stdout.write(json.dumps(result, sort_keys=True))
