"""The HTTP cassettes in `tests/fixtures/http/` hold no credentials, no tracking and no real article.

The rules are written out here again rather than imported from `build_cassettes.py`, so that a builder
that stopped scrubbing is caught by a check that does not share its mistake. The cassettes are also
checked to be exactly what the builder writes, so none is edited by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from tests.fixtures.http import build_cassettes
from tests.fixtures.http.cassettes import CASSETTE_DIRECTORY, FIXTURES_ROOT, cassette_names, load_cassette

CREDENTIAL_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "set-cookie2",
    "www-authenticate",
}
TRACKING_HEADERS = {
    "cf-ray",
    "nel",
    "report-to",
    "server-timing",
    "x-request-id",
    "x-amz-cf-id",
    "traceparent",
}
REQUIRED_KINDS = {
    "news",
    "think-tank",
    "government",
    "open-access PDF",
    "paywalled",
    "robots-disallowed",
    "404",
}
SAMPLE_DIRECTORIES = {"access", "extraction"}
"""t03's and t04's synthetic samples: the only bodies a cassette may serve."""
TEASER_WORD_LIMIT = 200
"""A paywalled response carries a teaser, never an article: fewer visible words than this."""


def documents() -> list[tuple[str, dict[str, Any]]]:
    return [
        (path.name, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(CASSETTE_DIRECTORY.glob("*.json"))
    ]


def visible_words(html: str) -> int:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return len(re.sub(r"<[^>]+>", " ", text).split())


def test_the_committed_cassettes_are_what_the_builder_writes() -> None:
    committed = {path.name: path.read_text(encoding="utf-8") for path in CASSETTE_DIRECTORY.glob("*.json")}

    assert committed == build_cassettes.rendered(), (
        "run: uv run python tests/fixtures/http/build_cassettes.py"
    )


def test_at_least_seven_cassettes_cover_every_kind_the_spec_names() -> None:
    kinds = {load_cassette(name).kind for name in cassette_names()}

    assert len(cassette_names()) >= 7
    assert kinds >= REQUIRED_KINDS


@pytest.mark.parametrize("name", cassette_names())
def test_no_response_carries_a_cookie_credential_or_tracking_header(name: str) -> None:
    for interaction in load_cassette(name).interactions:
        names = {header.lower() for header, _ in interaction.headers}
        assert names & CREDENTIAL_HEADERS == set(), f"{name}: {interaction.url}"
        assert names & TRACKING_HEADERS == set(), f"{name}: {interaction.url}"


@pytest.mark.parametrize(("file_name", "document"), documents())
def test_no_request_is_recorded_beyond_its_method_and_url(file_name: str, document: dict[str, Any]) -> None:
    """Request headers are where a recording would keep a cookie or a token: a cassette keeps none."""
    for interaction in document["interactions"]:
        assert set(interaction["request"]) == {"method", "url"}, file_name
        assert set(interaction["response"]) <= {"status_code", "headers", "body_file", "body_text"}, file_name


@pytest.mark.parametrize("name", cassette_names())
def test_every_host_is_an_invented_example_host(name: str) -> None:
    for interaction in load_cassette(name).interactions:
        host = urlsplit(interaction.url).hostname or ""
        assert "example" in host.split("."), f"{name}: {host} is not under an example domain"


@pytest.mark.parametrize("name", cassette_names())
def test_every_body_is_a_synthetic_sample_of_t03_or_t04(name: str) -> None:
    for interaction in load_cassette(name).interactions:
        if interaction.body_file is None:
            assert interaction.url.endswith("/robots.txt"), f"{name}: only robots.txt is written inline"
            continue
        sample = (FIXTURES_ROOT / interaction.body_file).resolve()
        assert sample.is_file()
        assert Path(interaction.body_file).parts[0] in SAMPLE_DIRECTORIES, interaction.body_file


def test_a_paywalled_cassette_serves_a_teaser_and_never_an_article() -> None:
    paywalled = [load_cassette(name) for name in cassette_names() if load_cassette(name).kind == "paywalled"]

    assert paywalled
    for cassette in paywalled:
        page = cassette.page
        assert page is not None
        assert visible_words(page.body.decode("utf-8")) < TEASER_WORD_LIMIT, cassette.name


def test_the_robots_disallowed_cassette_never_records_the_page() -> None:
    """The fetcher must never ask for a page robots.txt refuses, so no response for it exists to replay."""
    cassette = load_cassette("robots-disallowed")

    assert cassette.page is None
    assert [interaction.url for interaction in cassette.interactions] == [
        "https://www.closed-stacks.example/robots.txt"
    ]
