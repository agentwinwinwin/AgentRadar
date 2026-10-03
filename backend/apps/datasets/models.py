from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repositories.models import Repository, RepositoryCategory


class DataOrigin(models.TextChoices):
    BACKFILLED = "BACKFILLED", "Backfilled from historical API"
    OBSERVED = "OBSERVED", "Observed by AgentRadar"


class HistoricalActivityWindow(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="historical_activity_windows"
    )
    window_start = models.DateField()
    window_end = models.DateField()
    data_origin = models.CharField(max_length=20, choices=DataOrigin.choices)
    commits = models.PositiveIntegerField(null=True, blank=True)
    prs_created = models.PositiveIntegerField(null=True, blank=True)
    prs_merged = models.PositiveIntegerField(null=True, blank=True)
    issues_created = models.PositiveIntegerField(null=True, blank=True)
    issues_closed = models.PositiveIntegerField(null=True, blank=True)
    active_contributors = models.PositiveIntegerField(null=True, blank=True)
    releases = models.PositiveIntegerField(null=True, blank=True)
    days_since_last_release = models.PositiveIntegerField(null=True, blank=True)
    data_completeness = models.FloatField(
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0))
    )
    source_metadata = models.JSONField(default=dict)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "historical_activity_windows"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "window_start", "window_end", "data_origin"),
                name="unique_repository_historical_activity_window",
            ),
            models.CheckConstraint(
                condition=models.Q(window_start__lte=models.F("window_end")),
                name="historical_window_start_not_after_end",
            ),
            models.CheckConstraint(
                condition=models.Q(data_completeness__gte=0.0)
                & models.Q(data_completeness__lte=1.0),
                name="historical_window_completeness_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.repository.full_name}: {self.window_start}..{self.window_end} "
            f"({self.data_origin})"
        )


class HistoricalBucketKind(models.TextChoices):
    ACTIVITY_30D = "ACTIVITY_30D", "Exact 30-day activity bucket"
    FEATURE_TAIL_7D = "FEATURE_TAIL_7D", "Exact 7-day feature tail"


class HistoricalActivityBucket(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="historical_activity_buckets"
    )
    bucket_start = models.DateField()
    bucket_end = models.DateField()
    bucket_kind = models.CharField(max_length=30, choices=HistoricalBucketKind.choices)
    commits = models.PositiveIntegerField(null=True, blank=True)
    prs_created = models.PositiveIntegerField(null=True, blank=True)
    prs_merged = models.PositiveIntegerField(null=True, blank=True)
    issues_created = models.PositiveIntegerField(null=True, blank=True)
    issues_closed = models.PositiveIntegerField(null=True, blank=True)
    active_contributors = models.PositiveIntegerField(null=True, blank=True)
    releases = models.PositiveIntegerField(null=True, blank=True)
    days_since_last_release = models.PositiveIntegerField(null=True, blank=True)
    data_completeness = models.FloatField(
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0))
    )
    acquisition_version = models.CharField(max_length=50)
    source_metadata = models.JSONField(default=dict)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "historical_activity_buckets"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "bucket_start", "bucket_end", "bucket_kind"),
                name="unique_repository_historical_activity_bucket",
            ),
            models.CheckConstraint(
                condition=models.Q(bucket_start__lte=models.F("bucket_end")),
                name="historical_bucket_start_not_after_end",
            ),
            models.CheckConstraint(
                condition=models.Q(data_completeness__gte=0.0)
                & models.Q(data_completeness__lte=1.0),
                name="historical_bucket_completeness_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.bucket_start}..{self.bucket_end}"


class HistoricalContributorWeek(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="historical_contributor_weeks"
    )
    contributor_key = models.CharField(max_length=255)
    week_start = models.DateField()
    commits = models.PositiveIntegerField()
    additions = models.PositiveIntegerField(null=True, blank=True)
    deletions = models.PositiveIntegerField(null=True, blank=True)
    data_origin = models.CharField(max_length=20, choices=DataOrigin.choices)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "historical_contributor_weeks"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "contributor_key", "week_start"),
                name="unique_repository_contributor_week",
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.contributor_key} @ {self.week_start}"


class HistoricalSourceCache(models.Model):
    repository = models.OneToOneField(
        Repository, on_delete=models.CASCADE, related_name="historical_source_cache"
    )
    contributor_stats_fetched_at = models.DateTimeField(null=True, blank=True)
    contributor_week_start = models.DateField(null=True, blank=True)
    contributor_week_end = models.DateField(null=True, blank=True)
    contributor_stats_empty = models.BooleanField(default=False)
    releases_fetched_at = models.DateTimeField(null=True, blank=True)
    release_dates = models.JSONField(default=list)
    acquisition_version = models.CharField(max_length=50)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "historical_source_caches"

    def __str__(self) -> str:
        return self.repository.full_name


class TrainingSample(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="training_samples"
    )
    sample_at = models.DateTimeField(db_index=True)
    feature_window_start = models.DateField()
    feature_window_end = models.DateField()
    label_window_start = models.DateField()
    label_window_end = models.DateField()
    category = models.CharField(max_length=50, choices=RepositoryCategory.choices)
    age_cohort = models.CharField(max_length=30)
    features = models.JSONField(default=dict)
    label = models.PositiveSmallIntegerField()
    label_score = models.FloatField(validators=(MinValueValidator(0.0), MaxValueValidator(100.0)))
    future_activity_percentile = models.FloatField(
        null=True,
        blank=True,
        validators=(MinValueValidator(0.0), MaxValueValidator(100.0)),
    )
    binary_top20_label = models.PositiveSmallIntegerField(null=True, blank=True)
    label_cohort_size = models.PositiveIntegerField(null=True, blank=True)
    feature_version = models.CharField(max_length=50)
    label_version = models.CharField(max_length=50)
    data_origin = models.CharField(max_length=20, choices=DataOrigin.choices)
    label_evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "training_samples"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "sample_at", "feature_version", "label_version"),
                name="unique_repository_training_sample_version",
            ),
            models.CheckConstraint(
                condition=models.Q(label__in=(0, 1)), name="training_sample_binary_label"
            ),
            models.CheckConstraint(
                condition=models.Q(label_score__gte=0.0) & models.Q(label_score__lte=100.0),
                name="training_sample_label_score_between_zero_and_hundred",
            ),
            models.CheckConstraint(
                condition=models.Q(future_activity_percentile__isnull=True)
                | (
                    models.Q(future_activity_percentile__gte=0.0)
                    & models.Q(future_activity_percentile__lte=100.0)
                ),
                name="training_future_percentile_between_zero_and_hundred",
            ),
            models.CheckConstraint(
                condition=models.Q(binary_top20_label__isnull=True)
                | models.Q(binary_top20_label__in=(0, 1)),
                name="training_binary_top20_label_valid",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.repository.full_name}: {self.sample_at} "
            f"({self.feature_version}/{self.label_version})"
        )


class BackfillBatchStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    PARTIAL = "PARTIAL", "Partial"


class BackfillItemStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class RepositoryPoolType(models.TextChoices):
    CANDIDATE = "CANDIDATE", "Candidate"
    TRACKED = "TRACKED", "Tracked"
    TRAINING = "TRAINING", "Training"


class RepositoryPoolStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"


class RepositoryPool(models.Model):
    name = models.CharField(max_length=120, unique=True)
    pool_type = models.CharField(max_length=20, choices=RepositoryPoolType.choices)
    status = models.CharField(
        max_length=20,
        choices=RepositoryPoolStatus.choices,
        default=RepositoryPoolStatus.DRAFT,
    )
    selection_version = models.CharField(max_length=50, default="sampling-v1.0.0")
    selection_config = models.JSONField(default=dict)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    repositories = models.ManyToManyField(
        Repository, through="RepositoryPoolMembership", related_name="dataset_pools"
    )

    class Meta:
        db_table = "repository_pools"

    def __str__(self) -> str:
        return self.name


class RepositoryPoolMembership(models.Model):
    pool = models.ForeignKey(RepositoryPool, on_delete=models.CASCADE, related_name="memberships")
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="dataset_pool_memberships"
    )
    category = models.CharField(max_length=50, choices=RepositoryCategory.choices)
    star_bucket = models.CharField(max_length=30)
    age_cohort = models.CharField(max_length=30)
    activity_level = models.CharField(max_length=30)
    selection_reason = models.CharField(max_length=120)
    stratum_rank = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "repository_pool_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=("pool", "repository"), name="unique_pool_repository_membership"
            )
        ]

    def __str__(self) -> str:
        return f"{self.pool.name}: {self.repository.full_name}"


class AcquisitionQueryShard(models.Model):
    query = models.CharField(max_length=500, unique=True)
    category = models.CharField(max_length=50, choices=RepositoryCategory.choices)
    star_bucket = models.CharField(max_length=30)
    age_cohort = models.CharField(max_length=30)
    shortage = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    repositories_seen = models.PositiveIntegerField(default=0)
    repositories_created = models.PositiveIntegerField(default=0)
    last_total_count = models.PositiveIntegerField(null=True, blank=True)
    last_incomplete_results = models.BooleanField(default=False)
    last_truncated = models.BooleanField(default=False)
    execution_count = models.PositiveIntegerField(default=0)
    shard_metadata = models.JSONField(default=dict)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acquisition_query_shards"

    def __str__(self) -> str:
        return self.query


class RepositoryDiscoveryEvidence(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="discovery_evidence"
    )
    shard = models.ForeignKey(
        AcquisitionQueryShard, on_delete=models.CASCADE, related_name="repository_evidence"
    )
    times_seen = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repository_discovery_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "shard"), name="unique_repository_discovery_shard"
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.shard_id}"


class HistoricalBackfillBatch(models.Model):
    name = models.CharField(max_length=120, unique=True)
    status = models.CharField(
        max_length=20,
        choices=BackfillBatchStatus.choices,
        default=BackfillBatchStatus.PENDING,
    )
    configuration = models.JSONField(default=dict)
    endpoint_request_counts = models.JSONField(default=dict)
    rate_limit_state = models.JSONField(default=dict)
    retry_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "historical_backfill_batches"

    def __str__(self) -> str:
        return self.name


class HistoricalBackfillBatchItem(models.Model):
    batch = models.ForeignKey(
        HistoricalBackfillBatch, on_delete=models.CASCADE, related_name="items"
    )
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="historical_backfill_items"
    )
    sample_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=BackfillItemStatus.choices,
        default=BackfillItemStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    windows_created = models.PositiveSmallIntegerField(default=0)
    endpoint_request_counts = models.JSONField(default=dict)
    last_error = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "historical_backfill_batch_items"
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "repository", "sample_date"),
                name="unique_backfill_batch_repository_sample",
            )
        ]

    def __str__(self) -> str:
        return f"{self.batch.name}: {self.repository.full_name} @ {self.sample_date}"
