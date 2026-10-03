import json
from dataclasses import asdict

from django.core.management.base import BaseCommand

from apps.datasets.batch_services import MeteredRateLimitedGitHubClient
from apps.datasets.discovery_expansion import DiscoveryExpansionService


class Command(BaseCommand):
    help = "Plan and execute resumable metadata-only GitHub Discovery shards."

    def add_arguments(self, parser):
        parser.add_argument("--target", type=int, default=3000)
        parser.add_argument("--max-shards", type=int, default=500)
        parser.add_argument("--plan-only", action="store_true")

    def handle(self, *args, **options):
        del args
        client = MeteredRateLimitedGitHubClient(timeout=45)
        service = DiscoveryExpansionService(client)
        planned = service.plan()
        if options["plan_only"]:
            self.stdout.write(json.dumps({"planned_shards": planned}, sort_keys=True))
            return
        result = service.execute(target=options["target"], max_shards=options["max_shards"])
        output = {
            "planned_shards": planned,
            **asdict(result),
            "rate_limit_state": client.rate_limit_state,
            "rate_waits": client.rate_limit_waits,
            "transport_retries": client.transport_retries,
        }
        self.stdout.write(json.dumps(output, sort_keys=True))
