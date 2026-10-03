from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from redis import Redis
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from apps.datasets.models import TrainingSample
from apps.datasets.services import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    LABEL_VERSION,
    PERCENTILE_LABEL_VERSION,
    DatasetQualityService,
)
from apps.repositories.models import Repository

from .models import MLModel, ModelStatus, PredictionRolloutStatus, RepositoryForecast

MODEL_NAME = "activity-growth-30d"
FORECAST_DEFINITION = "未来30天进入同 Category 高开发活跃增长组的概率"
FORECAST_DISPLAY_FEATURES = (*FEATURE_NAMES, "age_cohort")
NUMERIC_FEATURES = tuple(name for name in FEATURE_NAMES if name != "category")
CATEGORICAL_FEATURES = ("category", "age_cohort")
QUALITY_GATE_FEATURES = tuple(
    name
    for name in FEATURE_NAMES
    if name
    not in {
        "current_stars",
        "current_forks",
        "days_since_last_push",
        "community_health",
        "topic_momentum",
    }
)


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    checks: dict[str, dict[str, Any]]
    report: dict[str, Any]


class DatasetQualityGate:
    MIN_TOTAL = 200
    MIN_POSITIVE = 20
    MIN_NEGATIVE = 80
    MIN_POSITIVE_RATIO = 0.05
    MAX_POSITIVE_RATIO = 0.45
    MIN_CATEGORIES = 2
    MIN_AGE_COHORTS = 2
    MAX_FEATURE_MISSING_RATE = 0.60
    MIN_TIME_SPAN_DAYS = 90
    MIN_DISTINCT_SAMPLE_DATES = 3

    def __init__(self, *, label_version: str = LABEL_VERSION) -> None:
        if label_version not in {LABEL_VERSION, PERCENTILE_LABEL_VERSION}:
            raise ValueError("unsupported quality gate label version")
        self.label_version = label_version

    def evaluate(self, queryset: QuerySet[TrainingSample] | None = None) -> QualityGateResult:
        queryset = TrainingSample.objects.all() if queryset is None else queryset
        report = DatasetQualityService().report(queryset)
        dates = list(queryset.order_by().values_list("sample_at", flat=True).distinct())
        start = min(dates) if dates else None
        end = max(dates) if dates else None
        span = (end - start).days if start and end else 0
        max_missing = (
            max(
                report["missing_features"][feature]["rate"] or 0.0
                for feature in QUALITY_GATE_FEATURES
            )
            if report["total_samples"]
            else 1.0
        )
        origins_ok = all(
            sample.data_origin == "BACKFILLED"
            and sample.features.get("_provenance", {}).get("data_origin") == "BACKFILLED"
            for sample in queryset
        ) and bool(report["total_samples"])
        versions_ok = set(report["feature_versions"]) == {FEATURE_VERSION} and set(
            report["label_versions"]
        ) == {self.label_version}
        values = {
            "total_samples": (
                report["total_samples"],
                self.MIN_TOTAL,
                report["total_samples"] >= self.MIN_TOTAL,
            ),
            "positive_samples": (
                report["positive_samples"],
                self.MIN_POSITIVE,
                report["positive_samples"] >= self.MIN_POSITIVE,
            ),
            "negative_samples": (
                report["negative_samples"],
                self.MIN_NEGATIVE,
                report["negative_samples"] >= self.MIN_NEGATIVE,
            ),
            "positive_ratio": (
                report["positive_ratio"],
                [self.MIN_POSITIVE_RATIO, self.MAX_POSITIVE_RATIO],
                report["positive_ratio"] is not None
                and self.MIN_POSITIVE_RATIO <= report["positive_ratio"] <= self.MAX_POSITIVE_RATIO,
            ),
            "category_count": (
                len(report["category_distribution"]),
                self.MIN_CATEGORIES,
                len(report["category_distribution"]) >= self.MIN_CATEGORIES,
            ),
            "age_cohort_count": (
                len(report["age_cohort_distribution"]),
                self.MIN_AGE_COHORTS,
                len(report["age_cohort_distribution"]) >= self.MIN_AGE_COHORTS,
            ),
            "maximum_feature_missing_rate": (
                max_missing,
                {
                    "maximum": self.MAX_FEATURE_MISSING_RATE,
                    "evaluated_features": QUALITY_GATE_FEATURES,
                },
                max_missing <= self.MAX_FEATURE_MISSING_RATE,
            ),
            "time_span_days": (span, self.MIN_TIME_SPAN_DAYS, span >= self.MIN_TIME_SPAN_DAYS),
            "distinct_sample_dates": (
                len(dates),
                self.MIN_DISTINCT_SAMPLE_DATES,
                len(dates) >= self.MIN_DISTINCT_SAMPLE_DATES,
            ),
            "feature_label_versions": (
                {
                    "feature": list(report["feature_versions"]),
                    "label": list(report["label_versions"]),
                },
                {"feature": FEATURE_VERSION, "label": self.label_version},
                versions_ok,
            ),
            "verified_historical_origin": (
                origins_ok,
                "BACKFILLED with provenance",
                origins_ok,
            ),
        }
        checks = {
            name: {"actual": actual, "required": required, "passed": passed}
            for name, (actual, required, passed) in values.items()
        }
        return QualityGateResult(all(item["passed"] for item in checks.values()), checks, report)


class DatasetEarlyStopService:
    def __init__(self, *, label_version: str = LABEL_VERSION) -> None:
        self.label_version = label_version

    def evaluate(self, queryset: QuerySet[TrainingSample] | None = None) -> dict[str, Any]:
        queryset = TrainingSample.objects.all() if queryset is None else queryset
        gate = DatasetQualityGate(label_version=self.label_version).evaluate(queryset)
        samples = list(queryset.order_by("sample_at", "id"))
        split_ready = False
        split_counts: dict[str, dict[str, int]] = {}
        if gate.passed:
            train, validation, test = ForecastTrainingService._time_split(samples)
            groups = {"training": train, "validation": validation, "test": test}
            split_counts = {
                name: {
                    "samples": len(group),
                    "positive": sum(item.label == 1 for item in group),
                    "negative": sum(item.label == 0 for item in group),
                }
                for name, group in groups.items()
            }
            split_ready = all(
                values["positive"] > 0 and values["negative"] > 0
                for values in split_counts.values()
            )
        return {
            "early_stop": gate.passed and split_ready,
            "quality_gate_passed": gate.passed,
            "time_split_ready": split_ready,
            "split_counts": split_counts,
            "checks": gate.checks,
            "quality": gate.report,
        }


class TrainingBlockedError(ValueError):
    def __init__(self, gate: QualityGateResult) -> None:
        self.gate = gate
        super().__init__("dataset quality gate failed")


def _rows(samples: list[TrainingSample]) -> list[dict[str, Any]]:
    rows = []
    for sample in samples:
        row = {name: sample.features.get(name) for name in NUMERIC_FEATURES}
        row.update({"category": sample.category, "age_cohort": sample.age_cohort})
        rows.append(row)
    return rows


def _matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray(
        [[row.get(name) for name in (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)] for row in rows],
        dtype=object,
    )


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predictions = (probabilities >= 0.5).astype(int)
    both_classes = len(set(labels.tolist())) == 2
    return {
        "accuracy": round(float(accuracy_score(labels, predictions)), 6),
        "precision": round(float(precision_score(labels, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(labels, predictions, zero_division=0)), 6),
        "f1": round(float(f1_score(labels, predictions, zero_division=0)), 6),
        "roc_auc": round(float(roc_auc_score(labels, probabilities)), 6) if both_classes else None,
        "pr_auc": round(float(average_precision_score(labels, probabilities)), 6)
        if both_classes
        else None,
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
        "sample_count": len(labels),
        "positive_count": int(labels.sum()),
    }


class ForecastTrainingService:
    ALGORITHMS = {
        "logistic_regression": lambda: LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=42
        ),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=42, n_jobs=1
        ),
        "xgboost": lambda: XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
            n_jobs=1,
        ),
    }

    def __init__(self, *, label_version: str = LABEL_VERSION) -> None:
        if label_version not in {LABEL_VERSION, PERCENTILE_LABEL_VERSION}:
            raise ValueError("unsupported training label version")
        self.label_version = label_version

    @transaction.atomic
    def train(self, queryset: QuerySet[TrainingSample] | None = None) -> dict[str, Any]:
        queryset = (TrainingSample.objects.all() if queryset is None else queryset).filter(
            feature_version=FEATURE_VERSION, label_version=self.label_version
        )
        gate = DatasetQualityGate(label_version=self.label_version).evaluate(queryset)
        if not gate.passed:
            raise TrainingBlockedError(gate)
        samples = list(queryset.order_by("sample_at", "id"))
        train, validation, test = self._time_split(samples)
        dataset_fingerprint = hashlib.sha256(
            "|".join(
                f"{sample.id}:{sample.updated_at.isoformat()}:{sample.label}" for sample in samples
            ).encode()
        ).hexdigest()
        output = []
        for algorithm, factory in self.ALGORITHMS.items():
            output.append(
                self._train_one(
                    algorithm,
                    factory(),
                    train,
                    validation,
                    test,
                    gate,
                    dataset_fingerprint,
                )
            )
        selected = max(
            output,
            key=lambda model: (
                model.validation_metrics.get("pr_auc") or -1,
                model.validation_metrics.get("f1") or -1,
                model.validation_metrics.get("precision") or -1,
            ),
        )
        return {
            "models": output,
            "selected_model_version": selected.model_version,
            "forecast_status": "NOT_READY",
        }

    @staticmethod
    def _time_split(
        samples: list[TrainingSample],
    ) -> tuple[list[TrainingSample], list[TrainingSample], list[TrainingSample]]:
        dates = sorted({sample.sample_at for sample in samples})
        train_cut = dates[max(1, int(len(dates) * 0.70)) - 1]
        validation_index = max(int(len(dates) * 0.85), 2)
        validation_cut = dates[min(validation_index, len(dates) - 1) - 1]
        train = [sample for sample in samples if sample.sample_at <= train_cut]
        validation = [
            sample for sample in samples if train_cut < sample.sample_at <= validation_cut
        ]
        test = [sample for sample in samples if sample.sample_at > validation_cut]
        if not all((train, validation, test)) or any(
            len({item.label for item in split}) < 2 for split in (train, validation, test)
        ):
            raise ValueError(
                "time-based train/validation/test splits must each contain both labels"
            )
        return train, validation, test

    def _train_one(
        self,
        algorithm: str,
        estimator: Any,
        train: list[TrainingSample],
        validation: list[TrainingSample],
        test: list[TrainingSample],
        gate: QualityGateResult,
        dataset_fingerprint: str,
    ) -> MLModel:
        pipeline = self._pipeline(estimator)
        train_x = _matrix(_rows(train))
        train_y = np.asarray([item.label for item in train])
        pipeline.fit(train_x, train_y)
        validation_metrics = _metrics(
            np.asarray([item.label for item in validation]),
            pipeline.predict_proba(_matrix(_rows(validation)))[:, 1],
        )
        test_metrics = _metrics(
            np.asarray([item.label for item in test]),
            pipeline.predict_proba(_matrix(_rows(test)))[:, 1],
        )
        version = f"forecast-v1-{algorithm}-{dataset_fingerprint[:16]}"
        root = Path(settings.ML_ARTIFACT_ROOT)
        root.mkdir(parents=True, exist_ok=True)
        artifact = root / f"{version}.joblib"
        joblib.dump(pipeline, artifact)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        importance = self._feature_importance(pipeline)
        existing_status = (
            MLModel.objects.filter(model_version=version).values_list("status", flat=True).first()
        )
        model, _ = MLModel.objects.update_or_create(
            model_version=version,
            defaults={
                "model_name": MODEL_NAME,
                "feature_version": FEATURE_VERSION,
                "label_version": self.label_version,
                "algorithm": algorithm,
                "training_start": train[0].sample_at,
                "training_end": train[-1].sample_at,
                "validation_metrics": validation_metrics,
                "test_metrics": test_metrics,
                "dataset_quality": {
                    "passed": gate.passed,
                    "checks": gate.checks,
                    "report": gate.report,
                    "fingerprint": dataset_fingerprint,
                },
                "feature_importance": importance,
                "artifact_path": str(artifact),
                "artifact_sha256": digest,
                "status": (
                    ModelStatus.ACTIVE
                    if existing_status == ModelStatus.ACTIVE
                    else ModelStatus.VALIDATED
                ),
            },
        )
        return model

    @staticmethod
    def _pipeline(estimator: Any) -> Pipeline:
        numeric_indexes = list(range(len(NUMERIC_FEATURES)))
        category_indexes = list(
            range(len(NUMERIC_FEATURES), len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES))
        )
        transformer = ColumnTransformer(
            [
                (
                    "numeric",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    numeric_indexes,
                ),
                (
                    "category",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    category_indexes,
                ),
            ]
        )
        return Pipeline([("features", transformer), ("model", estimator)])

    def learning_curve(self, samples: list[TrainingSample], *, algorithm: str) -> dict[str, Any]:
        train, validation, _ = self._time_split(samples)
        points = []
        for fraction in (0.25, 0.50, 0.75, 1.0):
            count = max(int(len(train) * fraction), 2)
            subset = train[:count]
            if len({item.label for item in subset}) < 2:
                continue
            pipeline = self._pipeline(self.ALGORITHMS[algorithm]())
            pipeline.fit(_matrix(_rows(subset)), np.asarray([item.label for item in subset]))
            metrics = _metrics(
                np.asarray([item.label for item in validation]),
                pipeline.predict_proba(_matrix(_rows(validation)))[:, 1],
            )
            points.append(
                {"fraction": fraction, "training_samples": len(subset), "metrics": metrics}
            )
        first = points[0]["metrics"] if points else {}
        last = points[-1]["metrics"] if points else {}
        improvement = max(
            (last.get("pr_auc") or 0) - (first.get("pr_auc") or 0),
            (last.get("f1") or 0) - (first.get("f1") or 0),
        )
        return {
            "algorithm": algorithm,
            "points": points,
            "assessment": (
                "MORE_DATA_LIKELY_BENEFICIAL"
                if improvement >= 0.05
                else "DATASET_SIZE_CURRENTLY_SUFFICIENT"
            ),
            "material_improvement_threshold": 0.05,
        }

    @staticmethod
    def _feature_importance(pipeline: Pipeline) -> dict[str, float]:
        names = [
            ForecastTrainingService._semantic_feature_name(name)
            for name in pipeline.named_steps["features"].get_feature_names_out().tolist()
        ]
        model = pipeline.named_steps["model"]
        raw = abs(model.coef_[0]) if hasattr(model, "coef_") else model.feature_importances_
        total = float(np.sum(raw))
        return {
            name: round(float(value / total), 8) if total else 0.0
            for name, value in sorted(
                zip(names, raw, strict=True), key=lambda item: item[1], reverse=True
            )
        }

    @staticmethod
    def _semantic_feature_name(name: str) -> str:
        prefix, _, encoded = name.partition("__")
        match = re.match(r"x(\d+)(?:_(.*))?$", encoded)
        if not match:
            return name
        index = int(match.group(1))
        source_names = (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)
        if index >= len(source_names):
            return name
        category_value = match.group(2)
        base = source_names[index]
        return f"{prefix}__{base}_{category_value}" if category_value else f"{prefix}__{base}"


class PercentileRegressionService:
    def train(self, queryset: QuerySet[TrainingSample] | None = None) -> dict[str, Any]:
        queryset = (TrainingSample.objects.all() if queryset is None else queryset).filter(
            feature_version=FEATURE_VERSION,
            label_version=PERCENTILE_LABEL_VERSION,
            future_activity_percentile__isnull=False,
        )
        gate = DatasetQualityGate(label_version=PERCENTILE_LABEL_VERSION).evaluate(queryset)
        if not gate.passed:
            raise TrainingBlockedError(gate)
        samples = list(queryset.order_by("sample_at", "id"))
        train, validation, test = ForecastTrainingService._time_split(samples)
        pipeline = ForecastTrainingService._pipeline(
            RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=1)
        )
        pipeline.fit(
            _matrix(_rows(train)),
            np.asarray([item.future_activity_percentile for item in train], dtype=float),
        )
        validation_metrics = self._metrics(validation, pipeline)
        test_metrics = self._metrics(test, pipeline)
        fingerprint = hashlib.sha256(
            "|".join(
                f"{sample.id}:{sample.updated_at.isoformat()}:{sample.future_activity_percentile}"
                for sample in samples
            ).encode()
        ).hexdigest()
        version = f"percentile-regression-v1-random-forest-{fingerprint[:16]}"
        root = Path(settings.ML_ARTIFACT_ROOT)
        root.mkdir(parents=True, exist_ok=True)
        artifact = root / f"{version}.joblib"
        joblib.dump(pipeline, artifact)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        model, _ = MLModel.objects.update_or_create(
            model_version=version,
            defaults={
                "model_name": "activity-percentile-30d",
                "feature_version": FEATURE_VERSION,
                "label_version": PERCENTILE_LABEL_VERSION,
                "algorithm": "random_forest_regressor",
                "training_start": train[0].sample_at,
                "training_end": train[-1].sample_at,
                "validation_metrics": validation_metrics,
                "test_metrics": test_metrics,
                "dataset_quality": {
                    "passed": gate.passed,
                    "checks": gate.checks,
                    "report": gate.report,
                    "fingerprint": fingerprint,
                    "target": "future_activity_percentile",
                },
                "feature_importance": ForecastTrainingService._feature_importance(pipeline),
                "artifact_path": str(artifact),
                "artifact_sha256": digest,
                "status": ModelStatus.VALIDATED,
            },
        )
        return {
            "model": model,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
        }

    @staticmethod
    def _metrics(samples: list[TrainingSample], pipeline: Pipeline) -> dict[str, Any]:
        actual = np.asarray([item.future_activity_percentile for item in samples], dtype=float)
        predicted = pipeline.predict(_matrix(_rows(samples)))
        return {
            "mae": round(float(mean_absolute_error(actual, predicted)), 6),
            "rmse": round(float(mean_squared_error(actual, predicted) ** 0.5), 6),
            "r2": round(float(r2_score(actual, predicted)), 6),
            "sample_count": len(samples),
        }


class ModelActivationService:
    MIN_METRICS = {"precision": 0.40, "recall": 0.40, "f1": 0.40, "pr_auc": 0.35}
    STAR_PERCENTILE_MAX_MAE = 20.0
    STAR_PERCENTILE_MIN_R2 = 0.10

    @classmethod
    def eligibility(cls, model: MLModel) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if model.status != ModelStatus.VALIDATED:
            reasons.append("模型状态不是 VALIDATED")
        if not model.dataset_quality.get("passed"):
            reasons.append("Dataset Quality Gate 未通过")
        is_percentile_regression = (
            model.feature_version == "feature-v2.0.0"
            and model.algorithm == "random_forest_regressor"
        )
        if is_percentile_regression:
            feature_names = model.dataset_quality.get("feature_names")
            if not isinstance(feature_names, list) or not feature_names:
                reasons.append("Star percentile model 未保存 feature_names")
            elif "repository_id" in feature_names:
                reasons.append("repository_id 禁止作为模型 Feature")
        for split_name, split in (
            ("Validation", model.validation_metrics),
            ("Test", model.test_metrics),
        ):
            if is_percentile_regression:
                mae = split.get("mae")
                r2 = split.get("r2")
                if mae is None or mae > cls.STAR_PERCENTILE_MAX_MAE:
                    reasons.append(
                        f"{split_name} mae 超过 {cls.STAR_PERCENTILE_MAX_MAE:.2f}"
                    )
                if r2 is None or r2 < cls.STAR_PERCENTILE_MIN_R2:
                    reasons.append(f"{split_name} r2 未达到 {cls.STAR_PERCENTILE_MIN_R2:.2f}")
            else:
                for metric, minimum in cls.MIN_METRICS.items():
                    value = split.get(metric)
                    if value is None or value < minimum:
                        reasons.append(f"{split_name} {metric} 未达到 {minimum:.2f}")
        return not reasons, reasons

    @transaction.atomic
    def activate(self, model_version: str) -> MLModel:
        model = MLModel.objects.select_for_update().get(model_version=model_version)
        eligible, reasons = self.eligibility(model)
        if not eligible:
            raise ValueError(f"model is below activation thresholds: {'; '.join(reasons)}")
        # Activity classification and Star percentile are separate product models.
        # Activating one family must never retire the other family.
        MLModel.objects.filter(
            status=ModelStatus.ACTIVE, model_name=model.model_name
        ).exclude(pk=model.pk).update(status=ModelStatus.RETIRED)
        model.status = ModelStatus.ACTIVE
        model.activated_at = timezone.now()
        update_fields = ["status", "activated_at"]
        if model.feature_version == "feature-v2.0.0":
            from apps.capabilities.models import CapabilityName, DataCapability

            capability = DataCapability.objects.filter(
                name=CapabilityName.FORECAST_V2_DATA_READINESS
            ).first()
            metrics = capability.metrics if capability else {}
            current_span = int(metrics.get("maximum_observed_span_days") or 0)
            current_repositories = int(
                metrics.get("observed_target_span_repositories")
                or metrics.get("observed_60d_repositories")
                or 0
            )
            current_samples = int(metrics.get("star_enhanced_training_samples") or 0)
            current_categories = int(metrics.get("qualified_categories") or 0)
            total_categories = (
                Repository.objects.filter(
                    is_disabled=False, is_fork=False, monitoring_enabled=True
                )
                .values("category")
                .distinct()
                .count()
            )
            model.retraining_targets = {
                "cycle": "NEXT_RETRAINING",
                "observed_span_days": max(90, current_span + 30),
                "observed_repositories": max(400, current_repositories + 200),
                "training_samples": max(400, current_samples + 200),
                "categories": min(total_categories, max(5, current_categories + 2)),
                "based_on_model_version": model.model_version,
            }
            model.prediction_rollout_status = PredictionRolloutStatus.QUEUED
            model.prediction_rollout = {
                "model_version": model.model_version,
                "trigger": "MODEL_ACTIVATION",
                "predictions_are_immutable_until_next_activation": True,
            }
            update_fields.extend(
                ("retraining_targets", "prediction_rollout_status", "prediction_rollout")
            )
            transaction.on_commit(
                lambda: __import__(
                    "apps.forecasts.tasks", fromlist=["dispatch_star_percentile_rollout"]
                ).dispatch_star_percentile_rollout.delay(model.model_version)
            )
        model.save(update_fields=update_fields)
        return model


class StarPercentileRolloutService:
    """Generate a version-frozen Star percentile snapshot for one model activation."""

    FEATURE_VERSION = "feature-v2.0.0"

    @staticmethod
    def _confidence(model: MLModel) -> float:
        errors = [
            float(metrics["mae"])
            for metrics in (model.validation_metrics, model.test_metrics)
            if metrics.get("mae") is not None
        ]
        if len(errors) != 2:
            raise ValueError("Star percentile model is missing validation/test MAE")
        return round(max(0.0, min(1.0, 1.0 - max(errors) / 100.0)), 6)

    def run(
        self,
        model_version: str,
        *,
        only_missing: bool = False,
        limit: int | None = None,
    ) -> dict[str, int]:
        model = MLModel.objects.get(
            model_version=model_version,
            status=ModelStatus.ACTIVE,
            feature_version=self.FEATURE_VERSION,
        )
        feature_names = model.dataset_quality.get("feature_names")
        if not isinstance(feature_names, list) or not feature_names:
            raise ValueError("Star percentile model does not declare feature_names")
        if "repository_id" in feature_names:
            raise ValueError("repository_id cannot be a model feature")
        artifact = Path(model.artifact_path)
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != model.artifact_sha256:
            raise ValueError("model artifact checksum mismatch")
        pipeline = joblib.load(artifact)
        confidence = self._confidence(model)
        repositories = Repository.objects.filter(is_disabled=False)
        if only_missing:
            # A project is eligible only after the versioned V2 feature builder has
            # persisted a leakage-safe sample.  Once one forecast exists for this
            # model version, later collection must not rewrite the frozen result.
            repositories = (
                repositories.filter(
                    training_samples__feature_version=model.feature_version,
                    training_samples__label_version=model.label_version,
                    training_samples__sample_at__lte=timezone.now(),
                )
                .exclude(forecasts__model=model)
                .distinct()
                .order_by("id")
            )
        if limit is not None:
            repositories = repositories[:limit]
        counts = {"total": repositories.count(), "predicted": 0, "skipped": 0, "failed": 0}
        for repository_id in repositories.values_list("id", flat=True).iterator(chunk_size=200):
            sample = (
                TrainingSample.objects.filter(
                    repository_id=repository_id,
                    feature_version=model.feature_version,
                    label_version=model.label_version,
                    sample_at__lte=model.activated_at or timezone.now(),
                )
                .order_by("-sample_at")
                .first()
            )
            if sample is None:
                counts["skipped"] += 1
                continue
            timestamps = sample.features.get("_provenance", {}).get("feature_timestamps", [])
            if any(datetime.fromisoformat(value) > sample.sample_at for value in timestamps):
                counts["failed"] += 1
                continue
            try:
                matrix = np.asarray(
                    [[sample.features.get(name) for name in feature_names]], dtype=object
                )
                percentile = float(pipeline.predict(matrix)[0])
                if not np.isfinite(percentile) or not 0.0 <= percentile <= 100.0:
                    raise ValueError("percentile prediction is outside 0..100")
                RepositoryForecast.objects.update_or_create(
                    repository_id=repository_id,
                    model_version=model.model_version,
                    sample_at=sample.sample_at,
                    defaults={
                        "model": model,
                        "forecast_horizon_days": 30,
                        "high_growth_probability": None,
                        "prediction": None,
                        "confidence": confidence,
                        "predicted_activity_percentile": percentile,
                        "percentile_model_version": model.model_version,
                        "feature_snapshot": {
                            "feature_version": model.feature_version,
                            "features": {
                                name: sample.features.get(name) for name in feature_names
                            },
                            "source_training_sample_id": sample.id,
                            "prediction_policy": "FROZEN_UNTIL_NEXT_MODEL_ACTIVATION",
                        },
                    },
                )
            except Exception:
                counts["failed"] += 1
            else:
                counts["predicted"] += 1
        return counts


class ForecastService:
    @staticmethod
    def _active_model() -> MLModel | None:
        return (
            MLModel.objects.filter(
                status=ModelStatus.ACTIVE,
                model_name=MODEL_NAME,
                feature_version=FEATURE_VERSION,
            )
            .order_by("-created_at")
            .first()
        )

    def run(self, repository_id: int) -> RepositoryForecast:
        active = self._active_model()
        if active is None:
            raise ValueError("forecast model is not active")
        sample = (
            TrainingSample.objects.filter(
                repository_id=repository_id,
                feature_version=active.feature_version,
                label_version=active.label_version,
                sample_at__lte=timezone.now(),
            )
            .order_by("-sample_at")
            .first()
        )
        if sample is None:
            raise ValueError("no eligible feature snapshot")
        timestamps = sample.features.get("_provenance", {}).get("feature_timestamps", [])
        if any(datetime.fromisoformat(value) > sample.sample_at for value in timestamps):
            raise ValueError("feature snapshot contains future data")
        artifact = Path(active.artifact_path)
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != active.artifact_sha256:
            raise ValueError("model artifact checksum mismatch")
        pipeline = joblib.load(artifact)
        probability = float(pipeline.predict_proba(_matrix(_rows([sample])))[:, 1][0])
        forecast, _ = RepositoryForecast.objects.update_or_create(
            repository_id=repository_id,
            model_version=active.model_version,
            sample_at=sample.sample_at,
            defaults={
                "model": active,
                "forecast_horizon_days": 30,
                "high_growth_probability": probability,
                "prediction": int(probability >= 0.5),
                "confidence": abs(probability - 0.5) * 2,
                "feature_snapshot": {
                    "feature_version": active.feature_version,
                    "features": sample.features,
                    "source_training_sample_id": sample.id,
                    "max_feature_time": sample.sample_at.isoformat(),
                },
            },
        )
        return forecast

    def status(self, repository_id: int) -> dict[str, Any]:
        active = self._active_model()
        if active is None:
            return {
                "repository_id": repository_id,
                "status": "NOT_READY",
                "forecast": None,
                "fallback": "POTENTIAL_SCORE",
                "definition": FORECAST_DEFINITION,
            }
        forecast = (
            RepositoryForecast.objects.filter(repository_id=repository_id, model=active)
            .order_by("-sample_at")
            .first()
        )
        if forecast is None:
            has_features = TrainingSample.objects.filter(
                repository_id=repository_id,
                feature_version=active.feature_version,
                label_version=active.label_version,
                sample_at__lte=timezone.now(),
            ).exists()
            if has_features:
                key = f"agentGitHub:forecast:on-demand:{active.model_version}:{repository_id}"
                scheduled = bool(
                    Redis.from_url(settings.CELERY_BROKER_URL).set(key, "1", nx=True, ex=300)
                )
                if scheduled:
                    from .tasks import run_forecast

                    run_forecast.delay(repository_id)
                return {
                    "repository_id": repository_id,
                    "status": "PENDING",
                    "forecast": None,
                    "fallback": "POTENTIAL_SCORE",
                    "definition": FORECAST_DEFINITION,
                    "model_version": active.model_version,
                }
            return {
                "repository_id": repository_id,
                "status": "NOT_READY",
                "forecast": None,
                "fallback": "POTENTIAL_SCORE",
                "definition": FORECAST_DEFINITION,
                "reason": "INSUFFICIENT_FEATURES",
            }
        features = forecast.feature_snapshot.get("features", {})
        safe_features = {
            name: features.get(name)
            for name in FORECAST_DISPLAY_FEATURES
            if name in features
        }
        return {
            "repository_id": repository_id,
            "status": "READY",
            "forecast": {
                "model_version": forecast.model_version,
                "forecast_horizon_days": forecast.forecast_horizon_days,
                "high_growth_probability": forecast.high_growth_probability,
                "prediction": forecast.prediction,
                "confidence": forecast.confidence,
                "sample_at": forecast.sample_at,
                "forecast_type": "ACTIVITY_FORECAST_V1",
                "input_features": safe_features,
            },
            "fallback": None,
            "definition": FORECAST_DEFINITION,
        }
