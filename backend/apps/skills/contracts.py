from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Intent(StrEnum):
    PROJECT_DISCOVERY = "PROJECT_DISCOVERY"
    TREND_DISCOVERY = "TREND_DISCOVERY"
    POTENTIAL_DISCOVERY = "POTENTIAL_DISCOVERY"
    FUTURE_PREDICTION = "FUTURE_PREDICTION"
    LEARNING_RECOMMENDATION = "LEARNING_RECOMMENDATION"
    ENTERPRISE_SELECTION = "ENTERPRISE_SELECTION"
    PROJECT_ANALYSIS = "PROJECT_ANALYSIS"
    PROJECT_COMPARISON = "PROJECT_COMPARISON"
    WATCHLIST_QUERY = "WATCHLIST_QUERY"
    ALERT_QUERY = "ALERT_QUERY"
    REPORT_QUERY = "REPORT_QUERY"
    PROJECT_KNOWLEDGE = "PROJECT_KNOWLEDGE"
    SYSTEM_HELP = "SYSTEM_HELP"


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    version: str
    description: str
    supported_intents: tuple[str, ...]
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    workflow_steps: tuple[dict[str, Any], ...]
    evidence_requirements: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    fallback_policy: dict[str, str]
    output_contract: dict[str, Any]
    safety_constraints: tuple[str, ...]
    tool_call_budget: int
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillDefinition:
        tuple_fields = (
            "supported_intents",
            "required_inputs",
            "optional_inputs",
            "allowed_tools",
            "workflow_steps",
            "evidence_requirements",
            "stop_conditions",
            "safety_constraints",
        )
        values = dict(data)
        for field in tuple_fields:
            values[field] = tuple(values[field])
        return cls(**values)

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "supported_intents": list(self.supported_intents),
            "required_inputs": list(self.required_inputs),
            "optional_inputs": list(self.optional_inputs),
            "allowed_tools": list(self.allowed_tools),
            "workflow_steps": list(self.workflow_steps),
            "evidence_requirements": list(self.evidence_requirements),
            "stop_conditions": list(self.stop_conditions),
            "fallback_policy": self.fallback_policy,
            "output_contract": self.output_contract,
            "safety_constraints": list(self.safety_constraints),
            "tool_call_budget": self.tool_call_budget,
            "enabled": self.enabled,
        }
