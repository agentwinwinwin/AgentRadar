import json

from django.core.management.base import BaseCommand

from apps.forecasts.services import DatasetEarlyStopService


class Command(BaseCommand):
    help = (
        "Evaluate Dataset Gate plus independent Validation/Test class readiness without training."
    )

    def handle(self, *args, **options):
        del args, options
        self.stdout.write(json.dumps(DatasetEarlyStopService().evaluate(), sort_keys=True))
