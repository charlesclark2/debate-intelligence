"""The shared JSON-LD walk (v1-e06-t01): top-level nodes and `@graph` members, in page order."""

from __future__ import annotations

from debate_core.retrieval.json_ld import json_ld_nodes, json_ld_types


def test_nodes_come_in_page_order_with_graph_members_after_their_node() -> None:
    blocks = (
        '{"@type": "WebSite", "@graph": [{"@type": "Person"}, "not a node", {"@type": "Article"}]}',
        '[{"@type": "BreadcrumbList"}, 7, {"@type": "Report"}]',
    )

    types = [node.get("@type") for node in json_ld_nodes(blocks)]

    assert types == ["WebSite", "Person", "Article", "BreadcrumbList", "Report"]


def test_a_block_that_is_not_json_is_skipped_and_the_rest_are_read() -> None:
    blocks = ("{not json", '"a bare string"', '{"@type": "NewsArticle"}')

    assert [node["@type"] for node in json_ld_nodes(blocks)] == ["NewsArticle"]


def test_nested_nodes_are_not_walked() -> None:
    """An author inside an article is the article's business, not a node of its own."""
    blocks = ('{"@type": "Article", "author": {"@type": "Person", "name": "A"}}',)

    assert len(list(json_ld_nodes(blocks))) == 1


def test_types_read_a_string_a_list_or_nothing() -> None:
    assert json_ld_types({"@type": "Article"}) == {"Article"}
    assert json_ld_types({"@type": ["Article", 3, "NewsArticle"]}) == {"Article", "NewsArticle"}
    assert json_ld_types({"@type": 3}) == frozenset()
    assert json_ld_types({}) == frozenset()
