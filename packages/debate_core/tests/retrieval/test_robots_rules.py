"""robots.txt read by RFC 9309 alone: the longest matching rule decides, with `*` and `$`.

Every expected answer here is written by hand: from the RFC's own examples (§2.2.2, §2.2.3, §5.1,
§5.2), and for the cases where `urllib.robotparser` reads a file differently (PM ruling 2026-10-21).
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from importlib import resources

import pytest

from debate_core.retrieval.fetch_types import RobotsRefusalReason
from debate_core.retrieval.robots_rules import (
    ROBOTS_MAX_AGE,
    ROBOTS_MAX_BYTES,
    RobotsRules,
    robots_rules_expired,
)

TOKEN = "debate-research"
SITE = "https://news.example.org"


def refusal(rules: RobotsRules, path: str, token: str = TOKEN) -> RobotsRefusalReason | None:
    return rules.refusal_for(f"{SITE}{path}", product_token=token)


def rules_from(text: str) -> RobotsRules:
    return RobotsRules.from_response(200, text.encode())


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, None),
        (204, None),
        (400, None),
        (404, None),
        (410, None),
        (401, RobotsRefusalReason.ROBOTS_ACCESS_DENIED),
        (403, RobotsRefusalReason.ROBOTS_ACCESS_DENIED),
        (429, RobotsRefusalReason.ROBOTS_UNREACHABLE),
        (500, RobotsRefusalReason.ROBOTS_UNREACHABLE),
        (503, RobotsRefusalReason.ROBOTS_UNREACHABLE),
        (302, RobotsRefusalReason.ROBOTS_UNREACHABLE),
    ],
)
def test_each_status_of_robots_txt_has_its_reading(status: int, expected: RobotsRefusalReason | None) -> None:
    assert refusal(RobotsRules.from_response(status, b""), "/any/page") == expected


def test_a_disallowed_prefix_is_refused_and_the_rest_allowed() -> None:
    rules = rules_from("User-agent: *\nDisallow: /private/\n")
    assert refusal(rules, "/private/memo") is RobotsRefusalReason.DISALLOWED
    assert refusal(rules, "/public/memo") is None
    assert refusal(rules, "/private") is None


def test_the_longest_rule_wins_even_after_a_broader_allow() -> None:
    rules = rules_from("User-agent: *\nAllow: /\nDisallow: /archive/2026/\n")
    assert refusal(rules, "/archive/2026/budget") is RobotsRefusalReason.DISALLOWED
    assert refusal(rules, "/archive/2025/budget") is None


def test_an_allow_list_written_disallow_first_lets_the_allowed_path_through() -> None:
    """The stdlib stops at `Disallow: /`; RFC 9309's longer `Allow: /public/` wins."""
    rules = rules_from("User-agent: *\nDisallow: /\nAllow: /public/\n")
    assert refusal(rules, "/public/a") is None
    assert refusal(rules, "/private/a") is RobotsRefusalReason.DISALLOWED


RFC_9309_SIMPLE_EXAMPLE = """\
User-Agent: *
Disallow: *.gif$
Disallow: /example/
Allow: /publications/

User-Agent: foobot
Disallow:/
Allow:/example/page.html
Allow:/example/allowed.gif

User-Agent: barbot
User-Agent: bazbot
Disallow: /example/page.html

User-Agent: quxbot

EOF
"""
"""RFC 9309 §5.1, verbatim; its `EOF` line is the RFC's own end marker and parses as nothing."""


@pytest.mark.parametrize(
    ("token", "path", "refused"),
    [
        ("foobot", "/example/page.html", False),
        ("foobot", "/example/allowed.gif", False),
        ("foobot", "/example/other.html", True),
        ("foobot", "/publications/a", True),
        ("barbot", "/example/page.html", True),
        ("bazbot", "/example/page.html", True),
        ("barbot", "/example/other.html", False),
        ("barbot", "/x.gif", False),
        ("quxbot", "/example/page.html", False),
        ("quxbot", "/x.gif", False),
        ("otherbot", "/images/x.gif", True),
        ("otherbot", "/example/a", True),
        ("otherbot", "/publications/a", False),
        ("otherbot", "/index.html", False),
    ],
)
def test_rfc_9309_simple_example(token: str, path: str, refused: bool) -> None:
    rules = rules_from(RFC_9309_SIMPLE_EXAMPLE)
    assert (refusal(rules, path, token) is RobotsRefusalReason.DISALLOWED) is refused


@pytest.mark.parametrize(
    ("path", "refused"),
    [
        ("/example/page/", False),
        ("/example/page/allowed.html", False),
        ("/example/page/disallowed.gif", True),
    ],
)
def test_rfc_9309_longest_match_example(path: str, refused: bool) -> None:
    """RFC 9309 §5.2: the more specific Disallow wins over the shorter Allow."""
    rules = rules_from("User-Agent: foobot\nAllow: /example/page/\nDisallow: /example/page/disallowed.gif\n")
    assert (refusal(rules, path, "foobot") is RobotsRefusalReason.DISALLOWED) is refused


@pytest.mark.parametrize(
    ("rule", "path", "refused"),
    [
        ("/this/path/exactly$", "/this/path/exactly", True),
        ("/this/path/exactly$", "/this/path/exactly/more", False),
        ("/this/*/exactly", "/this/any/thing/exactly", True),
        ("/foo/bar?baz=https://foo.bar", "/foo/bar?baz=https%3A%2F%2Ffoo.bar", True),
        ("/foo/bar/%E3%83%84", "/foo/bar/\u30c4", True),
        ("/foo/bar/%62%61%7A", "/foo/bar/baz", True),
    ],
)
def test_rfc_9309_special_characters_and_percent_encoding(rule: str, path: str, refused: bool) -> None:
    """RFC 9309 §2.2.3's `$` and `*` examples and §2.2.2's percent-encoding table."""
    rules = rules_from(f"User-agent: *\nDisallow: {rule}\n")
    assert (refusal(rules, path) is RobotsRefusalReason.DISALLOWED) is refused


def test_a_group_matched_only_by_part_of_the_token_does_not_apply() -> None:
    """RFC 9309 §2.2.1 matches the whole product token; the stdlib would apply `debate` to us."""
    rules = rules_from("User-agent: debate\nDisallow: /\n")
    assert refusal(rules, "/anything") is None


def test_robots_rules_expire_after_24_hours() -> None:
    """RFC 9309 §2.4: a crawler should not use a cached robots.txt for more than 24 hours."""
    read_at = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
    assert timedelta(hours=24) == ROBOTS_MAX_AGE
    assert not robots_rules_expired(read_at, now=read_at + timedelta(hours=23, minutes=59, seconds=59))
    assert robots_rules_expired(read_at, now=read_at + timedelta(hours=24))


def test_an_allow_list_written_allow_first_lets_the_allowed_path_through() -> None:
    rules = rules_from("User-agent: *\nAllow: /public/\nDisallow: /\n")
    assert refusal(rules, "/public/a") is None
    assert refusal(rules, "/other") is RobotsRefusalReason.DISALLOWED


@pytest.mark.parametrize(
    ("pattern", "path", "refused"),
    [
        ("/*.pdf$", "/reports/annual.pdf", True),
        ("/*.pdf$", "/reports/annual.pdf?download=1", False),
        ("/*.pdf$", "/reports/annual.pdfx", False),
        ("/*?session=", "/a?session=7", True),
        ("/*?session=", "/a?page=7", False),
        ("/drafts*/old", "/drafts-2026/old/x", True),
    ],
)
def test_wildcards_are_understood(pattern: str, path: str, refused: bool) -> None:
    rules = rules_from(f"User-agent: *\nDisallow: {pattern}\n")
    assert (refusal(rules, path) is RobotsRefusalReason.DISALLOWED) is refused


def test_a_group_naming_this_crawler_replaces_the_star_group() -> None:
    rules = rules_from("User-agent: *\nDisallow: /\n\nUser-agent: Debate-Research\nDisallow: /drafts/\n")
    assert refusal(rules, "/2026/article") is None
    assert refusal(rules, "/drafts/x") is RobotsRefusalReason.DISALLOWED


def test_groups_naming_this_crawler_twice_are_merged() -> None:
    rules = rules_from(
        "User-agent: debate-research\nDisallow: /a/\n\nUser-agent: other\nDisallow: /\n\n"
        "User-agent: debate-research\nDisallow: /b/\n"
    )
    assert refusal(rules, "/a/x") is RobotsRefusalReason.DISALLOWED
    assert refusal(rules, "/b/x") is RobotsRefusalReason.DISALLOWED
    assert refusal(rules, "/c/x") is None


def test_comments_and_an_empty_disallow_mean_nothing() -> None:
    rules = rules_from("# the whole site is open\nUser-agent: *  # everyone\nDisallow:\n")
    assert refusal(rules, "/anything") is None


def test_percent_encoding_is_compared_in_one_form() -> None:
    rules = rules_from("User-agent: *\nDisallow: /caf%C3%A9/\n")
    assert refusal(rules, "/café/menu") is RobotsRefusalReason.DISALLOWED


def test_a_robots_txt_past_the_limit_is_cut_at_its_last_whole_line() -> None:
    head = b"User-agent: *\nDisallow: /private/\n"
    body = head + b"#" * (ROBOTS_MAX_BYTES - len(head) - 5) + b"\nDisallow: /\n"
    rules = RobotsRules.from_response(200, body)
    assert refusal(rules, "/private/x") is RobotsRefusalReason.DISALLOWED
    assert refusal(rules, "/open") is None


def test_urllib_robotparser_takes_no_part_in_the_decision() -> None:
    """PM ruling 2026-10-21: RFC 9309 alone decides; the stdlib parser is wrong in both directions."""
    source = (resources.files("debate_core.retrieval") / "robots_rules.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert not any(name.startswith("urllib.robotparser") for name in imported)


def test_an_allow_and_a_disallow_of_equal_length_resolve_to_allow() -> None:
    """RFC 9309 §2.2.2: the least restrictive of two equally specific rules. `/a*` and `/ab` both
    match `/abc` and are both three characters; the stdlib cannot read the wildcard, so only the
    RFC reading decides."""
    rules = rules_from("User-agent: *\nDisallow: /a*\nAllow: /ab\n")
    assert refusal(rules, "/abc") is None
    assert refusal(rules, "/axe") is RobotsRefusalReason.DISALLOWED
