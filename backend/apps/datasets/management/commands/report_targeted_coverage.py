import json

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.models import RepositoryPool, RepositoryPoolStatus, RepositoryPoolType
from apps.datasets.targeted_services import TargetedCoverageService


class Command(BaseCommand):
    help = "Report local three-category historical/label coverage without GitHub requests."

    def add_arguments(self, parser):
        parser.add_argument("--training-pool", default="sprint8-training-v2")

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
        self.stdout.write(json.dumps(TargetedCoverageService().report(pool), sort_keys=True))
