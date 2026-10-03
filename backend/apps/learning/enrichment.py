from dataclasses import dataclass

from django.utils import timezone

from apps.github.client import GitHubClientProtocol
from apps.repositories.models import Repository

from .models import RepositoryAssessmentEvidence


@dataclass(frozen=True)
class EnrichmentResult:
    evidence: RepositoryAssessmentEvidence
    requests: int


class AssessmentEnrichmentService:
    """Bounded filename/path inspection. It never downloads a repository tree or embeds content."""

    def __init__(self, client: GitHubClientProtocol) -> None:
        self.client = client

    @staticmethod
    def _names(items) -> dict[str, dict]:
        return {
            str(item.get("name", "")).casefold(): item
            for item in items
            if isinstance(item, dict) and item.get("name")
        }

    def enrich(self, repository: Repository) -> EnrichmentResult:
        requests = 1
        root = self._names(self.client.get_contents(repository.full_name, ""))
        matched = [str(item.get("path")) for item in root.values() if item.get("path")]
        docs_items: dict[str, dict] = {}
        github_items: dict[str, dict] = {}
        if root.get("docs", {}).get("type") == "dir":
            requests += 1
            docs_items = self._names(self.client.get_contents(repository.full_name, "docs"))
            matched.extend(
                str(item.get("path")) for item in docs_items.values() if item.get("path")
            )
        if root.get(".github", {}).get("type") == "dir":
            requests += 1
            github_items = self._names(self.client.get_contents(repository.full_name, ".github"))
            matched.extend(
                str(item.get("path")) for item in github_items.values() if item.get("path")
            )
        all_names = set(root) | set(docs_items) | set(github_items)

        def has(*terms: str) -> bool:
            return any(any(term in name for term in terms) for name in all_names)

        evidence, _ = RepositoryAssessmentEvidence.objects.update_or_create(
            repository=repository,
            defaults={
                "status": RepositoryAssessmentEvidence.Status.COMPLETE,
                "readme": any(name.startswith("readme") for name in root),
                "docs": "docs" in root or bool(docs_items),
                "getting_started": has("getting-started", "getting_started", "quickstart"),
                "examples": has("example", "tutorial"),
                "architecture": has("architecture", "design.md"),
                "contributing": has("contributing"),
                "security": has("security"),
                "testing": has("test", "pytest", "jest", "vitest"),
                "deployment": has("deploy", "installation", "install.md", "configuration"),
                "container": has("dockerfile", "docker-compose", "container"),
                "matched_paths": matched,
                "request_count": requests,
                "checked_at": timezone.now(),
                "last_error": "",
            },
        )
        return EnrichmentResult(evidence=evidence, requests=requests)

    def mark_not_found(self, repository: Repository) -> RepositoryAssessmentEvidence:
        evidence, _ = RepositoryAssessmentEvidence.objects.update_or_create(
            repository=repository,
            defaults={
                "status": RepositoryAssessmentEvidence.Status.FAILED,
                "last_error": "NOT_FOUND",
                "checked_at": timezone.now(),
            },
        )
        return evidence
