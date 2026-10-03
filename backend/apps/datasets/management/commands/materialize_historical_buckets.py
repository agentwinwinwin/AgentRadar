import json
from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.batch_services import MeteredRateLimitedGitHubClient
from apps.datasets.bucket_services import (
    ACQUISITION_VERSION,
    HistoricalBucketMaterializer,
    estimate_requests,
    sparse_sample_dates,
)
from apps.datasets.models import RepositoryPool, RepositoryPoolStatus, RepositoryPoolType
from apps.github.client import GitHubClientError


class Command(BaseCommand):
    help = "Materialize reusable exact activity buckets for a confirmed Training Pool slice."

    def add_arguments(self, parser):
        parser.add_argument("--training-pool", required=True)
        parser.add_argument("--pool-offset", type=int, default=0)
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--start-date", type=date.fromisoformat, required=True)
        parser.add_argument("--end-date", type=date.fromisoformat, required=True)
        parser.add_argument("--interval-days", type=int, default=30)

    def handle(self, *args, **options):
        del args
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
        start = options["pool_offset"]
        memberships = list(
            pool.memberships.select_related("repository").order_by("id")[
                start : start + options["limit"]
            ]
        )
        client = MeteredRateLimitedGitHubClient(timeout=45)
        materializer = HistoricalBucketMaterializer(client)
        totals: Counter[str] = Counter()
        failures = []
        for membership in memberships:
            try:
                result = materializer.materialize(membership.repository, dates)
            except GitHubClientError as exc:
                failures.append(
                    {"repository": membership.repository.full_name, "error": str(exc)[:200]}
                )
                continue
            totals.update(
                buckets_created=result.buckets_created,
                buckets_reused=result.buckets_reused,
                windows_created=result.windows_created,
            )
        output = {
            "acquisition_version": ACQUISITION_VERSION,
            "repositories": len(memberships),
            "successful_repositories": len(memberships) - len(failures),
            "failed_repositories": len(failures),
            "failures": failures,
            "sample_dates": [value.isoformat() for value in dates],
            **totals,
            "endpoint_request_counts": dict(client.request_counts),
            "retry_count": client.rate_limit_waits + client.transport_retries,
            "rate_limit_state": client.rate_limit_state,
            "request_estimate": estimate_requests(len(dates)),
        }
        self.stdout.write(json.dumps(output, sort_keys=True))
