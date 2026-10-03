import json
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.enterprise.services import EnterpriseService
from apps.learning.services import LearningService
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Calculate deterministic Learning and Enterprise scores."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--all", action="store_true")
        parser.add_argument(
            "--summary",
            action="store_true",
            help="Return aggregate counts instead of one row per repository.",
        )
        parser.add_argument(
            "--knowledge-pilot",
            action="store_true",
            help="Restrict selection to repositories with active Knowledge documents.",
        )

    def handle(self, *args, **options):
        queryset = Repository.objects.filter(is_disabled=False, is_fork=False).order_by(
            "category", "-is_archived", "id"
        )
        if options["knowledge_pilot"]:
            queryset = queryset.filter(knowledge_documents__is_active=True).distinct()
        if options["all"]:
            repositories = list(queryset)
        else:
            if not 1 <= options["limit"] <= 500:
                raise ValueError("limit must be between 1 and 500")
            groups = defaultdict(list)
            for repository in queryset:
                groups[repository.category].append(repository)
            repositories = []
            while groups and len(repositories) < options["limit"]:
                for category in list(groups):
                    if groups[category] and len(repositories) < options["limit"]:
                        repositories.append(groups[category].pop(0))
                    if not groups[category]:
                        groups.pop(category)
        output = []
        summary = {
            "repositories": 0,
            "learning_scored": 0,
            "learning_null": 0,
            "learning_high_confidence": 0,
            "enterprise_scored": 0,
            "enterprise_null": 0,
            "enterprise_high_confidence": 0,
        }
        learning_service = LearningService()
        enterprise_service = EnterpriseService()
        for repository in repositories:
            learning = learning_service.calculate_repository(repository.id)
            enterprise = enterprise_service.calculate_repository(repository.id)
            summary["repositories"] += 1
            if learning.score is None:
                summary["learning_null"] += 1
            else:
                summary["learning_scored"] += 1
            if learning.confidence >= 0.6:
                summary["learning_high_confidence"] += 1
            if enterprise.score is None:
                summary["enterprise_null"] += 1
            else:
                summary["enterprise_scored"] += 1
            if enterprise.confidence >= 0.6:
                summary["enterprise_high_confidence"] += 1
            output.append(
                {
                    "repository": repository.full_name,
                    "category": repository.category,
                    "archived": repository.is_archived,
                    "learning": float(learning.score) if learning.score is not None else None,
                    "learning_confidence": learning.confidence,
                    "enterprise": float(enterprise.score) if enterprise.score is not None else None,
                    "enterprise_confidence": enterprise.confidence,
                    "recommendation": enterprise.recommendation,
                    "knowledge_status": learning.evidence["knowledge_status"],
                }
            )
        self.stdout.write(json.dumps(summary if options["summary"] else output, sort_keys=True))
