"""What the CLI prints reads the same under test whatever terminal the suite was started in.

The first CI run of v1-e01-t04 failed three tests that had passed on every laptop: on GitHub
Actions Typer forces a terminal, the help panels arrived full of ANSI escapes, and an option name
was no longer a substring of `result.stdout`. Measured afterwards, 16 tests in 9 modules failed in
some terminal (forced colour, or a width anywhere from 20 to 60 columns). The autouse fixture in
the root conftest.py pins the rendering; these tests hold it there.

* The subprocess tests start a fresh pytest the way a hostile runner would, with colour forced by
  `GITHUB_ACTIONS` and `FORCE_COLOR`, at a deliberately narrow and at a wide width, and run those
  16 tests. It has to be a fresh process: Typer reads those variables when it is imported, which
  in this process has already happened.
* The command-tree test renders `--help` for every command and checks that every option name
  appears intact, so a new long flag cannot bring width-dependent help back unnoticed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer.main
from typer.testing import CliRunner

from debate_cli.app import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Every test that failed in at least one terminal before the rendering was pinned. CI's first run
# caught three of them (test_help_lists_the_global_options_and_the_commands,
# test_the_command_is_registered, test_the_help_names_the_three_things_a_run_can_be_asked_to_do).
# A test renamed here fails the run below as "not found", which is the prompt to update the list.
TERMINAL_SENSITIVE_TESTS = (
    "packages/debate_cli/tests/commands/test_caselist_auth.py"
    "::test_status_after_login_reports_the_token_without_printing_it",
    "packages/debate_cli/tests/commands/test_caselist_pull.py"
    "::test_the_help_names_the_three_things_a_run_can_be_asked_to_do",
    "packages/debate_cli/tests/commands/test_caselist_runs.py"
    "::test_a_truncated_pull_states_wanted_and_deferred_and_the_next_run_carries_the_backlog",
    "packages/debate_cli/tests/commands/test_caselist_runs.py::test_runs_calls_out_a_schedule_that_has_stopped",
    "packages/debate_cli/tests/commands/test_store.py"
    "::TestFailures::test_a_person_still_sees_the_table_when_the_run_failed",
    "packages/debate_cli/tests/commands/test_store.py"
    "::TestFailures::test_an_expired_sso_session_is_one_line_and_not_a_traceback",
    "packages/debate_cli/tests/commands/test_store.py::TestListing::test_ls_lists_the_bucket",
    "packages/debate_cli/tests/test_app.py::test_doctor_renders_a_table",
    "packages/debate_cli/tests/test_app.py::test_help_lists_the_global_options_and_the_commands",
    "packages/debate_cli/tests/test_caselist_cards.py::test_cards_prints_totals_and_the_top_clusters",
    "packages/debate_cli/tests/test_caselist_import.py::test_a_dry_run_says_so_in_the_table",
    "packages/debate_cli/tests/test_caselist_import.py::test_an_older_archive_is_refused_with_a_domain_failure",
    "packages/debate_cli/tests/test_caselist_import.py"
    "::test_importing_one_week_succeeds_and_prints_a_summary_table",
    "packages/debate_cli/tests/test_caselist_import.py::test_the_command_is_registered",
    "packages/debate_cli/tests/test_config_command.py::test_config_show_renders_a_table",
    "tests/smoke/test_caselist_cards.py::test_caselist_cards_by_team_and_table",
)

# 20 columns fails all 16 above with nothing pinned; 400 is wider than any real terminal.
NARROW = 20
WIDE = 400


def _hostile_environment(width: int) -> dict[str, str]:
    """This process's environment, minus what pytest, xdist, coverage and the pin put in it,
    plus what a colour-forcing runner of `width` columns would set."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PYTEST_", "COV_CORE_")) and name not in ("NO_COLOR", "COLUMNS")
    }
    return inherited | {
        "GITHUB_ACTIONS": "true",
        "FORCE_COLOR": "1",
        "COLUMNS": str(width),
        "TERMINAL_WIDTH": str(width),
    }


@pytest.mark.parametrize("width", [NARROW, WIDE], ids=["narrow", "wide"])
def test_the_terminal_sensitive_tests_pass_on_a_colour_forcing_terminal_of_any_width(width: int) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            # The project's addopts would start xdist workers and coverage for sixteen tests.
            "-o",
            "addopts=",
            "--import-mode=importlib",
            "--disable-socket",
            "--allow-unix-socket",
            "-p",
            "no:cacheprovider",
            "-q",
            *TERMINAL_SENSITIVE_TESTS,
        ],
        cwd=REPOSITORY_ROOT,
        env=_hostile_environment(width),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"{len(TERMINAL_SENSITIVE_TESTS)} passed" in completed.stdout


def _commands(command: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every command in the tree, with the arguments that reach it."""
    yield path, command
    if hasattr(command, "list_commands"):
        for name in command.list_commands(None):
            yield from _commands(command.get_command(None, name), (*path, name))


def test_every_command_help_is_plain_text_naming_every_option() -> None:
    app = create_app()
    runner = CliRunner()
    commands = list(_commands(typer.main.get_command(app)))
    assert len(commands) > 1, "the command tree walk found no subcommands"

    for path, command in commands:
        result = runner.invoke(app, [*path, "--help"])
        shown = " ".join(("debate-research", *path))

        assert result.exit_code == 0, f"{shown} --help: {result.output}"
        assert "\x1b" not in result.stdout, f"{shown} --help carries ANSI escapes"
        for parameter in command.params:
            for option in (*parameter.opts, *parameter.secondary_opts):
                if option.startswith("-"):
                    assert option in result.stdout, f"{shown} --help does not show {option} intact"
