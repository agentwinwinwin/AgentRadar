from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.tools.registry import ToolRegistry

from .contracts import Intent, SkillDefinition
from .registry import SkillError, SkillRegistry


@dataclass
class ExecutionState:
    calls: int = 0
    results: dict[str, Any] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_count: int = 0
    stop_reason: str = "WORKFLOW_COMPLETED"
    result_status: str = "COMPLETED"


class SkillExecutor:
    """A fixed workflow harness. It has no planning, LLM, or autonomous tool selection."""

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self.registry = registry or SkillRegistry(tool_registry=self.tool_registry)
        self.tool_input_fields = {
            item["name"]: set(item.get("inputSchema", {}).get("properties", {}))
            for item in self.tool_registry.list()
        }

    def execute(
        self,
        intent: str,
        *,
        user_constraints: dict[str, Any] | None = None,
        resolved_entities: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        skill = self.registry.resolve(intent)
        constraints = user_constraints or {}
        entities = resolved_entities or {}
        self._require_inputs(skill, constraints, entities)
        state = ExecutionState()
        for step in skill.workflow_steps:
            if not self._condition(step.get("when"), state, constraints):
                continue
            invocations = self._invocations(step, constraints, entities, state)
            for arguments in invocations:
                if state.calls >= skill.tool_call_budget:
                    state.result_status = "TOOL_BUDGET_EXCEEDED"
                    state.stop_reason = "TOOL_BUDGET_EXCEEDED"
                    return self._output(skill, intent, state)
                self._call(skill, step, arguments, state)
                if step.get("stop_on_error") and state.result_status == "PARTIAL":
                    state.stop_reason = "REQUIRED_TOOL_FAILED"
                    return self._output(skill, intent, state)
            if self._enough_evidence(skill, state):
                state.stop_reason = "MINIMUM_EVIDENCE_SATISFIED"
                break
        self._finalize(skill, intent, state)
        return self._output(skill, intent, state)

    @staticmethod
    def _require_inputs(
        skill: SkillDefinition, constraints: dict[str, Any], entities: dict[str, Any]
    ) -> None:
        available = set(constraints) | set(entities)
        missing = set(skill.required_inputs) - available
        if missing:
            raise SkillError("MISSING_INPUT", "Required Skill input is missing", sorted(missing))

    def _call(
        self,
        skill: SkillDefinition,
        step: dict[str, Any],
        arguments: dict[str, Any],
        state: ExecutionState,
    ) -> None:
        tool = step["tool"]
        if tool not in skill.allowed_tools:
            raise SkillError("TOOL_NOT_ALLOWED", f"Tool not allowed by Skill: {tool}")
        response = self.tool_registry.call(tool, arguments)
        state.calls += 1
        trace = {
            "step": step["id"],
            "tool": tool,
            "ok": response["ok"],
            "duration_ms": response.get("metadata", {}).get("duration_ms"),
        }
        state.trace.append(trace)
        bucket = state.results.setdefault(step["id"], [])
        if response["ok"]:
            bucket.append(response["data"])
            state.evidence_count += self._count_evidence(response["data"])
        else:
            bucket.append(response)
            state.result_status = "PARTIAL"
            state.warnings.append(f"{tool}:{response['error_code']}")

    def _invocations(
        self,
        step: dict[str, Any],
        constraints: dict[str, Any],
        entities: dict[str, Any],
        state: ExecutionState,
    ) -> list[dict[str, Any]]:
        mode = step.get("mode", "single")
        if mode == "single":
            return [dict(step.get("arguments", {}))]
        if mode == "search":
            allowed = self.tool_input_fields.get(step["tool"], set())
            arguments = {
                key: value
                for key, value in constraints.items()
                if value is not None and key in allowed
            }
            defaults = dict(step.get("arguments", {}))
            constraint_keys = set(step.get("constraint_keys", []))
            if constraint_keys:
                defaults.update(
                    {key: value for key, value in arguments.items() if key in constraint_keys}
                )
                arguments = defaults
            else:
                arguments.update(defaults)
            return [arguments]
        if mode == "entity":
            arguments = self._entity_arguments(entities)
            arguments.update(step.get("arguments", {}))
            return [arguments]
        if mode == "entity_constraints":
            arguments = self._entity_arguments(entities)
            mapping = step.get("constraint_map", {})
            for source, target in mapping.items():
                if source in constraints and constraints[source] is not None:
                    arguments[target] = constraints[source]
            arguments = {**step.get("arguments", {}), **arguments}
            return [arguments]
        if mode == "category":
            return [{"category": constraints["category"]}] if constraints.get("category") else []
        if mode == "constraints":
            mapping = step.get("argument_map", {})
            arguments = {}
            for key in step.get("constraint_keys", []):
                if key in constraints:
                    arguments[mapping.get(key, key)] = constraints[key]
            arguments.update(step.get("arguments", {}))
            return [arguments]
        if mode == "compare_entities":
            return [{"repositories": entities["repositories"]}]
        if mode in {"each_candidate", "compare_candidates"}:
            candidates = self._candidates(state)
            if mode == "compare_candidates":
                values = [item["id"] for item in candidates[: step.get("limit", 2)]]
                return [{"repositories": values}] if len(values) >= 2 else []
            output = []
            for candidate in candidates[: step.get("limit", 3)]:
                arguments = {"repository_id": candidate["id"]}
                arguments.update(step.get("arguments", {}))
                output.append(arguments)
            return output
        if mode == "each_entity":
            output = []
            for value in entities["repositories"]:
                arguments = (
                    {"repository_id": value} if isinstance(value, int) else {"full_name": value}
                )
                arguments.update(step.get("arguments", {}))
                output.append(arguments)
            return output
        raise SkillError("INVALID_WORKFLOW", f"Unknown workflow mode: {mode}")

    @staticmethod
    def _entity_arguments(entities: dict[str, Any]) -> dict[str, Any]:
        if "repository_id" in entities:
            return {"repository_id": entities["repository_id"]}
        return {"full_name": entities["full_name"]}

    @staticmethod
    def _candidates(state: ExecutionState) -> list[dict[str, Any]]:
        search = state.results.get("search", [])
        return search[0].get("projects", []) if search and isinstance(search[0], dict) else []

    @staticmethod
    def _condition(
        condition: str | None,
        state: ExecutionState,
        constraints: dict[str, Any],
    ) -> bool:
        if condition is None:
            return True
        if condition == "FORECAST_NOT_READY":
            rows = state.results.get("forecast", [])
            return bool(rows and rows[0].get("status") == "NOT_READY")
        if condition == "KNOWLEDGE_INGESTED":
            summaries = state.results.get("knowledge_summary", [])
            return any(item.get("status") == "INGESTED" for item in summaries)
        if condition == "CATEGORY_PROVIDED":
            return bool(constraints.get("category"))
        return False

    @staticmethod
    def _count_evidence(data: Any) -> int:
        if isinstance(data, list):
            return len(data)
        if not isinstance(data, dict):
            return 0
        if isinstance(data.get("projects"), list):
            return sum(
                1
                for item in data["projects"]
                if isinstance(item, dict) and isinstance(item.get("id"), int)
            )
        count = int(bool(data.get("evidence")))
        count += sum(
            1 for value in data.values() if isinstance(value, dict) and value.get("evidence")
        )
        return count

    @staticmethod
    def _enough_evidence(skill: SkillDefinition, state: ExecutionState) -> bool:
        candidates = SkillExecutor._candidates(state)
        if skill.name == "trend-research":
            return bool(candidates)
        if skill.name == "learning-recommendation":
            return (
                len(state.results.get("learning", [])) >= min(3, len(candidates))
                and len(state.results.get("trend", [])) >= min(3, len(candidates))
                and bool(state.results.get("knowledge_summary"))
                and bool(state.results.get("knowledge"))
            )
        return False

    @staticmethod
    def _finalize(skill: SkillDefinition, intent: str, state: ExecutionState) -> None:
        if skill.name == "trend-research":
            reliable = any(
                item.get("trend_score") is not None and (item.get("data_completeness") or 0) >= 0.5
                for item in SkillExecutor._candidates(state)
            )
            if not reliable:
                state.result_status = "INSUFFICIENT_EVIDENCE"
                state.warnings.append("SHORT_HISTORY_NOT_LONG_TERM_TREND")
        if intent == Intent.FUTURE_PREDICTION:
            forecast = state.results.get("forecast", [{}])[0]
            if forecast.get("status") == "NOT_READY":
                state.result_status = "CURRENT_SIGNAL_ANALYSIS"
                state.warnings.append("FORECAST_NOT_READY")
        if skill.name == "enterprise-selection":
            enterprise = state.results.get("enterprise", [])
            sufficient = any(
                item.get("confidence", 0) >= 0.6
                and item.get("evidence", {})
                .get("components", {})
                .get("maintenance", {})
                .get("status")
                == "VALUE"
                for item in enterprise
                if isinstance(item, dict)
            )
            if not sufficient:
                state.result_status = "INSUFFICIENT_EVIDENCE"
        if state.result_status == "COMPLETED" and state.evidence_count == 0:
            state.result_status = "INSUFFICIENT_EVIDENCE"

    @staticmethod
    def _output(skill: SkillDefinition, intent: str, state: ExecutionState) -> dict[str, Any]:
        return {
            "selected_skill": skill.name,
            "skill_version": skill.version,
            "intent": intent,
            "executed_tools": [item["tool"] for item in state.trace],
            "tool_duration_ms": round(sum(item["duration_ms"] or 0 for item in state.trace), 3),
            "result_status": state.result_status,
            "warnings": state.warnings,
            "evidence_count": state.evidence_count,
            "stop_reason": state.stop_reason,
            "tool_calls": state.calls,
            "tool_budget": skill.tool_call_budget,
            "results": state.results,
        }
