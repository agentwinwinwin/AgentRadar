from django.core.management.base import BaseCommand, CommandParser

from apps.github.client import RealGitHubClient
from apps.repositories.services import RepositoryDiscoveryService


class Command(BaseCommand):
    help = "Discover AI Agent repositories through configured GitHub queries."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--per-query", type=int, default=100)
        parser.add_argument("--pages-per-query", type=int, default=10)
        parser.add_argument("--start-page", type=int, default=1)

    def handle(self, *args, **options) -> None:
        result = RepositoryDiscoveryService(RealGitHubClient()).discover(
            per_query=options["per_query"],
            pages_per_query=options["pages_per_query"],
            start_page=options["start_page"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"queries={result.queries_executed} seen={result.repositories_seen} "
                f"created={result.repositories_created} updated={result.repositories_updated} "
                f"skipped={result.repositories_skipped} "
                f"incomplete={result.incomplete_queries} truncated={result.truncated_queries}"
            )
        )
