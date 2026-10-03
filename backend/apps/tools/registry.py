from __future__ import annotations

import json
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.common.actor import ActorRequired, actor_user_id
from apps.forecasts.models import MLModel, ModelStatus
from apps.repositories.api_services import RepositoryReadService
from apps.repositories.models import RepositoryCategory
from apps.watchlists.models import ScheduledReport

from .services import ToolDataService
from .system_help import HELP_TOPICS, system_help

TOOL_VERSION = "tools-v1.0.0"
DEFAULT_TIMEOUT_SECONDS = settings.MCP_TOOL_TIMEOUT_SECONDS
MAX_LIST_LIMIT = 50


class ToolError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    version: str = TOOL_VERSION
    read_only: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "annotations": {"readOnlyHint": self.read_only},
            "_meta": {"version": self.version, "timeout_seconds": self.timeout_seconds},
        }


EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
OUTPUT = {
    "oneOf": [
        {
            "type": "object",
            "required": ["ok", "data", "evidence", "warnings", "metadata"],
            "properties": {
                "ok": {"type": "boolean"},
                "data": {},
                "evidence": {},
                "warnings": {"type": "array", "items": {}},
                "metadata": {"type": "object"},
            },
        },
        {
            "type": "object",
            "required": ["ok", "error_code", "message", "details"],
            "properties": {
                "ok": {"type": "boolean"},
                "error_code": {"type": "string"},
                "message": {"type": "string"},
                "details": {},
            },
        },
    ]
}
CATEGORIES = [value for value, _ in RepositoryCategory.choices]
SORTS = [
    "trend",
    "-trend",
    "potential",
    "-potential",
    "learning",
    "-learning",
    "enterprise",
    "-enterprise",
    "stars",
    "-stars",
    "updated",
    "-updated",
]


def _repository_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "repository_id": {"type": "integer", "minimum": 1},
            "full_name": {"type": "string", "minLength": 3, "maxLength": 512},
        },
        "oneOf": [
            {"type": "object", "required": ["repository_id"]},
            {"type": "object", "required": ["full_name"]},
        ],
        "additionalProperties": False,
    }


def _repository_value(arguments: dict[str, Any]) -> int | str:
    return arguments.get("repository_id") or arguments["full_name"]


def _search(arguments: dict[str, Any]) -> dict[str, Any]:
    filters = {
        "q": arguments.get("query"),
        "category": arguments.get("category"),
        "min_stars": arguments.get("min_stars"),
        "max_stars": arguments.get("max_stars"),
        "trend_min": arguments.get("trend_min"),
        "potential_min": arguments.get("potential_min"),
        "learning_min": arguments.get("learning_min"),
        "enterprise_min": arguments.get("enterprise_min"),
        "sort": arguments.get("sort", "-trend"),
    }
    return {"projects": ToolDataService.search(filters, arguments.get("limit", 10))}


def _forecast(arguments: dict[str, Any]) -> dict[str, Any]:
    result = RepositoryReadService.forecast(
        ToolDataService.resolve_repository(_repository_value(arguments)).id
    )
    result["validated_model_exists"] = MLModel.objects.filter(status=ModelStatus.VALIDATED).exists()
    if result.get("status") == "NOT_READY":
        result["reason"] = "No explicitly activated production model is available."
        result["missing"] = ["ACTIVE_MODEL", "EXPLICIT_ADMIN_ACTIVATION"]
    return result


def _score(method: str, arguments: dict[str, Any]) -> dict[str, Any]:
    repository = ToolDataService.resolve_repository(_repository_value(arguments))
    result = getattr(RepositoryReadService, method)(repository.id)
    if method == "potential" and result.get("status") == "AVAILABLE":
        result["reliability_status"] = (
            "DATA_ACCUMULATING"
            if result.get("confidence", 0) < RepositoryReadService.MIN_POTENTIAL_RANKING_CONFIDENCE
            else "SUFFICIENT_DATA"
        )
    if method == "learning":
        result["recommendation"] = None
    return result


SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "maxLength": 200},
        "category": {"type": "string", "enum": CATEGORIES},
        "min_stars": {"type": "integer", "minimum": 0},
        "max_stars": {"type": "integer", "minimum": 0},
        "trend_min": {"type": "number", "minimum": 0, "maximum": 100},
        "potential_min": {"type": "number", "minimum": 0, "maximum": 100},
        "learning_min": {"type": "number", "minimum": 0, "maximum": 100},
        "enterprise_min": {"type": "number", "minimum": 0, "maximum": 100},
        "sort": {"type": "string", "enum": SORTS},
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIST_LIMIT, "default": 10},
    },
    "additionalProperties": False,
}


def definitions() -> list[ToolDefinition]:
    repo = _repository_schema()
    return [
        ToolDefinition(
            "search_projects",
            "Search persisted projects for bounded discovery; never collect from GitHub.",
            SEARCH_SCHEMA,
            OUTPUT,
            _search,
        ),
        ToolDefinition(
            "get_system_help",
            "Read trusted built-in AgentRadar product and metric documentation.",
            {
                "type": "object",
                "properties": {"topic": {"type": "string", "enum": list(HELP_TOPICS)}},
                "required": ["topic"],
                "additionalProperties": False,
            },
            OUTPUT,
            lambda arguments: system_help(arguments["topic"]),
        ),
        ToolDefinition(
            "get_project",
            "Read one persisted project and current summaries. Do not use to refresh GitHub.",
            repo,
            OUTPUT,
            lambda a: ToolDataService.project(_repository_value(a)),
        ),
        ToolDefinition(
            "get_project_trend",
            "Read deterministic Trend Score and evidence; do not infer future success.",
            repo,
            OUTPUT,
            lambda a: _score("trend", a),
        ),
        ToolDefinition(
            "get_project_potential",
            "Read deterministic Potential Score; it is not a forecast probability.",
            repo,
            OUTPUT,
            lambda a: _score("potential", a),
        ),
        ToolDefinition(
            "get_project_forecast",
            "Read production Forecast status; never runs VALIDATED models or invents probability.",
            repo,
            OUTPUT,
            _forecast,
        ),
        ToolDefinition(
            "get_learning_score",
            "Read deterministic learning-value score and Knowledge evidence.",
            repo,
            OUTPUT,
            lambda a: _score("learning", a),
        ),
        ToolDefinition(
            "get_enterprise_score",
            "Read deterministic enterprise-readiness score and evidence; not procurement advice.",
            repo,
            OUTPUT,
            lambda a: _score("enterprise", a),
        ),
        ToolDefinition(
            "get_watchlist",
            "Read the current user's persisted Watchlist; never mutates it.",
            EMPTY,
            OUTPUT,
            lambda a: ToolDataService.watchlist(),
        ),
        ToolDefinition(
            "get_project_alerts",
            "Read deterministic alerts and evidence for one persisted project.",
            {
                **repo,
                "properties": {
                    **repo["properties"],
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            OUTPUT,
            lambda a: ToolDataService.alerts(_repository_value(a), a.get("limit", 20)),
        ),
        ToolDefinition(
            "get_latest_report",
            "Read the latest deterministic Daily or Weekly report.",
            {
                "type": "object",
                "required": ["report_type"],
                "properties": {
                    "report_type": {"type": "string", "enum": ScheduledReport.Type.values}
                },
                "additionalProperties": False,
            },
            OUTPUT,
            lambda a: ToolDataService.latest_report(a["report_type"]),
        ),
        ToolDefinition(
            "compare_projects",
            "Compare 2-5 projects using persisted facts; does not write narrative analysis.",
            {
                "type": "object",
                "required": ["repositories"],
                "properties": {
                    "repositories": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 5,
                        "items": {
                            "oneOf": [
                                {"type": "integer", "minimum": 1},
                                {"type": "string", "minLength": 3},
                            ]
                        },
                    }
                },
                "additionalProperties": False,
            },
            OUTPUT,
            lambda a: ToolDataService.compare(a["repositories"]),
            timeout_seconds=15,
        ),
        ToolDefinition(
            "search_repository_knowledge",
            "Retrieve untrusted README/docs evidence, never structured scores.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "repository_id": {"type": "integer", "minimum": 1},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "query": {"type": "string", "minLength": 2, "maxLength": 1000},
                    "source_type": {
                        "type": "string",
                        "enum": [
                            "README",
                            "DOC",
                            "ARCHITECTURE",
                            "DESIGN",
                            "SECURITY",
                            "CONTRIBUTING",
                            "RELEASE",
                            "PULL_REQUEST",
                            "ISSUE",
                        ],
                    },
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                },
                "additionalProperties": False,
            },
            OUTPUT,
            ToolDataService.retrieve_knowledge,
            timeout_seconds=15,
        ),
        ToolDefinition(
            "get_project_knowledge_summary",
            "Read deterministic Knowledge metadata; does not generate an AI summary.",
            repo,
            OUTPUT,
            lambda a: ToolDataService.knowledge_summary(_repository_value(a)),
        ),
        ToolDefinition(
            "list_categories",
            "List category counts and basic persisted aggregates; no dedicated trend model.",
            EMPTY,
            OUTPUT,
            lambda _: {"categories": ToolDataService.categories()},
        ),
        ToolDefinition(
            "get_category_projects",
            "Read a bounded project list in one category using structured filters.",
            {**SEARCH_SCHEMA, "required": ["category"]},
            OUTPUT,
            _search,
        ),
        ToolDefinition(
            "get_category_trend",
            "Read category aggregates only; returns NO_DEDICATED_CATEGORY_TREND_MODEL.",
            {
                "type": "object",
                "required": ["category"],
                "properties": {"category": {"type": "string", "enum": CATEGORIES}},
                "additionalProperties": False,
            },
            OUTPUT,
            lambda a: ToolDataService.category_trend(a["category"]),
        ),
    ]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools = {tool.name: tool for tool in definitions()}

    def list(self) -> list[dict[str, Any]]:
        return [tool.metadata() for tool in self._tools.values()]

    def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        actor_id: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            return self._error(
                "UNKNOWN_TOOL", f"Unknown tool: {name}", {"available": sorted(self._tools)}
            )
        arguments = arguments or {}
        try:
            self._validate(tool.input_schema, arguments)
            token = actor_user_id.set(actor_id)
            try:
                with CaptureQueriesContext(connection) as queries:
                    data = self._with_timeout(tool.timeout_seconds, lambda: tool.handler(arguments))
            finally:
                actor_user_id.reset(token)
            duration = round((time.perf_counter() - started) * 1000, 3)
            size = len(json.dumps(data, default=str).encode())
            response = {
                "ok": True,
                "data": data,
                "evidence": data.get("evidence") if isinstance(data, dict) else None,
                "warnings": [],
                "metadata": {
                    "tool": name,
                    "tool_version": tool.version,
                    "read_only": True,
                    "duration_ms": duration,
                    "result_bytes": size,
                    "db_query_count": len(queries),
                    "timeout_seconds": tool.timeout_seconds,
                },
            }
            self._validate(tool.output_schema, response, "output")
            return response
        except ToolError as exc:
            return self._error(exc.code, exc.message, exc.details)
        except ObjectDoesNotExist:
            return self._error("NOT_FOUND", "Requested repository was not found.")
        except ActorRequired:
            return self._error("AUTH_REQUIRED", "Authenticated user context is required.")
        except Exception as exc:  # defensive boundary: internal exception details stay private
            return self._error(
                "INTERNAL_ERROR",
                "The tool could not complete the request.",
                {"type": type(exc).__name__},
            )

    @staticmethod
    def _error(code: str, message: str, details: Any = None) -> dict[str, Any]:
        return {"ok": False, "error_code": code, "message": message, "details": details}

    @classmethod
    def _validate(cls, schema: dict[str, Any], value: Any, path: str = "arguments") -> None:
        if "oneOf" in schema:
            successes = 0
            for option in schema["oneOf"]:
                try:
                    cls._validate(option, value, path)
                    successes += 1
                except ToolError:
                    pass
            if successes != 1:
                raise ToolError("INVALID_ARGUMENT", f"{path} must match exactly one allowed schema")
        expected = schema.get("type")
        valid = {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, int | float) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
        }
        if expected and not valid.get(expected, False):
            raise ToolError("INVALID_ARGUMENT", f"{path} must be {expected}")
        if expected == "object":
            for field in schema.get("required", []):
                if field not in value:
                    raise ToolError("INVALID_ARGUMENT", f"{path}.{field} is required")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                unknown = set(value) - set(properties)
                if unknown:
                    raise ToolError("INVALID_ARGUMENT", f"Unknown fields: {sorted(unknown)}")
            for field, item in value.items():
                if field in properties:
                    cls._validate(properties[field], item, f"{path}.{field}")
        if expected == "array":
            if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10**9):
                raise ToolError("INVALID_ARGUMENT", f"{path} has invalid item count")
            for index, item in enumerate(value):
                cls._validate(schema["items"], item, f"{path}[{index}]")
        if "enum" in schema and value not in schema["enum"]:
            raise ToolError("INVALID_ARGUMENT", f"{path} has unsupported value")
        if isinstance(value, int | float) and not isinstance(value, bool):
            if value < schema.get("minimum", value) or value > schema.get("maximum", value):
                raise ToolError("INVALID_ARGUMENT", f"{path} is outside allowed range")
        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
                "maxLength", 10**9
            ):
                raise ToolError("INVALID_ARGUMENT", f"{path} has invalid length")

    @staticmethod
    def _with_timeout(seconds: int, callback: Callable[[], Any]) -> Any:
        if threading.current_thread() is not threading.main_thread():
            started = time.monotonic()
            result = callback()
            if time.monotonic() - started > seconds:
                raise ToolError("TIMEOUT", "Tool execution exceeded its timeout.")
            return result

        def timeout_handler(signum, frame):
            raise ToolError("TIMEOUT", "Tool execution exceeded its timeout.")

        previous = signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            return callback()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
