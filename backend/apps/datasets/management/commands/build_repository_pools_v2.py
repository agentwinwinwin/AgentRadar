import json

from django.core.management.base import BaseCommand

from apps.datasets.acquisition_services import RepositoryPoolService


class Command(BaseCommand):
    help = "Build versioned post-expansion Candidate/Tracked and DRAFT Training pools."

    def add_arguments(self, parser):
        parser.add_argument("--training-target", type=int, default=800)

    def handle(self, *args, **options):
        del args
        report = RepositoryPoolService().build_v2(training_target=options["training_target"])
        self.stdout.write(json.dumps(report, sort_keys=True))
