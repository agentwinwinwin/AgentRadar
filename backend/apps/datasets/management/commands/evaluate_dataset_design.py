import json
from datetime import date

from django.core.management.base import BaseCommand

from apps.datasets.acquisition_services import RepositoryPoolService
from apps.datasets.models import HistoricalActivityBucket, TrainingSample
from apps.datasets.services import PERCENTILE_LABEL_VERSION, DatasetBuilder
from apps.repositories.models import Repository

SAMPLE_DATES = (
    date(2026, 4, 18),
    date(2026, 5, 18),
    date(2026, 6, 17),
    date(2026, 7, 17),
)


class Command(BaseCommand):
    help = "Simulate Training Pool sizes and locally validate label-v1.2.0."

    def handle(self, *args, **options):
        del args, options
        simulation = RepositoryPoolService().simulate_training_sizes(
            targets=(800, 1000, 1200, 1500),
            sample_dates=SAMPLE_DATES,
        )
        repository_ids = list(
            HistoricalActivityBucket.objects.values_list("repository_id", flat=True).distinct()
        )
        repositories = Repository.objects.filter(id__in=repository_ids, is_disabled=False)
        builder = DatasetBuilder(label_version=PERCENTILE_LABEL_VERSION)
        build_totals = {
            "eligible": 0,
            "skipped_incomplete_label": 0,
            "skipped_small_cohort": 0,
            "created": 0,
            "updated": 0,
        }
        per_date = {}
        for sample_date in SAMPLE_DATES:
            result = builder.build(sample_date, repositories)
            per_date[sample_date.isoformat()] = result
            for key, value in result.items():
                build_totals[key] += value
        samples = TrainingSample.objects.filter(label_version=PERCENTILE_LABEL_VERSION)
        output = {
            **simulation,
            "existing_bucket_validation": {
                "bucket_count": HistoricalActivityBucket.objects.count(),
                "repository_count": len(repository_ids),
                "per_date": per_date,
                "totals": build_totals,
                "percentile_labels": samples.exclude(future_activity_percentile=None).count(),
                "binary_labels": samples.exclude(binary_top20_label=None).count(),
            },
        }
        self.stdout.write(json.dumps(output, sort_keys=True))
