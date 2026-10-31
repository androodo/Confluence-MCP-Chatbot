from types import SimpleNamespace

import pytest

from app import KnowledgeAssistant
from mcp_client import MCPConnection


class FakeResponses:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = [
                SimpleNamespace(
                    type="function_call",
                    name="search_pages",
                    arguments='{"query":"CI failed test reporting","limit":3}',
                    call_id="search-1",
                )
            ]
            return SimpleNamespace(id="response-1", output=output, output_text="")
        if self.calls == 2:
            output = [
                SimpleNamespace(
                    type="function_call",
                    name="get_page",
                    arguments='{"page_id":"eng-ci-001"}',
                    call_id="page-1",
                )
            ]
            return SimpleNamespace(id="response-2", output=output, output_text="")
        if self.calls == 3:
            return SimpleNamespace(id="response-3", output=[], output_text="ready")
        assert "DOCUMENTATION" in kwargs["input"]
        assert "CI Pipeline and Failed Test Reporting" in kwargs["input"]
        return SimpleNamespace(
            id="response-4",
            output=[],
            output_text=(
                "CI publishes merged JUnit results.\n\nSources\n"
                "- CI Pipeline and Failed Test Reporting: "
                "https://confluence.demo.local/display/ENG/CI+Pipeline+Failed+Tests"
            ),
        )


@pytest.mark.asyncio
async def test_tool_loop_retrieves_over_mcp_then_answers_from_context() -> None:
    fake_openai = SimpleNamespace(responses=FakeResponses())
    async with MCPConnection(mode="demo") as mcp:
        assistant = KnowledgeAssistant(fake_openai, mcp)
        result = await assistant.ask("How are failed CI tests reported?")

    assert result.tool_calls == 2
    assert result.page_count == 1
    assert "CI Pipeline and Failed Test Reporting" in result.text
    assert fake_openai.responses.calls == 4
