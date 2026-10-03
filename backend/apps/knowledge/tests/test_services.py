import base64
from copy import deepcopy

import pytest

from apps.github.fakes import FakeGitHubClient
from apps.knowledge.chunking import MarkdownChunker
from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.knowledge.services import KnowledgeIngestionService, RetrievalService
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload


def file_payload(path, content):
    return {
        "path": path,
        "name": path.split("/")[-1],
        "sha": f"sha-{path}",
        "size": len(content),
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
        "html_url": f"https://github.test/{path}",
        "type": "file",
    }


class KnowledgeFake(FakeGitHubClient):
    def __init__(self, repository, readme):
        super().__init__([repository])
        self.readme = readme

    def get_readme(self, full_name):
        return deepcopy(self.readme)

    def get_contents(self, full_name, path=""):
        return []

    def get_recent_releases(self, full_name, *, limit=5):
        return [
            {
                "id": 1,
                "tag_name": "v1",
                "name": "Memory Release",
                "body": "New vector memory architecture",
                "html_url": "https://github.test/release",
                "draft": False,
            }
        ]

    def search_issues(self, query, *, per_page=20):
        from apps.github.client import RepositorySearchResult

        return RepositorySearchResult(0, False, [])


def test_heading_chunker_preserves_code_and_heading_path():
    content = (
        "# Install\n\nUse pip.\n\n```bash\npip install agent\n```\n\n## Memory\n\nVector memory."
    )
    chunks = MarkdownChunker().chunk(content, root_heading="README")
    assert "pip install agent" in "".join(item.content for item in chunks)
    assert any("Memory" in item.heading_path for item in chunks)


@pytest.mark.django_db(transaction=True)
def test_ingestion_change_detection_embedding_and_repository_filtered_retrieval():
    payload = github_repository_payload()
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(payload)
    client = KnowledgeFake(
        payload, file_payload("README.md", "# Agent\n\nMemory architecture and pip install.")
    )
    service = KnowledgeIngestionService(client)

    first = service.sync_repository(repository)
    second = service.sync_repository(repository)

    assert first["documents"] == 2
    assert first["embedding_calls"] == 2
    assert second["skipped_unchanged"] == 2
    assert KnowledgeDocument.objects.count() == 2
    assert KnowledgeChunk.objects.count() == 2
    evidence = RetrievalService().retrieve("memory architecture", repository_id=repository.id)
    assert evidence[0]["repository_id"] == repository.id
    assert evidence[0]["source_type"] in {"README", "RELEASE"}


@pytest.mark.django_db(transaction=True)
def test_changed_document_increments_version_and_rebuilds_chunks():
    payload = github_repository_payload()
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(payload)
    readme = file_payload("README.md", "# Old\n\nOld architecture")
    client = KnowledgeFake(payload, readme)
    service = KnowledgeIngestionService(client)
    service.sync_repository(repository)
    client.readme = file_payload("README.md", "# New\n\nNew secure architecture")
    service.sync_repository(repository)
    document = KnowledgeDocument.objects.get(source_type="README")
    assert document.document_version == 2
    assert "New secure" in document.chunks.get().content


@pytest.mark.django_db(transaction=True)
def test_file_identity_is_path_based_when_github_blob_sha_changes():
    payload = github_repository_payload()
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(payload)
    readme = file_payload("README.md", "# First")
    client = KnowledgeFake(payload, readme)
    service = KnowledgeIngestionService(client)
    service.sync_repository(repository)

    client.readme = file_payload("README.md", "# Second")
    client.readme["sha"] = "a-different-github-blob-sha"
    service.sync_repository(repository)

    documents = KnowledgeDocument.objects.filter(source_type="README")
    assert documents.count() == 1
    assert documents.get().external_id == "README.md"
    assert documents.get().document_version == 2
