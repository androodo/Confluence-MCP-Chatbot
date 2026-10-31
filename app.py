"""Terminal chatbot using OpenAI tool calling over a reusable MCP connection."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import AsyncOpenAI

from mcp_client import MCPConnection
from retrieval import ContextBuilder


TOOL_INSTRUCTIONS = """You are retrieving internal engineering documentation.
Use only the supplied read-only MCP tools. Search first, then retrieve the full
content of the most relevant pages needed to answer the question. Retrieve no
more than five pages. Prefer a small number of precise tool calls. Do not invent
page IDs or answer from general knowledge. If search finds nothing useful, stop.
"""

ANSWER_INSTRUCTIONS = """You are an engineering knowledge assistant. Answer only
from the supplied DOCUMENTATION. Give a concise, direct answer. End with a
'Sources' list containing the exact document title and URL for each source used.
Never invent a title, URL, policy, or technical detail. If the documentation does
not support an answer, say: 'The retrieved documentation is insufficient to
answer this question.' You may briefly state what information is missing.
"""


@dataclass
class Answer:
    text: str
    elapsed_seconds: float
    page_count: int
    tool_calls: int


class KnowledgeAssistant:
    def __init__(self, openai_client: AsyncOpenAI, mcp: MCPConnection) -> None:
        self.openai = openai_client
        self.mcp = mcp
        self.model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
        self.max_tool_rounds = int(os.getenv("MAX_TOOL_ROUNDS", "4"))
        self.max_tool_calls = int(os.getenv("MAX_TOOL_CALLS", "8"))
        self.max_pages = int(os.getenv("MAX_PAGES", "5"))
        self.max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "24000"))
        self.history: list[tuple[str, str]] = []

    def _history_text(self) -> str:
        turns = self.history[-6:]
        if not turns:
            return "(none)"
        return "\n".join(f"{role}: {text}" for role, text in turns)

    async def ask(self, question: str) -> Answer:
        started = time.perf_counter()
        collector = ContextBuilder(self.max_pages, self.max_context_chars)
        tools = await self.mcp.openai_tools()
        if not tools:
            raise RuntimeError("The MCP server exposed no allowed read-only tools")

        prompt = (
            f"Limited recent conversation:\n{self._history_text()}\n\n"
            f"Current question: {question}"
        )
        response = await self.openai.responses.create(
            model=self.model,
            instructions=TOOL_INSTRUCTIONS,
            input=prompt,
            tools=tools,
            tool_choice="auto",
            max_output_tokens=600,
        )

        tool_call_count = 0
        for _ in range(self.max_tool_rounds):
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls or tool_call_count >= self.max_tool_calls:
                break

            outputs: list[dict[str, str]] = []
            for call in calls:
                if tool_call_count >= self.max_tool_calls:
                    break
                if not collector.can_call(call.name):
                    raw = json.dumps({"error": "Five-page retrieval limit reached"})
                else:
                    try:
                        arguments = json.loads(call.arguments or "{}")
                        raw = await self.mcp.call_tool(call.name, arguments)
                    except (json.JSONDecodeError, TypeError) as exc:
                        raw = json.dumps({"error": f"Invalid tool arguments: {exc}"})
                bounded = collector.record(call.name, raw)
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": bounded,
                    }
                )
                tool_call_count += 1

            if not outputs:
                break
            response = await self.openai.responses.create(
                model=self.model,
                instructions=TOOL_INSTRUCTIONS,
                previous_response_id=response.id,
                input=outputs,
                tools=tools,
                tool_choice="auto",
                max_output_tokens=600,
            )

        context = collector.build()
        final_prompt = (
            f"Question: {question}\n\n"
            f"DOCUMENTATION:\n{context if context else '(No full pages were retrieved.)'}"
        )
        final_response = await self.openai.responses.create(
            model=self.model,
            instructions=ANSWER_INSTRUCTIONS,
            input=final_prompt,
            max_output_tokens=600,
        )
        answer_text = final_response.output_text.strip()
        self.history.extend((("User", question), ("Assistant", answer_text)))
        self.history = self.history[-6:]
        return Answer(
            text=answer_text,
            elapsed_seconds=time.perf_counter() - started,
            page_count=len(collector.pages),
            tool_calls=tool_call_count,
        )


async def main() -> None:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing. Copy .env.example to .env and add it.")

    print("Confluence MCP Knowledge Assistant")
    print("Ask an engineering question, or type 'quit'.")
    async with MCPConnection.from_env() as mcp:
        assistant = KnowledgeAssistant(AsyncOpenAI(), mcp)
        while True:
            try:
                question = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if question.lower() in {"quit", "exit", "q"}:
                break
            if not question:
                continue
            try:
                answer = await assistant.ask(question)
                print(f"\nAssistant: {answer.text}")
                print(
                    f"\n[{answer.elapsed_seconds:.2f}s; "
                    f"{answer.tool_calls} MCP calls; {answer.page_count} pages]"
                )
            except Exception as exc:
                print(f"\nError: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

