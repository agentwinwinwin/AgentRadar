from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings

INJECTION = re.compile(
    r"(?i)(ignore\s+(all\s+)?previous\s+instructions|reveal\s+.{0,30}(key|secret)|execute\s+(this\s+)?(shell|command)|call\s+this\s+tool)"
)


class ContextBuilder:
    def build(self, execution: dict[str, Any]) -> dict[str, Any]:
        compact = self._compact(execution.get("results", {}), depth=0)
        payload = {
            "status": execution["result_status"],
            "warnings": execution["warnings"],
            "stop_reason": execution["stop_reason"],
            "results": compact,
        }
        encoded = json.dumps(payload, default=str, ensure_ascii=False)
        return (
            json.loads(encoded[: settings.AGENT_MAX_CONTEXT_CHARS])
            if len(encoded) <= settings.AGENT_MAX_CONTEXT_CHARS
            else {
                "status": execution["result_status"],
                "warnings": execution["warnings"] + ["CONTEXT_TRUNCATED"],
                "stop_reason": execution["stop_reason"],
                "results": self._compact(execution.get("results", {}), depth=0, aggressive=True),
            }
        )

    def evidence(self, execution: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for source, value in execution.get("results", {}).items():
            self._collect(value, output, source=source)
        return output[: settings.AGENT_MAX_EVIDENCE]

    def repository_links(self, execution: dict[str, Any]) -> list[dict[str, Any]]:
        links: dict[int, str] = {}

        def collect(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if not isinstance(value, dict):
                return
            repository_id = value.get("id", value.get("repository_id"))
            full_name = value.get("full_name")
            if (
                isinstance(repository_id, int)
                and isinstance(full_name, str)
                and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name)
            ):
                links[repository_id] = full_name
            for item in value.values():
                collect(item)

        collect(execution.get("results", {}))
        return [
            {"repository_id": repository_id, "full_name": full_name}
            for repository_id, full_name in links.items()
        ][: settings.AGENT_MAX_EVIDENCE]

    def _compact(self, value: Any, *, depth: int, aggressive: bool = False) -> Any:
        if depth > 6:
            return "[TRUNCATED]"
        if isinstance(value, str):
            clean = INJECTION.sub("[UNTRUSTED_DIRECTIVE_REMOVED]", value)
            return clean[: (300 if aggressive else 600)]
        if isinstance(value, list):
            limit = 3 if aggressive else 5
            return [
                self._compact(item, depth=depth + 1, aggressive=aggressive)
                for item in value[:limit]
            ]
        if isinstance(value, dict):
            output = {}
            for key, item in value.items():
                if key in {"raw_metadata", "content", "feature_snapshot"}:
                    continue
                if key == "projects" and isinstance(item, list):
                    limit = 8 if aggressive else 20
                    output[key] = [
                        self._compact(row, depth=depth + 1, aggressive=aggressive)
                        for row in item[:limit]
                    ]
                else:
                    output[key] = self._compact(item, depth=depth + 1, aggressive=aggressive)
            return output
        return value

    def _collect(self, value: Any, output: list[dict[str, Any]], *, source: str) -> None:
        if len(output) >= settings.AGENT_MAX_EVIDENCE:
            return
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and {"repository", "snippet", "source_type"} <= set(item):
                    output.append(
                        {
                            "repository": item["repository"],
                            "source_type": item["source_type"],
                            "title": item.get("title"),
                            "path": item.get("path"),
                            "url": item.get("url"),
                            "snippet": self._compact(item["snippet"], depth=0),
                            "similarity": item.get("similarity"),
                            "updated_at": item.get("updated_at"),
                            "trust": "UNTRUSTED_EXTERNAL_CONTENT",
                        }
                    )
                else:
                    self._collect(item, output, source=source)
        elif isinstance(value, dict):
            if (
                isinstance(value.get("id"), int)
                and isinstance(value.get("full_name"), str)
                and value.get("trend_score") is not None
            ):
                output.append(
                    {
                        "source_type": "STRUCTURED_TOOL_EVIDENCE",
                        "title": f"趋势排行 · {value['full_name']}",
                        "repository_id": value["id"],
                        "algorithm_version": value.get("algorithm_version"),
                        "confidence": value.get("data_completeness"),
                    }
                )
            if value.get("evidence"):
                repository_id = value.get("repository_id")
                output.append(
                    {
                        "source_type": "STRUCTURED_TOOL_EVIDENCE",
                        "title": self._structured_title(source, repository_id),
                        "repository_id": repository_id,
                        "algorithm_version": value.get("algorithm_version"),
                        "confidence": value.get("confidence", value.get("data_completeness")),
                    }
                )
            for item in value.values():
                self._collect(item, output, source=source)

    @staticmethod
    def _structured_title(source: str, repository_id: Any) -> str:
        labels = {
            "search": "项目检索结果",
            "project": "项目基础信息",
            "trend": "趋势与维护证据",
            "potential": "潜力评分证据",
            "learning": "学习价值证据",
            "enterprise": "企业成熟度证据",
            "forecast": "预测状态证据",
            "knowledge_summary": "项目知识覆盖",
            "compare": "项目对比证据",
            "category": "分类统计证据",
            "help": "AgentRadar 产品与指标说明",
            "knowledge": "项目知识证据",
        }
        title = labels.get(source, "结构化系统证据")
        return f"{title} · 项目 #{repository_id}" if repository_id else title
