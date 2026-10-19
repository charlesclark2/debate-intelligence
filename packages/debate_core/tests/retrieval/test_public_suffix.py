"""Registrable domains from the bundled Public Suffix List snapshot (`v1-e04-t01`, ac3's same-site test).

The vectors are the Public Suffix List project's own, transcribed from `tests/test_psl.txt` at the
commit the bundled snapshot was taken from (52b71b3c, dedicated to the public domain). Each
`checkPublicSuffix(domain, expected)` line is one row; the Unicode rows expect the punycoded
answers the same file gives, because `registrable_domain` answers in ASCII.
"""

from __future__ import annotations

import hashlib
from importlib import resources

import pytest

from debate_core.retrieval.public_suffix import (
    PUBLIC_SUFFIX_LIST_FILE,
    PUBLIC_SUFFIX_LIST_HASH_FILE,
    bundled_public_suffix_rules,
    parse_public_suffix_list,
    registrable_domain,
)

PSL_PROJECT_VECTORS = [
    # Mixed case.
    ("COM", None),
    ("example.COM", "example.com"),
    ("WwW.example.COM", "example.com"),
    # Leading dot.
    (".com", None),
    (".example", None),
    (".example.com", None),
    (".example.example", None),
    # Unlisted TLD.
    ("example", None),
    ("example.example", "example.example"),
    ("b.example.example", "example.example"),
    ("a.b.example.example", "example.example"),
    # TLD with only 1 rule.
    ("biz", None),
    ("domain.biz", "domain.biz"),
    ("b.domain.biz", "domain.biz"),
    ("a.b.domain.biz", "domain.biz"),
    # TLD with some 2-level rules.
    ("com", None),
    ("example.com", "example.com"),
    ("b.example.com", "example.com"),
    ("a.b.example.com", "example.com"),
    ("uk.com", None),
    ("example.uk.com", "example.uk.com"),
    ("b.example.uk.com", "example.uk.com"),
    ("a.b.example.uk.com", "example.uk.com"),
    ("test.ac", "test.ac"),
    # TLD with only 1 (wildcard) rule.
    ("mm", None),
    ("c.mm", None),
    ("b.c.mm", "b.c.mm"),
    ("a.b.c.mm", "b.c.mm"),
    # More complex TLD.
    ("jp", None),
    ("test.jp", "test.jp"),
    ("www.test.jp", "test.jp"),
    ("ac.jp", None),
    ("test.ac.jp", "test.ac.jp"),
    ("www.test.ac.jp", "test.ac.jp"),
    ("kyoto.jp", None),
    ("test.kyoto.jp", "test.kyoto.jp"),
    ("ide.kyoto.jp", None),
    ("b.ide.kyoto.jp", "b.ide.kyoto.jp"),
    ("a.b.ide.kyoto.jp", "b.ide.kyoto.jp"),
    ("c.kobe.jp", None),
    ("b.c.kobe.jp", "b.c.kobe.jp"),
    ("a.b.c.kobe.jp", "b.c.kobe.jp"),
    ("city.kobe.jp", "city.kobe.jp"),
    ("www.city.kobe.jp", "city.kobe.jp"),
    # TLD with a wildcard rule and exceptions.
    ("ck", None),
    ("test.ck", None),
    ("b.test.ck", "b.test.ck"),
    ("a.b.test.ck", "b.test.ck"),
    ("www.ck", "www.ck"),
    ("www.www.ck", "www.ck"),
    # US K12.
    ("us", None),
    ("test.us", "test.us"),
    ("www.test.us", "test.us"),
    ("ak.us", None),
    ("test.ak.us", "test.ak.us"),
    ("www.test.ak.us", "test.ak.us"),
    ("k12.ak.us", None),
    ("test.k12.ak.us", "test.k12.ak.us"),
    ("www.test.k12.ak.us", "test.k12.ak.us"),
    # IDN labels, answered punycoded.
    ("食狮.com.cn", "xn--85x722f.com.cn"),
    ("食狮.公司.cn", "xn--85x722f.xn--55qx5d.cn"),
    ("www.食狮.公司.cn", "xn--85x722f.xn--55qx5d.cn"),
    ("shishi.公司.cn", "shishi.xn--55qx5d.cn"),
    ("公司.cn", None),
    ("食狮.中国", "xn--85x722f.xn--fiqs8s"),
    ("www.食狮.中国", "xn--85x722f.xn--fiqs8s"),
    ("shishi.中国", "shishi.xn--fiqs8s"),
    ("中国", None),
    # Same as above, but punycoded.
    ("xn--85x722f.com.cn", "xn--85x722f.com.cn"),
    ("xn--85x722f.xn--55qx5d.cn", "xn--85x722f.xn--55qx5d.cn"),
    ("www.xn--85x722f.xn--55qx5d.cn", "xn--85x722f.xn--55qx5d.cn"),
    ("shishi.xn--55qx5d.cn", "shishi.xn--55qx5d.cn"),
    ("xn--55qx5d.cn", None),
    ("xn--85x722f.xn--fiqs8s", "xn--85x722f.xn--fiqs8s"),
    ("www.xn--85x722f.xn--fiqs8s", "xn--85x722f.xn--fiqs8s"),
    ("shishi.xn--fiqs8s", "shishi.xn--fiqs8s"),
    ("xn--fiqs8s", None),
]


@pytest.mark.parametrize(("host", "expected"), PSL_PROJECT_VECTORS)
def test_the_public_suffix_list_projects_vectors(host: str, expected: str | None) -> None:
    assert registrable_domain(host) == expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        pytest.param("www.theguardian.com", "theguardian.com", id="news"),
        pytest.param("www.bbc.co.uk", "bbc.co.uk", id="two-label-suffix"),
        pytest.param("www.supremecourt.gov", "supremecourt.gov", id="gov"),
        pytest.param("alice.github.io", "alice.github.io", id="private-section-suffix"),
        pytest.param("github.io", None, id="private-section-suffix-itself"),
        pytest.param("www-nytimes-com.cdn.ampproject.org", "ampproject.org", id="amp-cache"),
        pytest.param("www.example.com.", "example.com", id="trailing-dot"),
        pytest.param("192.0.2.10", None, id="ipv4"),
        pytest.param("[2001:db8::1]", None, id="ipv6-bracketed"),
        pytest.param("2001:db8::1", None, id="ipv6"),
        pytest.param("", None, id="empty"),
        pytest.param("example..com", None, id="empty-label"),
    ],
)
def test_hosts_the_canonicalizer_asks_about(host: str, expected: str | None) -> None:
    assert registrable_domain(host) == expected


PACKAGE = resources.files("debate_core.retrieval")


def test_the_bundled_snapshot_matches_its_pinned_hash() -> None:
    """The file changes only with its hash, by the refresh command in the module docstring."""
    data = PACKAGE.joinpath(PUBLIC_SUFFIX_LIST_FILE).read_bytes()
    recorded = PACKAGE.joinpath(PUBLIC_SUFFIX_LIST_HASH_FILE).read_text(encoding="ascii")
    assert recorded == f"{hashlib.sha256(data).hexdigest()}  public_suffix_list.dat\n"


def test_the_bundled_snapshot_names_its_version_and_commit() -> None:
    """Read from the list's own header, so a refresh cannot leave a stale copy of either in code."""
    rules = bundled_public_suffix_rules()
    assert rules.version == "2026-10-17_18-52-06_UTC"
    assert rules.commit == "52b71b3c4576ff77450cc7ebcfc7f34a916af3f9"


def test_the_bundled_snapshot_holds_both_sections() -> None:
    rules = bundled_public_suffix_rules()
    assert {"com", "co.uk", "github.io", "blogspot.com"} <= rules.exact
    assert {"ck", "kawasaki.jp"} <= rules.wildcards
    assert {"www.ck", "city.kawasaki.jp"} <= rules.exceptions
    assert len(rules.exact) > 9000


def test_a_small_list_is_parsed_by_the_published_rule_syntax() -> None:
    rules = parse_public_suffix_list(
        "// VERSION: test-version\n"
        "// COMMIT: test-commit\n"
        "// ===BEGIN ICANN DOMAINS===\n"
        "example\n"
        "*.wild.example\n"
        "!keep.wild.example\n"
        "  co.example  \n"
        "\n"
        "// a comment\n"
        "公司.example\n"
    )
    assert rules.version == "test-version"
    assert rules.commit == "test-commit"
    assert rules.exact == {"example", "co.example", "xn--55qx5d.example"}
    assert rules.wildcards == {"wild.example"}
    assert rules.exceptions == {"keep.wild.example"}
    assert registrable_domain("a.b.co.example", rules) == "b.co.example"
    assert registrable_domain("a.b.wild.example", rules) == "a.b.wild.example"
    assert registrable_domain("b.wild.example", rules) is None
    assert registrable_domain("x.keep.wild.example", rules) == "keep.wild.example"
    assert registrable_domain("x.公司.example", rules) == "x.xn--55qx5d.example"
