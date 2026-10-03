import json
from datetime import date

from django.core.management.base import BaseCommand

from apps.datasets.services import LABEL_VERSION, DatasetBuilder
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Build idempotent feature-v1/label-v1.1 training samples from local windows."

    def add_arguments(self, parser):
        parser.add_argument("sample_date", type=date.fromisoformat)
        parser.add_argument("--repository-id", type=int)

    def handle(self, *args, **options):
        repositories = Repository.objects.filter(is_disabled=False)
        if options["repository_id"] is not None:
            repositories = repositories.filter(pk=options["repository_id"])
        result = DatasetBuilder(label_version=LABEL_VERSION).build(
            options["sample_date"], repositories
        )
        self.stdout.write(json.dumps(result, sort_keys=True))
