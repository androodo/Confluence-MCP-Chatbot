import json

from retrieval import ContextBuilder, Page, has_source_attribution, states_insufficient_context


def _page(page_id: str, content: str = "evidence") -> str:
    return json.dumps(
        {
            "id": page_id,
            "title": f"Page {page_id}",
            "url": f"https://example.test/{page_id}",
            "content": content,
        }
    )


def test_context_deduplicates_pages_and_enforces_page_limit() -> None:
    context = ContextBuilder(max_pages=2, max_chars=10_000)
    context.record("get_page", _page("one"))
    context.record("get_page", _page("one"))
    context.record("get_page", _page("two"))
    context.record("get_page", _page("three"))

    assert list(context.pages) == ["one", "two"]
    assert "Page one" in context.build()
    assert "Page three" not in context.build()


def test_tool_output_and_context_are_bounded() -> None:
    context = ContextBuilder(max_pages=1, max_chars=120)
    bounded = context.record("get_page", _page("one", "x" * 500))
    assert len(bounded) < 180
    assert "truncated" in bounded
    assert len(context.build()) <= 120


def test_grounding_checks() -> None:
    page = Page("one", "Page one", "https://example.test/one", "evidence")
    assert has_source_attribution("See https://example.test/one", [page])
    assert not has_source_attribution("No citation", [page])
    assert states_insufficient_context(
        "The retrieved documentation is insufficient to answer this question."
    )

