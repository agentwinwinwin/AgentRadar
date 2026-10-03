import pytest

from apps.enterprise.engine import ALGORITHM_VERSION, calculate
from apps.enterprise.services import EnterpriseService
from apps.knowledge.models import KnowledgeSourceType
from apps.learning.tests.test_scores import document, repository, trend


def test_enterprise_engine_is_deterministic_and_hype_is_penalty():
    values = {
        "maintenance": 100,
        "community": 100,
        "delivery": 100,
        "security": 100,
        "license": 100,
        "documentation": 100,
        "architecture_operations": 100,
        "risk": 100,
    }
    assert calculate(values, 40).score == 96
    assert calculate(values, 40) == calculate(values, 40)


@pytest.mark.django_db
def test_archived_repository_has_zero_maintenance_but_missing_knowledge_is_not_zero():
    repo = repository(3)
    repo.is_archived = True
    repo.license_spdx = "MIT"
    repo.save(update_fields=("is_archived", "license_spdx"))
    trend(repo)
    score = EnterpriseService().calculate_repository(repo.id)
    assert score.algorithm_version == ALGORITHM_VERSION
    assert score.evidence["components"]["maintenance"]["value"] == 0
    assert score.evidence["components"]["security"]["value"] is None
    assert score.evidence["knowledge_status"] == "NOT_INGESTED"


@pytest.mark.django_db
def test_security_and_deployment_documents_are_evidence():
    repo = repository(4)
    repo.license_spdx = "Apache-2.0"
    repo.save(update_fields=("license_spdx",))
    trend(repo)
    document(repo, KnowledgeSourceType.README, "README.md")
    document(repo, KnowledgeSourceType.SECURITY, "SECURITY.md")
    document(repo, KnowledgeSourceType.DOC, "docs/deployment.md")
    score = EnterpriseService().calculate_repository(repo.id)
    assert score.evidence["components"]["security"]["value"] == 100
    assert score.evidence["components"]["architecture_operations"]["value"] >= 35
