"""The `debate-research` application as a user (or a script) meets it.

Everything here goes through Typer's `CliRunner`, which runs the real command line: the same
parsing, the same root callback, the same error handling and the same exit codes the installed
console script produces. Commands that do not exist yet — the ones E03–E34 add — are stood in for
by commands registered on a throwaway app built with :func:`~debate_cli.app.create_app`, because
what is being tested is the skeleton every one of them will run inside.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

from debate_cli import UNKNOWN_VERSION, __version__, package_version
from debate_cli.app import create_app, main
from debate_cli.commands import command_group
from debate_cli.container import ServiceContainer, Settings, SettingsNotConfigured
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, TableSpec
from debate_core.application.errors import NotFound, ProviderUnavailable
from debate_core.application.settings import load_settings

runner = CliRunner()


def envelope_of(result: Result) -> dict[str, Any]:
    """Parse the result's stdout, asserting it is exactly one JSON object."""
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


@pytest.fixture
def app_with() -> Callable[..., typer.Typer]:
    """Build a real application with extra commands registered on it."""

    def build(**commands: Callable[..., None]) -> typer.Typer:
        app = create_app()
        for name, command in commands.items():
            app.command(name)(command)
        return app

    return build


# ---------------------------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------------------------


def test_version_prints_the_package_version() -> None:
    result = runner.invoke(create_app(), ["--version"])

    assert result.exit_code == ExitCode.OK
    assert __version__ in result.stdout


def test_version_in_json_mode_is_an_envelope() -> None:
    result = runner.invoke(create_app(), ["--json", "--version"])

    assert result.exit_code == ExitCode.OK
    envelope = envelope_of(result)
    assert envelope["status"] == "ok"
    assert envelope["command"] == "version"
    assert envelope["data"] == {"package": "debate-cli", "version": __version__}


def test_help_lists_the_global_options_and_the_commands() -> None:
    result = runner.invoke(create_app(), ["--help"])

    assert result.exit_code == ExitCode.OK
    assert "--verbose" in result.stdout
    assert "--json" in result.stdout
    assert "--version" in result.stdout
    assert "doctor" in result.stdout


def test_short_help_option_works() -> None:
    assert runner.invoke(create_app(), ["-h"]).exit_code == ExitCode.OK


def test_no_command_is_a_usage_error() -> None:
    result = runner.invoke(create_app(), [])

    assert result.exit_code == ExitCode.USAGE_ERROR


def test_no_command_in_json_mode_puts_only_the_envelope_on_stdout() -> None:
    result = runner.invoke(create_app(), ["--json"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    envelope = envelope_of(result)
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "USAGE_ERROR"
    assert envelope["error"]["exit_code"] == ExitCode.USAGE_ERROR


# ---------------------------------------------------------------------------------------------
# doctor: the worked example of the command pattern
# ---------------------------------------------------------------------------------------------


def test_doctor_renders_a_table() -> None:
    result = runner.invoke(create_app(), ["doctor"])

    assert result.exit_code == ExitCode.OK
    assert "debate-cli" in result.stdout
    assert __version__ in result.stdout


def test_doctor_reports_the_environment_as_json() -> None:
    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.OK
    envelope = envelope_of(result)
    assert envelope["command"] == "doctor"
    data = envelope["data"]
    assert data["cli_version"] == __version__
    assert data["python_version"].startswith("3.12")
    # Every real run has a settings loader (v1-e02-t05); `doctor` reports that it is wired, not
    # that it has been run — loading is lazy and `doctor` does not need settings.
    assert data["settings_configured"] is True
    # The services the container can build, which `evidence_sync` (v1-e29-t05) was the first of,
    # `caselist_import` (v1-e30-t03) the second, the publisher and the status comparison
    # (v1-e30-t05) the next, the OpenCaselist token store and client (v1-e34-t01) after them, and
    # the OpenEv importer (v1-e30-t04) the last.
    # A later epic adding one adds it here too: this is the list an operator reads to find out
    # what this installation is wired for.
    assert data["services"] == [
        "caselist_import",
        "caselist_publish",
        "caselist_status",
        "caselist_token_store",
        "evidence_sync",
        "openev_import",
        "opencaselist_client",
    ]


def test_verbose_diagnostics_stay_off_stdout() -> None:
    result = runner.invoke(create_app(), ["--json", "--verbose", "doctor"])

    assert envelope_of(result)["status"] == "ok"
    assert "collecting environment facts" in result.stderr


# ---------------------------------------------------------------------------------------------
# Usage errors
# ---------------------------------------------------------------------------------------------


def test_unknown_command_is_a_usage_error() -> None:
    result = runner.invoke(create_app(), ["--json", "shrubbery"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    envelope = envelope_of(result)
    assert envelope["error"]["code"] == "USAGE_ERROR"
    assert envelope["command"] is None


def test_unknown_option_on_a_command_names_the_command() -> None:
    result = runner.invoke(create_app(), ["--json", "doctor", "--stethoscope"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    envelope = envelope_of(result)
    assert envelope["command"] == "doctor"
    assert "--stethoscope" in envelope["error"]["message"]


def test_unknown_root_option_is_reported_before_the_callback_runs() -> None:
    result = runner.invoke(create_app(), ["--json", "--stethoscope"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert envelope_of(result)["error"]["code"] == "USAGE_ERROR"


def test_a_usage_error_without_json_keeps_stdout_empty() -> None:
    result = runner.invoke(create_app(), ["shrubbery"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "shrubbery" in result.stderr


# ---------------------------------------------------------------------------------------------
# What a command raises, and what the process exits with
# ---------------------------------------------------------------------------------------------


def missing_card(ctx: typer.Context) -> None:
    """Stands in for any command whose service reports a missing record."""
    cli_context(ctx)
    raise NotFound("Card", "01JABCDEF")


def provider_down(ctx: typer.Context) -> None:
    """Stands in for any command whose provider is unreachable."""
    cli_context(ctx)
    raise ProviderUnavailable("openalex", "connection reset")


def buggy(ctx: typer.Context) -> None:
    """Stands in for a bug in a command."""
    cli_context(ctx)
    raise ValueError("off by one")


def unverified(ctx: typer.Context) -> None:
    """Stands in for `verify` reporting an outcome rather than raising."""
    cli = cli_context(ctx)
    cli.output.failure(
        CommandFailure(
            code="UNVERIFIED",
            message="3 of 12 cards could not be reproduced from their snapshot",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"unverified": 3, "total": 12},
        ),
        command=command_name(ctx),
    )
    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)


def test_a_domain_error_exits_one_and_keeps_its_facts(
    app_with: Callable[..., typer.Typer],
) -> None:
    result = runner.invoke(app_with(cut=missing_card), ["--json", "cut"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    envelope = envelope_of(result)
    assert envelope["command"] == "cut"
    assert envelope["error"]["code"] == "NOT_FOUND"
    assert envelope["error"]["exit_code"] == 1
    assert envelope["error"]["details"] == {"entity": "Card", "key": "01JABCDEF"}


def test_a_domain_error_renders_a_panel_on_stderr(app_with: Callable[..., typer.Typer]) -> None:
    result = runner.invoke(app_with(cut=missing_card), ["cut"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert result.stdout == ""
    assert "NOT_FOUND" in result.stderr
    assert "01JABCDEF" in result.stderr


def test_a_provider_failure_exits_three(app_with: Callable[..., typer.Typer]) -> None:
    result = runner.invoke(app_with(search=provider_down), ["--json", "search"])

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    envelope = envelope_of(result)
    assert envelope["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert envelope["error"]["details"]["provider"] == "openalex"


def test_an_unmodelled_exception_exits_seventy(app_with: Callable[..., typer.Typer]) -> None:
    result = runner.invoke(app_with(cut=buggy), ["--json", "cut"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    envelope = envelope_of(result)
    assert envelope["error"]["code"] == "INTERNAL_ERROR"
    assert envelope["error"]["exit_code"] == 70
    assert envelope["error"]["hint"] is not None


def test_the_traceback_of_a_bug_needs_verbose(app_with: Callable[..., typer.Typer]) -> None:
    quiet = runner.invoke(app_with(cut=buggy), ["cut"])
    loud = runner.invoke(app_with(cut=buggy), ["--verbose", "cut"])

    assert "Traceback" not in quiet.stderr
    assert "Traceback" in loud.stderr
    assert "off by one" in quiet.stderr


def test_an_outcome_failure_reports_itself_and_exits_one(
    app_with: Callable[..., typer.Typer],
) -> None:
    result = runner.invoke(app_with(verify=unverified), ["--json", "verify"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    envelope = envelope_of(result)
    assert envelope["command"] == "verify"
    assert envelope["error"]["code"] == "UNVERIFIED"
    assert envelope["error"]["details"] == {"unverified": 3, "total": 12}


# ---------------------------------------------------------------------------------------------
# Command groups, which most later tasks add
# ---------------------------------------------------------------------------------------------


def sync(ctx: typer.Context) -> None:
    """A subcommand of a group, reporting a result through the shared output."""
    cli = cli_context(ctx)
    cli.output.success(
        command_name(ctx),
        {"uploaded": 2},
        display=TableSpec(columns=("Uploaded",), rows=(("2",),)),
    )


def sync_fails(ctx: typer.Context) -> None:
    """A subcommand of a group whose service raises."""
    cli_context(ctx)
    raise ProviderUnavailable("s3", "no credentials")


def app_with_store(subcommand: Callable[..., None]) -> typer.Typer:
    app = create_app()
    store = command_group("store", "Work with the evidence store.")
    store.command("sync")(subcommand)
    app.add_typer(store)
    return app


def test_a_subcommand_group_reports_its_full_command_name() -> None:
    result = runner.invoke(app_with_store(sync), ["--json", "store", "sync"])

    assert result.exit_code == ExitCode.OK
    envelope = envelope_of(result)
    assert envelope["command"] == "store sync"
    assert envelope["data"] == {"uploaded": 2}


def test_a_subcommand_group_inherits_the_error_handling() -> None:
    result = runner.invoke(app_with_store(sync_fails), ["--json", "store", "sync"])

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    envelope = envelope_of(result)
    assert envelope["command"] == "store sync"
    assert envelope["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_a_group_without_a_subcommand_shows_its_help() -> None:
    result = runner.invoke(app_with_store(sync), ["store"])

    assert "sync" in result.stdout


# ---------------------------------------------------------------------------------------------
# The composition root is the seam
# ---------------------------------------------------------------------------------------------


class ArticleCounter:
    """Stands in for an application service a later task builds in the container."""

    def __init__(self, count: int) -> None:
        self.count = count


def count_articles(ctx: typer.Context) -> None:
    """A command that obtains its service from the container and nowhere else."""
    cli = cli_context(ctx)
    counter = cli.services.singleton("articles", lambda: ArticleCounter(0))
    cli.output.success(command_name(ctx), {"articles": counter.count})


def test_a_command_gets_its_service_from_the_container(
    app_with: Callable[..., typer.Typer],
) -> None:
    result = runner.invoke(app_with(articles=count_articles), ["--json", "articles"])

    assert envelope_of(result)["data"] == {"articles": 0}


def test_a_test_can_replace_a_service_before_the_command_runs() -> None:
    app = create_app()
    app.command("articles")(count_articles)

    def with_fake_service(ctx: typer.Context) -> None:
        cli = cli_context(ctx)
        cli.services.override("articles", ArticleCounter(42))
        count_articles(ctx)

    app_with_fake = create_app()
    app_with_fake.command("articles")(with_fake_service)
    result = runner.invoke(app_with_fake, ["--json", "articles"])

    assert envelope_of(result)["data"] == {"articles": 42}


def test_a_command_outside_the_app_is_a_programming_error() -> None:
    """Without the root callback there is no CliContext, and that is a wiring bug, not a usage one."""
    app = typer.Typer()
    app.command("stray")(count_articles)
    app.command("also-stray")(count_articles)  # two commands keep Typer's app a group

    result = runner.invoke(app, ["stray"], catch_exceptions=True)

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


def test_a_container_built_without_a_loader_refuses_to_invent_settings() -> None:
    container = ServiceContainer()

    assert container.settings_configured is False
    with pytest.raises(SettingsNotConfigured, match="settings_loader"):
        _ = container.settings


def test_a_settings_loader_is_called_once_and_cached(tmp_path: Path) -> None:
    calls: list[int] = []

    def load_once() -> Settings:
        calls.append(1)
        return load_settings(environment="test", overrides={"storage": {"data_dir": tmp_path}})

    container = ServiceContainer(settings_loader=load_once)

    assert container.settings_configured is True
    assert container.settings.storage.data_dir == tmp_path
    assert container.settings.storage.data_dir == tmp_path
    assert calls == [1]


def test_a_service_is_built_once_per_run() -> None:
    container = ServiceContainer()
    built: list[ArticleCounter] = []

    def build() -> ArticleCounter:
        counter = ArticleCounter(len(built))
        built.append(counter)
        return counter

    first = container.singleton("articles", build)
    second = container.singleton("articles", build)

    assert first is second
    assert len(built) == 1


# ---------------------------------------------------------------------------------------------
# Odds and ends of the skeleton
# ---------------------------------------------------------------------------------------------


def report_flags(ctx: typer.Context) -> None:
    """A command reporting the global options as the CliContext sees them."""
    cli = cli_context(ctx)
    cli.output.success(command_name(ctx), {"verbose": cli.verbose, "json": cli.json_output})


def test_the_global_options_reach_the_command(app_with: Callable[..., typer.Typer]) -> None:
    result = runner.invoke(app_with(flags=report_flags), ["--json", "--verbose", "flags"])

    assert envelope_of(result)["data"] == {"verbose": True, "json": True}


def test_an_uninstalled_distribution_reports_an_unknown_version() -> None:
    assert package_version("no-such-distribution") == UNKNOWN_VERSION


def test_the_console_script_entry_point_runs_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main` is what `debate-research` on the PATH calls."""
    monkeypatch.setattr(sys, "argv", ["debate-research", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == ExitCode.OK
