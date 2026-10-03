import json

import pytest

from apps.skills.contracts import Intent
from apps.tools.mcp import MCPServer

from ..mcp_client import MCPClient, MCPToolAdapter
from ..runtime import AgentError, PMCopilotRuntime
from .fakes import FakeLLM, FakeRegistry, MemorySessions, answer, intent


def runtime(outputs):
    registry = FakeRegistry()
    tools = MCPToolAdapter(MCPClient(MCPServer(registry=registry)))
    client = FakeLLM(outputs)
    return PMCopilotRuntime(client=client, tools=tools, sessions=MemorySessions()), registry, client


@pytest.mark.parametrize(
    ("intent_name", "repositories", "category", "expected_skill"),
    [
        (Intent.TREND_DISCOVERY, None, "CODING_AGENT", "trend-research"),
        (Intent.POTENTIAL_DISCOVERY, None, None, "potential-research"),
        (Intent.LEARNING_RECOMMENDATION, None, "CODING_AGENT", "learning-recommendation"),
        (Intent.ENTERPRISE_SELECTION, None, "CODING_AGENT", "enterprise-selection"),
        (Intent.PROJECT_ANALYSIS, ["acme/agent"], None, "project-analysis"),
        (Intent.PROJECT_COMPARISON, ["acme/a", "acme/b"], None, "project-comparison"),
        (Intent.FUTURE_PREDICTION, ["acme/agent"], None, "future-prediction"),
        (Intent.PROJECT_DISCOVERY, None, None, "project-discovery"),
        (Intent.PROJECT_KNOWLEDGE, ["acme/agent"], None, "project-knowledge"),
    ],
)
def test_business_intents_use_skill_and_mcp(intent_name, repositories, category, expected_skill):
    constraints = {"knowledge_query": "如何安装"} if intent_name == Intent.PROJECT_KNOWLEDGE else {}
    agent, registry, _ = runtime(
        [intent(intent_name, repositories=repositories, category=category, **constraints), answer()]
    )
    result = agent.chat("测试问题")
    assert result["skill"] == expected_skill
    if expected_skill in {
        "trend-research",
        "potential-research",
        "learning-recommendation",
        "enterprise-selection",
    }:
        assert result["repository_links"]
    assert result["trace"]["tool_count"] <= agent.skills.resolve(intent_name).tool_call_budget
    assert registry.calls
    assert all(
        item[0] in agent.skills.resolve(intent_name).allowed_tools for item in registry.calls
    )


def test_global_top_ten_trend_query_preserves_requested_limit_and_ranking_sort():
    agent, registry, client = runtime(
        [intent(Intent.TREND_DISCOVERY, limit=10), answer("以下是趋势前十。")]
    )

    result = agent.chat("趋势前十的项目有哪些？")

    assert result["skill"] == "trend-research"
    assert registry.calls == [("search_projects", {"sort": "-trend", "limit": 10})]
    assert result["status"] == "COMPLETED"
    final_context = json.loads(client.messages[-1][-1]["content"])
    assert len(final_context["tool_context"]["results"]["search"][0]["projects"]) == 3


def test_global_top_ten_potential_query_uses_potential_ranking():
    agent, registry, _ = runtime(
        [intent(Intent.POTENTIAL_DISCOVERY, limit=10), answer("以下是高潜力前十。")]
    )

    result = agent.chat("高潜力前十的项目有哪些？")

    assert result["skill"] == "potential-research"
    assert registry.calls == [("search_projects", {"sort": "-potential", "limit": 10})]


def test_system_help_uses_trusted_help_tool_instead_of_repository_workflow():
    agent, registry, _ = runtime(
        [intent(Intent.SYSTEM_HELP, help_topic="TREND_SCORE"), answer("趋势评分说明。")]
    )

    result = agent.chat("趋势评分是怎么算的？")

    assert result["skill"] == "system-help"
    assert registry.calls == [("get_system_help", {"topic": "TREND_SCORE"})]


def test_constraints_from_an_unrelated_previous_intent_are_not_reused():
    agent, registry, _ = runtime(
        [
            intent(Intent.TREND_DISCOVERY, category="CODING_AGENT"),
            answer("编码智能体趋势。"),
            intent(Intent.PROJECT_DISCOVERY, limit=10),
            answer("项目列表。"),
        ]
    )
    session_id = "intent-isolation-123456"

    agent.chat("编码智能体趋势如何？", session_id)
    agent.chat("再推荐十个项目", session_id)

    assert registry.calls[-1] == ("search_projects", {"sort": "-stars", "limit": 10})


def test_invalid_intent_is_repaired_once_then_rejected():
    agent, _, _ = runtime([{"broken": True}, {"still": "broken"}])
    with pytest.raises(AgentError) as exc:
        agent.chat("含糊问题")
    assert exc.value.code == "INTENT_UNRESOLVED"


def test_invalid_final_answer_is_repaired_once():
    agent, _, _ = runtime(
        [
            intent(Intent.TREND_DISCOVERY, category="CODING_AGENT"),
            {"invalid": True},
            answer("修复后的有依据回答。"),
        ]
    )
    assert agent.chat("趋势如何")["answer"] == "修复后的有依据回答。"


def test_untrusted_repository_instruction_is_removed_before_final_llm():
    agent, _, client = runtime(
        [intent(Intent.PROJECT_ANALYSIS, repositories=["acme/agent"]), answer()]
    )
    agent.chat("分析 acme/agent")
    final_prompt = json.dumps(client.messages[-1], ensure_ascii=False)
    assert "ignore previous instructions" not in final_prompt
    assert "UNTRUSTED_DIRECTIVE_REMOVED" in final_prompt


def test_forecast_not_ready_never_accepts_probability():
    agent, _, _ = runtime(
        [
            intent(Intent.FUTURE_PREDICTION, repositories=["acme/agent"]),
            answer("未来上涨概率为 88%。"),
        ]
    )
    with pytest.raises(AgentError) as exc:
        agent.chat("这个项目未来会怎样？")
    assert exc.value.code == "FORECAST_SAFETY_VIOLATION"


def test_null_is_preserved_and_session_only_keeps_bounded_context():
    sessions = MemorySessions()
    registry = FakeRegistry()
    tools = MCPToolAdapter(MCPClient(MCPServer(registry=registry)))
    client = FakeLLM([intent(Intent.PROJECT_ANALYSIS, repositories=["acme/agent"]), answer()])
    agent = PMCopilotRuntime(client=client, tools=tools, sessions=sessions)
    result = agent.chat("分析 acme/agent", "safe-session-123456")
    final_context = json.loads(client.messages[-1][-1]["content"])
    assert final_context["tool_context"]["results"]["project"][0]["stars"] is None
    assert any(
        item.get("title", "").startswith("项目基础信息")
        for item in result["evidence"]
        if item["source_type"] == "STRUCTURED_TOOL_EVIDENCE"
    )
    stored = sessions.data[result["session_id"]]
    assert set(stored) >= {"recent_turns", "resolved_entities", "user_constraints", "last_intent"}
    assert "evidence" not in stored


def test_learning_goal_context_is_not_forwarded_to_search_tool():
    payload = intent(Intent.LEARNING_RECOMMENDATION, category="CODING_AGENT")
    payload["constraints"]["user_goal"] = "推荐适合学习的编码智能体项目"
    agent, registry, _ = runtime([payload, answer()])

    result = agent.chat("推荐适合学习的编码智能体项目")

    search_arguments = next(
        arguments for name, arguments in registry.calls if name == "search_projects"
    )
    assert "user_goal" not in search_arguments
    assert result["status"] != "PARTIAL"
