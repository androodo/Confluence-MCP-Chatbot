"""Reusable MCP connection and read-only tool adapter."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client


READ_ONLY_PREFIXES = ("search", "get", "list", "discover", "executeread")


class MCPConnection:
    """Connect to either the local stdio server or a remote HTTP MCP server."""

    def __init__(
        self,
        mode: str = "demo",
        remote_url: str | None = None,
        auth_header: str | None = None,
        allowed_tools: set[str] | None = None,
    ) -> None:
        self.mode = mode
        self.remote_url = remote_url
        self.auth_header = auth_header
        self.allowed_tools = allowed_tools
        self._stack = AsyncExitStack()
        self.client: Client | None = None

    @classmethod
    def from_env(cls) -> "MCPConnection":
        raw_allowlist = os.getenv("MCP_ALLOWED_TOOLS", "")
        allowlist = {name.strip() for name in raw_allowlist.split(",") if name.strip()}
        return cls(
            mode=os.getenv("MCP_MODE", "demo").lower(),
            remote_url=os.getenv("MCP_REMOTE_URL"),
            auth_header=os.getenv("MCP_AUTH_HEADER"),
            allowed_tools=allowlist or None,
        )

    async def __aenter__(self) -> "MCPConnection":
        if self.mode == "demo":
            server_path = Path(__file__).with_name("demo_server.py")
            target: Any = StdioServerParameters(
                command=sys.executable,
                args=[str(server_path)],
                cwd=str(server_path.parent),
            )
        elif self.mode == "remote":
            if not self.remote_url:
                raise ValueError("MCP_REMOTE_URL is required when MCP_MODE=remote")
            if self.auth_header:
                http_client = await self._stack.enter_async_context(
                    httpx2.AsyncClient(
                        headers={"Authorization": self.auth_header},
                        timeout=httpx2.Timeout(30, read=300),
                    )
                )
                target = streamable_http_client(
                    self.remote_url, http_client=http_client
                )
            else:
                target = self.remote_url
        else:
            raise ValueError("MCP_MODE must be 'demo' or 'remote'")

        self.client = await self._stack.enter_async_context(Client(target))
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    def _is_allowed(self, name: str) -> bool:
        if self.allowed_tools is not None:
            return name in self.allowed_tools
        normalized = name.lower().replace("_", "")
        return normalized.startswith(READ_ONLY_PREFIXES)

    async def list_tools(self) -> list[Any]:
        if self.client is None:
            raise RuntimeError("MCP connection is not open")
        tools: list[Any] = []
        cursor: str | None = None
        for _ in range(20):  # Bound pagination even for a misbehaving remote server.
            result = await self.client.list_tools(cursor=cursor)
            tools.extend(tool for tool in result.tools if self._is_allowed(tool.name))
            cursor = result.next_cursor
            if not cursor:
                break
        return tools

    async def openai_tools(self) -> list[dict[str, Any]]:
        tools = await self.list_tools()
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description or f"Call MCP tool {tool.name}",
                "parameters": tool.input_schema,
                "strict": False,
            }
            for tool in tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if self.client is None:
            raise RuntimeError("MCP connection is not open")
        if not self._is_allowed(name):
            return json.dumps({"error": f"Tool is not allowed: {name}"})

        result = await self.client.call_tool(name, arguments)
        if result.is_error:
            error_text = "\n".join(
                getattr(item, "text", str(item)) for item in result.content
            )
            return json.dumps({"error": error_text or "MCP tool call failed"})
        if result.structured_content is not None:
            return json.dumps(result.structured_content, ensure_ascii=False)
        return "\n".join(
            getattr(item, "text", str(item)) for item in result.content
        )

