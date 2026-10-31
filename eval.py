"""Deterministic MCP retrieval evaluation; makes no OpenAI API calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from mcp_client import MCPConnection
from retrieval import Page, has_source_attribution, states_insufficient_context


QUESTIONS_PATH = Path(__file__).with_name("eval_questions.json")


async def evaluate(path: Path = QUESTIONS_PATH) -> int:
    cases = json.loads(path.read_text(encoding="utf-8"))
    hit_count = 0
    recalled = 0
    expected_total = 0
    latencies: list[float] = []

    async with MCPConnection(mode="demo") as mcp:
        for case in cases:
            started = time.perf_counter()
            raw = await mcp.call_tool(
                "search_pages", {"query": case["question"], "limit": 3}
            )
            latencies.append(time.perf_counter() - started)
            result = json.loads(raw)
            actual = [item["id"] for item in result.get("results", [])[:3]]
            expected = set(case["expected_pages"])
            found = expected.intersection(actual)
            hit_count += bool(found)
            recalled += len(found)
            expected_total += len(expected)
            status = "PASS" if found else "MISS"
            print(f"{status:4}  {case['question']}  -> {actual}")

        missing_raw = await mcp.call_tool(
            "search_pages", {"query": "cafeteria vegan menu parking permit", "limit": 3}
        )
        missing_results = json.loads(missing_raw).get("results", [])

    total = len(cases)
    hit_at_3 = hit_count / total if total else 0.0
    recall_at_3 = recalled / expected_total if expected_total else 0.0
    sorted_latencies = sorted(latencies)
    p95_index = max(0, int(len(sorted_latencies) * 0.95) - 1)

    sample_page = Page("sample", "Sample", "https://example.test/page", "text")
    attribution_ok = has_source_attribution(
        "Source: https://example.test/page", [sample_page]
    )
    insufficient_ok = not missing_results and states_insufficient_context(
        "The retrieved documentation is insufficient to answer this question."
    )

    print("\nSummary")
    print(f"Questions: {total}")
    print(f"Hit@3: {hit_count}/{total} = {hit_at_3:.3f}")
    print(f"Recall@3: {recalled}/{expected_total} = {recall_at_3:.3f}")
    print(f"Mean MCP search latency: {statistics.mean(latencies) * 1000:.1f} ms")
    print(f"P95 MCP search latency: {sorted_latencies[p95_index] * 1000:.1f} ms")
    print(f"Source attribution check: {'PASS' if attribution_ok else 'FAIL'}")
    print(f"Insufficient-context check: {'PASS' if insufficient_ok else 'FAIL'}")
    return 0 if hit_count == total and attribution_ok and insufficient_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(evaluate(args.questions)))


if __name__ == "__main__":
    main()

