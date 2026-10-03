import json

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.batch_services import HistoricalBackfillBatchService
from apps.datasets.models import HistoricalBackfillBatch


class Command(BaseCommand):
    help = "Report durable progress and request counts for one historical backfill batch."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        try:
            batch = HistoricalBackfillBatch.objects.get(name=options["name"])
        except HistoricalBackfillBatch.DoesNotExist as exc:
            raise CommandError("batch not found") from exc
        self.stdout.write(json.dumps(HistoricalBackfillBatchService.report(batch), sort_keys=True))
