from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.github.fakes import FakeGitHubClient
from apps.learning.enrichment import AssessmentEnrichmentService
from apps.learning.models import RepositoryAssessmentEvidence
from apps.learning.tasks import dispatch_learning_scoring
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload


def make_repository(index: int):
    return RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(id=990_000 + index, full_name=f"pipeline/repo-{index}")
    )[0]


class ContentsClient:
    def __init__(self):
        self.calls = []

    def get_contents(self, full_name, path=""):
        self.calls.append((full_name, path))
        if not path:
            return [
                {"name": "README.md", "path": "README.md", "type": "file"},
                {"name": "docs", "path": "docs", "type": "dir"},
                {"name": ".github", "path": ".github", "type": "dir"},
                {"name": "Dockerfile", "path": "Dockerfile", "type": "file"},
            ]
        if path == "docs":
            return [
                {"name": "getting-started.md", "path": "docs/getting-started.md"},
                {"name": "architecture.md", "path": "docs/architecture.md"},
            ]
        return [{"name": "SECURITY.md", "path": ".github/SECURITY.md"}]


@pytest.mark.django_db
def test_whitelist_enrichment_is_bounded_and_does_not_require_rag():
    repo = make_repository(1)
    client = ContentsClient()
    result = AssessmentEnrichmentService(client).enrich(repo)

    assert result.requests == 3
    assert result.evidence.readme is True
    assert result.evidence.architecture is True
    assert result.evidence.security is True
    assert result.evidence.container is True
    assert result.evidence.status == RepositoryAssessmentEvidence.Status.COMPLETE


@pytest.mark.django_db
@override_settings(ASSESSMENT_SCORING_BATCH_SIZE=2)
def test_dispatch_is_bounded_and_resumable():
    first, second, third = make_repository(2), make_repository(3), make_repository(4)
    with (
        patch("apps.learning.tasks.calculate_repository_learning.delay") as score,
        patch("apps.learning.tasks.dispatch_learning_scoring.apply_async") as resume,
    ):
        result = dispatch_learning_scoring.run()

    assert result["dispatched"] == 2
    score.assert_any_call(first.id)
    score.assert_any_call(second.id)
    resume.assert_called_once_with(args=[second.id], countdown=5)
    assert third.id > result["next_after_id"]
