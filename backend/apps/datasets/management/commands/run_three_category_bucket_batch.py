import json
import time
from collections import Counter
from time import monotonic

from django.core.management.base import BaseCommand, CommandError

from apps.activities.services import ContributorStatisticsPendingError
from apps.datasets.batch_services import MeteredRateLimitedGitHubClient
from apps.datasets.bucket_services import HistoricalBucketMaterializer
from apps.datasets.models import (
    HistoricalActivityBucket,
    RepositoryPool,
    RepositoryPoolStatus,
    RepositoryPoolType,
    TrainingSample,
)
from apps.datasets.services import (
    FEATURE_VERSION,
    PERCENTILE_LABEL_VERSION,
    DatasetBuilder,
)
from apps.datasets.targeted_services import (
    TARGET_CATEGORIES,
    TARGET_SAMPLE_DATES,
    TargetedCoverageService,
    TargetedRepositorySelector,
)
from apps.forecasts.services import DatasetEarlyStopService
from apps.github.client import GitHubClientError, GitHubRateLimitError
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Run one targeted Framework/Multi/Coding activity-bucket batch."

    contributor_stats_max_attempts = 3

    def add_arguments(self, parser):
        parser.add_argument("--training-pool", default="sprint8-training-v2")
        parser.add_argument("--batch-size", type=int, default=30)
        parser.add_argument("--target-cohort-size", type=int, default=35)

    def handle(self, *args, **options):
        del args
        if not 1 <= options["batch_size"] <= 30:
            raise CommandError("batch-size must be between 1 and 30")
        if not 20 <= options["target_cohort_size"] <= 50:
            raise CommandError("target-cohort-size must be between 20 and 50")
        try:
            pool = RepositoryPool.objects.get(
                name=options["training_pool"],
                pool_type=RepositoryPoolType.TRAINING,
                status=RepositoryPoolStatus.CONFIRMED,
            )
        except RepositoryPool.DoesNotExist as exc:
            raise CommandError("a CONFIRMED Training Pool is required") from exc

        client = MeteredRateLimitedGitHubClient(timeout=45)
        rate_limit_before = client.get_rate_limit()["resources"]
        self._wait_if_needed(rate_limit_before, client)
        selected = TargetedRepositorySelector().select(
            pool,
            limit=options["batch_size"],
            target_cohort_size=options["target_cohort_size"],
        )
        if not selected:
            raise CommandError("no targeted Repository remains below the requested cohort target")

        started = monotonic()
        materializer = HistoricalBucketMaterializer(client)
        totals = Counter()
        failures = []
        contributor_202_waits = 0
        aborted_for_rate_limit = False
        processed = 0
        successful = 0
        for membership in selected:
            repository = membership.repository
            processed += 1
            for attempt in range(1, self.contributor_stats_max_attempts + 1):
                try:
                    result = materializer.materialize(repository, list(TARGET_SAMPLE_DATES))
                except ContributorStatisticsPendingError as exc:
                    if attempt == self.contributor_stats_max_attempts:
                        failures.append(
                            {"repository": repository.full_name, "error": "contributor_stats_202"}
                        )
                        break
                    contributor_202_waits += 1
                    retry_after = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 5
                    time.sleep(min(max(retry_after, 1), 60))
                except GitHubRateLimitError:
                    failures.append({"repository": repository.full_name, "error": "rate_limit"})
                    aborted_for_rate_limit = True
                    break
                except GitHubClientError as exc:
                    failures.append({"repository": repository.full_name, "error": str(exc)[:200]})
                    break
                else:
                    successful += 1
                    totals.update(
                        buckets_created=result.buckets_created,
                        buckets_reused=result.buckets_reused,
                        windows_created=result.windows_created,
                    )
                    break
            if aborted_for_rate_limit:
                break

        target_repository_ids = list(
            pool.memberships.filter(category__in=TARGET_CATEGORIES).values_list(
                "repository_id", flat=True
            )
        )
        repositories = Repository.objects.filter(id__in=target_repository_ids, is_disabled=False)
        builder = DatasetBuilder(label_version=PERCENTILE_LABEL_VERSION)
        per_date_build = {
            sample_date.isoformat(): builder.build(sample_date, repositories)
            for sample_date in TARGET_SAMPLE_DATES
        }
        samples = TrainingSample.objects.filter(
            repository_id__in=target_repository_ids,
            sample_at__date__in=TARGET_SAMPLE_DATES,
            feature_version=FEATURE_VERSION,
            label_version=PERCENTILE_LABEL_VERSION,
        )
        early_stop = DatasetEarlyStopService(label_version=PERCENTILE_LABEL_VERSION).evaluate(
            samples
        )
        coverage = TargetedCoverageService().report(pool)
        matrix = self._sample_matrix(coverage["matrix"], samples)
        request_counts = dict(client.request_counts)
        search_requests = sum(
            request_counts.get(name, 0) for name in ("commit_search", "pr_search", "issue_search")
        )
        output = {
            "batch": {
                "selected": len(selected),
                "processed": processed,
                "successful": successful,
                "skipped_after_abort": len(selected) - processed,
                "failures": failures,
                "aborted_for_rate_limit": aborted_for_rate_limit,
                "repositories": [membership.repository.full_name for membership in selected],
                "distribution": {
                    "category": dict(Counter(item.category for item in selected)),
                    "star_bucket": dict(Counter(item.star_bucket for item in selected)),
                },
                "buckets_created": totals["buckets_created"],
                "buckets_reused": totals["buckets_reused"],
                "elapsed_seconds": round(monotonic() - started, 3),
            },
            "github_api": {
                "rate_limit_before": self._safe_rate_limit(rate_limit_before),
                "total_requests": sum(request_counts.values()),
                "search_requests": search_requests,
                "core_requests": sum(request_counts.values()) - search_requests,
                "endpoint_request_counts": request_counts,
                "transport_retries": client.transport_retries,
                "rate_waits": client.rate_limit_waits,
                "contributor_202_waits": contributor_202_waits,
                "rate_limit_state": client.rate_limit_state,
            },
            "bucket_total": HistoricalActivityBucket.objects.count(),
            "dataset_build": per_date_build,
            "cohort_matrix": matrix,
            "early_stop": early_stop,
        }
        self.stdout.write(json.dumps(output, sort_keys=True))

    @staticmethod
    def _wait_if_needed(resources, client):
        now = int(time.time())
        for resource in ("search", "core"):
            values = resources.get(resource, {})
            remaining = values.get("remaining")
            reset = values.get("reset")
            if isinstance(remaining, int) and remaining <= 2:
                client._wait_for_reset(reset if isinstance(reset, int) else now + 60)

    @staticmethod
    def _safe_rate_limit(resources):
        return {
            resource: {
                key: resources.get(resource, {}).get(key)
                for key in ("limit", "used", "remaining", "reset")
            }
            for resource in ("search", "core")
        }

    @staticmethod
    def _sample_matrix(coverage, samples):
        output = {}
        for category in TARGET_CATEGORIES:
            output[category] = {}
            for sample_date in TARGET_SAMPLE_DATES:
                subset = samples.filter(category=category, sample_at__date=sample_date)
                values = coverage[category][sample_date.isoformat()]
                output[category][sample_date.isoformat()] = {
                    **values,
                    "percentile_samples": subset.exclude(future_activity_percentile=None).count(),
                    "positive": subset.filter(binary_top20_label=1).count(),
                    "negative": subset.filter(binary_top20_label=0).count(),
                }
        return output
