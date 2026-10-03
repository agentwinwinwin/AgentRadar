from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from django.db import DatabaseError

from apps.skills.executor import SkillExecutor
from apps.skills.registry import SkillError, SkillRegistry

from .context import ContextBuilder
from .entities import EntityResolver
from .history import CopilotHistoryService
from .intent import IntentRouter, IntentUnresolved
from .llm import LLMClient, LLMError, llm_client
from .mcp_client import MCPToolAdapter
from .response import AnswerGenerator
from .session import RedisSessionStore, SessionStore, new_session_id


class AgentError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PMCopilotRuntime:
    def __init__(
        self,
        *,
        client: LLMClient | None = None,
        tools: MCPToolAdapter | None = None,
        sessions: SessionStore | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        try:
            self.client = client or llm_client()
        except LLMError as exc:
            raise AgentError(exc.code, exc.message, 503) from exc
        self.actor_user_id = actor_user_id
        self.tools = tools or MCPToolAdapter(actor_user_id=actor_user_id)
        self.skills = SkillRegistry(tool_registry=self.tools)
        self.executor = SkillExecutor(self.skills, self.tools)
        self.sessions = sessions or RedisSessionStore()
        self.router = IntentRouter(self.client)
        self.resolver = EntityResolver(self.tools)
        self.context_builder = ContextBuilder()
        self.generator = AnswerGenerator(self.client)

    def chat(
        self,
        message: str,
        session_id: str | None = None,
        *,
        provider_stream: bool = False,
        on_answer_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        trace_id = str(uuid.uuid4())
        session_id = session_id or new_session_id()
        session = self.sessions.get(session_id, self.actor_user_id)
        intent_started = time.perf_counter()
        try:
            routed = self.router.route(message, self._session_context(session))
        except IntentUnresolved as exc:
            raise AgentError("INTENT_UNRESOLVED", "无法可靠识别问题意图。", 422) from exc
        except LLMError as exc:
            raise AgentError(exc.code, exc.message, 502) from exc
        intent_duration = round((time.perf_counter() - intent_started) * 1000, 3)
        try:
            skill = self.skills.resolve(routed.intent)
            resolved = self.resolver.resolve(
                routed.intent,
                routed.entities,
                routed.constraints,
                session,
                skill.allowed_tools,
            )
            execution = self.executor.execute(
                routed.intent,
                user_constraints=resolved.constraints,
                resolved_entities=resolved.entities,
                context=self._session_context(session),
            )
        except SkillError as exc:
            raise AgentError(exc.code, exc.message, 422) from exc
        total_tool_calls = len(resolved.trace) + execution["tool_calls"]
        if total_tool_calls > skill.tool_call_budget:
            raise AgentError("TOOL_BUDGET_EXCEEDED", "Agent Tool budget exceeded.", 422)
        context = self.context_builder.build(execution)
        answer_started = time.perf_counter()
        try:
            generated = self.generator.generate(
                message,
                skill={
                    "name": skill.name,
                    "version": skill.version,
                    "evidence_requirements": list(skill.evidence_requirements),
                    "fallback_policy": skill.fallback_policy,
                    "safety_constraints": list(skill.safety_constraints),
                },
                context=context,
                provider_stream=provider_stream,
                on_answer_delta=on_answer_delta,
            )
        except LLMError as exc:
            raise AgentError(exc.code, exc.message, 502) from exc
        answer_duration = round((time.perf_counter() - answer_started) * 1000, 3)
        warnings = list(dict.fromkeys([*execution["warnings"], *generated.warnings]))
        evidence = self.context_builder.evidence(execution)
        token_usage = {
            "prompt_tokens": (routed.prompt_tokens or 0) + (generated.prompt_tokens or 0) or None,
            "completion_tokens": (routed.completion_tokens or 0)
            + (generated.completion_tokens or 0)
            or None,
        }
        result = {
            "answer": generated.answer,
            "intent": routed.intent,
            "intent_confidence": routed.confidence,
            "skill": skill.name,
            "skill_version": skill.version,
            "status": execution["result_status"],
            "recommendations": generated.recommendations,
            "warnings": warnings,
            "evidence": evidence,
            "repository_links": self.context_builder.repository_links(execution),
            "trace_id": trace_id,
            "session_id": session_id,
            "trace": {
                "trace_id": trace_id,
                "session_id": session_id,
                "intent": routed.intent,
                "intent_confidence": routed.confidence,
                "selected_skill": skill.name,
                "skill_version": skill.version,
                "tool_calls": [*resolved.trace, *execution["executed_tools"]],
                "tool_count": total_tool_calls,
                "tool_duration_ms": execution["tool_duration_ms"]
                + sum(item["duration_ms"] or 0 for item in resolved.trace),
                "evidence_count": len(evidence),
                "warnings": warnings,
                "stop_reason": execution["stop_reason"],
                "llm_provider": self.client.provider,
                "llm_model": self.client.model,
                "token_usage": token_usage,
                "intent_duration_ms": intent_duration,
                "llm_answer_duration_ms": answer_duration,
                "total_duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }
        self._save_session(session_id, session, message, result, resolved)
        if self.actor_user_id is not None:
            try:
                CopilotHistoryService.persist_turn(
                    owner_id=self.actor_user_id,
                    session_id=session_id,
                    question=message,
                    result=result,
                )
            except DatabaseError as exc:
                raise AgentError("HISTORY_UNAVAILABLE", "历史记录暂时无法保存。", 503) from exc
        return result

    @staticmethod
    def _session_context(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "last_intent": session.get("last_intent"),
            "resolved_entities": session.get("resolved_entities", {}),
            "category": session.get("user_constraints", {}).get("category"),
            "recent_turns": session.get("recent_turns", [])[-4:],
        }

    def _save_session(
        self,
        session_id: str,
        session: dict[str, Any],
        message: str,
        result: dict[str, Any],
        resolved,
    ) -> None:
        turns = session.get("recent_turns", [])
        turns.append(
            {
                "user": message[:1000],
                "assistant": result["answer"][:1500],
                "intent": result["intent"],
            }
        )
        self.sessions.save(
            session_id,
            {
                **session,
                "recent_turns": turns,
                "resolved_entities": resolved.entities,
                "user_constraints": resolved.constraints,
                "last_intent": result["intent"],
            },
            self.actor_user_id,
        )
