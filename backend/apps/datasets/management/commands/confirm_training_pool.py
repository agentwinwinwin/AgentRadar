import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.datasets.models import RepositoryPool, RepositoryPoolStatus, RepositoryPoolType


class Command(BaseCommand):
    help = "Explicitly confirm a stratified Training Pool before historical backfill."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        del args
        try:
            pool = RepositoryPool.objects.get(
                name=options["name"], pool_type=RepositoryPoolType.TRAINING
            )
        except RepositoryPool.DoesNotExist as exc:
            raise CommandError("training pool does not exist") from exc
        if not pool.memberships.exists():
            raise CommandError("training pool is empty")
        pool.status = RepositoryPoolStatus.CONFIRMED
        pool.confirmed_at = timezone.now()
        pool.save(update_fields=("status", "confirmed_at", "updated_at"))
        self.stdout.write(json.dumps({"name": pool.name, "status": pool.status}))
