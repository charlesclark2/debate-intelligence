"""robots.txt read by `urllib.robotparser` and by RFC 9309, and a URL needs both to allow it."""

from __future__ import annotations

import ast
from importlib import resources

import pytest

from debate_core.retrieval.fetch_types import RobotsRefusalReason
from debate_core.retrieval.robots_rules import ROBOTS_MAX_BYTES, RobotsRules

USER_AGENT = "debate-research/1.3.0 (+https://example.org/debate-contact)"
TOKEN = "debate-research"
SITE = "https://news.example.org"


def refusal(rules: RobotsRules, path: str) -> RobotsRefusalReason | None:
    return rules.refusal_for(f"{SITE}{path}", user_agent=USER_AGENT, product_token=TOKEN)


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


def test_an_allow_list_written_disallow_first_refuses_as_the_stdlib_does() -> None:
    rules = rules_from("User-agent: *\nDisallow: /\nAllow: /public/\n")
    assert refusal(rules, "/public/a") is RobotsRefusalReason.DISALLOWED


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


def test_robotparser_is_only_ever_handed_text() -> None:
    """`RobotFileParser.read()` would fetch through urllib, past the fetcher's own client and rules."""
    source = (resources.files("debate_core.retrieval") / "robots_rules.py").read_text(encoding="utf-8")
    called = {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "parse" in called
    assert not called & {"read", "set_url"}


def test_an_allow_and_a_disallow_of_equal_length_resolve_to_allow() -> None:
    """RFC 9309 §2.2.2: the least restrictive of two equally specific rules. `/a*` and `/ab` both
    match `/abc` and are both three characters; the stdlib cannot read the wildcard, so only the
    RFC reading decides."""
    rules = rules_from("User-agent: *\nDisallow: /a*\nAllow: /ab\n")
    assert refusal(rules, "/abc") is None
    assert refusal(rules, "/axe") is RobotsRefusalReason.DISALLOWED
