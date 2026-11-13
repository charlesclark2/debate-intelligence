"""`debate-research daily` on the build under test, offline (v1-e08-t07, working agreement 5).

A digest asks the providers its preset names, and every preset names a feed provider, so no digest can
run without the network; the recorded tier refuses every connection. What the build can show offline
is that the command is installed with its options and exit codes, and that it loads and checks the
presets it carries: an unknown preset is refused with the bundled file's preset names, which a build
without `config/daily_presets.yaml` could not list.
"""

from __future__ import annotations

from tests.smoke.installed_build import InstalledCli

from debate_cli.exit_codes import ExitCode


def test_daily_is_installed_with_its_options_and_exit_codes(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("daily", "--help", env={"COLUMNS": "200"})

    assert run.exit_code == 0, run.output
    for line in (
        "0  complete",
        "2  usage error",
        "3  no provider answered",
        "6  partial",
        "8  auto-cut short",
        "--date",
        "--window",
        "--format",
        "--auto-cut",
        "--digest-dir",
    ):
        assert line in run.stdout


def test_an_unknown_preset_exits_2_listing_the_presets_the_build_carries(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("daily", "data-centers", "--date", "2026-09-17", env={"COLUMNS": "200"})

    assert run.exit_code == ExitCode.USAGE_ERROR, run.output
    assert "the presets are politics, nhi" in " ".join(run.stderr.split())


def test_a_digest_with_no_date_is_dated_in_the_zone_the_builds_profile_names(
    installed_cli: InstalledCli,
) -> None:
    """v1-e08-t25: with no `--date` a digest covers the 24 hours before the run and is dated in
    `daily.time_zone`, which the profile a published build carries sets to America/Chicago."""
    shown = installed_cli.run("--json", "config", "show").envelope()["data"]
    assert isinstance(shown, dict)
    assert shown["settings"]["daily.time_zone"] == "America/Chicago"
    assert shown["sources"]["daily.time_zone"].startswith("profile:")

    run = installed_cli.run("daily", "--help", env={"COLUMNS": "200"})

    assert run.exit_code == 0, run.output
    assert "the 24 hours before the run" in " ".join(run.stdout.split())
