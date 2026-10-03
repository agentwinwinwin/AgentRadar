import json
from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.models import RepositoryPool, RepositoryPoolType


class Command(BaseCommand):
    help = "Simulate local Category + sample_at label cohorts without GitHub requests."

    def add_arguments(self, parser):
        parser.add_argument("pool")
        parser.add_argument(
            "--sample-at",
            action="append",
            type=date.fromisoformat,
            default=[],
        )

    def handle(self, *args, **options):
        del args
        dates = options["sample_at"] or [
            date(2026, 4, 18),
            date(2026, 5, 18),
            date(2026, 6, 17),
            date(2026, 7, 17),
        ]
        try:
            pool = RepositoryPool.objects.get(
                name=options["pool"], pool_type=RepositoryPoolType.TRAINING
            )
        except RepositoryPool.DoesNotExist as exc:
            raise CommandError("training pool does not exist") from exc
        matrix = {}
        passing_dates = 0
        passing_categories = set()
        for sample_at in dates:
            counts = Counter(
                pool.memberships.filter(
                    repository__github_created_at__date__lte=sample_at
                ).values_list("category", flat=True)
            )
            matrix[sample_at.isoformat()] = {
                category: {"count": count, "status": "PASS" if count >= 20 else "FAIL"}
                for category, count in sorted(counts.items())
            }
            passed = {category for category, count in counts.items() if count >= 20}
            passing_categories.update(passed)
            passing_dates += int(len(passed) >= 3)
        gate = len(passing_categories) >= 3 and passing_dates >= 3
        self.stdout.write(
            json.dumps(
                {
                    "pool": pool.name,
                    "pool_status": pool.status,
                    "matrix": matrix,
                    "passing_categories": sorted(passing_categories),
                    "passing_sample_dates": passing_dates,
                    "simulation_gate_passed": gate,
                },
                sort_keys=True,
            )
        )
