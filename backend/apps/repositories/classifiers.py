from collections.abc import Iterable

from .models import RepositoryCategory

CATEGORY_RULES: tuple[tuple[RepositoryCategory, tuple[str, ...]], ...] = (
    (RepositoryCategory.AGENT_SECURITY, ("agent-security", "agent security")),
    (RepositoryCategory.AGENT_OBSERVABILITY, ("agent-observability", "agent observability")),
    (RepositoryCategory.COMPUTER_USE, ("computer-use", "computer use")),
    (RepositoryCategory.MCP_TOOL, ("model-context-protocol", "mcp-agent", "mcp tool")),
    (RepositoryCategory.CODING_AGENT, ("coding-agent", "coding agent")),
    (RepositoryCategory.BROWSER_AGENT, ("browser-agent", "browser agent")),
    (RepositoryCategory.RESEARCH_AGENT, ("research-agent", "research agent")),
    (RepositoryCategory.MULTI_AGENT, ("multi-agent", "multi agent")),
    (RepositoryCategory.AGENT_MEMORY, ("agent-memory", "agent memory")),
    (RepositoryCategory.AGENT_WORKFLOW, ("agent-workflow", "agent workflow")),
    (RepositoryCategory.AGENT_FRAMEWORK, ("agent-framework", "agent framework", "ai-agent")),
)


def classify_repository(*, topics: Iterable[str], description: str | None) -> RepositoryCategory:
    normalized_topics = {topic.strip().casefold() for topic in topics}
    description_text = (description or "").casefold()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in normalized_topics or keyword in description_text for keyword in keywords):
            return category
    return RepositoryCategory.OTHER_AGENT
