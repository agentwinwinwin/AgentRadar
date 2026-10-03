from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.datasets.models import DataOrigin, HistoricalActivityWindow, TrainingSample
from apps.datasets.services import (
    FEATURE_VERSION,
    LABEL_VERSION,
    LEGACY_LABEL_VERSION,
    PERCENTILE_LABEL_VERSION,
    DataLeakageError,
    DataLeakageGuard,
    DatasetBuilder,
    DatasetQualityService,
)
from apps.datasets.tests.test_backfill import create_repository
from apps.repositories.models import RepositoryCategory


def create_windows(repository, sample_date: date, value: int) -> None:
    for start, end, multiplier in (
        (sample_date - timedelta(days=6), sample_date, 1),
        (sample_date - timedelta(days=29), sample_date, 2),
        (sample_date + timedelta(days=1), sample_date + timedelta(days=30), 3),
    ):
        HistoricalActivityWindow.objects.create(
            repository=repository,
            window_start=start,
            window_end=end,
            data_origin=DataOrigin.BACKFILLED,
            commits=value * multiplier,
            prs_created=value * multiplier,
            prs_merged=value * multiplier,
            issues_created=value * multiplier,
            issues_closed=value * multiplier,
            active_contributors=value * multiplier,
            releases=value * multiplier,
            days_since_last_release=0 if value else None,
            data_completeness=1,
            source_metadata={"source": "test"},
        )


@pytest.mark.django_db
def test_builder_creates_percentile_label_and_preserves_null_features() -> None:
    sample_date = date(2026, 6, 1)
    repositories = [create_repository(index) for index in range(1, 6)]
    for repository, value in zip(repositories, (0, 2, 4, 6, 10), strict=True):
        repository.category = RepositoryCategory.BROWSER_AGENT
        repository.save(update_fields=("category", "updated_at"))
        create_windows(repository, sample_date, value)

    result = DatasetBuilder(minimum_cohort_size=5).build(sample_date)

    assert result == {
        "eligible": 5,
        "skipped_incomplete_label": 0,
        "skipped_small_cohort": 0,
        "created": 5,
        "updated": 0,
    }
    positive = TrainingSample.objects.get(repository=repositories[-1])
    negative = TrainingSample.objects.get(repository=repositories[0])
    assert positive.label == 1
    assert positive.label_score == 100
    assert negative.label == 0
    assert negative.label_score == 0
    assert positive.feature_version == FEATURE_VERSION
    assert positive.label_version == LABEL_VERSION
    assert positive.features["current_stars"] is None
    assert positive.features["commit_30d"] == 20
    assert positive.features["topic_momentum"] is None
    assert "repository_id" not in positive.features
    assert positive.label_window_start > positive.sample_at.date()


@pytest.mark.django_db
def test_builder_is_idempotent_and_allows_multiple_historical_points() -> None:
    repositories = [create_repository(index) for index in range(1, 6)]
    first_date = date(2026, 5, 1)
    second_date = date(2026, 6, 1)
    for index, repository in enumerate(repositories, 1):
        create_windows(repository, first_date, index)
        create_windows(repository, second_date, index + 1)

    builder = DatasetBuilder(minimum_cohort_size=5)
    first = builder.build(first_date)
    repeated = builder.build(first_date)
    second = builder.build(second_date)

    assert first["created"] == 5
    assert repeated["updated"] == 5
    assert second["created"] == 5
    assert TrainingSample.objects.filter(repository=repositories[0]).count() == 2


@pytest.mark.django_db
def test_builder_skips_small_label_cohort() -> None:
    repository = create_repository()
    sample_date = date(2026, 6, 1)
    create_windows(repository, sample_date, 3)

    result = DatasetBuilder(minimum_cohort_size=5).build(sample_date)

    assert result["skipped_small_cohort"] == 1
    assert TrainingSample.objects.count() == 0


@pytest.mark.django_db
def test_label_v1_1_groups_by_category_and_sample_at_not_age() -> None:
    sample_date = date(2026, 6, 1)
    repositories = [create_repository(index) for index in range(1, 5)]
    for index, repository in enumerate(repositories):
        repository.category = RepositoryCategory.BROWSER_AGENT
        repository.github_created_at = datetime(
            2026 if index < 2 else 2020, 1, index + 1, tzinfo=UTC
        )
        repository.save(update_fields=("category", "github_created_at", "updated_at"))
        create_windows(repository, sample_date, index + 1)

    current = DatasetBuilder(minimum_cohort_size=4).build(sample_date)
    legacy = DatasetBuilder(minimum_cohort_size=4, label_version=LEGACY_LABEL_VERSION).build(
        sample_date
    )

    assert current["created"] == 4
    assert legacy["skipped_small_cohort"] == 4
    assert TrainingSample.objects.filter(label_version=LABEL_VERSION).count() == 4
    assert TrainingSample.objects.filter(label_version=LEGACY_LABEL_VERSION).count() == 0
    sample = TrainingSample.objects.filter(label_version=LABEL_VERSION).first()
    assert sample is not None
    assert sample.age_cohort
    assert sample.features["repo_age_days"] is not None
    assert sample.label_evidence["cohort"] == {
        "category": RepositoryCategory.BROWSER_AGENT,
        "sample_at": sample_date.isoformat(),
        "label_version": LABEL_VERSION,
    }


@pytest.mark.django_db
def test_label_versions_coexist_without_overwrite() -> None:
    sample_date = date(2026, 6, 1)
    repositories = [create_repository(index) for index in range(1, 5)]
    for index, repository in enumerate(repositories):
        create_windows(repository, sample_date, index + 1)

    DatasetBuilder(minimum_cohort_size=4, label_version=LEGACY_LABEL_VERSION).build(sample_date)
    DatasetBuilder(minimum_cohort_size=4).build(sample_date)

    assert TrainingSample.objects.filter(label_version=LEGACY_LABEL_VERSION).count() == 4
    assert TrainingSample.objects.filter(label_version=LABEL_VERSION).count() == 4


@pytest.mark.django_db
def test_label_v1_2_persists_percentile_and_derives_binary_target() -> None:
    sample_date = date(2026, 6, 1)
    repositories = [create_repository(index) for index in range(1, 6)]
    for index, repository in enumerate(repositories):
        create_windows(repository, sample_date, index)

    result = DatasetBuilder(minimum_cohort_size=5, label_version=PERCENTILE_LABEL_VERSION).build(
        sample_date
    )

    assert result["created"] == 5
    samples = TrainingSample.objects.filter(label_version=PERCENTILE_LABEL_VERSION)
    assert samples.count() == 5
    for sample in samples:
        assert sample.future_activity_percentile == sample.label_score
        assert sample.binary_top20_label == int(sample.future_activity_percentile >= 80)
        assert sample.label == sample.binary_top20_label
        assert sample.label_cohort_size == 5


@pytest.mark.django_db
def test_label_v1_2_small_cohort_produces_no_targets() -> None:
    sample_date = date(2026, 6, 1)
    repositories = [create_repository(index) for index in range(1, 5)]
    for index, repository in enumerate(repositories):
        create_windows(repository, sample_date, index)

    result = DatasetBuilder(minimum_cohort_size=5, label_version=PERCENTILE_LABEL_VERSION).build(
        sample_date
    )

    assert result["skipped_small_cohort"] == 4
    assert not TrainingSample.objects.filter(label_version=PERCENTILE_LABEL_VERSION).exists()


@pytest.mark.django_db
def test_incomplete_label_is_skipped_not_converted_to_negative() -> None:
    repository = create_repository()
    sample_date = date(2026, 6, 1)
    create_windows(repository, sample_date, 3)
    label = HistoricalActivityWindow.objects.get(
        repository=repository, window_start=sample_date + timedelta(days=1)
    )
    label.commits = None
    label.save(update_fields=("commits",))

    result = DatasetBuilder().build(sample_date)

    assert result["skipped_incomplete_label"] == 1
    assert TrainingSample.objects.count() == 0


@pytest.mark.django_db
def test_data_leakage_guard_rejects_future_feature_timestamp() -> None:
    repository = create_repository()
    sample_date = date(2026, 6, 1)
    create_windows(repository, sample_date, 3)
    candidate = DatasetBuilder()._candidate(repository, sample_date)
    assert candidate is not None
    leaked_features = {
        **candidate.features,
        "_provenance": {
            **candidate.features["_provenance"],
            "feature_timestamps": [datetime(2026, 6, 2, tzinfo=UTC).isoformat()],
        },
    }

    with pytest.raises(DataLeakageError, match="future timestamp"):
        DataLeakageGuard.validate(replace(candidate, features=leaked_features))


@pytest.mark.django_db
def test_database_constraints_reject_duplicate_window_and_invalid_label() -> None:
    repository = create_repository()
    sample_date = date(2026, 6, 1)
    create_windows(repository, sample_date, 1)
    existing = HistoricalActivityWindow.objects.first()
    assert existing is not None
    with pytest.raises(IntegrityError), transaction.atomic():
        HistoricalActivityWindow.objects.create(
            repository=repository,
            window_start=existing.window_start,
            window_end=existing.window_end,
            data_origin=existing.data_origin,
            data_completeness=1,
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        TrainingSample.objects.create(
            repository=repository,
            sample_at=datetime(2026, 6, 1, 23, 59, tzinfo=UTC),
            feature_window_start=date(2026, 5, 3),
            feature_window_end=sample_date,
            label_window_start=date(2026, 6, 2),
            label_window_end=date(2026, 7, 1),
            category=repository.category,
            age_cohort="AGE_181_730",
            label=2,
            label_score=50,
            feature_version=FEATURE_VERSION,
            label_version=LABEL_VERSION,
            data_origin=DataOrigin.BACKFILLED,
        )


@pytest.mark.django_db
def test_quality_report_contains_balance_distribution_range_and_missingness() -> None:
    sample_date = date(2026, 6, 1)
    repositories = [create_repository(index) for index in range(1, 6)]
    for index, repository in enumerate(repositories):
        create_windows(repository, sample_date, index)
    DatasetBuilder(minimum_cohort_size=5).build(sample_date)

    report = DatasetQualityService().report()

    assert report["total_samples"] == 5
    assert report["positive_samples"] == 1
    assert report["negative_samples"] == 4
    assert report["positive_ratio"] == 0.2
    assert report["category_distribution"] == {RepositoryCategory.BROWSER_AGENT: 5}
    assert report["sample_at_distribution"] == {sample_date.isoformat(): 5}
    assert report["sample_time_range"]["start"] is not None
    assert report["missing_features"]["current_stars"]["rate"] == 1.0
