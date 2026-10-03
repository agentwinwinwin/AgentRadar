from dataclasses import replace

import pytest

from apps.skills.contracts import Intent
from apps.skills.executor import SkillExecutor
from apps.skills.registry import SkillError, SkillLoader, SkillRegistry
from apps.tools.registry import ToolRegistry


class FakeTools:
    def __init__(self, *, fail: str | None = None) -> None:
        self.real = ToolRegistry()
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    def list(self):
        return self.real.list()

    def call(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        if name == self.fail:
            return {"ok": False, "error_code": "TEST_FAILURE", "message": "failed", "details": None}
        data = self._data(name)
        return {
            "ok": True,
            "data": data,
            "evidence": data.get("evidence") if isinstance(data, dict) else None,
            "warnings": [],
            "metadata": {"duration_ms": 1.0, "read_only": True},
        }

    @staticmethod
    def _data(name):
        if name == "search_projects":
            return {
                "projects": [
                    {
                        "id": value,
                        "full_name": f"acme/agent-{value}",
                        "stars": None,
                        "trend_score": 80 - value,
                        "potential_score": 75 - value,
                        "data_completeness": 0.8,
                    }
                    for value in (1, 2, 3)
                ]
            }
        if name == "get_project_forecast":
            return {"status": "NOT_READY", "forecast": None, "validated_model_exists": True}
        if name == "get_project_trend":
            return {"status": "AVAILABLE", "data_completeness": 0.8, "evidence": {"trend": True}}
        if name == "get_project_potential":
            return {"status": "AVAILABLE", "confidence": 0.8, "evidence": {"potential": True}}
        if name == "get_learning_score":
            return {
                "status": "AVAILABLE",
                "confidence": 0.8,
                "score": 70,
                "evidence": {"knowledge_status": "INGESTED"},
            }
        if name == "get_enterprise_score":
            return {
                "status": "AVAILABLE",
                "confidence": 0.8,
                "score": 75,
                "evidence": {"components": {"maintenance": {"status": "VALUE", "value": 70}}},
            }
        if name == "get_project_knowledge_summary":
            return {
                "status": "INGESTED",
                "readme_exists": True,
                "docs_count": 2,
                "evidence": {"document_count": 3},
            }
        if name == "search_repository_knowledge":
            return [{"repository": "acme/agent", "snippet": "architecture", "similarity": 0.8}]
        if name == "compare_projects":
            return {"projects": [], "differences": {}}
        if name == "get_category_trend":
            return {"status": "NO_DEDICATED_CATEGORY_TREND_MODEL", "evidence": {"aggregate": True}}
        if name == "get_watchlist":
            return {"items": [], "evidence": {"source": "watchlist"}}
        if name == "get_project_alerts":
            return {"alerts": [], "evidence": {"source": "alerts"}}
        if name == "get_latest_report":
            return {"report_type": "DAILY", "evidence": {"source": "scheduled_report"}}
        if name == "get_system_help":
            return {
                "topic": "TREND_SCORE",
                "explanation": "trusted help",
                "evidence": {"source": "TRUSTED_BUILT_IN_DOCUMENTATION"},
            }
        return {"repository_id": 1, "stars": None, "evidence": {"metadata": True}}


class StaticLoader:
    def __init__(self, skills):
        self.skills = skills

    def load(self):
        return self.skills


def registry_with(fake=None):
    tools = fake or FakeTools()
    return SkillRegistry(tool_registry=tools), tools


def test_loader_registry_versions_intents_and_dry_run():
    registry, tools = registry_with()
    assert len(registry.list()) == 13
    assert all("-v1." in item["version"] for item in registry.list())
    for intent in Intent:
        assert registry.resolve(intent.value).name
    plan = registry.dry_run(
        Intent.TREND_DISCOVERY,
        user_constraints={"category": "CODING_AGENT"},
    )
    assert plan["selected_skill"] == "trend-research"
    assert plan["executed"] is False
    assert tools.calls == []


@pytest.mark.parametrize(
    ("intent", "constraints", "entities", "tool", "arguments"),
    [
        (Intent.WATCHLIST_QUERY, {}, {}, "get_watchlist", {}),
        (
            Intent.ALERT_QUERY,
            {},
            {"repository_id": 1},
            "get_project_alerts",
            {"repository_id": 1, "limit": 20},
        ),
        (
            Intent.REPORT_QUERY,
            {"report_type": "DAILY"},
            {},
            "get_latest_report",
            {"report_type": "DAILY"},
        ),
    ],
)
def test_sprint14_read_skills(intent, constraints, entities, tool, arguments):
    registry, tools = registry_with()
    result = SkillExecutor(registry=registry, tool_registry=tools).execute(
        intent, user_constraints=constraints, resolved_entities=entities
    )
    assert result["executed_tools"] == [tool]
    assert tools.calls == [(tool, arguments)]


def test_registry_rejects_version_unknown_tool_unknown_skill_and_disabled():
    definitions = SkillLoader().load()
    with pytest.raises(SkillError, match="Invalid version"):
        SkillRegistry(
            loader=StaticLoader([replace(definitions[0], version="bad"), *definitions[1:]]),
            tool_registry=FakeTools(),
        )
    broken = replace(
        definitions[0],
        allowed_tools=(*definitions[0].allowed_tools, "write_database"),
    )
    with pytest.raises(SkillError, match="unknown Tools"):
        SkillRegistry(
            loader=StaticLoader([broken, *definitions[1:]]),
            tool_registry=FakeTools(),
        )
    disabled = replace(definitions[0], enabled=False)
    registry = SkillRegistry(
        loader=StaticLoader([disabled, *definitions[1:]]), tool_registry=FakeTools()
    )
    with pytest.raises(SkillError) as exc:
        registry.get(disabled.name)
    assert exc.value.code == "SKILL_DISABLED"
    with pytest.raises(SkillError) as exc:
        registry.get("missing")
    assert exc.value.code == "UNKNOWN_SKILL"


@pytest.mark.parametrize(
    ("intent", "constraints", "entities", "required_tool"),
    [
        (Intent.TREND_DISCOVERY, {"category": "CODING_AGENT"}, {}, "search_projects"),
        (Intent.POTENTIAL_DISCOVERY, {"limit": 10}, {}, "search_projects"),
        (Intent.PROJECT_DISCOVERY, {"limit": 10}, {}, "search_projects"),
        (
            Intent.PROJECT_KNOWLEDGE,
            {"knowledge_query": "installation"},
            {"repository_id": 1},
            "search_repository_knowledge",
        ),
        (Intent.SYSTEM_HELP, {"help_topic": "TREND_SCORE"}, {}, "get_system_help"),
        (
            Intent.LEARNING_RECOMMENDATION,
            {"category": "AGENT_FRAMEWORK"},
            {},
            "search_repository_knowledge",
        ),
        (Intent.ENTERPRISE_SELECTION, {"category": "CODING_AGENT"}, {}, "compare_projects"),
        (Intent.PROJECT_ANALYSIS, {}, {"repository_id": 1}, "get_enterprise_score"),
        (Intent.PROJECT_COMPARISON, {}, {"repositories": [1, 2]}, "compare_projects"),
    ],
)
def test_deterministic_workflows(intent, constraints, entities, required_tool):
    registry, tools = registry_with()
    result = SkillExecutor(registry, tools).execute(
        intent, user_constraints=constraints, resolved_entities=entities
    )
    assert required_tool in result["executed_tools"]
    assert result["tool_calls"] <= result["tool_budget"]
    assert result["evidence_count"] > 0
    assert "-v1." in result["skill_version"]


def test_future_prediction_not_ready_fallback_and_no_probability():
    registry, tools = registry_with()
    result = SkillExecutor(registry, tools).execute(
        Intent.FUTURE_PREDICTION, resolved_entities={"repository_id": 1}
    )
    assert result["executed_tools"][0] == "get_project_forecast"
    assert result["result_status"] == "CURRENT_SIGNAL_ANALYSIS"
    assert "FORECAST_NOT_READY" in result["warnings"]
    assert result["results"]["forecast"][0]["forecast"] is None


def test_search_mode_only_forwards_fields_declared_by_tool_schema():
    registry, tools = registry_with()
    result = SkillExecutor(registry, tools).execute(
        Intent.LEARNING_RECOMMENDATION,
        user_constraints={
            "category": "CODING_AGENT",
            "user_goal": "学习编码智能体",
            "risk_preference": "LOW",
        },
    )

    assert result["result_status"] == "COMPLETED"
    search_arguments = next(
        arguments for name, arguments in tools.calls if name == "search_projects"
    )
    assert search_arguments == {"category": "CODING_AGENT", "sort": "-learning", "limit": 10}


def test_trend_search_accepts_global_top_twenty_and_optional_category():
    registry, tools = registry_with()
    result = SkillExecutor(registry, tools).execute(
        Intent.TREND_DISCOVERY,
        user_constraints={"limit": 20},
    )

    assert result["result_status"] == "COMPLETED"
    assert tools.calls == [("search_projects", {"sort": "-trend", "limit": 20})]


def test_potential_search_is_distinct_from_trend_and_forecast():
    registry, tools = registry_with()
    result = SkillExecutor(registry, tools).execute(
        Intent.POTENTIAL_DISCOVERY,
        user_constraints={"limit": 10},
    )

    assert result["result_status"] == "COMPLETED"
    assert result["selected_skill"] == "potential-research"
    assert tools.calls == [("search_projects", {"sort": "-potential", "limit": 10})]


def test_system_help_maps_router_constraint_to_tool_topic():
    registry, tools = registry_with()
    result = SkillExecutor(registry, tools).execute(
        Intent.SYSTEM_HELP,
        user_constraints={"help_topic": "TREND_SCORE"},
    )

    assert result["result_status"] == "COMPLETED"
    assert tools.calls == [("get_system_help", {"topic": "TREND_SCORE"})]


def test_budget_partial_failure_and_null_are_preserved():
    registry, tools = registry_with()
    budget = SkillExecutor(registry, tools).execute(
        Intent.PROJECT_COMPARISON,
        resolved_entities={"repositories": [1, 2, 3, 4, 5]},
    )
    assert budget["result_status"] == "TOOL_BUDGET_EXCEEDED"
    assert budget["tool_calls"] == budget["tool_budget"]

    failing = FakeTools(fail="get_project_potential")
    registry = SkillRegistry(tool_registry=failing)
    partial = SkillExecutor(registry, failing).execute(
        Intent.PROJECT_ANALYSIS, resolved_entities={"repository_id": 1}
    )
    assert partial["result_status"] == "PARTIAL"
    assert "get_enterprise_score" in partial["executed_tools"]
    assert partial["results"]["project"][0]["stars"] is None
