import json

from django.core.management.base import BaseCommand

from apps.datasets.acquisition_services import HeadCoverageService
from apps.github.client import RealGitHubClient


class Command(BaseCommand):
    help = "Verify major Category GitHub star Top N coverage without overwriting existing rows."

    def add_arguments(self, parser):
        parser.add_argument("--top-n", type=int, default=10)

    def handle(self, *args, **options):
        del args
        report = HeadCoverageService(RealGitHubClient(timeout=45)).ensure(top_n=options["top_n"])
        self.stdout.write(json.dumps(report, sort_keys=True))
