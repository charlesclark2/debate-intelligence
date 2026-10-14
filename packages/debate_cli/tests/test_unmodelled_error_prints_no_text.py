"""An exception the CLI does not model never prints its message, only its class (`v1-e01-t25`).

The root handler turns such an exception into exit 70. Its message is not this project's sentence:
an `OSError` quotes the path it failed on, which carries the home directory and, for a file in the
inbox, a camp file's title. So the default output and the `--json` envelope name the class and
say how to see more; the traceback, message included, is printed with `--verbose` only. A
`DomainError` is this project's own sentence and keeps it, with its own exit code.

The probe below is invented: no such home directory, camp or file exists. Its absence is checked in
stdout and stderr with everything but letters and digits removed, so a panel border or a line wrap
cannot split it and pass the check by accident.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import NotFound, StoreUnavailable
from debate_core.application.settings import ConfigurationError

PROBE_PATH = "/Users/zqxprobe-home/debate-data/inbox/openev-901-Zqxprobe_Lantern_Camp_Release.zip"
PROBE_TITLE = "Zqxprobe Lantern Camp Release"
PROBE_WORD = "zqxprobe"
"""In both the path and the title, and in nothing this project writes."""

runner = CliRunner()

# Wide enough that Rich never wraps a line, so a present probe is found whole as well.
WIDE = {"COLUMNS": "200"}


def refused_write(ctx: typer.Context) -> None:
    """The inbox refusing a write: an `OSError` quoting the file it failed on."""
    cli_context(ctx)
    raise PermissionError(13, "Permission denied", PROBE_PATH)


def bug_quoting_a_title(ctx: typer.Context) -> None:
    """A bug whose message quotes a path and a title it was handed."""
    cli_context(ctx)
    raise RuntimeError(f"could not file {PROBE_TITLE!r} at {PROBE_PATH}")


def fails_after_its_result(ctx: typer.Context) -> None:
    """A command that reported its result and then failed while finishing up."""
    cli = cli_context(ctx)
    cli.output.success(command_name(ctx), {"written": 1}, display="1 written")
    raise PermissionError(13, "Permission denied", PROBE_PATH)


def configuration_quoting_its_file(ctx: typer.Context) -> None:
    """A modelled error whose own message names a file: this project wrote that sentence."""
    cli_context(ctx)
    raise ConfigurationError(f"could not read {PROBE_PATH}: not valid TOML", source=PROBE_PATH)


def missing_card(ctx: typer.Context) -> None:
    cli_context(ctx)
    raise NotFound("Card", "01JZQXPROBE")


def bucket_down(ctx: typer.Context) -> None:
    cli_context(ctx)
    raise StoreUnavailable("put_object", "the evidence bucket", "the bucket did not answer")


def app_with(name: str, command: Callable[..., None]) -> typer.Typer:
    app = create_app()
    app.command(name)(command)
    return app


def letters_and_digits(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def holds_probe(text: str) -> bool:
    return PROBE_WORD in letters_and_digits(text)


def envelope_of(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


UNMODELLED = [
    pytest.param(refused_write, "PermissionError", id="an OSError quoting its path"),
    pytest.param(bug_quoting_a_title, "RuntimeError", id="a bug quoting a path and a title"),
]


# ---------------------------------------------------------------------------------------------
# Default output: the class and a pointer to --verbose, never the message
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("command", "class_name"), UNMODELLED)
def test_the_envelope_names_the_class_and_not_the_message(
    command: Callable[..., None], class_name: str
) -> None:
    result = runner.invoke(app_with("file", command), ["--json", "file"], env=WIDE)

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    error = envelope_of(result)["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["exit_code"] == 70
    assert class_name in error["message"]
    assert error["details"] == {"exception_type": class_name}
    assert "--verbose" in error["hint"]
    assert not holds_probe(result.stdout), result.stdout
    assert not holds_probe(result.stderr), result.stderr


@pytest.mark.parametrize(("command", "class_name"), UNMODELLED)
def test_the_panel_names_the_class_and_not_the_message(command: Callable[..., None], class_name: str) -> None:
    result = runner.invoke(app_with("file", command), ["file"], env=WIDE)

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    assert result.stdout == ""
    assert "INTERNAL_ERROR" in result.stderr
    assert class_name in result.stderr
    assert "--verbose" in result.stderr
    assert "Traceback" not in result.stderr
    assert not holds_probe(result.stderr), result.stderr


def test_a_failure_after_the_result_names_only_the_class() -> None:
    # The envelope is already on stdout, so the failure is a diagnostic on stderr instead.
    result = runner.invoke(app_with("file", fails_after_its_result), ["--json", "file"], env=WIDE)

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    assert envelope_of(result)["status"] == "ok"
    assert "PermissionError" in result.stderr
    assert not holds_probe(result.stdout + result.stderr), result.stderr


# ---------------------------------------------------------------------------------------------
# --verbose: the traceback, with the message
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [["--verbose"], ["--verbose", "--json"]], ids=["panel", "envelope"])
def test_verbose_prints_the_traceback_with_the_message(mode: list[str]) -> None:
    result = runner.invoke(app_with("file", refused_write), [*mode, "file"], env=WIDE)

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    assert "Traceback (most recent call last)" in result.stderr
    assert f"PermissionError: [Errno 13] Permission denied: '{PROBE_PATH}'" in result.stderr


def test_verbose_keeps_the_message_out_of_the_envelope() -> None:
    # The traceback is a diagnostic, on stderr; what a program reads on stdout is the same as without.
    result = runner.invoke(app_with("file", refused_write), ["--verbose", "--json", "file"], env=WIDE)

    assert not holds_probe(result.stdout), result.stdout
    assert envelope_of(result)["error"]["details"] == {"exception_type": "PermissionError"}


# ---------------------------------------------------------------------------------------------
# A modelled error keeps its message and its exit code
# ---------------------------------------------------------------------------------------------


def test_a_domain_error_still_prints_its_own_message() -> None:
    result = runner.invoke(app_with("cut", missing_card), ["--json", "cut"], env=WIDE)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "Card not found: 01JZQXPROBE"
    assert error["details"] == {"entity": "Card", "key": "01JZQXPROBE"}


def test_a_domain_error_that_names_a_file_keeps_its_sentence() -> None:
    # Withholding is for text this project did not write; a modelled message is unchanged.
    quiet = runner.invoke(app_with("load", configuration_quoting_its_file), ["load"], env=WIDE)
    envelope = runner.invoke(app_with("load", configuration_quoting_its_file), ["--json", "load"], env=WIDE)

    assert quiet.exit_code == envelope.exit_code == ExitCode.DOMAIN_FAILURE
    assert PROBE_PATH in quiet.stderr
    assert envelope_of(envelope)["error"]["message"] == f"could not read {PROBE_PATH}: not valid TOML"


def test_a_retryable_store_failure_still_exits_three_with_its_message() -> None:
    result = runner.invoke(app_with("sync", bucket_down), ["--json", "sync"], env=WIDE)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "STORE_UNAVAILABLE"
    assert "the bucket did not answer" in error["message"]
