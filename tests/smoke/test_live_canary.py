"""validate-dev's live canary tier: opt-in, one polite request, under the dev budget (ac4).

**What this is, honestly.** The tier exists so that later tasks have somewhere to put a live check
of a command that talks to a real service. Today no command has one that is worth running
unattended: `caselist` talks to OpenCaselist, whose download allowance belongs to the weekly agent
and the maintainer agreement (docs/policies/caselist-data-use.md), so this tier never calls it;
`store` needs AWS credentials a runner does not hold; nothing calls a model yet. So the tier ships
with one minimal, harmless check: the installed build's own interpreter and HTTP stack (httpx and
its CA bundle, which every live command will use) make **one** HEAD request to the public GitHub
page of the release the build was installed from. That proves outbound HTTPS works from the
installed environment and that a coach could find the release, and costs one request to GitHub.

**How it is enabled.** Never by default: the default selection is `not live`, and validate-dev
runs `-m "live and canary"` only when its workflow is dispatched with `live: true` or the
repository variable `VALIDATE_DEV_LIVE` is `true`. The check runs as DEBATE_ENV=dev and first
confirms the build agrees it is in dev with the dev budget.

A later task replaces or joins this with a live check of its own command, marked `live` and
`canary`, and keeps to the same rules: a handful of calls at most, read-only, dev budget, never
OpenCaselist.
"""

from __future__ import annotations

import os

import pytest
from tests.smoke.installed_build import InstalledCli

RELEASE_REPOSITORY = os.environ.get("DEBATE_RELEASE_REPO", "charlesclark2/debate-intelligence")
DEV_DAILY_BUDGET_CAP_USD = 2.0

HEAD_REQUEST = """
import sys
import httpx
response = httpx.head(sys.argv[1], follow_redirects=True, timeout=20,
                      headers={"User-Agent": "debate-research-validate-dev-canary"})
print(response.status_code)
"""


@pytest.mark.live
@pytest.mark.canary
def test_the_installed_build_reaches_its_own_release_page_over_https(installed_cli: InstalledCli) -> None:
    build = installed_cli.build
    assert installed_cli.network, "a live check runs with the network guard off"
    settings = installed_cli.run("--json", "config", "show")
    assert settings.exit_code == 0, settings.output
    report = settings.envelope()["data"]
    assert report["environment"] == "dev"  # type: ignore[index]
    assert report["settings"]["models.budget_usd_daily"] <= DEV_DAILY_BUDGET_CAP_USD  # type: ignore[index]

    page = f"https://github.com/{RELEASE_REPOSITORY}"
    if build.tag is not None:
        page += f"/releases/tag/{build.tag}"
    run = installed_cli.run_program([str(build.interpreter), "-c", HEAD_REQUEST, page], timeout=60)

    assert run.exit_code == 0, run.output
    assert run.stdout.strip() == "200", f"HEAD {page} → {run.stdout.strip()}\n{run.stderr}"
