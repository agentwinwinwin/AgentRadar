import json
import time
from collections import Counter, defaultdict
from datetime import date
from time import monotonic

from django.core.management.base import BaseCommand, CommandError

from apps.activities.services import ContributorStatisticsPendingError
from apps.datasets.batch_services import MeteredRateLimitedGitHubClient
from apps.datasets.bucket_services import (
    ACQUISITION_VERSION,
    SAMPLING_VERSION,
    HistoricalBucketMaterializer,
    estimate_requests,
    sparse_sample_dates,
)
from apps.datasets.models import (
    HistoricalActivityBucket,
    RepositoryPool,
    RepositoryPoolStatus,
    RepositoryPoolType,
    TrainingSample,
)
from apps.datasets.services import FEATURE_NAMES, DatasetBuilder, DatasetQualityService
from apps.github.client import GitHubClientError
from apps.repositories.models import Repository


def stratified_memberships(pool: RepositoryPool, limit: int, eligible_at: date):
    groups = defaultdict(list)
    memberships = pool.memberships.select_related("repository").filter(
        repository__github_created_at__date__lte=eligible_at,
        repository__is_disabled=False,
    )
    for membership in memberships.order_by("stratum_rank", "id"):
        groups[(membership.category, membership.star_bucket, membership.age_cohort)].append(
            membership
        )
    selected = []
    depth = 0
    keys = sorted(groups)
    while len(selected) < limit:
        added = False
        for key in keys:
            if depth < len(groups[key]):
                selected.append(groups[key][depth])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        depth += 1
    return selected


class Command(BaseCommand):
    help = "Run one stratified, metered activity-bucket validation batch."

    contributor_stats_max_attempts = 3

    def add_arguments(self, parser):
        parser.add_argument("--training-pool", required=True)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--start-date", type=date.fromisoformat, required=True)
        parser.add_argument("--end-date", type=date.fromisoformat, required=True)
        parser.add_argument("--interval-days", type=int, default=30)

    def handle(self, *args, **options):
        del args
        if options["limit"] < 1:
            raise CommandError("limit must be positive")
        try:
            pool = RepositoryPool.objects.get(
                name=options["training_pool"],
                pool_type=RepositoryPoolType.TRAINING,
                status=RepositoryPoolStatus.CONFIRMED,
            )
        except RepositoryPool.DoesNotExist as exc:
            raise CommandError("a CONFIRMED Training Pool is required") from exc
        dates = sparse_sample_dates(
            options["start_date"], options["end_date"], options["interval_days"]
        )
        memberships = stratified_memberships(pool, options["limit"], dates[0])
        if len(memberships) != options["limit"]:
            raise CommandError("not enough historically eligible Training Pool repositories")

        client = MeteredRateLimitedGitHubClient(timeout=45)
        materializer = HistoricalBucketMaterializer(client)
        started = monotonic()
        totals = Counter()
        failures = []
        successful_ids = []
        for membership in memberships:
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
                    client.rate_limit_waits += 1
                    retry_after = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 5
                    time.sleep(min(max(retry_after, 1), 60))
                    continue
                except GitHubClientError as exc:
                    failures.append({"repository": repository.full_name, "error": str(exc)[:200]})
                    break
                else:
                    totals.update(
                        buckets_created=result.buckets_created,
                        buckets_reused=result.buckets_reused,
                        windows_created=result.windows_created,
                    )
                    successful_ids.append(repository.id)
                    break

        repositories = Repository.objects.filter(id__in=successful_ids)
        per_date = {}
        builder = DatasetBuilder()
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
        candidate_missing = {
            feature: sum(candidate.features.get(feature) is None for candidate in candidates)
            for feature in FEATURE_NAMES
        }

        samples = TrainingSample.objects.filter(
            repository_id__in=successful_ids,
            sample_at__date__in=dates,
        )
        quality = DatasetQualityService().report(samples)
        request_counts = dict(client.request_counts)
        search_requests = sum(
            request_counts.get(name, 0) for name in ("commit_search", "pr_search", "issue_search")
        )
        distribution = {
            "category": dict(Counter(item.category for item in memberships)),
            "star_bucket": dict(Counter(item.star_bucket for item in memberships)),
            "age_cohort": dict(Counter(item.age_cohort for item in memberships)),
        }
        output = {
            "acquisition_version": ACQUISITION_VERSION,
            "sampling_version": SAMPLING_VERSION,
            "training_pool": pool.name,
            "repositories": len(memberships),
            "successful_repositories": len(successful_ids),
            "failed_repositories": len(failures),
            "failures": failures,
            "selected_repositories": [item.repository.full_name for item in memberships],
            "distribution": distribution,
            "sample_dates": [value.isoformat() for value in dates],
            "historical_buckets": HistoricalActivityBucket.objects.filter(
                repository_id__in=successful_ids,
                acquisition_version=ACQUISITION_VERSION,
            ).count(),
            "buckets_created": totals["buckets_created"],
            "buckets_reused": totals["buckets_reused"],
            "training_sample_candidates": totals["eligible"],
            "valid_training_samples": samples.count(),
            "positive_samples": quality["positive_samples"],
            "negative_samples": quality["negative_samples"],
            "excluded_cohort_gate": totals["skipped_small_cohort"],
            "excluded_incomplete_data": totals["skipped_incomplete_label"],
            "candidate_feature_missingness": {
                feature: {
                    "count": count,
                    "rate": round(count / len(candidates), 6) if candidates else None,
                }
                for feature, count in candidate_missing.items()
            },
            "valid_sample_feature_missingness": quality["missing_features"],
            "per_date": per_date,
            "endpoint_request_counts": request_counts,
            "github_api_requests": sum(request_counts.values()),
            "search_requests": search_requests,
            "retry_count": client.rate_limit_waits + client.transport_retries,
            "rate_limit_state": client.rate_limit_state,
            "request_estimate": estimate_requests(len(dates)),
            "elapsed_seconds": round(monotonic() - started, 3),
        }
        self.stdout.write(json.dumps(output, sort_keys=True))
