import json
import subprocess
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge.models import KnowledgeDocument
from apps.repositories.models import Repository


class Command(BaseCommand):
    help = "Run real JSON-RPC stdio smoke calls against the read-only MCP server."

    def handle(self, *args, **options):
        knowledge_repository_id = (
            KnowledgeDocument.objects.filter(is_active=True)
            .values_list("repository_id", flat=True)
            .first()
        )
        repository_ids = list(
            Repository.objects.filter(is_disabled=False, is_fork=False)
            .order_by("id")
            .values_list("id", flat=True)[:2]
        )
        if knowledge_repository_id is None or len(repository_ids) < 2:
            raise CommandError("real MCP smoke requires Knowledge data and two repositories")
        calls = [
            ("search_projects", {"sort": "-stars", "limit": 3}),
            ("get_project", {"repository_id": repository_ids[0]}),
            ("get_project_trend", {"repository_id": repository_ids[0]}),
            ("get_project_potential", {"repository_id": repository_ids[0]}),
            ("get_learning_score", {"repository_id": knowledge_repository_id}),
            ("get_enterprise_score", {"repository_id": knowledge_repository_id}),
            ("compare_projects", {"repositories": repository_ids}),
            (
                "search_repository_knowledge",
                {
                    "repository_id": knowledge_repository_id,
                    "query": "installation architecture security",
                    "top_k": 3,
                },
            ),
            ("get_project_forecast", {"repository_id": repository_ids[0]}),
        ]
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        requests.extend(
            {
                "jsonrpc": "2.0",
                "id": index,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
            for index, (name, arguments) in enumerate(calls, 3)
        )
        payload = "".join(json.dumps(request) + "\n" for request in requests)
        process = subprocess.run(
            [sys.executable, "manage.py", "mcp_server"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if process.returncode:
            raise CommandError("MCP server process failed without exposing stderr")
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        if len(responses) != len(requests):
            raise CommandError("MCP response count mismatch")
        tools = responses[1]["result"]["tools"]
        results = []
        for (name, _), response in zip(calls, responses[2:], strict=True):
            structured = response["result"]["structuredContent"]
            if not structured["ok"]:
                raise CommandError(f"MCP tool failed: {name}/{structured['error_code']}")
            results.append(
                {
                    "tool": name,
                    "ok": True,
                    "duration_ms": structured["metadata"]["duration_ms"],
                    "db_query_count": structured["metadata"]["db_query_count"],
                    "result_bytes": structured["metadata"]["result_bytes"],
                }
            )
        forecast = responses[-1]["result"]["structuredContent"]["data"]
        knowledge_rows = responses[-2]["result"]["structuredContent"]["data"]
        if forecast["status"] != "NOT_READY" or forecast["forecast"] is not None:
            raise CommandError("Forecast safety contract failed")
        if not knowledge_rows:
            raise CommandError("pgvector retrieval returned no Evidence")
        self.stdout.write(
            json.dumps(
                {
                    "server": responses[0]["result"]["serverInfo"],
                    "registered_tools": len(tools),
                    "calls": results,
                    "knowledge_evidence": len(knowledge_rows),
                    "forecast_status": forecast["status"],
                },
                sort_keys=True,
            )
        )
