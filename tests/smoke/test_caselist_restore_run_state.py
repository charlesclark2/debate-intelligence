"""`caselist restore-run-state` and the dev profile it reads, in an installed build (`v1-e40-t06`).

What the cutover's runbook relies on before anything reaches AWS: the build has the command, its
bundled dev profile names the weekly run's caselists and keeps the run's state in the bucket, and the
command refuses this environment's own data directory before it builds a client or takes a lock. The
hand prod publish's restore (`v1-e40-t10`) adds `--with-sources`, which keeps that refusal and takes
`--snapshot` only with it. The
restore itself, against a bucket, is tested in-process against moto
(`packages/debate_cli/tests/bucket_mode/test_restore_run_state.py`); here nothing reaches a network,
and the guard would fail the check if anything tried.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.smoke.installed_build import InstalledCli

from debate_cli.exit_codes import ExitCode


def test_the_bundled_dev_profile_names_the_weekly_caselists_and_keeps_the_runs_state_in_the_bucket(
    installed_cli: InstalledCli,
) -> None:
    """ADR-0020 (5): `caselist pull` with no `--caselist`, in the cloud and on the Mac, reads these.

    A published build reads the profile its wheel carries. This checkout's own console script, run from
    a scratch directory, reads no profile at all, so there the two settings are their defaults, which
    `test_settings_environments.py` holds apart from the committed profile.
    """
    shown: Any = installed_cli.run("--json", "config", "show").envelope()["data"]

    if installed_cli.build.installed:
        assert shown["settings"]["caselist.sync_caselists"] == ["hsld26", "hspolicy26", "hspf26"]
        assert shown["settings"]["caselist.run_state"] == "bucket"
        assert shown["sources"]["caselist.run_state"].startswith("profile:")
    else:
        assert shown["sources"]["caselist.run_state"] == "default"
        assert shown["settings"]["caselist.run_state"] == "local"


#: Bucket mode and a bucket, named here so that a source checkout's run meets the same guards as a
#: published build's. The refusal comes before any client is built, so the bucket is never asked.
IN_BUCKET_MODE: dict[str, str | None] = {
    "DEBATE_CASELIST__RUN_STATE": "bucket",
    "DEBATE_STORAGE__S3__BUCKET": "debate-dev-evidence-smoke",
    "DEBATE_CASELIST__SYNC_CASELISTS": '["hsld26"]',
}


@pytest.mark.parametrize("extra", [(), ("--with-sources",)], ids=["without sources", "with sources"])
def test_restore_run_state_refuses_the_data_directory_before_it_reaches_the_bucket(
    installed_cli: InstalledCli, extra: tuple[str, ...]
) -> None:
    installed_cli.data_dir.mkdir(parents=True, exist_ok=True)

    run = installed_cli.run(
        "--json",
        "caselist",
        "restore-run-state",
        "--into",
        str(installed_cli.data_dir),
        *extra,
        env=IN_BUCKET_MODE,
    )

    assert run.exit_code == ExitCode.DOMAIN_FAILURE, run.output
    error: Any = run.envelope()["error"]
    assert error["code"] == "RESTORE_TARGET_REFUSED", error
    assert "this environment's own data directory" in error["message"]
    assert "the run lock was not taken" in error["message"]


def test_restore_run_state_refuses_local_mode(installed_cli: InstalledCli) -> None:
    """A bucket the cutover seeded is restored in bucket mode; local mode has no run state there."""
    run = installed_cli.run(
        "--json",
        "caselist",
        "restore-run-state",
        "--into",
        str(installed_cli.home / "copy"),
        env={**IN_BUCKET_MODE, "DEBATE_CASELIST__RUN_STATE": "local"},
    )

    assert run.exit_code == ExitCode.DOMAIN_FAILURE, run.output
    error: Any = run.envelope()["error"]
    assert error["code"] == "RUN_STATE_IS_LOCAL", error
    assert not (installed_cli.home / "copy").exists()


def test_restore_run_state_says_what_it_takes(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("caselist", "restore-run-state", "--help", env={"COLUMNS": "200"})

    assert run.exit_code == 0, run.output
    assert "--into" in run.stdout
    assert "under its lock" in run.stdout


def test_restore_run_state_offers_sources_and_takes_a_snapshot_only_with_them(
    installed_cli: InstalledCli,
) -> None:
    shown = installed_cli.run("caselist", "restore-run-state", "--help", env={"COLUMNS": "200"})
    assert shown.exit_code == 0, shown.output
    assert "--with-sources" in shown.stdout
    assert "--snapshot" in shown.stdout

    refused = installed_cli.run(
        "caselist",
        "restore-run-state",
        "--into",
        str(installed_cli.home / "copy"),
        "--snapshot",
        "2026-11-04",
        env=IN_BUCKET_MODE,
    )

    assert refused.exit_code == ExitCode.USAGE_ERROR, refused.output
    assert "--with-sources" in refused.output
    assert not (installed_cli.home / "copy").exists()
