"""Write the HTTP cassettes in `cassettes/` from the synthetic samples of v1-e04-t03 and v1-e04-t04.

Nothing here talks to the network, and nothing was ever recorded from a real site (the PM's amendment
of 2026-10-25 to v1-e04-t06): a real article is someone else's text, so the corpus is the invented
pages t03 and t04 already wrote, each served at an invented address under a reserved `.example`
domain, as the response it imitates. How real pages behave is v1-e04-t07's measurement, made in place.

Each cassette is one fixture URL: its origin's robots.txt and the page. A response's headers pass
through :func:`scrub_headers` before they are written, the rules a recording would need too, and
`test_cassette_hygiene.py` checks every committed cassette against the same rules independently.

`test_cassette_hygiene.py` also checks that the committed files are exactly what this script writes.
After changing it, rewrite them:

    uv run python tests/fixtures/http/build_cassettes.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DIRECTORY: Final = Path(__file__).parent / "cassettes"

HTML: Final = "text/html; charset=utf-8"
PDF: Final = "application/pdf"
ROBOTS: Final = "text/plain; charset=utf-8"

ALLOW_ALL: Final = "User-agent: *\nAllow: /\n"

FORBIDDEN_HEADERS: Final = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
        "set-cookie",
        "set-cookie2",
        "www-authenticate",
        "x-api-key",
        "x-amz-security-token",
    }
)
"""Credentials and session state: never in a cassette, in either direction."""

TRACKING_HEADERS: Final = frozenset(
    {
        "cf-ray",
        "nel",
        "report-to",
        "server-timing",
        "x-amz-cf-id",
        "x-request-id",
        "x-trace-id",
        "traceparent",
    }
)
"""Per-request identifiers and reporting endpoints: they identify one visit, not the page."""


def scrub_headers(headers: dict[str, str]) -> dict[str, str]:
    """`headers` without credentials, cookies or tracking identifiers, names lower-cased, sorted."""
    return {
        name.lower(): value
        for name, value in sorted(headers.items(), key=lambda item: item[0].lower())
        if name.lower() not in FORBIDDEN_HEADERS | TRACKING_HEADERS
    }


@dataclass(frozen=True, slots=True)
class Page:
    """One fixture: the URL fetched, the sample served there, and what robots.txt says about it."""

    name: str
    kind: str
    url: str
    status_code: int
    content_type: str
    body_file: str | None
    """The sample, relative to `tests/fixtures/`; None when robots.txt refuses the page."""
    made_from: str
    robots: str = ALLOW_ALL


PAGES: Final = (
    Page(
        name="news-article",
        kind="news",
        url="https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter",
        status_code=200,
        content_type=HTML,
        body_file="extraction/news-article.html",
        made_from="v1-e04-t04's hand-written newspaper story (The Daily Meridian is invented), as a 200",
    ),
    Page(
        name="think-tank-report",
        kind="think-tank",
        url="https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction",
        status_code=200,
        content_type=HTML,
        body_file="extraction/think-tank-report.html",
        made_from="v1-e04-t04's hand-written policy report (the Harwell Institute is invented), as a 200",
    ),
    Page(
        name="government-press-release",
        kind="government",
        url="https://www.fosw.example.gov/news/2026/06/agency-announces-grants",
        status_code=200,
        content_type=HTML,
        body_file="extraction/gov-press-release.html",
        made_from=(
            "v1-e04-t04's hand-written federal press release (the Federal Office of Synthetic Wildlife "
            "is invented and imitates no real agency), served as a 200"
        ),
    ),
    Page(
        name="open-access-pdf",
        kind="open-access PDF",
        url="https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012",
        status_code=200,
        content_type=PDF,
        body_file="extraction/journal-article.pdf",
        made_from=(
            "v1-e04-t04's three-page journal article, written by build_pdf_fixtures.py with no PDF "
            "library, served as a 200 at a URL carrying a test-prefix DOI (10.5555)"
        ),
    ),
    Page(
        name="paywalled",
        kind="paywalled",
        url="https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks",
        status_code=200,
        content_type=HTML,
        body_file="access/hard-paywall.html",
        made_from=(
            "v1-e04-t03's hard-paywall teaser (The Harbor Review is invented): one paragraph, "
            'isAccessibleForFree "False" and a subscribe box. No article body exists to leak'
        ),
    ),
    Page(
        name="robots-disallowed",
        kind="robots-disallowed",
        url="https://www.closed-stacks.example/archive/2026/water-rights-ruling",
        status_code=200,
        content_type=HTML,
        body_file=None,
        made_from=(
            "an invented site whose robots.txt disallows /archive/ to every agent; the page is never "
            "requested, so the cassette has no page response"
        ),
        robots="User-agent: *\nDisallow: /archive/\n",
    ),
    Page(
        name="not-found",
        kind="404",
        url="https://www.prairiedispatch.example/news/2026/10/county-fair-moved",
        status_code=404,
        content_type=HTML,
        body_file="access/not-found.html",
        made_from=(
            "v1-e04-t03's 404 page (The Prairie Dispatch is invented), which carries the site's "
            "metering script: a missing page is not a paywall"
        ),
    ),
    Page(
        name="bot-challenge",
        kind="blocked",
        url="https://www.northwindpost.example/world/2026/10/ferry-strike-ends",
        status_code=403,
        content_type=HTML,
        body_file="access/challenge-page.html",
        made_from="v1-e04-t03's bot-challenge interstitial, served as a 403 (The Northwind Post is invented)",
    ),
)


def robots_url(url: str) -> str:
    scheme, rest = url.split("://", 1)
    return f"{scheme}://{rest.split('/', 1)[0]}/robots.txt"


def cassette(page: Page) -> dict[str, object]:
    """The cassette document for `page`."""
    interactions: list[dict[str, object]] = [
        {
            "request": {"method": "GET", "url": robots_url(page.url)},
            "response": {
                "status_code": 200,
                "headers": scrub_headers({"Content-Type": ROBOTS}),
                "body_text": page.robots,
            },
        }
    ]
    if page.body_file is not None:
        interactions.append(
            {
                "request": {"method": "GET", "url": page.url},
                "response": {
                    "status_code": page.status_code,
                    "headers": scrub_headers({"Content-Type": page.content_type}),
                    "body_file": page.body_file,
                },
            }
        )
    return {
        "cassette_version": 1,
        "kind": page.kind,
        "url": page.url,
        "made_from": page.made_from,
        "interactions": interactions,
    }


def rendered() -> dict[str, str]:
    """Every cassette file's text, keyed by file name."""
    return {f"{page.name}.json": json.dumps(cassette(page), indent=2) + "\n" for page in PAGES}


def main() -> int:
    DIRECTORY.mkdir(exist_ok=True)
    expected = rendered()
    for stale in sorted(set(path.name for path in DIRECTORY.glob("*.json")) - set(expected)):
        (DIRECTORY / stale).unlink()
        print(f"removed cassettes/{stale}")
    for name, text in expected.items():
        (DIRECTORY / name).write_text(text, encoding="utf-8")
        print(f"wrote cassettes/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
