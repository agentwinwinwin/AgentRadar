import json
from collections import defaultdict
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.enterprise.services import EnterpriseService
from apps.github.client import (
    GitHubClientError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    RealGitHubClient,
)
from apps.learning.enrichment import AssessmentEnrichmentService
from apps.learning.models import RepositoryAssessmentEvidence
from apps.learning.services import LearningService
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Run a bounded, representative GitHub evidence enrichment smoke."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 50:
            raise CommandError("limit must be between 1 and 50")

        client = RealGitHubClient()
        rate_before = client.get_rate_limit()["resources"]["core"]
        remaining = int(rate_before.get("remaining", 0))
        safe_limit = max(0, (remaining - settings.GITHUB_CORE_MIN_REMAINING) // 3)
        if safe_limit <= 0:
            raise CommandError("GitHub core rate-limit reserve reached")
        limit = min(limit, safe_limit)

        groups = defaultdict(list)
        queryset = (
            Repository.objects.filter(
                is_disabled=False,
                is_fork=False,
                assessment_evidence__isnull=True,
            )
            .order_by("category", "id")
            .iterator()
        )
        for repository in queryset:
            groups[repository.category].append(repository)
        selected = []
        while groups and len(selected) < limit:
            for category in list(groups):
                if groups[category] and len(selected) < limit:
                    selected.append(groups[category].pop(0))
                if not groups[category]:
                    groups.pop(category)

        enrichment = AssessmentEnrichmentService(client)
        learning = LearningService()
        enterprise = EnterpriseService()
        stats = {
            "selected": len(selected),
            "completed": 0,
            "not_found": 0,
            "failed": 0,
            "github_content_requests": 0,
            "categories": {},
        }
        started = monotonic()
        for repository in selected:
            try:
                result = enrichment.enrich(repository)
                stats["github_content_requests"] += result.requests
                stats["completed"] += 1
                stats["categories"][repository.category] = (
                    stats["categories"].get(repository.category, 0) + 1
                )
                learning.calculate_repository(repository.id)
                enterprise.calculate_repository(repository.id)
            except GitHubNotFoundError:
                enrichment.mark_not_found(repository)
                stats["not_found"] += 1
            except GitHubRateLimitError as exc:
                raise CommandError("GitHub rate limit reached; smoke stopped safely") from exc
            except GitHubClientError:
                stats["failed"] += 1

        rate_after = client.get_rate_limit()["resources"]["core"]
        stats["core_remaining_before"] = remaining
        stats["core_remaining_after"] = int(rate_after.get("remaining", 0))
        stats["elapsed_seconds"] = round(monotonic() - started, 2)
        stats["persisted_evidence"] = RepositoryAssessmentEvidence.objects.count()
        self.stdout.write(json.dumps(stats, sort_keys=True))
