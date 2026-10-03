import json

from django.core.management.base import BaseCommand

from apps.datasets.services import DatasetQualityService


class Command(BaseCommand):
    help = "Print Historical Dataset quality statistics as JSON."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(DatasetQualityService().report(), sort_keys=True))
