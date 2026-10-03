from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .registry import ToolRegistry

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agentradar-readonly", "version": "1.0.0"}


class MCPServer:
    """Minimal MCP JSON-RPC stdio adapter over the internal Tool Registry."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None:  # MCP notifications do not receive responses.
            return None
        try:
            if request.get("jsonrpc") != "2.0":
                return self._rpc_error(request_id, -32600, "Invalid Request")
            if method == "initialize":
                return self._result(
                    request_id,
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": SERVER_INFO,
                    },
                )
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": self.registry.list()})
            if method == "tools/call":
                params = request.get("params") or {}
                call_args = (params.get("name", ""), params.get("arguments"))
                result = (
                    self.registry.call(*call_args, actor_id=params["actor_user_id"])
                    if params.get("actor_user_id") is not None
                    else self.registry.call(*call_args)
                )
                return self._result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, default=str, ensure_ascii=False),
                            }
                        ],
                        "structuredContent": result,
                        "isError": not result["ok"],
                    },
                )
            return self._rpc_error(request_id, -32601, "Method not found")
        except Exception:  # JSON-RPC boundary never leaks stack traces or secrets.
            return self._rpc_error(request_id, -32603, "Internal error")

    def serve(self, input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
        for line in input_stream:
            try:
                request = json.loads(line)
                response = self.handle(request)
            except (json.JSONDecodeError, TypeError):
                response = self._rpc_error(None, -32700, "Parse error")
            if response is not None:
                output_stream.write(json.dumps(response, default=str, ensure_ascii=False) + "\n")
                output_stream.flush()

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
