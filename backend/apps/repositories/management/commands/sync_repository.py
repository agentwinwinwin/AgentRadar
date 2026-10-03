from django.core.management.base import BaseCommand, CommandParser

from apps.github.client import RealGitHubClient
from apps.repositories.services import RepositoryService


class Command(BaseCommand):
    help = "Fetch and upsert one repository by owner/name through GitHubClient."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("full_name")

    def handle(self, *args, **options) -> None:
        repository, created = RepositoryService(RealGitHubClient()).sync_by_full_name(
            options["full_name"]
        )
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"{action} {repository.full_name}"))
