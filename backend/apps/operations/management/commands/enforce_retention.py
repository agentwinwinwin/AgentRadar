import json

from django.core.management.base import BaseCommand

from apps.operations.retention import retention_counts


class Command(BaseCommand):
    help = "Report expired rows; delete only when --apply is explicitly supplied."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(retention_counts(apply=options["apply"]), sort_keys=True))
