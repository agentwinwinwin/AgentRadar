from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.repositories.models import MonitoringTier, Repository


def initial_tier(repository: Repository, *, now) -> MonitoringTier:
    if repository.is_archived or repository.is_disabled:
        return MonitoringTier.ARCHIVED
    if (now - repository.github_created_at).days <= 7:
        return MonitoringTier.NEW
    if repository.github_pushed_at is None or (now - repository.github_pushed_at).days >= 180:
        return MonitoringTier.DORMANT
    if (now - repository.github_created_at).days >= 365 and (
        now - repository.github_pushed_at
    ).days >= 30:
        return MonitoringTier.STABLE
    return MonitoringTier.NORMAL


class Command(BaseCommand):
    help = "Initialize adaptive monitoring from existing observed snapshots without GitHub calls."

    def handle(self, *args, **options):
        now = timezone.now()
        repositories = list(
            Repository.objects.annotate(observed_last=Max("snapshots__snapshot_at")).order_by("id")
        )
        for repository in repositories:
            tier = initial_tier(repository, now=now)
            repository.monitoring_tier = tier
            repository.monitoring_enabled = tier != MonitoringTier.ARCHIVED
            repository.last_snapshot_at = repository.observed_last
            base = repository.observed_last or now
            repository.next_snapshot_at = base + timedelta(
                hours=settings.MONITORING_TIER_INTERVAL_HOURS[str(tier)]
            )
        Repository.objects.bulk_update(
            repositories,
            (
                "monitoring_tier",
                "monitoring_enabled",
                "last_snapshot_at",
                "next_snapshot_at",
            ),
            batch_size=500,
        )
        self.stdout.write(
            str(
                {
                    "repositories": len(repositories),
                    "enabled": sum(item.monitoring_enabled for item in repositories),
                    "disabled": sum(not item.monitoring_enabled for item in repositories),
                }
            )
        )
