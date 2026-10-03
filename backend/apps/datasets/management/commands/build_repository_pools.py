import json

from django.core.management.base import BaseCommand

from apps.datasets.acquisition_services import RepositoryPoolService


class Command(BaseCommand):
    help = "Build Candidate/Tracked pools and a stratified DRAFT Training Pool."

    def add_arguments(self, parser):
        parser.add_argument("--training-target", type=int, default=300)
        parser.add_argument("--head-repository-id", type=int, action="append", default=[])

    def handle(self, *args, **options):
        del args
        report = RepositoryPoolService().build(
            training_target=options["training_target"],
            head_repository_ids=options["head_repository_id"],
        )
        self.stdout.write(json.dumps(report, sort_keys=True))
