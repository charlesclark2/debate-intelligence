"""Tests for `scripts/site_smoke.py`, the post-deploy check on the team website.

The checker's only input is what a deployed site says over HTTP, so every test here builds a
deployed site out of respx routes and then breaks exactly one thing about it. Nothing makes a
live call: respx intercepts the transport, and the default pytest run has sockets disabled
besides.

The failures worth having a test each are the ones nobody would notice by looking at the site:
a page that quietly 404s, a security header dropped by a Terraform change, the preview losing
its `noindex` and becoming findable, and an edge still serving the previous build after a deploy
reported success.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import site_smoke  # noqa: E402

DEV_URL = "https://dev.wfbdebate.com"
PROD_URL = "https://wfbdebate.com"
DEPLOYED_SHA = "1111111111111111111111111111111111111111"

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{origin}/</loc></url>
  <url><loc>{origin}/about/</loc></url>
  <url><loc>{origin}/faq/</loc></url>
</urlset>
"""

SECURITY_HEADERS = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), geolocation=()",
}

PAGE_PATHS = ("/", "/about/", "/faq/")

#: A home page as the export actually serves it: the October 1 panel with every fact filled in.
HOME_BODY = (
    "<!doctype html><title>/</title>"
    '<section id="parent-session"><dl><dt>Room</dt><dd>Room 214</dd></dl></section>'
)

#: The parent FAQ as v1-e36-t07 built it: native disclosures, one per question.
FAQ_BODY = (
    "<!doctype html><title>/faq/</title>"
    "<details><summary>What does a season cost?</summary><p>Answer.</p></details>"
    "<details><summary>How much travel is there?</summary><p>Answer.</p></details>"
)

#: What a page renders where a fact nobody has supplied would go. A prod build refuses to export
#: one, so seeing it on prod means the build guard was bypassed.
HOME_BODY_WITH_A_GAP = HOME_BODY.replace(
    "<dd>Room 214</dd>", '<dd><span class="placeholder">TBD</span></dd>'
)


class DeployedSite:
    """A site that answers correctly, until a test tells it not to."""

    def __init__(self, router: respx.Router, origin: str, environment: str) -> None:
        self.router = router
        self.origin = origin
        self.environment = environment
        self.page_headers: dict[str, dict[str, str]] = {}
        self.page_status: dict[str, int] = {}
        self.page_bodies: dict[str, str] = {"/": HOME_BODY, "/faq/": FAQ_BODY}
        self.sitemap_body = SITEMAP.format(origin=origin)
        self.sitemap_status = 200
        self.robots_body = (
            "User-Agent: *\nDisallow: /\n" if environment == "dev" else "User-Agent: *\nAllow: /\n"
        )
        self.version_status = 200
        self.version_body = json.dumps({"commit": DEPLOYED_SHA, "environment": environment})
        self.redirect_status = 301
        self.redirect_location = f"{origin}/"

    def default_headers(self) -> dict[str, str]:
        headers = dict(SECURITY_HEADERS)
        if self.environment == "dev":
            headers["x-robots-tag"] = "noindex, nofollow"
        return headers

    def install(self) -> None:
        host = self.origin.removeprefix("https://")
        self.router.get(f"http://{host}/").mock(
            return_value=httpx.Response(self.redirect_status, headers={"location": self.redirect_location})
        )
        self.router.get(f"{self.origin}/sitemap.xml").mock(
            return_value=httpx.Response(
                self.sitemap_status,
                text=self.sitemap_body,
                headers={"content-type": "application/xml"},
            )
        )
        self.router.get(f"{self.origin}/robots.txt").mock(
            return_value=httpx.Response(200, text=self.robots_body)
        )
        self.router.get(f"{self.origin}/version.json").mock(
            return_value=httpx.Response(self.version_status, text=self.version_body)
        )
        for path in PAGE_PATHS:
            self.router.get(f"{self.origin}{path}").mock(
                return_value=httpx.Response(
                    self.page_status.get(path, 200),
                    headers=self.page_headers.get(path, self.default_headers()),
                    text=self.page_bodies.get(path, f"<!doctype html><title>{path}</title>"),
                )
            )

    def run(self, expected_sha: str | None = None) -> list[site_smoke.CheckResult]:
        self.install()
        return site_smoke.check_site(self.origin, self.environment, expected_sha=expected_sha)


@pytest.fixture
def router() -> Iterator[respx.Router]:
    with respx.mock(assert_all_called=False) as mock_router:
        yield mock_router


@pytest.fixture
def dev_site(router: respx.Router) -> DeployedSite:
    return DeployedSite(router, DEV_URL, "dev")


@pytest.fixture
def prod_site(router: respx.Router) -> DeployedSite:
    return DeployedSite(router, PROD_URL, "prod")


def failures(results: list[site_smoke.CheckResult]) -> list[site_smoke.CheckResult]:
    return [result for result in results if not result.passed]


def failure_text(results: list[site_smoke.CheckResult]) -> str:
    return " | ".join(f"{result.name}: {result.detail}" for result in failures(results))


# --------------------------------------------------------------------------------------
# A healthy site
# --------------------------------------------------------------------------------------


def test_a_correct_dev_preview_passes_every_check(dev_site: DeployedSite) -> None:
    results = dev_site.run(expected_sha=DEPLOYED_SHA)

    assert failures(results) == [], failure_text(results)
    assert {result.name for result in results} >= {
        "https redirect",
        "sitemap",
        "page /",
        "headers /",
        "noindex /",
        "robots.txt",
        "version.json",
    }


def test_a_correct_prod_site_passes_every_check(prod_site: DeployedSite) -> None:
    results = prod_site.run(expected_sha=DEPLOYED_SHA)

    assert failures(results) == [], failure_text(results)


def test_every_page_in_the_sitemap_is_checked(dev_site: DeployedSite) -> None:
    results = dev_site.run()

    assert [result.name for result in results if result.name.startswith("page ")] == [
        f"page {path}" for path in PAGE_PATHS
    ]


# --------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------


def test_a_page_that_does_not_return_200_fails(dev_site: DeployedSite) -> None:
    dev_site.page_status["/faq/"] = 404

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["page /faq/"]
    assert "404" in failure_text(results)


def test_a_sitemap_that_is_not_served_fails_and_checks_no_pages(dev_site: DeployedSite) -> None:
    dev_site.sitemap_status = 403

    results = dev_site.run()

    assert "sitemap" in {result.name for result in failures(results)}
    assert not [result for result in results if result.name.startswith("page ")]


def test_a_sitemap_that_lists_nothing_fails(dev_site: DeployedSite) -> None:
    dev_site.sitemap_body = (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
    )

    results = dev_site.run()

    assert "lists no pages" in failure_text(results)


# --------------------------------------------------------------------------------------
# Security headers, from the CloudFront response-headers policy of v1-e36-t02
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "referrer-policy",
        "x-frame-options",
        "permissions-policy",
    ],
)
def test_a_missing_security_header_fails(dev_site: DeployedSite, header: str) -> None:
    headers = dev_site.default_headers()
    del headers[header]
    dev_site.page_headers["/about/"] = headers

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["headers /about/"]
    assert header in failure_text(results)


def test_x_content_type_options_must_say_nosniff(dev_site: DeployedSite) -> None:
    headers = dev_site.default_headers()
    headers["x-content-type-options"] = "sniff-away"
    dev_site.page_headers["/"] = headers

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["headers /"]
    assert "nosniff" in failure_text(results)


# --------------------------------------------------------------------------------------
# HTTPS
# --------------------------------------------------------------------------------------


def test_a_missing_http_to_https_redirect_fails(dev_site: DeployedSite) -> None:
    dev_site.redirect_status = 200

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["https redirect"]


def test_a_redirect_that_stays_on_http_fails(dev_site: DeployedSite) -> None:
    dev_site.redirect_location = "http://dev.wfbdebate.com/"

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["https redirect"]


def test_an_http_url_is_refused_outright() -> None:
    with pytest.raises(site_smoke.SiteSmokeError, match="must be https"):
        site_smoke.check_site("http://dev.wfbdebate.com", "dev")


# --------------------------------------------------------------------------------------
# Indexability: the preview is not for the public, and prod is
# --------------------------------------------------------------------------------------


def test_the_dev_preview_losing_noindex_fails(dev_site: DeployedSite) -> None:
    """Every run asserts this: a findable preview is the privacy failure the policy is about."""
    headers = dev_site.default_headers()
    del headers["x-robots-tag"]
    dev_site.page_headers["/about/"] = headers

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["noindex /about/"]


def test_noindex_on_prod_fails(prod_site: DeployedSite) -> None:
    headers = prod_site.default_headers()
    headers["x-robots-tag"] = "noindex, nofollow"
    prod_site.page_headers["/"] = headers

    results = prod_site.run()

    assert [result.name for result in failures(results)] == ["noindex /"]
    assert "must be indexable" in failure_text(results)


def test_a_dev_robots_txt_that_allows_crawling_fails(dev_site: DeployedSite) -> None:
    dev_site.robots_body = "User-Agent: *\nAllow: /\n"

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["robots.txt"]


def test_a_prod_robots_txt_that_disallows_everything_fails(prod_site: DeployedSite) -> None:
    prod_site.robots_body = "User-Agent: *\nDisallow: /\n"

    results = prod_site.run()

    assert [result.name for result in failures(results)] == ["robots.txt"]


# --------------------------------------------------------------------------------------
# What the pages actually say: the launch surfaces of v1-e36-t06, t07 and t08
# --------------------------------------------------------------------------------------


def test_a_home_page_without_the_parent_session_panel_fails(dev_site: DeployedSite) -> None:
    """The panel is the reason most parents open the site at all."""
    dev_site.page_bodies["/"] = "<!doctype html><title>/</title><p>Welcome.</p>"

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["parent session panel"]
    assert "missing from the home page" in failure_text(results)


def test_a_gap_badge_on_prod_fails(prod_site: DeployedSite) -> None:
    """A fact nobody supplied cannot reach prod through the build, so finding one live means the
    guard in site/src/lib/publishing-policy.ts was gone round rather than satisfied."""
    prod_site.page_bodies["/"] = HOME_BODY_WITH_A_GAP

    results = prod_site.run()

    assert [result.name for result in failures(results)] == ["unfilled facts"]
    assert "did not come through the guard" in failure_text(results)


def test_a_gap_badge_on_the_preview_is_reported_rather_than_failed(dev_site: DeployedSite) -> None:
    """A dev build prints its gaps and carries on: that is how Charlie reviews copy with the holes
    visible. The count is still worth saying out loud before a promotion."""
    dev_site.page_bodies["/"] = HOME_BODY_WITH_A_GAP

    results = dev_site.run()

    assert failures(results) == []
    gaps = next(result for result in results if result.name == "unfilled facts")
    assert "1 page(s) on the preview" in gaps.detail
    assert "/" in gaps.detail


def test_a_parent_faq_without_disclosures_fails(dev_site: DeployedSite) -> None:
    dev_site.page_bodies["/faq/"] = "<!doctype html><title>/faq/</title><p>Questions.</p>"

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["faq disclosures"]


def test_the_faq_check_is_skipped_when_the_sitemap_has_no_faq(dev_site: DeployedSite) -> None:
    """The checks read the sitemap rather than a list of paths written here, so a site without a
    parent FAQ is checked for what it has rather than failed for what it does not."""
    dev_site.sitemap_body = SITEMAP.format(origin=DEV_URL).replace(
        f"  <url><loc>{DEV_URL}/faq/</loc></url>\n", ""
    )

    results = dev_site.run()

    assert failures(results) == []
    assert "faq disclosures" not in {result.name for result in results}


# --------------------------------------------------------------------------------------
# version.json: which build is actually being served
# --------------------------------------------------------------------------------------


def test_a_version_sha_mismatch_fails(dev_site: DeployedSite) -> None:
    results = dev_site.run(expected_sha="2222222222222222222222222222222222222222")

    assert [result.name for result in failures(results)] == ["version.json"]
    assert "old build" in failure_text(results)


def test_a_missing_version_json_fails(dev_site: DeployedSite) -> None:
    dev_site.version_status = 404

    results = dev_site.run()

    assert [result.name for result in failures(results)] == ["version.json"]


def test_a_version_json_that_is_not_json_fails(dev_site: DeployedSite) -> None:
    dev_site.version_body = "<!doctype html><title>404</title>"

    results = dev_site.run()

    assert "not valid JSON" in failure_text(results)


def test_version_json_passes_without_expect_sha(dev_site: DeployedSite) -> None:
    results = dev_site.run()

    assert failures(results) == [], failure_text(results)


# --------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------


def test_main_exits_non_zero_when_a_check_fails(
    dev_site: DeployedSite, capsys: pytest.CaptureFixture[str]
) -> None:
    dev_site.page_status["/faq/"] = 500
    dev_site.install()

    exit_code = site_smoke.main(["--url", DEV_URL, "--env", "dev"])

    assert exit_code == 1
    assert "[FAIL] page /faq/" in capsys.readouterr().out


def test_main_exits_zero_and_reports_when_everything_passes(
    dev_site: DeployedSite, capsys: pytest.CaptureFixture[str]
) -> None:
    dev_site.install()

    exit_code = site_smoke.main(["--url", DEV_URL, "--env", "dev", "--expect-sha", DEPLOYED_SHA])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "All " in output and "checks passed." in output


def test_main_reports_a_site_that_cannot_be_reached(
    router: respx.Router, capsys: pytest.CaptureFixture[str]
) -> None:
    router.get(f"http://{DEV_URL.removeprefix('https://')}/").mock(
        side_effect=httpx.ConnectError("nodename nor servname provided")
    )

    exit_code = site_smoke.main(["--url", DEV_URL, "--env", "dev"])

    assert exit_code == 1
    assert "smoke check could not run" in capsys.readouterr().err
