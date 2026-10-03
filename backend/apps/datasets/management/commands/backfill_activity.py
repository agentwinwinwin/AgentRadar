import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.activities.services import ContributorStatisticsPendingError
from apps.datasets.services import HistoricalBackfillService
from apps.github.client import GitHubClientError, RealGitHubClient
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Backfill three historical GitHub activity windows for a repository/sample date."

    def add_arguments(self, parser):
        parser.add_argument("repository_id", type=int)
        parser.add_argument("sample_date", type=date.fromisoformat)

    def handle(self, *args, **options):
        try:
            repository = Repository.objects.get(pk=options["repository_id"], is_disabled=False)
            result = HistoricalBackfillService(RealGitHubClient()).collect(
                repository, options["sample_date"]
            )
        except (
            Repository.DoesNotExist,
            ValueError,
            GitHubClientError,
            ContributorStatisticsPendingError,
        ) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "repository_id": repository.id,
                    "sample_date": options["sample_date"].isoformat(),
                    "windows": len(result.windows),
                    "created": result.created,
                }
            )
        )
