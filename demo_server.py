"""Small Confluence-like MCP server used by the local demo."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from mcp.server import MCPServer


DOCUMENTS_PATH = Path(__file__).with_name("documents.json")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "our",
    "should", "the", "to", "we", "what", "when", "where", "which", "with",
}


def load_documents(path: Path = DOCUMENTS_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    normalized: list[str] = []
    for word in words:
        if word in STOP_WORDS:
            continue
        # Tiny, intentionally transparent stemmer for the demo corpus.
        for suffix in ("ing", "ies", "ied", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) > len(suffix) + 3:
                word = word[: -len(suffix)]
                break
        normalized.append(word)
    return normalized


def search_documents(
    query: str, limit: int = 5, documents: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Return deterministic lexical matches; Confluence performs this in real mode."""
    documents = documents or load_documents()
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    ranked: list[tuple[float, dict[str, Any]]] = []
    query_phrase = " ".join(query.lower().split())
    for doc in documents:
        title_tokens = _tokens(doc["title"])
        tag_tokens = _tokens(" ".join(doc.get("tags", [])))
        body_tokens = _tokens(doc["content"])
        title_set, tag_set, body_set = set(title_tokens), set(tag_tokens), set(body_tokens)

        score = 0.0
        for token in query_tokens:
            if token in title_set:
                score += 5.0
            if token in tag_set:
                score += 3.0
            if token in body_set:
                score += 1.0 + math.log1p(body_tokens.count(token))

        searchable = f"{doc['title']} {' '.join(doc.get('tags', []))} {doc['content']}".lower()
        if len(query_phrase) >= 5 and query_phrase in searchable:
            score += 8.0
        if score > 0:
            ranked.append((score, doc))

    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    results = []
    for score, doc in ranked[: max(1, min(limit, 5))]:
        results.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "url": doc["url"],
                "snippet": doc["content"][:280],
                "score": round(score, 3),
            }
        )
    return results


mcp = MCPServer(
    name="Demo Confluence",
    instructions="Read-only fictional engineering documentation for the knowledge assistant demo.",
)


@mcp.tool(
    description=(
        "Search the engineering knowledge base. Call this before get_page. "
        "Returns up to five page IDs, titles, URLs, and snippets ranked by relevance."
    )
)
def search_pages(query: str, limit: int = 5) -> dict[str, Any]:
    return {"query": query, "results": search_documents(query, limit)}


@mcp.tool(
    description=(
        "Retrieve one complete engineering page by ID from search_pages. "
        "Use this for pages needed to answer the user's question."
    )
)
def get_page(page_id: str) -> dict[str, Any]:
    for document in load_documents():
        if document["id"] == page_id:
            return document
    return {"error": f"Page not found: {page_id}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")

