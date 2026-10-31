"""Bounded evidence collection and small deterministic evaluation helpers."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class Page:
    id: str
    title: str
    url: str
    content: str


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _page_from_dict(value: dict[str, Any]) -> Page | None:
    content = value.get("content") or value.get("body") or value.get("text")
    title = value.get("title") or value.get("name")
    url = value.get("url") or value.get("webUrl") or value.get("web_url")
    page_id = value.get("id") or value.get("pageId") or value.get("contentId")
    if isinstance(content, dict):
        content = content.get("value") or content.get("text")
    if not all(isinstance(item, (str, int)) and str(item).strip() for item in (content, title, page_id)):
        return None
    return Page(str(page_id), str(title), str(url or ""), str(content))


class ContextBuilder:
    """Collect unique full pages and keep all tool output within one character budget."""

    def __init__(self, max_pages: int = 5, max_chars: int = 24_000) -> None:
        self.max_pages = max_pages
        self.max_chars = max_chars
        self.pages: OrderedDict[str, Page] = OrderedDict()
        self.tool_chars = 0
        self.page_read_calls = 0

    @staticmethod
    def is_search_tool(name: str) -> bool:
        lowered = name.lower()
        return "search" in lowered or lowered in {"discover", "list_pages"}

    def can_call(self, name: str) -> bool:
        return self.is_search_tool(name) or self.page_read_calls < self.max_pages

    def record(self, name: str, output: str) -> str:
        """Record evidence and return a bounded version to send back to the LLM."""
        if not self.is_search_tool(name):
            self.page_read_calls += 1
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = None

        if parsed is not None:
            for candidate in _walk_dicts(parsed):
                page = _page_from_dict(candidate)
                if page is None:
                    continue
                key = page.id or page.url
                if key not in self.pages and len(self.pages) < self.max_pages:
                    self.pages[key] = page

        remaining = max(0, self.max_chars - self.tool_chars)
        bounded = output[:remaining]
        if len(output) > remaining:
            marker = "\n[tool output truncated by context budget]"
            bounded = (output[: max(0, remaining - len(marker))] + marker)[:remaining]
        self.tool_chars += len(bounded)
        return bounded

    def build(self) -> str:
        if not self.pages:
            return ""
        sections: list[str] = []
        used = 0
        for page in self.pages.values():
            separator = "\n\n---\n\n" if sections else ""
            header = f"[{page.id}] {page.title}\nSource: {page.url or 'URL not supplied'}\n"
            available = self.max_chars - used - len(separator) - len(header)
            if available <= 0:
                break
            body = page.content[:available]
            sections.append(separator + header + body)
            used += len(separator) + len(header) + len(body)
        return "".join(sections)


def has_source_attribution(answer: str, pages: Iterable[Page]) -> bool:
    urls = [page.url for page in pages if page.url]
    return bool(urls) and any(url in answer for url in urls)


def states_insufficient_context(answer: str) -> bool:
    lowered = answer.lower()
    phrases = (
        "insufficient documentation",
        "documentation is insufficient",
        "not enough information",
        "could not find",
        "cannot answer from",
    )
    return any(phrase in lowered for phrase in phrases)

