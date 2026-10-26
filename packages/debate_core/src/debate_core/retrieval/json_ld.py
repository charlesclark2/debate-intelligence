"""A page's JSON-LD as plain nodes: the one walk every reader of a page's schema.org markup shares.

Three readers look at a page's JSON-LD: the access classifier (:mod:`debate_core.retrieval.access`,
v1-e04-t03) for a declared article length, the HTML extractor (`debate_core.integrations.html_extractor`,
v1-e04-t04) for its paywall marker and metadata hints, and the citation harvester
(:mod:`debate_core.retrieval.citation_harvest`, v1-e06-t01) for cite fields. Each finds the
`<script type="application/ld+json">` blocks with its own HTML parser and hands their text here.
Until v1-e06-t01 the first two carried a copy each of this walk.

:func:`json_ld_nodes` parses each block and yields every top-level node, then the members of its
`@graph`, in page order. A block that is not JSON is skipped, as is anything in it that is not an
object. Nothing deeper is walked: an `author` or `publisher` inside a node is that node's business.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any, cast

__all__ = ["json_ld_nodes", "json_ld_types"]


def json_ld_nodes(blocks: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Every top-level JSON-LD node in `blocks`, `@graph` members included; non-JSON blocks skipped."""
    for block in blocks:
        try:
            parsed: object = json.loads(block)
        except ValueError:
            continue
        for node in cast(list[object], parsed) if isinstance(parsed, list) else [parsed]:
            if isinstance(node, dict):
                typed = cast(dict[str, Any], node)
                yield typed
                graph = typed.get("@graph")
                if isinstance(graph, list):
                    members = cast(list[object], graph)
                    yield from (
                        cast(dict[str, Any], member) for member in members if isinstance(member, dict)
                    )


def json_ld_types(node: dict[str, Any]) -> frozenset[str]:
    """The node's `@type`, a string or a list of strings, as a set; empty when it declares none."""
    declared = node.get("@type")
    if isinstance(declared, str):
        return frozenset({declared})
    if isinstance(declared, list):
        return frozenset(item for item in cast(list[object], declared) if isinstance(item, str))
    return frozenset()
