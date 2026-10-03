import json
import time
from collections import Counter, defaultdict
from datetime import date
from time import monotonic

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.activities.services import ContributorStatisticsPendingError
from apps.datasets.batch_services import MeteredRateLimitedGitHubClient
from apps.datasets.bucket_services import (
    ACQUISITION_VERSION,
    HistoricalBucketMaterializer,
    sparse_sample_dates,
)
from apps.datasets.models import (
    HistoricalActivityBucket,
    RepositoryPool,
    RepositoryPoolStatus,
    RepositoryPoolType,
    TrainingSample,
)
from apps.datasets.services import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    LABEL_VERSION,
    DatasetBuilder,
    DatasetQualityService,
)
from apps.forecasts.services import DatasetEarlyStopService, DatasetQualityGate
from apps.github.client import GitHubClientError
from apps.repositories.models import Repository

TARGET_CATEGORIES = (
    "AGENT_FRAMEWORK",
    "MULTI_AGENT",
    "CODING_AGENT",
    "COMPUTER_USE",
    "BROWSER_AGENT",
)
STAR_BUCKETS = ("STAR_0_99", "STAR_100_999", "STAR_1K_9K", "STAR_10K_PLUS", "UNKNOWN")


def _cycle_star_buckets(memberships):
    groups = defaultdict(list)
    for membership in memberships:
        groups[membership.star_bucket].append(membership)
    output = []
    depth = 0
    while True:
        added = False
        for bucket in STAR_BUCKETS:
            values = groups[bucket]
            if depth < len(values):
                output.append(values[depth])
                added = True
        if not added:
            return output
        depth += 1


def targeted_memberships(pool: RepositoryPool, *, limit: int, eligible_at: date):
    existing_ids = set(
        HistoricalActivityBucket.objects.filter(acquisition_version=ACQUISITION_VERSION)
        .values_list("repository_id", flat=True)
        .distinct()
    )
    by_category = defaultdict(list)
    memberships = (
        pool.memberships.select_related("repository")
        .filter(
            category__in=TARGET_CATEGORIES,
            repository__github_created_at__date__lte=eligible_at,
            repository__is_disabled=False,
        )
        .exclude(repository__raw_metadata={})
    )
    for membership in memberships:
        by_category[membership.category].append(membership)
    ordered = {}
    for category, values in by_category.items():
        values.sort(
            key=lambda item: (
                item.repository_id not in existing_ids,
                item.stratum_rank or 0,
                item.id,
            )
        )
        ordered[category] = _cycle_star_buckets(values)
    selected = []
    depth = 0
    while len(selected) < limit:
        added = False
        for category in TARGET_CATEGORIES:
            values = ordered[category]
            if depth < len(values):
                selected.append(values[depth])
                added = True
                if len(selected) == limit:
                    return selected
        if not added:
            return selected
        depth += 1
    return selected


def _required_ranges(sample_dates: list[date]) -> int:
    ranges = set()
    from datetime import timedelta

    for sample_date in sample_dates:
        ranges.add((sample_date - timedelta(days=29), sample_date, "ACTIVITY_30D"))
        ranges.add(
            (
                sample_date + timedelta(days=1),
                sample_date + timedelta(days=30),
                "ACTIVITY_30D",
            )
        )
        ranges.add((sample_date - timedelta(days=6), sample_date, "FEATURE_TAIL_7D"))
    return len(ranges)


class Command(BaseCommand):
    help = "Run one resumable targeted Sprint 8 activity-bucket batch and local gate."

    contributor_stats_max_attempts = 3

    def add_arguments(self, parser):
        parser.add_argument("--training-pool", default="sprint8-training-v1")
        parser.add_argument("--selection-limit", type=int, default=150)
        parser.add_argument("--batch-offset", type=int, required=True)
        parser.add_argument("--batch-size", type=int, default=30)
        parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 4, 18))
        parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 7, 17))

    def handle(self, *args, **options):
        del args
        if not 1 <= options["selection_limit"] <= 150:
            raise CommandError("selection-limit must be between 1 and 150")
        if options["batch_offset"] < 0 or options["batch_size"] < 1:
            raise CommandError("invalid batch slice")
        try:
            pool = RepositoryPool.objects.get(
                name=options["training_pool"],
                pool_type=RepositoryPoolType.TRAINING,
                status=RepositoryPoolStatus.CONFIRMED,
            )
        except RepositoryPool.DoesNotExist as exc:
            raise CommandError("a CONFIRMED Training Pool is required") from exc
        dates = sparse_sample_dates(options["start_date"], options["end_date"])
        selected = targeted_memberships(
            pool, limit=options["selection_limit"], eligible_at=dates[0]
        )
        offset = options["batch_offset"]
        batch = selected[offset : offset + options["batch_size"]]
        if not batch:
            raise CommandError("empty batch slice")

        client = MeteredRateLimitedGitHubClient(timeout=45)
        materializer = HistoricalBucketMaterializer(client)
        started = monotonic()
        totals = Counter()
        failures = []
        contributor_202_waits = 0
        for membership in batch:
            repository = membership.repository
            for attempt in range(1, self.contributor_stats_max_attempts + 1):
                try:
                    result = materializer.materialize(repository, dates)
                except ContributorStatisticsPendingError as exc:
                    if attempt == self.contributor_stats_max_attempts:
                        failures.append(
                            {"repository": repository.full_name, "error": "contributor_stats_202"}
                        )
                        break
                    contributor_202_waits += 1
                    retry_after = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 5
                    time.sleep(min(max(retry_after, 1), 60))
                except GitHubClientError as exc:
                    failures.append({"repository": repository.full_name, "error": str(exc)[:200]})
                    break
                else:
                    totals.update(
                        buckets_created=result.buckets_created,
                        buckets_reused=result.buckets_reused,
                        windows_created=result.windows_created,
                    )
                    break

        cumulative_memberships = selected[: offset + len(batch)]
        cumulative_ids = [item.repository_id for item in cumulative_memberships]
        required = _required_ranges(dates)
        complete_ids = list(
            HistoricalActivityBucket.objects.filter(
                repository_id__in=cumulative_ids,
                acquisition_version=ACQUISITION_VERSION,
            )
            .values("repository_id")
            .annotate(bucket_count=Count("id"))
            .filter(bucket_count__gte=required)
            .values_list("repository_id", flat=True)
        )
        repositories = Repository.objects.filter(id__in=complete_ids)
        builder = DatasetBuilder()
        per_date = {}
        for sample_date in dates:
            result = builder.build(sample_date, repositories)
            totals.update(result)
            per_date[sample_date.isoformat()] = result
        candidates = [
            candidate
            for sample_date in dates
            for repository in repositories
            if (candidate := builder._candidate(repository, sample_date)) is not None
        ]
        samples = TrainingSample.objects.filter(
            repository_id__in=complete_ids,
            sample_at__date__in=dates,
            feature_version=FEATURE_VERSION,
            label_version=LABEL_VERSION,
        )
        quality = DatasetQualityService().report(samples)
        gate = DatasetQualityGate().evaluate(samples)
        early_stop = DatasetEarlyStopService().evaluate(samples)
        request_counts = dict(client.request_counts)
        search_requests = sum(
            request_counts.get(name, 0) for name in ("commit_search", "pr_search", "issue_search")
        )
        candidate_missing = {
            feature: sum(candidate.features.get(feature) is None for candidate in candidates)
            for feature in FEATURE_NAMES
        }
        output = {
            "acquisition_version": ACQUISITION_VERSION,
            "label_version": LABEL_VERSION,
            "batch": {
                "offset": offset,
                "size": len(batch),
                "successful": len(batch) - len(failures),
                "failed": len(failures),
                "failures": failures,
                "repositories": [item.repository.full_name for item in batch],
                "distribution": {
                    "category": dict(Counter(item.category for item in batch)),
                    "star_bucket": dict(Counter(item.star_bucket for item in batch)),
                    "age_cohort": dict(Counter(item.age_cohort for item in batch)),
                },
                "buckets_created": totals["buckets_created"],
                "buckets_reused": totals["buckets_reused"],
                "elapsed_seconds": round(monotonic() - started, 3),
            },
            "github_api": {
                "total_requests": sum(request_counts.values()),
                "search_requests": search_requests,
                "core_requests": sum(request_counts.values()) - search_requests,
                "endpoint_request_counts": request_counts,
                "transport_retries": client.transport_retries,
                "rate_waits": client.rate_limit_waits,
                "contributor_202_waits": contributor_202_waits,
                "rate_limit_state": client.rate_limit_state,
            },
            "cumulative": {
                "selected": len(cumulative_memberships),
                "complete_repositories": len(complete_ids),
                "candidate_samples": totals["eligible"],
                "valid_samples": samples.count(),
                "excluded_cohort_gate": totals["skipped_small_cohort"],
                "excluded_incomplete_label": totals["skipped_incomplete_label"],
                "positive_samples": quality["positive_samples"],
                "negative_samples": quality["negative_samples"],
                "category_distribution": quality["category_distribution"],
                "age_cohort_distribution": quality["age_cohort_distribution"],
                "sample_at_distribution": quality["sample_at_distribution"],
                "candidate_feature_missingness": {
                    feature: {
                        "count": count,
                        "rate": round(count / len(candidates), 6) if candidates else None,
                    }
                    for feature, count in candidate_missing.items()
                },
                "per_date": per_date,
            },
            "quality_gate": {"passed": gate.passed, "checks": gate.checks},
            "early_stop": early_stop,
        }
        self.stdout.write(json.dumps(output, sort_keys=True))
