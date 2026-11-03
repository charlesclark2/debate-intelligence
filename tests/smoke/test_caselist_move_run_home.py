"""`caselist move-run-home` in an installed build (`v1-e40-t11`).

What the promotion's runbook relies on before anything reaches AWS: the build has the command, with its
dry run, `--execute` and `--release`, and it refuses prod, whose lock names prod from its seed, before it
builds a client or reads a lock. The move and its release against a bucket are tested in-process
against moto (`packages/debate_core/tests/application/test_run_state_home_moved.py` and
`packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py`); here nothing reaches a network, and
the guard would fail the check if anything tried.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.smoke.installed_build import InstalledCli

from debate_cli.exit_codes import ExitCode

#: Prod, in bucket mode, with a bucket named, so that a source checkout's run meets the same guards as
#: a published build's. The refusal comes before any client is built, so the bucket is never asked.
PROD_IN_BUCKET_MODE: dict[str, str | None] = {
    "DEBATE_ENV": "prod",
    "DEBATE_CASELIST__RUN_STATE": "bucket",
    "DEBATE_STORAGE__S3__BUCKET": "debate-prod-evidence-smoke",
}


@pytest.mark.parametrize(
    "arguments",
    [(), ("--execute",), ("--release",), ("--release", "--execute")],
    ids=lambda a: " ".join(a) or "dry run",
)
def test_move_run_home_refuses_prod_before_it_reaches_the_bucket(
    installed_cli: InstalledCli, arguments: tuple[str, ...]
) -> None:
    run = installed_cli.run("--json", "caselist", "move-run-home", *arguments, env=PROD_IN_BUCKET_MODE)

    assert run.exit_code == ExitCode.DOMAIN_FAILURE, run.output
    error: Any = run.envelope()["error"]
    assert error["code"] == "RUN_HOME_MOVE_REFUSED", error
    assert "moves from dev to prod, and this is prod" in error["message"]


def test_move_run_home_says_what_it_does(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("caselist", "move-run-home", "--help", env={"COLUMNS": "200"})

    assert run.exit_code == 0, run.output
    assert "--execute" in run.stdout
    assert "--release" in run.stdout
    assert "weekly run's home moves to prod" in run.stdout
