from django.db import models
from pgvector.django import VectorField

from apps.repositories.models import Repository


class KnowledgeSourceType(models.TextChoices):
    README = "README", "README"
    DOC = "DOC", "Documentation"
    ARCHITECTURE = "ARCHITECTURE", "Architecture"
    DESIGN = "DESIGN", "Design"
    SECURITY = "SECURITY", "Security"
    CONTRIBUTING = "CONTRIBUTING", "Contributing"
    RELEASE = "RELEASE", "Release"
    PULL_REQUEST = "PULL_REQUEST", "Pull request"
    ISSUE = "ISSUE", "Issue"


class KnowledgeDocument(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="knowledge_documents"
    )
    source_type = models.CharField(max_length=30, choices=KnowledgeSourceType.choices)
    source_path = models.CharField(max_length=1000)
    external_id = models.CharField(max_length=255)
    title = models.CharField(max_length=1000)
    content = models.TextField()
    source_url = models.TextField()
    github_created_at = models.DateTimeField(null=True, blank=True)
    github_updated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fetched_at = models.DateTimeField()
    content_hash = models.CharField(max_length=64)
    document_version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "knowledge_documents"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "source_type", "external_id"),
                name="unique_repository_knowledge_source",
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.source_type}/{self.source_path}"


class KnowledgeChunk(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="knowledge_chunks"
    )
    chunk_index = models.PositiveIntegerField()
    heading_path = models.CharField(max_length=1500, blank=True)
    content = models.TextField()
    token_count = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict)
    embedding = VectorField(dimensions=384)
    embedding_model = models.CharField(max_length=100)
    embedding_version = models.CharField(max_length=50)

    class Meta:
        db_table = "knowledge_chunks"
        constraints = [
            models.UniqueConstraint(
                fields=("document", "chunk_index", "embedding_version"),
                name="unique_document_chunk_embedding_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.document_id}:{self.chunk_index}"


class KnowledgeSyncState(models.Model):
    repository = models.OneToOneField(
        Repository, on_delete=models.CASCADE, related_name="knowledge_sync_state"
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    next_sync_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_status = models.CharField(max_length=30, default="PENDING")
    last_stats = models.JSONField(default=dict)

    class Meta:
        db_table = "knowledge_sync_states"

    def __str__(self) -> str:
        return self.repository.full_name
