from __future__ import annotations

from typing import Any

from apps.tools.mcp import MCPServer


class MCPClientError(RuntimeError):
    pass


class MCPClient:
    """JSON-RPC client boundary; Agent code never calls ToolRegistry directly."""

    def __init__(self, server: MCPServer | None = None, actor_user_id: int | None = None) -> None:
        self.server = server or MCPServer()
        self.actor_user_id = actor_user_id
        self.request_id = 0

    def list_tools(self) -> list[dict[str, Any]]:
        return self._request("tools/list", {})["tools"]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments, "actor_user_id": self.actor_user_id},
        )
        return result["structuredContent"]

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.request_id += 1
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        )
        if response is None or "error" in response:
            raise MCPClientError("MCP request failed")
        return response["result"]


class MCPToolAdapter:
    """SkillExecutor-compatible adapter backed exclusively by MCP calls."""

    def __init__(self, client: MCPClient | None = None, actor_user_id: int | None = None) -> None:
        self.client = client or MCPClient(actor_user_id=actor_user_id)

    def list(self) -> list[dict[str, Any]]:
        return self.client.list_tools()

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.call(name, arguments or {})
