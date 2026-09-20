"""The team website's smoke checks, as `validate-dev` runs them.

This is the one suite in the repository that is meant to touch the network: it asks a *deployed*
site the questions in `scripts/site_smoke.py`. Everything else about the site is tested offline,
in `site/tests/` and `tests/scripts/`.

It runs only when it is told which site to check, so a default `pytest` run collects it and skips
it:

    SITE_SMOKE_URL=https://dev.wfbdebate.com \\
    SITE_SMOKE_ENV=dev \\
    SITE_SMOKE_SHA=$(git rev-parse HEAD) \\
    uv run pytest tests/smoke -m dev

The default pytest options exclude `live` and disable sockets for the whole suite; the
`enable_socket` marker on each test below is what lets these two, and only these two, reach the
network. `SITE_SMOKE_SHA` is optional and worth setting: without it the checks confirm that *a*
site is healthy, and with it that the site is serving *this* commit.

Per docs/process/branching-and-environments.md, a green run of this against dev is one of the
conditions for a dev-to-main promotion; the same file run against prod is what confirms a
release actually reached parents.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import site_smoke  # noqa: E402

SITE_URL = os.environ.get("SITE_SMOKE_URL", "").strip()
SITE_ENVIRONMENT = os.environ.get("SITE_SMOKE_ENV", "dev").strip() or "dev"
EXPECTED_SHA = os.environ.get("SITE_SMOKE_SHA", "").strip() or None


def _skip_unless_targeted(environment: str) -> None:
    if not SITE_URL:
        pytest.skip("SITE_SMOKE_URL is not set: no deployed site to check.")
    if environment != SITE_ENVIRONMENT:
        pytest.skip(f"SITE_SMOKE_ENV is {SITE_ENVIRONMENT!r}, not {environment!r}.")


def _check(environment: str) -> None:
    try:
        results = site_smoke.check_site(SITE_URL, environment, expected_sha=EXPECTED_SHA)
    except site_smoke.SiteSmokeError as error:
        # The site could not be reached or answered nonsense, which is a failure of the deploy
        # rather than of this suite. Report it as one, with the reason.
        pytest.fail(f"the {environment} site could not be checked: {error}")
    report = site_smoke.format_report(site_smoke.normalise_site_url(SITE_URL), environment, results)
    assert all(result.passed for result in results), report


@pytest.mark.live
@pytest.mark.dev
@pytest.mark.enable_socket
def test_the_dev_preview_passes_the_smoke_check() -> None:
    """Pages, HTTPS, security headers, `noindex` and the deployed commit, on the preview."""
    _skip_unless_targeted("dev")
    _check("dev")


@pytest.mark.live
@pytest.mark.prod
@pytest.mark.enable_socket
def test_the_prod_site_passes_the_smoke_check() -> None:
    """The same checks against the public site, where `noindex` must be absent."""
    _skip_unless_targeted("prod")
    _check("prod")
