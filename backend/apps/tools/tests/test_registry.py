from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from django.utils import timezone

from apps.activities.models import RepositoryActivityMetric
from apps.enterprise.engine import ALGORITHM_VERSION as ENTERPRISE_ALGORITHM_VERSION
from apps.enterprise.models import RepositoryEnterpriseScore
from apps.knowledge.embeddings import embedding_client
from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeSourceType
from apps.learning.engine import ALGORITHM_VERSION as LEARNING_ALGORITHM_VERSION
from apps.learning.models import RepositoryLearningScore
from apps.potentials.models import RepositoryPotentialScore
from apps.repositories.models import Repository, RepositoryCategory
from apps.snapshots.models import RepositorySnapshot
from apps.tools.registry import MAX_LIST_LIMIT, ToolRegistry
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore


@pytest.fixture
def projects(db):
    now = timezone.now()
    repositories = []
    for index, name in enumerate(("alpha", "beta", "gamma"), 1):
        repository = Repository.objects.create(
            github_id=9000 + index,
            owner="acme",
            name=name,
            full_name=f"acme/{name}",
            category=RepositoryCategory.CODING_AGENT,
            stars=index * 100,
            forks=index * 10,
            default_branch="main",
            github_created_at=now,
            github_updated_at=now,
            last_synced_at=now,
        )
        RepositorySnapshot.objects.create(
            repository=repository,
            snapshot_at=now,
            snapshot_date=now.date(),
            snapshot_bucket=f"2026-08-17T0{index}",
            stars=repository.stars,
            forks=repository.forks,
            data_completeness=1,
        )
        RepositoryActivityMetric.objects.create(
            repository=repository,
            metric_date=date(2026, 8, 17),
            commits_30d=index * 5,
            prs_created_30d=index,
            issues_created_30d=0,
            releases_30d=0,
        )
        RepositoryTrendScore.objects.create(
            repository=repository,
            trend_score=50 + index,
            momentum_score=50,
            development_score=50,
            community_score=50,
            delivery_score=50,
            adoption_score=50,
            maintenance_score=50,
            hype_risk=None,
            hype_risk_status=HypeRiskStatus.INSUFFICIENT_HISTORY,
            lifecycle_stage=LifecycleStage.GROWING,
            data_completeness=0.8,
            algorithm_version="trend-v1.0.0",
            calculated_at=now,
            evidence={"source": "test"},
        )
        RepositoryPotentialScore.objects.create(
            repository=repository,
            potential_score=60 + index,
            confidence=0.8,
            algorithm_version="potential-v1.0.0",
            evidence={"components": {}},
            calculated_at=now,
        )
        RepositoryLearningScore.objects.create(
            repository=repository,
            score=70 + index,
            confidence=0.8,
            algorithm_version=LEARNING_ALGORITHM_VERSION,
            evidence={"knowledge_status": "INGESTED"},
            calculated_at=now,
        )
        RepositoryEnterpriseScore.objects.create(
            repository=repository,
            score=65 + index,
            confidence=0.8,
            recommendation="POC",
            algorithm_version=ENTERPRISE_ALGORITHM_VERSION,
            evidence={"knowledge_status": "INGESTED"},
            calculated_at=now,
        )
        repositories.append(repository)
    document = KnowledgeDocument.objects.create(
        repository=repositories[0],
        source_type=KnowledgeSourceType.README,
        source_path="README.md",
        external_id="README.md",
        title="Install and architecture",
        content="Install the coding agent and review its architecture.",
        source_url="https://example.test/readme",
        fetched_at=now,
        content_hash="a" * 64,
    )
    embedder = embedding_client()
    content = "Install the coding agent and review its architecture."
    KnowledgeChunk.objects.create(
        document=document,
        repository=repositories[0],
        chunk_index=0,
        heading_path="Install",
        content=content,
        token_count=10,
        content_hash="b" * 64,
        embedding=embedder.embed([content])[0],
        embedding_model=embedder.model,
        embedding_version=embedder.version,
    )
    return repositories


@pytest.mark.django_db
def test_registry_metadata_validation_and_structured_errors(projects):
    registry = ToolRegistry()
    assert len(registry.list()) == 17
    assert all(item["annotations"]["readOnlyHint"] for item in registry.list())
    assert registry.call("missing", {})["error_code"] == "UNKNOWN_TOOL"
    invalid = registry.call("search_projects", {"limit": MAX_LIST_LIMIT + 1})
    assert invalid["error_code"] == "INVALID_ARGUMENT"
    assert "Traceback" not in str(registry.call("get_project", {"repository_id": 999999}))


@pytest.mark.django_db
def test_composed_tool_scenarios_are_read_only_and_preserve_null(projects):
    registry = ToolRegistry()
    before = Repository.objects.count()
    search = registry.call(
        "search_projects", {"category": "CODING_AGENT", "sort": "-trend", "limit": 3}
    )
    assert search["ok"] and len(search["data"]["projects"]) == 3
    first = search["data"]["projects"][0]["id"]
    assert registry.call("get_project_trend", {"repository_id": first})["ok"]
    assert registry.call("get_project_potential", {"repository_id": first})["ok"]

    comparison = registry.call("compare_projects", {"repositories": [projects[0].id, "acme/beta"]})
    assert comparison["ok"] and len(comparison["data"]["projects"]) == 2
    assert comparison["metadata"]["db_query_count"] <= 30
    assert registry.call("get_learning_score", {"repository_id": projects[0].id})["ok"]
    enterprise = registry.call("get_enterprise_score", {"repository_id": projects[0].id})
    assert enterprise["data"]["recommendation"] == "POC"
    forecast = registry.call("get_project_forecast", {"repository_id": projects[0].id})
    assert forecast["data"]["status"] == "NOT_READY"
    assert forecast["data"]["forecast"] is None
    assert Repository.objects.count() == before


@pytest.mark.django_db
def test_knowledge_and_category_tools(projects):
    registry = ToolRegistry()
    result = registry.call(
        "search_repository_knowledge",
        {"repository_id": projects[0].id, "query": "How to install?", "top_k": 3},
    )
    assert result["ok"]
    evidence = result["data"][0]
    assert set(
        ("repository", "source_type", "title", "path", "url", "snippet", "similarity", "updated_at")
    ) <= set(evidence)
    summary = registry.call("get_project_knowledge_summary", {"full_name": "acme/alpha"})
    assert summary["data"]["status"] == "INGESTED"
    assert registry.call("list_categories", {})["ok"]
    help_result = registry.call("get_system_help", {"topic": "TREND_SCORE"})
    assert help_result["ok"]
    assert help_result["data"]["evidence"]["source"] == "TRUSTED_BUILT_IN_DOCUMENTATION"
    category = registry.call("get_category_trend", {"category": "CODING_AGENT"})
    assert category["data"]["status"] == "NO_DEDICATED_CATEGORY_TREND_MODEL"


def test_tool_timeout_guard_can_execute_inside_streaming_worker_thread():
    with ThreadPoolExecutor(max_workers=1) as executor:
        response = executor.submit(
            ToolRegistry._with_timeout,
            1,
            lambda: "completed",
        ).result(timeout=5)

    assert response == "completed"
