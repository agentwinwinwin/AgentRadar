from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from apps.repositories.models import Repository

from .acquisition_services import STAR_BUCKETS
from .bucket_services import ACQUISITION_VERSION
from .models import (
    DataOrigin,
    HistoricalActivityBucket,
    HistoricalActivityWindow,
    RepositoryPool,
    RepositoryPoolMembership,
)

TARGET_CATEGORIES = ("AGENT_FRAMEWORK", "MULTI_AGENT", "CODING_AGENT")
TARGET_SAMPLE_DATES = (
    date(2026, 4, 18),
    date(2026, 5, 18),
    date(2026, 6, 17),
    date(2026, 7, 17),
)
LABEL_FIELDS = (
    "commits",
    "prs_created",
    "prs_merged",
    "issues_closed",
    "active_contributors",
    "releases",
)


def _window_ranges(sample_date: date) -> tuple[tuple[date, date], ...]:
    return (
        (sample_date - timedelta(days=6), sample_date),
        (sample_date - timedelta(days=29), sample_date),
        (sample_date + timedelta(days=1), sample_date + timedelta(days=30)),
    )


def _label_window(sample_date: date) -> tuple[date, date]:
    return sample_date + timedelta(days=1), sample_date + timedelta(days=30)


class TargetedCoverageService:
    def report(
        self,
        pool: RepositoryPool,
        *,
        categories: Iterable[str] = TARGET_CATEGORIES,
        sample_dates: Iterable[date] = TARGET_SAMPLE_DATES,
    ) -> dict[str, Any]:
        categories = tuple(categories)
        sample_dates = tuple(sample_dates)
        memberships = pool.memberships.filter(category__in=categories)
        matrix: dict[str, dict[str, dict[str, int]]] = {}
        for category in categories:
            category_memberships = memberships.filter(category=category)
            matrix[category] = {}
            for sample_date in sample_dates:
                theoretical_ids = list(
                    category_memberships.filter(
                        repository__github_created_at__date__lte=sample_date,
                        repository__is_disabled=False,
                    ).values_list("repository_id", flat=True)
                )
                historical_complete = self._historical_complete_ids(theoretical_ids, sample_date)
                label_complete = self._label_complete_ids(historical_complete, sample_date)
                label_count = len(label_complete)
                matrix[category][sample_date.isoformat()] = {
                    "theoretical_repository_count": len(theoretical_ids),
                    "historical_complete_repository_count": len(historical_complete),
                    "label_complete_repository_count": label_count,
                    "effective_cohort_size": label_count if label_count >= 20 else 0,
                }
        return {
            "pool": pool.name,
            "bucket_count": HistoricalActivityBucket.objects.count(),
            "backfilled_repository_count": HistoricalActivityBucket.objects.values("repository_id")
            .distinct()
            .count(),
            "matrix": matrix,
        }

    @staticmethod
    def _historical_complete_ids(repository_ids: list[int], sample_date: date) -> list[int]:
        complete = set(repository_ids)
        for start, end in _window_ranges(sample_date):
            present = set(
                HistoricalActivityWindow.objects.filter(
                    repository_id__in=complete,
                    window_start=start,
                    window_end=end,
                    data_origin=DataOrigin.BACKFILLED,
                ).values_list("repository_id", flat=True)
            )
            complete &= present
        return sorted(complete)

    @staticmethod
    def _label_complete_ids(repository_ids: list[int], sample_date: date) -> list[int]:
        start, end = _label_window(sample_date)
        queryset = HistoricalActivityWindow.objects.filter(
            repository_id__in=repository_ids,
            window_start=start,
            window_end=end,
            data_origin=DataOrigin.BACKFILLED,
        )
        for field in LABEL_FIELDS:
            queryset = queryset.exclude(**{f"{field}__isnull": True})
        return list(queryset.values_list("repository_id", flat=True))


def _cycle_star_buckets(memberships: list[RepositoryPoolMembership]):
    groups = defaultdict(list)
    for membership in memberships:
        groups[membership.star_bucket].append(membership)
    output = []
    depth = 0
    while True:
        added = False
        for bucket in STAR_BUCKETS:
            if depth < len(groups[bucket]):
                output.append(groups[bucket][depth])
                added = True
        if not added:
            return output
        depth += 1


class TargetedRepositorySelector:
    def select(
        self,
        pool: RepositoryPool,
        *,
        limit: int,
        target_cohort_size: int = 35,
    ) -> list[RepositoryPoolMembership]:
        if not 1 <= limit <= 30:
            raise ValueError("targeted batch limit must be between 1 and 30")
        coverage = TargetedCoverageService().report(pool)["matrix"]
        deficits = {
            category: max(
                target_cohort_size
                - min(values["label_complete_repository_count"] for values in dates.values()),
                0,
            )
            for category, dates in coverage.items()
        }
        complete_all = self._complete_for_all_dates()
        existing_bucket_counts = Counter(
            HistoricalActivityBucket.objects.filter(
                acquisition_version=ACQUISITION_VERSION
            ).values_list("repository_id", flat=True)
        )
        by_category = {}
        for category in TARGET_CATEGORIES:
            memberships = list(
                pool.memberships.select_related("repository")
                .filter(
                    category=category,
                    repository__github_created_at__date__lte=TARGET_SAMPLE_DATES[0],
                    repository__is_disabled=False,
                )
                .exclude(repository_id__in=complete_all)
            )
            memberships.sort(
                key=lambda item: (
                    -existing_bucket_counts[item.repository_id],
                    item.stratum_rank or 0,
                    item.repository_id,
                )
            )
            by_category[category] = _cycle_star_buckets(memberships)
        selected = []
        positions = Counter()
        selected_counts = Counter()
        while len(selected) < limit:
            available = [
                category
                for category in TARGET_CATEGORIES
                if positions[category] < len(by_category[category])
                and selected_counts[category] < deficits[category]
            ]
            if not available:
                break
            category = max(
                available,
                key=lambda item: (
                    deficits[item] - selected_counts[item],
                    -TARGET_CATEGORIES.index(item),
                ),
            )
            selected.append(by_category[category][positions[category]])
            positions[category] += 1
            selected_counts[category] += 1
        return selected

    @staticmethod
    def _complete_for_all_dates() -> set[int]:
        repository_ids = set(Repository.objects.values_list("id", flat=True))
        service = TargetedCoverageService()
        for sample_date in TARGET_SAMPLE_DATES:
            repository_ids &= set(
                service._historical_complete_ids(list(repository_ids), sample_date)
            )
        return repository_ids
