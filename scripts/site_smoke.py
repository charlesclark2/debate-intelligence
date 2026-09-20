#!/usr/bin/env python3
"""Check a deployed team website: is it there, is it served safely, and is it the build we think?

    uv run scripts/site_smoke.py --env dev  --url https://dev.wfbdebate.com
    uv run scripts/site_smoke.py --env prod --url https://wfbdebate.com --expect-sha "$(git rev-parse HEAD)"

Spec: ``plan_specs/v1/e36-team-website/t05-site-deploy.yaml``. It runs after every deploy
(``scripts/site_deploy.sh``), and ``tests/smoke/test_site.py`` runs it from ``validate-dev``
before a dev-to-main promotion (ADR-0013).

It makes real HTTP requests, so it is the one thing in this repository that needs the network,
and it needs nothing else: no AWS credentials, no state, no cookie. Everything it asserts is
visible to any visitor.

What it checks, and why each one is here rather than assumed:

sitemap        ``/sitemap.xml`` parses and lists at least one page. Every other page check reads
               its list, so an empty or broken sitemap is a failure in itself.
pages          every page in the sitemap answers 200 over HTTPS. A static export that half
               uploaded still serves a home page; this is what notices the rest.
https          ``http://`` redirects to ``https://``. The distribution is configured for it
               (v1-e36-t02), and a regression here is silent.
headers        HSTS, a content security policy, ``X-Content-Type-Options: nosniff``, a referrer
               policy, a frame policy and a permissions policy, on every page. They come from the
               CloudFront response-headers policy, so losing them is a Terraform regression rather
               than a site one, and this is where that shows up.
indexability   dev must send ``X-Robots-Tag: noindex`` and disallow everything in ``robots.txt``;
               prod must do neither. The preview is a page about children that nobody outside the
               team is meant to find, and checking it on every run is cheaper than discovering it
               in a search result.
version        ``/version.json`` parses and, with ``--expect-sha``, names the commit that was
               meant to be deployed. This is what distinguishes "the deploy worked" from "the old
               build is still being served".

Exit status is 0 when every check passed and 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

#: Set on the CloudFront response-headers policy by v1-e36-t02, on every response.
REQUIRED_SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "referrer-policy",
    "x-frame-options",
    "permissions-policy",
)

SITEMAP_NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

DEFAULT_TIMEOUT_SECONDS = 20.0

USER_AGENT = "wfb-debate-site-smoke/1.0 (+scripts/site_smoke.py)"


@dataclass(frozen=True)
class CheckResult:
    """One assertion about the deployed site."""

    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


class SiteSmokeError(Exception):
    """A check could not be made at all, as opposed to being made and failing."""


# ------------------------------------------------------------------------------------------
# Fetching
# ------------------------------------------------------------------------------------------


def normalise_site_url(url: str) -> str:
    """Reduce ``https://host/path/`` to ``https://host``, and refuse anything but HTTPS."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme != "https":
        raise SiteSmokeError(f"--url must be https, got {url!r}. The site is HTTPS only.")
    if not parsed.netloc:
        raise SiteSmokeError(f"--url has no host: {url!r}")
    return f"https://{parsed.netloc}"


def _get(client: httpx.Client, url: str) -> httpx.Response:
    try:
        return client.get(url)
    except httpx.HTTPError as error:  # a DNS failure, a TLS failure, a timeout
        raise SiteSmokeError(f"{url}: {type(error).__name__}: {error}") from error


# ------------------------------------------------------------------------------------------
# The checks
# ------------------------------------------------------------------------------------------


def parse_sitemap_paths(xml: str) -> list[str]:
    """The site-relative path of every ``<loc>`` in a sitemap, in document order.

    Paths rather than whole URLs: the sitemap holds the canonical origin the build was given,
    and a smoke check may be pointed at a different one (a CloudFront domain before DNS moves,
    say). The origin the sitemap claims is checked separately.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise SiteSmokeError(f"sitemap.xml is not valid XML: {error}") from error

    paths: list[str] = []
    for element in root.iter(f"{SITEMAP_NAMESPACE}loc"):
        location = (element.text or "").strip()
        if not location:
            continue
        parsed = urlparse(location)
        paths.append(parsed.path or "/")
    return paths


def check_sitemap(client: httpx.Client, site_url: str) -> tuple[CheckResult, list[str]]:
    response = _get(client, f"{site_url}/sitemap.xml")
    if response.status_code != 200:
        return (
            CheckResult("sitemap", False, f"GET /sitemap.xml returned {response.status_code}"),
            [],
        )
    paths = parse_sitemap_paths(response.text)
    if not paths:
        return CheckResult("sitemap", False, "sitemap.xml lists no pages"), []
    return CheckResult("sitemap", True, f"{len(paths)} pages listed"), paths


def check_page(client: httpx.Client, site_url: str, path: str, environment: str) -> Iterator[CheckResult]:
    """Status, security headers and indexability for one page."""
    url = urljoin(f"{site_url}/", path.lstrip("/"))
    response = _get(client, url)

    if response.status_code != 200:
        yield CheckResult(f"page {path}", False, f"returned {response.status_code}")
        return
    yield CheckResult(f"page {path}", True, "200")

    missing = [header for header in REQUIRED_SECURITY_HEADERS if header not in response.headers]
    if missing:
        yield CheckResult(f"headers {path}", False, f"missing {', '.join(missing)}")
    elif response.headers["x-content-type-options"].strip().lower() != "nosniff":
        yield CheckResult(
            f"headers {path}",
            False,
            f"x-content-type-options is {response.headers['x-content-type-options']!r}, not nosniff",
        )
    else:
        yield CheckResult(f"headers {path}", True, "all six present")

    robots_tag = response.headers.get("x-robots-tag", "")
    says_noindex = "noindex" in robots_tag.lower()
    if environment == "dev" and not says_noindex:
        yield CheckResult(
            f"noindex {path}",
            False,
            f"the preview must send X-Robots-Tag: noindex, got {robots_tag!r}",
        )
    elif environment == "prod" and says_noindex:
        yield CheckResult(
            f"noindex {path}",
            False,
            f"prod must be indexable, but sends X-Robots-Tag: {robots_tag!r}",
        )
    else:
        yield CheckResult(
            f"noindex {path}",
            True,
            "noindex" if says_noindex else "indexable",
        )


def check_https_redirect(client: httpx.Client, site_url: str) -> CheckResult:
    host = urlparse(site_url).netloc
    response = _get(client, f"http://{host}/")
    location = response.headers.get("location", "")
    if response.status_code not in (301, 302, 307, 308):
        return CheckResult(
            "https redirect", False, f"http:// returned {response.status_code}, not a redirect"
        )
    if not location.startswith("https://"):
        return CheckResult("https redirect", False, f"http:// redirects to {location!r}, not to https")
    return CheckResult("https redirect", True, f"{response.status_code} to {location}")


def check_robots(client: httpx.Client, site_url: str, environment: str) -> CheckResult:
    response = _get(client, f"{site_url}/robots.txt")
    if response.status_code != 200:
        return CheckResult("robots.txt", False, f"returned {response.status_code}")
    disallows_everything = any(
        line.strip().lower().replace(" ", "") == "disallow:/" for line in response.text.splitlines()
    )
    if environment == "dev" and not disallows_everything:
        return CheckResult("robots.txt", False, "the preview's robots.txt does not disallow every path")
    if environment == "prod" and disallows_everything:
        return CheckResult("robots.txt", False, "prod's robots.txt disallows every path")
    return CheckResult(
        "robots.txt",
        True,
        "disallows everything" if disallows_everything else "allows crawling",
    )


def check_version(client: httpx.Client, site_url: str, expected_sha: str | None) -> CheckResult:
    response = _get(client, f"{site_url}/version.json")
    if response.status_code != 200:
        return CheckResult("version.json", False, f"returned {response.status_code}")
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as error:
        return CheckResult("version.json", False, f"is not valid JSON: {error}")
    deployed_sha = payload.get("commit") if isinstance(payload, dict) else None
    if not deployed_sha:
        return CheckResult("version.json", False, "has no commit field")
    if expected_sha and deployed_sha != expected_sha:
        return CheckResult(
            "version.json",
            False,
            f"serves {deployed_sha}, expected {expected_sha}. The edge may still hold the old build.",
        )
    return CheckResult("version.json", True, f"commit {deployed_sha}")


def check_site(
    site_url: str,
    environment: str,
    expected_sha: str | None = None,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[CheckResult]:
    """Run every check against a deployed site and return the results in the order they ran."""
    site_url = normalise_site_url(site_url)
    owned_client = client is None
    client = client or httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        headers={"user-agent": USER_AGENT},
    )
    try:
        results = [check_https_redirect(client, site_url)]
        sitemap_result, paths = check_sitemap(client, site_url)
        results.append(sitemap_result)
        for path in paths:
            results.extend(check_page(client, site_url, path, environment))
        results.append(check_robots(client, site_url, environment))
        results.append(check_version(client, site_url, expected_sha))
        return results
    finally:
        if owned_client:
            client.close()


# ------------------------------------------------------------------------------------------
# Command line
# ------------------------------------------------------------------------------------------


def format_report(site_url: str, environment: str, results: Iterable[CheckResult]) -> str:
    results = list(results)
    failures = [result for result in results if not result.passed]
    lines = [f"Smoke check: {environment} at {site_url}", ""]
    lines.extend(str(result) for result in results)
    lines.append("")
    lines.append(
        f"{len(results) - len(failures)} passed, {len(failures)} failed."
        if failures
        else f"All {len(results)} checks passed."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a deployed Whitefish Bay debate team website.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="the deployed site, e.g. https://dev.wfbdebate.com")
    parser.add_argument(
        "--env",
        required=True,
        choices=("dev", "prod"),
        dest="environment",
        help="dev expects noindex; prod expects to be indexable",
    )
    parser.add_argument(
        "--expect-sha",
        dest="expected_sha",
        default=None,
        help="the commit version.json must name, usually $(git rev-parse HEAD)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"per-request timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        results = check_site(
            arguments.url,
            arguments.environment,
            expected_sha=arguments.expected_sha,
            timeout=arguments.timeout,
        )
    except SiteSmokeError as error:
        print(f"smoke check could not run: {error}", file=sys.stderr)
        return 1

    print(format_report(normalise_site_url(arguments.url), arguments.environment, results))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
