from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.repositories.models import RepositoryCategory
from apps.skills.contracts import Intent
from apps.skills.registry import SkillError

from .mcp_client import MCPToolAdapter

CATEGORY_ALIASES = {
    "agent framework": RepositoryCategory.AGENT_FRAMEWORK,
    "agent frameworks": RepositoryCategory.AGENT_FRAMEWORK,
    "coding agent": RepositoryCategory.CODING_AGENT,
    "coding agents": RepositoryCategory.CODING_AGENT,
    "browser agent": RepositoryCategory.BROWSER_AGENT,
    "browser agents": RepositoryCategory.BROWSER_AGENT,
    "research agent": RepositoryCategory.RESEARCH_AGENT,
    "multi agent": RepositoryCategory.MULTI_AGENT,
    "multi-agent": RepositoryCategory.MULTI_AGENT,
    "agent memory": RepositoryCategory.AGENT_MEMORY,
    "mcp": RepositoryCategory.MCP_TOOL,
    "mcp tool": RepositoryCategory.MCP_TOOL,
}


@dataclass(frozen=True)
class ResolvedInput:
    entities: dict[str, Any]
    constraints: dict[str, Any]
    trace: list[dict[str, Any]]


class EntityResolver:
    def __init__(self, tools: MCPToolAdapter) -> None:
        self.tools = tools

    def resolve(
        self,
        intent: str,
        parsed_entities: dict[str, Any],
        constraints: dict[str, Any],
        session: dict[str, Any],
        allowed_tools: tuple[str, ...],
    ) -> ResolvedInput:
        previous_constraints = (
            session.get("user_constraints", {}) if session.get("last_intent") == intent else {}
        )
        merged_constraints = {**previous_constraints, **constraints}
        if category := merged_constraints.get("category"):
            merged_constraints["category"] = self._category(category)
        entities = dict(parsed_entities)
        if not entities:
            entities = dict(session.get("resolved_entities", {}))
        names = entities.pop("repositories", [])
        if repository := entities.pop("repository", None):
            names = [repository]
        trace = []
        resolved_ids = []
        for name in names:
            if not isinstance(name, str):
                continue
            if "search_projects" not in allowed_tools:
                raise SkillError(
                    "ENTITY_UNRESOLVED", "Selected Skill cannot resolve Repository names"
                )
            response = self.tools.call(
                "search_projects", {"query": name[:200], "sort": "-stars", "limit": 5}
            )
            trace.append(
                {
                    "tool": "search_projects",
                    "ok": response["ok"],
                    "duration_ms": response.get("metadata", {}).get("duration_ms"),
                    "purpose": "ENTITY_RESOLUTION",
                }
            )
            if not response["ok"]:
                raise SkillError("ENTITY_UNRESOLVED", f"Repository could not be resolved: {name}")
            projects = response["data"]["projects"]
            selected = self._select(name, projects)
            if selected is None:
                raise SkillError("ENTITY_UNRESOLVED", f"Repository could not be resolved: {name}")
            resolved_ids.append(selected["id"])

        if intent == Intent.PROJECT_COMPARISON:
            if not resolved_ids:
                resolved_ids = list(entities.get("repositories", []))
            if len(resolved_ids) < 2:
                previous = session.get("resolved_entities", {}).get("repositories", [])
                resolved_ids = resolved_ids or previous
            entities = {"repositories": resolved_ids}
        elif intent in {
            Intent.PROJECT_ANALYSIS,
            Intent.PROJECT_KNOWLEDGE,
            Intent.FUTURE_PREDICTION,
            Intent.ALERT_QUERY,
        }:
            repository_id = resolved_ids[0] if resolved_ids else entities.get("repository_id")
            if repository_id is None:
                previous = session.get("resolved_entities", {})
                repository_id = (
                    previous.get("repository_id") or (previous.get("repositories") or [None])[0]
                )
            entities = {"repository_id": repository_id} if repository_id is not None else {}
        else:
            entities = {}
        return ResolvedInput(entities, merged_constraints, trace)

    @staticmethod
    def _category(value: str) -> str:
        if value in RepositoryCategory.values:
            return value
        normalized = value.casefold().replace("_", " ").strip()
        category = CATEGORY_ALIASES.get(normalized)
        if category is None:
            raise SkillError("CATEGORY_UNRESOLVED", f"Unknown Category: {value}")
        return category

    @staticmethod
    def _select(name: str, projects: list[dict[str, Any]]) -> dict[str, Any] | None:
        query = name.casefold()
        for project in projects:
            full_name = project["full_name"].casefold()
            if full_name == query or full_name.rsplit("/", 1)[-1] == query:
                return project
        return projects[0] if len(projects) == 1 else None
