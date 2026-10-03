import pytest
from django.utils import timezone

from apps.github.fakes import FakeGitHubClient
from apps.knowledge.models import KnowledgeDocument, KnowledgeSourceType
from apps.learning.engine import ALGORITHM_VERSION, calculate
from apps.learning.services import LearningService
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.trends.engine import ALGORITHM_VERSION as TREND_VERSION
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore


def repository(index=1):
    payload = github_repository_payload(id=80000 + index, full_name=f"scores/repo-{index}")
    return RepositoryService(FakeGitHubClient()).upsert_from_github(payload)[0]


def trend(repo):
    return RepositoryTrendScore.objects.create(
        repository=repo,
        community_score=80,
        maintenance_score=60,
        delivery_score=70,
        hype_risk=None,
        hype_risk_status=HypeRiskStatus.INSUFFICIENT_HISTORY,
        lifecycle_stage=LifecycleStage.GROWING,
        data_completeness=0.7,
        algorithm_version=TREND_VERSION,
        calculated_at=timezone.now(),
    )


def document(repo, source_type, path):
    return KnowledgeDocument.objects.create(
        repository=repo,
        source_type=source_type,
        source_path=path,
        external_id=path,
        title=path,
        content="content",
        source_url="https://example.test",
        fetched_at=timezone.now(),
        content_hash="a" * 64,
    )


def test_learning_engine_renormalizes_missing_without_zeroing():
    result = calculate(
        {
            "development_activity": None,
            "documentation": 100,
            "architecture_learning": None,
            "community": 50,
            "delivery": None,
            "maintenance": 50,
        }
    )
    assert result.score == 77.78
    assert result.confidence == 0.45


@pytest.mark.django_db
def test_not_ingested_knowledge_is_missing_and_score_is_idempotent():
    repo = repository()
    trend(repo)
    first = LearningService().calculate_repository(repo.id)
    second = LearningService().calculate_repository(repo.id)
    assert first.pk == second.pk
    assert first.algorithm_version == ALGORITHM_VERSION
    assert first.evidence["knowledge_status"] == "NOT_INGESTED"
    assert first.evidence["components"]["documentation"]["value"] is None
    assert first.score is not None
    assert first.confidence < 0.6


@pytest.mark.django_db
def test_ingested_documents_create_deterministic_learning_evidence():
    repo = repository(2)
    trend(repo)
    document(repo, KnowledgeSourceType.README, "README.md")
    document(repo, KnowledgeSourceType.ARCHITECTURE, "docs/ARCHITECTURE.md")
    document(repo, KnowledgeSourceType.DOC, "docs/getting-started.md")
    document(repo, KnowledgeSourceType.DOC, "docs/testing.md")
    score = LearningService().calculate_repository(repo.id)
    assert score.evidence["knowledge_status"] == "INGESTED"
    assert score.evidence["knowledge"]["architecture"] is True
    assert score.evidence["components"]["architecture_learning"]["value"] == 70
    assert score.confidence > 0.5
