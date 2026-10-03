import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.datasets.models import (
    BackfillItemStatus,
    HistoricalActivityWindow,
    HistoricalBackfillBatch,
    TrainingSample,
)
from apps.datasets.services import DatasetBuilder, DatasetQualityService
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Build Training Samples for one backfill batch and print its quality report."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        del args
        try:
            batch = HistoricalBackfillBatch.objects.get(name=options["name"])
        except HistoricalBackfillBatch.DoesNotExist as exc:
            raise CommandError("backfill batch does not exist") from exc
        repository_ids = list(batch.items.values_list("repository_id", flat=True).distinct())
        repositories = Repository.objects.filter(id__in=repository_ids)
        dates = list(batch.items.values_list("sample_date", flat=True).distinct().order_by())
        totals: Counter[str] = Counter()
        per_date = {}
        builder = DatasetBuilder()
        for sample_date in dates:
            result = builder.build(sample_date, repositories)
            totals.update(result)
            per_date[sample_date.isoformat()] = result
        samples = TrainingSample.objects.filter(
            repository_id__in=repository_ids,
            sample_at__date__in=dates,
        )
        item_statuses = Counter(batch.items.values_list("status", flat=True))
        output = {
            "batch": batch.name,
            "repositories": len(repository_ids),
            "backfill_items": batch.items.count(),
            "successful_items": item_statuses[BackfillItemStatus.SUCCEEDED],
            "failed_items": item_statuses[BackfillItemStatus.FAILED],
            "historical_windows_for_repositories": HistoricalActivityWindow.objects.filter(
                repository_id__in=repository_ids
            ).count(),
            "historical_windows_created_by_batch": sum(
                batch.items.values_list("windows_created", flat=True)
            ),
            "training_sample_candidates": totals["eligible"],
            "valid_labels": totals["created"] + totals["updated"],
            "excluded_incomplete_label": totals["skipped_incomplete_label"],
            "excluded_cohort_gate": totals["skipped_small_cohort"],
            "per_date": per_date,
            "quality": DatasetQualityService().report(samples),
        }
        self.stdout.write(json.dumps(output, sort_keys=True))
