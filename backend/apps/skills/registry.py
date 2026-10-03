from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.tools.registry import ToolRegistry

from .contracts import Intent, SkillDefinition

VERSION_PATTERN = re.compile(r"^[a-z][a-z0-9-]*-v\d+\.\d+\.\d+$")
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


class SkillError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class SkillLoader:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.SKILL_ROOT

    def load(self) -> list[SkillDefinition]:
        skills = [self._load_file(path) for path in sorted(self.root.glob("*/SKILL.md"))]
        if not skills:
            raise SkillError("NO_SKILLS", "No Skill definitions were found.")
        return skills

    @staticmethod
    def _load_file(path: Path) -> SkillDefinition:
        match = JSON_BLOCK.search(path.read_text(encoding="utf-8"))
        if not match:
            raise SkillError("INVALID_SKILL", f"Missing JSON contract in {path.name}")
        try:
            return SkillDefinition.from_dict(json.loads(match.group(1)))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SkillError("INVALID_SKILL", f"Invalid contract in {path.name}") from exc


class SkillRegistry:
    def __init__(
        self,
        loader: SkillLoader | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        skills = (loader or SkillLoader()).load()
        self._skills = {skill.name: skill for skill in skills}
        self._validate(skills)

    def list(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        return [
            skill.public() for skill in self._skills.values() if include_disabled or skill.enabled
        ]

    def get(self, name: str) -> SkillDefinition:
        skill = self._skills.get(name)
        if skill is None:
            raise SkillError("UNKNOWN_SKILL", f"Unknown Skill: {name}")
        if not skill.enabled:
            raise SkillError("SKILL_DISABLED", f"Skill is disabled: {name}")
        return skill

    def resolve(self, intent: str) -> SkillDefinition:
        try:
            Intent(intent)
        except ValueError as exc:
            raise SkillError("UNKNOWN_INTENT", f"Unknown Intent: {intent}") from exc
        matches = [
            skill
            for skill in self._skills.values()
            if skill.enabled and intent in skill.supported_intents
        ]
        if len(matches) != 1:
            raise SkillError("INTENT_MAPPING_INVALID", "Intent must resolve to exactly one Skill")
        return matches[0]

    def dry_run(
        self,
        intent: str,
        *,
        user_constraints: dict[str, Any] | None = None,
        resolved_entities: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        skill = self.resolve(intent)
        return {
            "selected_skill": skill.name,
            "skill_version": skill.version,
            "planned_steps": list(skill.workflow_steps),
            "allowed_tools": list(skill.allowed_tools),
            "required_evidence": list(skill.evidence_requirements),
            "stop_conditions": list(skill.stop_conditions),
            "fallback_policy": skill.fallback_policy,
            "tool_call_budget": skill.tool_call_budget,
            "inputs": {
                "user_constraints": user_constraints or {},
                "resolved_entities": resolved_entities or {},
                "context": context or {},
            },
            "executed": False,
        }

    def _validate(self, skills: list[SkillDefinition]) -> None:
        if len(self._skills) != len(skills):
            raise SkillError("DUPLICATE_SKILL", "Skill names must be unique")
        available = {tool["name"]: tool for tool in self.tool_registry.list()}
        intents: list[str] = []
        for skill in skills:
            if not VERSION_PATTERN.fullmatch(skill.version) or not skill.version.startswith(
                f"{skill.name}-v"
            ):
                raise SkillError("INVALID_VERSION", f"Invalid version for {skill.name}")
            if not 1 <= skill.tool_call_budget <= 25:
                raise SkillError("INVALID_BUDGET", f"Invalid budget for {skill.name}")
            referenced = set(skill.allowed_tools)
            referenced.update(step["tool"] for step in skill.workflow_steps)
            missing = referenced - set(available)
            if missing:
                raise SkillError(
                    "UNKNOWN_TOOL_REFERENCE",
                    f"{skill.name} references unknown Tools",
                    sorted(missing),
                )
            if any(not available[name]["annotations"]["readOnlyHint"] for name in referenced):
                raise SkillError("WRITE_TOOL_FORBIDDEN", f"{skill.name} references a write Tool")
            if any(step["tool"] not in skill.allowed_tools for step in skill.workflow_steps):
                raise SkillError("TOOL_NOT_ALLOWED", f"{skill.name} workflow exceeds its whitelist")
            intents.extend(skill.supported_intents)
        expected = {intent.value for intent in Intent}
        if set(intents) != expected or len(intents) != len(expected):
            raise SkillError("INTENT_MAPPING_INVALID", "Every Intent must map exactly once")
