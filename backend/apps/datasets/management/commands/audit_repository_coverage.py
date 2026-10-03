import json

from django.core.management.base import BaseCommand

from apps.datasets.acquisition_services import CoverageAuditService, QueryShardingService


class Command(BaseCommand):
    help = "Audit Repository coverage and persist targeted acquisition query shards."

    def handle(self, *args, **options):
        del args, options
        report = CoverageAuditService().report()
        shards = QueryShardingService().plan(report)
        report["query_shards"] = len(shards)
        self.stdout.write(json.dumps(report, sort_keys=True))
