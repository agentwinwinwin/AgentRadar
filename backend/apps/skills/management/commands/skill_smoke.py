import json

from django.core.management.base import BaseCommand, CommandError

from apps.activities.models import RepositoryActivityMetric
from apps.enterprise.models import RepositoryEnterpriseScore
from apps.forecasts.models import MLModel, RepositoryForecast
from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.learning.models import RepositoryLearningScore
from apps.potentials.models import RepositoryPotentialScore
from apps.repositories.models import Repository, RepositoryCategory
from apps.skills.contracts import Intent
from apps.skills.executor import SkillExecutor
from apps.skills.registry import SkillRegistry
from apps.snapshots.models import RepositorySnapshot
from apps.trends.models import RepositoryTrendScore


def protected_counts() -> dict[str, int]:
    return {
        "repositories": Repository.objects.count(),
        "snapshots": RepositorySnapshot.objects.count(),
        "activity": RepositoryActivityMetric.objects.count(),
        "trends": RepositoryTrendScore.objects.count(),
        "potentials": RepositoryPotentialScore.objects.count(),
        "models": MLModel.objects.count(),
        "forecasts": RepositoryForecast.objects.count(),
        "learning": RepositoryLearningScore.objects.count(),
        "enterprise": RepositoryEnterpriseScore.objects.count(),
        "documents": KnowledgeDocument.objects.count(),
        "chunks": KnowledgeChunk.objects.count(),
    }


class Command(BaseCommand):
    help = "Execute six deterministic Skill workflows against real read-only Tools."

    def handle(self, *args, **options):
        knowledge_ids = list(
            Repository.objects.filter(knowledge_documents__is_active=True)
            .distinct()
            .order_by("id")
            .values_list("id", flat=True)[:2]
        )
        if len(knowledge_ids) < 2:
            raise CommandError("Skill smoke requires two Knowledge repositories")
        executor = SkillExecutor()
        registry = SkillRegistry()
        dry_run = registry.dry_run(
            Intent.TREND_DISCOVERY,
            user_constraints={"category": RepositoryCategory.CODING_AGENT},
        )
        cases = [
            (
                Intent.TREND_DISCOVERY,
                {"category": RepositoryCategory.CODING_AGENT},
                {},
            ),
            (
                Intent.LEARNING_RECOMMENDATION,
                {"category": RepositoryCategory.AGENT_FRAMEWORK},
                {},
            ),
            (
                Intent.ENTERPRISE_SELECTION,
                {"category": RepositoryCategory.CODING_AGENT},
                {},
            ),
            (Intent.PROJECT_ANALYSIS, {}, {"repository_id": knowledge_ids[0]}),
            (Intent.PROJECT_COMPARISON, {}, {"repositories": knowledge_ids}),
            (Intent.FUTURE_PREDICTION, {}, {"repository_id": knowledge_ids[0]}),
        ]
        before = protected_counts()
        traces = []
        for intent, constraints, entities in cases:
            result = executor.execute(
                intent,
                user_constraints=constraints,
                resolved_entities=entities,
            )
            if result["tool_calls"] > result["tool_budget"]:
                raise CommandError(f"Tool budget exceeded for {intent}")
            traces.append(
                {
                    key: result[key]
                    for key in (
                        "selected_skill",
                        "skill_version",
                        "intent",
                        "executed_tools",
                        "tool_duration_ms",
                        "result_status",
                        "warnings",
                        "evidence_count",
                        "stop_reason",
                        "tool_calls",
                        "tool_budget",
                    )
                }
            )
        future = traces[-1]
        if future["result_status"] != "CURRENT_SIGNAL_ANALYSIS":
            raise CommandError("Forecast NOT_READY fallback failed")
        after = protected_counts()
        if before != after:
            raise CommandError("Read-only Skill workflow changed protected data")
        self.stdout.write(
            json.dumps(
                {
                    "dry_run": {
                        "selected_skill": dry_run["selected_skill"],
                        "executed": dry_run["executed"],
                        "planned_steps": len(dry_run["planned_steps"]),
                    },
                    "traces": traces,
                    "protected_counts_unchanged": True,
                },
                sort_keys=True,
            )
        )
