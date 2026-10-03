import json

from django.core.management.base import BaseCommand

from apps.github.client import RealGitHubClient
from apps.repositories.continuous import ContinuousDiscoveryService


class Command(BaseCommand):
    help = "Run bounded continuous discovery; intended for operator smoke verification."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=("new", "recent"), default="new")
        parser.add_argument("--max-queries", type=int, default=1)
        parser.add_argument("--per-query", type=int, default=2)

    def handle(self, *args, **options):
        if not 1 <= options["max_queries"] <= 16:
            raise ValueError("max-queries must be between 1 and 16")
        if not 1 <= options["per_query"] <= 20:
            raise ValueError("per-query must be between 1 and 20")
        result = ContinuousDiscoveryService(RealGitHubClient()).discover(
            mode=options["mode"],
            max_queries=options["max_queries"],
            per_query=options["per_query"],
        )
        self.stdout.write(json.dumps(result.__dict__, sort_keys=True))
