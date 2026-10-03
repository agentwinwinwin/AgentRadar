import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.batch_services import HistoricalBackfillBatchService, sample_dates
from apps.datasets.models import RepositoryPool, RepositoryPoolStatus, RepositoryPoolType


class Command(BaseCommand):
    help = "Create/resume a rate-limited, checkpointed historical backfill batch."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--start-date", type=date.fromisoformat, required=True)
        parser.add_argument("--end-date", type=date.fromisoformat, required=True)
        parser.add_argument("--interval-days", type=int, default=14)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--pool-offset", type=int, default=0)
        parser.add_argument("--max-items", type=int)
        parser.add_argument("--training-pool", required=True)
        parser.add_argument("--category", action="append", dest="categories")
        parser.add_argument("--created-on-or-after", type=date.fromisoformat)
        parser.add_argument("--created-on-or-before", type=date.fromisoformat)

    def handle(self, *args, **options):
        dates = sample_dates(options["start_date"], options["end_date"], options["interval_days"])
        try:
            training_pool = RepositoryPool.objects.get(
                name=options["training_pool"],
                pool_type=RepositoryPoolType.TRAINING,
                status=RepositoryPoolStatus.CONFIRMED,
            )
        except RepositoryPool.DoesNotExist as exc:
            raise CommandError("a CONFIRMED Training Pool is required") from exc
        memberships = (
            training_pool.memberships.select_related("repository")
            .filter(
                repository__is_disabled=False,
                repository__is_fork=False,
                repository__is_archived=False,
            )
            .exclude(
                repository__full_name__in=("smoke/activity", "github/docs", "octocat/Hello-World")
            )
        )
        if options["categories"]:
            memberships = memberships.filter(category__in=options["categories"])
        if options["created_on_or_after"]:
            memberships = memberships.filter(
                repository__github_created_at__date__gte=options["created_on_or_after"]
            )
        if options["created_on_or_before"]:
            memberships = memberships.filter(
                repository__github_created_at__date__lte=options["created_on_or_before"]
            )
        start = options["pool_offset"]
        end = start + options["limit"]
        repositories = [
            membership.repository for membership in memberships.order_by("id")[start:end]
        ]
        if not repositories:
            raise CommandError("no eligible repositories")
        configuration = {
            "repository_ids": [repository.id for repository in repositories],
            "training_pool": training_pool.name,
            "training_pool_selection_version": training_pool.selection_version,
            "pool_offset": options["pool_offset"],
            "categories": sorted(options["categories"] or []),
            "start_date": options["start_date"].isoformat(),
            "end_date": options["end_date"].isoformat(),
            "interval_days": options["interval_days"],
            "created_on_or_after": (
                options["created_on_or_after"].isoformat()
                if options["created_on_or_after"]
                else None
            ),
            "created_on_or_before": (
                options["created_on_or_before"].isoformat()
                if options["created_on_or_before"]
                else None
            ),
        }
        service = HistoricalBackfillBatchService()
        try:
            batch = service.create_or_resume(
                name=options["name"],
                repositories=repositories,
                dates=dates,
                configuration=configuration,
            )
            result = service.run(batch, max_items=options["max_items"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(service.report(result.batch), sort_keys=True))
