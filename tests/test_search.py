from demo_server import load_documents, search_documents


def test_search_is_deterministic_and_limited() -> None:
    documents = load_documents()
    first = search_documents("production canary rollout", limit=3, documents=documents)
    second = search_documents("production canary rollout", limit=3, documents=documents)
    assert first == second
    assert len(first) <= 3
    assert first[0]["id"] == "eng-deploy-001"


def test_search_returns_empty_for_unknown_topic() -> None:
    assert search_documents("cafeteria vegan menu parking permit") == []

