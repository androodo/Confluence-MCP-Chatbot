import json

import pytest

from mcp_client import MCPConnection


@pytest.mark.asyncio
async def test_demo_server_discovery_and_calls_use_mcp() -> None:
    async with MCPConnection(mode="demo") as connection:
        tools = await connection.list_tools()
        assert {tool.name for tool in tools} == {"search_pages", "get_page"}

        search = json.loads(
            await connection.call_tool(
                "search_pages", {"query": "CI pipeline failed test report", "limit": 3}
            )
        )
        assert search["results"][0]["id"] == "eng-ci-001"

        page = json.loads(
            await connection.call_tool("get_page", {"page_id": "eng-ci-001"})
        )
        assert page["title"] == "CI Pipeline and Failed Test Reporting"
        assert page["url"].startswith("https://")


@pytest.mark.asyncio
async def test_disallowed_tool_is_never_invoked() -> None:
    async with MCPConnection(mode="demo") as connection:
        result = json.loads(await connection.call_tool("delete_page", {"id": "x"}))
        assert "not allowed" in result["error"]

