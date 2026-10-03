import base64
import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from pgvector.django import CosineDistance

from apps.github.client import GitHubClientError, GitHubClientProtocol
from apps.repositories.models import Repository

from .chunking import MarkdownChunker
from .embeddings import EmbeddingClient, embedding_client
from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeSourceType

IMPORTANT_ROOT = {
    "ARCHITECTURE.MD": KnowledgeSourceType.ARCHITECTURE,
    "DESIGN.MD": KnowledgeSourceType.DESIGN,
    "SECURITY.MD": KnowledgeSourceType.SECURITY,
    "CONTRIBUTING.MD": KnowledgeSourceType.CONTRIBUTING,
    "ROADMAP.MD": KnowledgeSourceType.DOC,
    "DEVELOPMENT.MD": KnowledgeSourceType.DOC,
    "INSTALL.MD": KnowledgeSourceType.DOC,
    "DEPLOYMENT.MD": KnowledgeSourceType.DOC,
}
POSITIVE_PR = (
    "feature",
    "architecture",
    "refactor",
    "runtime",
    "memory",
    "agent",
    "tool",
    "mcp",
    "workflow",
    "security",
    "performance",
    "breaking",
)
NEGATIVE = ("typo", "format", "dependabot", "dependency bump", "minor docs", "chore")
POSITIVE_ISSUE = ("bug", "security", "performance", "architecture", "breaking", "major feature")


@dataclass(frozen=True)
class SourceDocument:
    source_type: str
    path: str
    external_id: str
    title: str
    content: str
    url: str
    created_at: Any = None
    updated_at: Any = None
    metadata: dict[str, Any] | None = None


@dataclass
class IngestionStats:
    repositories_processed: int = 0
    documents: int = 0
    chunks: int = 0
    tokens: int = 0
    embedding_calls: int = 0
    changed_documents: int = 0
    skipped_unchanged: int = 0
    github_api_calls: int = 0
    source_failures: int = 0


class KnowledgeIngestionService:
    def __init__(
        self,
        client: GitHubClientProtocol,
        embedder: EmbeddingClient | None = None,
        *,
        include_pr_issue: bool = False,
    ) -> None:
        self.client = client
        self.embedder = embedder or embedding_client()
        self.chunker = MarkdownChunker()
        self.include_pr_issue = include_pr_issue

    def sync_repository(self, repository: Repository) -> dict[str, Any]:
        stats = IngestionStats(repositories_processed=1)
        sources = self._collect(repository, stats)
        seen: set[tuple[str, str]] = set()
        for source in sources:
            seen.add((source.source_type, source.external_id))
            self._persist(repository, source, stats)
        for document in KnowledgeDocument.objects.filter(repository=repository, is_active=True):
            if (document.source_type, document.external_id) not in seen:
                document.is_active = False
                document.save(update_fields=("is_active",))
        return asdict(stats)

    def _collect(self, repository: Repository, stats: IngestionStats) -> list[SourceDocument]:
        result: list[SourceDocument] = []
        full_name = repository.full_name
        try:
            readme = self.client.get_readme(full_name)
            stats.github_api_calls += 1
            result.append(self._file_source(readme, KnowledgeSourceType.README, "README"))
        except GitHubClientError:
            stats.github_api_calls += 1
            stats.source_failures += 1
        try:
            root = self.client.get_contents(full_name)
            stats.github_api_calls += 1
            if isinstance(root, list):
                for item in root:
                    name = str(item.get("name", "")).upper()
                    if name in IMPORTANT_ROOT:
                        try:
                            result.append(
                                self._fetch_file(full_name, item, IMPORTANT_ROOT[name], stats)
                            )
                        except (GitHubClientError, ValueError, UnicodeDecodeError):
                            stats.source_failures += 1
                    elif name == "DOCS" and item.get("type") == "dir":
                        result.extend(
                            self._docs(
                                full_name,
                                "docs",
                                stats,
                                depth=0,
                                budget=[settings.KNOWLEDGE_MAX_DOC_FILES],
                            )
                        )
        except GitHubClientError:
            stats.github_api_calls += 1
            stats.source_failures += 1
        try:
            releases = self.client.get_recent_releases(full_name, limit=5)
            stats.github_api_calls += 1
        except GitHubClientError:
            stats.github_api_calls += 1
            stats.source_failures += 1
            releases = []
        for release in releases:
            body = (release.get("body") or "").strip()
            if body:
                result.append(
                    SourceDocument(
                        KnowledgeSourceType.RELEASE,
                        f"releases/{release.get('tag_name')}",
                        str(release["id"]),
                        release.get("name") or release.get("tag_name") or "Release",
                        body,
                        release.get("html_url") or "",
                        parse_datetime(release.get("created_at") or ""),
                        parse_datetime(
                            release.get("published_at") or release.get("updated_at") or ""
                        ),
                        {"tag": release.get("tag_name"), "selection": "latest_non_draft_release"},
                    )
                )
        if self.include_pr_issue:
            since = (timezone.now() - timedelta(days=90)).date().isoformat()
            prs = self.client.search_issues(
                f"repo:{full_name} type:pr is:merged merged:>={since}", per_page=20
            )
            stats.github_api_calls += 1
            result.extend(self._selected_items(prs.items, KnowledgeSourceType.PULL_REQUEST))
            issues = self.client.search_issues(f"repo:{full_name} type:issue", per_page=20)
            stats.github_api_calls += 1
            result.extend(self._selected_items(issues.items, KnowledgeSourceType.ISSUE))
        return result

    def _docs(
        self,
        full_name: str,
        path: str,
        stats: IngestionStats,
        *,
        depth: int,
        budget: list[int],
    ) -> list[SourceDocument]:
        if depth > 2 or budget[0] <= 0:
            return []
        try:
            listing = self.client.get_contents(full_name, path)
            stats.github_api_calls += 1
        except GitHubClientError:
            stats.github_api_calls += 1
            stats.source_failures += 1
            return []
        output: list[SourceDocument] = []
        if not isinstance(listing, list):
            return output
        for item in listing[:50]:
            if budget[0] <= 0:
                break
            item_path = str(item.get("path", ""))
            if item.get("type") == "dir":
                output.extend(
                    self._docs(
                        full_name,
                        item_path,
                        stats,
                        depth=depth + 1,
                        budget=budget,
                    )
                )
            elif (
                item_path.casefold().endswith(".md")
                and int(item.get("size") or 0) <= settings.KNOWLEDGE_MAX_FILE_BYTES
            ):
                try:
                    source_type = IMPORTANT_ROOT.get(
                        str(item.get("name") or "").upper(), KnowledgeSourceType.DOC
                    )
                    output.append(self._fetch_file(full_name, item, source_type, stats))
                    budget[0] -= 1
                except (GitHubClientError, ValueError, UnicodeDecodeError):
                    stats.source_failures += 1
        return output

    def _fetch_file(
        self, full_name: str, item: dict[str, Any], source_type: str, stats: IngestionStats
    ) -> SourceDocument:
        payload = self.client.get_contents(full_name, str(item["path"]))
        stats.github_api_calls += 1
        if not isinstance(payload, dict):
            raise ValueError("file content must be an object")
        return self._file_source(payload, source_type, str(item.get("name") or item["path"]))

    @staticmethod
    def _file_source(payload: dict[str, Any], source_type: str, title: str) -> SourceDocument:
        if int(payload.get("size") or 0) > settings.KNOWLEDGE_MAX_FILE_BYTES:
            raise ValueError("knowledge file exceeds size limit")
        if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            raise ValueError("knowledge file must contain base64 text")
        encoded = "".join(payload["content"].split())
        content = base64.b64decode(encoded, validate=True).decode("utf-8")
        return SourceDocument(
            source_type,
            payload.get("path") or title,
            payload.get("path") or title,
            title,
            content,
            payload.get("html_url") or "",
            metadata={
                "github_blob_sha": payload.get("sha"),
                "untrusted_external_content": True,
            },
        )

    @staticmethod
    def _selected_items(items: list[dict[str, Any]], source_type: str) -> list[SourceDocument]:
        selected = []
        positive = (
            POSITIVE_PR if source_type == KnowledgeSourceType.PULL_REQUEST else POSITIVE_ISSUE
        )
        for item in items:
            title = str(item.get("title") or "")
            text = f"{title} {item.get('body') or ''}".casefold()
            labels = {str(label.get("name", "")).casefold() for label in item.get("labels", [])}
            negative = any(term in text for term in NEGATIVE) or "duplicate" in labels
            signals = [term for term in positive if term in text or term in labels]
            comments = int(item.get("comments") or 0)
            reactions = int((item.get("reactions") or {}).get("total_count") or 0)
            if negative or not (signals or comments >= 5 or reactions >= 3):
                continue
            selected.append(
                SourceDocument(
                    source_type,
                    f"{source_type.lower()}/{item.get('number')}",
                    str(item["id"]),
                    title,
                    f"# {title}\n\n{item.get('body') or ''}",
                    item.get("html_url") or "",
                    parse_datetime(item.get("created_at") or ""),
                    parse_datetime(item.get("updated_at") or ""),
                    {
                        "selection_evidence": {
                            "keywords": signals,
                            "comments": comments,
                            "reactions": reactions,
                        },
                        "untrusted_external_content": True,
                    },
                )
            )
        return selected[:5]

    @transaction.atomic
    def _persist(
        self, repository: Repository, source: SourceDocument, stats: IngestionStats
    ) -> None:
        digest = hashlib.sha256(source.content.encode()).hexdigest()
        document = KnowledgeDocument.objects.filter(
            repository=repository, source_type=source.source_type, external_id=source.external_id
        ).first()
        if document and document.content_hash == digest:
            document.fetched_at = timezone.now()
            document.is_active = True
            document.save(update_fields=("fetched_at", "is_active"))
            stats.skipped_unchanged += 1
            return
        version = (document.document_version + 1) if document else 1
        document, _ = KnowledgeDocument.objects.update_or_create(
            repository=repository,
            source_type=source.source_type,
            external_id=source.external_id,
            defaults={
                "source_path": source.path,
                "title": source.title[:1000],
                "content": source.content,
                "source_url": source.url,
                "github_created_at": source.created_at,
                "github_updated_at": source.updated_at,
                "fetched_at": timezone.now(),
                "content_hash": digest,
                "document_version": version,
                "metadata": source.metadata or {},
                "is_active": True,
            },
        )
        document.chunks.all().delete()
        chunks = self.chunker.chunk(source.content, root_heading=source.title)
        vectors = self.embedder.embed([chunk.content for chunk in chunks])
        KnowledgeChunk.objects.bulk_create(
            [
                KnowledgeChunk(
                    document=document,
                    repository=repository,
                    chunk_index=chunk.index,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    content_hash=chunk.content_hash,
                    metadata={"document_version": version},
                    embedding=vector,
                    embedding_model=self.embedder.model,
                    embedding_version=self.embedder.version,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        stats.documents += 1
        stats.changed_documents += 1
        stats.chunks += len(chunks)
        stats.tokens += sum(chunk.token_count for chunk in chunks)
        stats.embedding_calls += int(bool(chunks))


class RetrievalService:
    def __init__(self, embedder: EmbeddingClient | None = None) -> None:
        self.embedder = embedder or embedding_client()

    def retrieve(
        self,
        question: str,
        *,
        repository_id: int | None = None,
        category: str | None = None,
        source_types: list[str] | None = None,
        updated_after=None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        vector = self.embedder.embed([question])[0]
        queryset = KnowledgeChunk.objects.select_related("document", "repository").filter(
            document__is_active=True, embedding_version=self.embedder.version
        )
        if repository_id is not None:
            queryset = queryset.filter(repository_id=repository_id)
        if category is not None:
            queryset = queryset.filter(repository__category=category)
        if source_types:
            queryset = queryset.filter(document__source_type__in=source_types)
        if updated_after is not None:
            queryset = queryset.filter(document__github_updated_at__gte=updated_after)
        if connection.vendor == "postgresql":
            rows = list(
                queryset.annotate(distance=CosineDistance("embedding", vector)).order_by(
                    "distance", "id"
                )[: max(limit * 10, 50)]
            )
            scored = [(row, max(0.0, 1.0 - float(row.distance))) for row in rows]
        else:
            scored = sorted(
                ((row, self._cosine(row.embedding, vector)) for row in queryset),
                key=lambda item: item[1],
                reverse=True,
            )
        scored = sorted(
            scored,
            key=lambda item: self._rank_score(question, item[0], item[1]),
            reverse=True,
        )[:limit]
        return [
            {
                "repository": row.repository.full_name,
                "repository_id": row.repository_id,
                "source_type": row.document.source_type,
                "title": row.document.title,
                "path": row.document.source_path,
                "url": row.document.source_url,
                "snippet": row.content[:500],
                "score": round(score, 6),
                "updated_at": row.document.github_updated_at,
            }
            for row, score in scored
        ]

    @staticmethod
    def _cosine(left, right) -> float:
        dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
        ln = math.sqrt(sum(float(a) ** 2 for a in left))
        rn = math.sqrt(sum(float(b) ** 2 for b in right))
        return dot / (ln * rn) if ln and rn else 0.0

    @staticmethod
    def _rank_score(question: str, row: KnowledgeChunk, similarity: float) -> float:
        query_tokens = {
            token for token in question.casefold().replace("?", " ").split() if len(token) >= 4
        }
        metadata_text = " ".join(
            (row.document.title, row.document.source_path, row.heading_path)
        ).casefold()
        lexical_hits = sum(token in metadata_text for token in query_tokens)
        source_boost = 0.0
        query = question.casefold()
        if any(term in query for term in ("architecture", "架构")):
            source_boost = 0.3 if "architect" in metadata_text else 0.0
        elif any(term in query for term in ("release", "version", "版本", "更新")):
            source_boost = 0.3 if row.document.source_type == KnowledgeSourceType.RELEASE else 0.0
        elif any(term in query for term in ("security", "risk", "安全", "风险")):
            source_boost = (
                0.25
                if row.document.source_type
                in {
                    KnowledgeSourceType.SECURITY,
                    KnowledgeSourceType.ISSUE,
                }
                else 0.0
            )
        elif any(term in query for term in ("install", "安装")):
            source_boost = 0.15 if "install" in metadata_text else 0.0
        return similarity + min(lexical_hits * 0.04, 0.2) + source_boost


class RAGService:
    def answer(self, repository_id: int, question: str) -> dict[str, Any]:
        evidence = RetrievalService().retrieve(question, repository_id=repository_id, limit=5)
        answer = (
            "没有找到可追溯的知识证据。"
            if not evidence
            else "\n\n".join(item["snippet"] for item in evidence[:3])
        )
        return {"answer": answer, "evidence": evidence}

    def structured_and_rag(self, repository_id: int, question: str) -> dict[str, Any]:
        repository = Repository.objects.get(pk=repository_id)
        trend = repository.trend_scores.order_by("-calculated_at").first()
        snapshot = repository.snapshots.order_by("-snapshot_at").first()
        activity = repository.activity_metrics.order_by("-metric_date").first()
        return {
            "structured": {
                "repository": repository.full_name,
                "snapshot": {
                    "stars": snapshot.stars,
                    "forks": snapshot.forks,
                    "at": snapshot.snapshot_at,
                }
                if snapshot
                else None,
                "trend": {
                    "score": float(trend.trend_score)
                    if trend and trend.trend_score is not None
                    else None,
                    "completeness": trend.data_completeness,
                }
                if trend
                else None,
                "activity": {
                    "commits_30d": activity.commits_30d,
                    "prs_created_30d": activity.prs_created_30d,
                }
                if activity
                else None,
            },
            "knowledge": self.answer(repository_id, question),
        }
