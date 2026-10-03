from django.conf import settings
from django.core.management.base import BaseCommand

from apps.tools.mcp import MCPServer


class Command(BaseCommand):
    help = "Run the read-only AgentRadar MCP server over stdio."

    def handle(self, *args, **options):
        if settings.MCP_TRANSPORT != "stdio":
            raise ValueError("Sprint 11 supports only the stdio MCP transport")
        MCPServer().serve()
