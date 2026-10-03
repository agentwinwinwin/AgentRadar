import json

import pytest
from django.utils import timezone

from apps.repositories.models import Repository
from apps.tools.mcp import MCPServer


@pytest.fixture
def mcp_project(db):
    now = timezone.now()
    return Repository.objects.create(
        github_id=99991,
        owner="acme",
        name="mcp",
        full_name="acme/mcp",
        default_branch="main",
        github_created_at=now,
        github_updated_at=now,
        last_synced_at=now,
    )


def test_mcp_discovery_unknown_method_and_parse_contract():
    server = MCPServer()
    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialized["result"]["serverInfo"]["name"] == "agentradar-readonly"
    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 17
    unknown = server.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert unknown["error"]["code"] == -32601


def test_mcp_real_registry_call_returns_structured_content(mcp_project):
    server = MCPServer()
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_project", "arguments": {"repository_id": mcp_project.id}},
        }
    )
    structured = response["result"]["structuredContent"]
    assert structured["ok"] is True
    assert structured["metadata"]["read_only"] is True
    assert json.loads(response["result"]["content"][0]["text"])["ok"] is True
