import json

from django.core.management.base import BaseCommand

from apps.datasets.acquisition_services import QueryShardingService
from apps.github.client import RealGitHubClient


class Command(BaseCommand):
    help = "Run only active coverage-shortage query shards in a bounded batch."

    def add_arguments(self, parser):
        parser.add_argument("--limit-shards", type=int, default=10)
        parser.add_argument("--per-shard", type=int, default=10)

    def handle(self, *args, **options):
        del args
        report = QueryShardingService(RealGitHubClient(timeout=45)).execute(
            limit_shards=options["limit_shards"], per_shard=options["per_shard"]
        )
        self.stdout.write(json.dumps(report, sort_keys=True))
