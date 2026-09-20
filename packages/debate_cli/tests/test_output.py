"""The output contract: what lands on stdout, what lands on stderr, and the shape of each.

These are the rules a later command task relies on without re-reading the code, so they are
asserted rather than described: one JSON object on stdout in `--json` mode whatever happens,
diagnostics always on stderr, and an exception's facts preserved in the envelope's `error`.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
import typer

from debate_cli.exit_codes import ExitCode, error_code_for, exit_code_for
from debate_cli.output import SCHEMA_VERSION, CliOutput, CommandFailure, OutputMode, TableSpec
from debate_core.application.errors import (
    BlobIntegrityError,
    NotFound,
    ProviderRateLimited,
    ProviderUnavailable,
    RevisionMismatch,
)

ENVELOPE_KEYS = {"schema_version", "status", "command", "data", "error"}
ERROR_KEYS = {"code", "message", "exit_code", "details", "hint"}


class Captured:
    """A :class:`CliOutput` writing into strings instead of the terminal."""

    def __init__(self, mode: OutputMode, *, verbose: bool = False) -> None:
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.output = CliOutput(
            mode,
            verbose=verbose,
            stdout=self.stdout,
            stderr=self.stderr,
            width=100,
        )

    @property
    def out(self) -> str:
        return self.stdout.getvalue()

    @property
    def err(self) -> str:
        return self.stderr.getvalue()

    def envelope(self) -> dict[str, Any]:
        """Parse stdout, asserting it is exactly one JSON object and nothing else."""
        lines = self.out.splitlines()
        assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
        envelope = json.loads(lines[0])
        assert isinstance(envelope, dict)
        return envelope


DOCTOR_ROWS = TableSpec(
    columns=("Check", "Value"),
    rows=(("Python", "3.12.7"), ("Settings loaded", "no")),
    title="doctor",
)


# ---------------------------------------------------------------------------------------------
# Rich mode
# ---------------------------------------------------------------------------------------------


def test_rich_success_renders_the_table_on_stdout() -> None:
    captured = Captured(OutputMode.RICH)

    captured.output.success("doctor", {"python_version": "3.12.7"}, display=DOCTOR_ROWS)

    assert "Check" in captured.out
    assert "3.12.7" in captured.out
    assert "doctor" in captured.out
    assert captured.err == ""


def test_rich_success_renders_a_plain_line_on_stdout() -> None:
    captured = Captured(OutputMode.RICH)

    captured.output.success("version", {"version": "0.1.0"}, display="debate-research 0.1.0")

    assert captured.out.strip() == "debate-research 0.1.0"


def test_rich_success_prints_nothing_without_a_display() -> None:
    captured = Captured(OutputMode.RICH)

    captured.output.success("quiet", {"ok": True})

    assert captured.out == ""


def test_rich_success_does_not_emit_json() -> None:
    captured = Captured(OutputMode.RICH)

    captured.output.success("doctor", {"python_version": "3.12.7"}, display=DOCTOR_ROWS)

    assert "schema_version" not in captured.out


def test_rich_failure_renders_a_panel_on_stderr_and_leaves_stdout_clean() -> None:
    captured = Captured(OutputMode.RICH)

    captured.output.failure(
        CommandFailure(
            code="UNVERIFIED",
            message="3 of 12 cards could not be reproduced",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"unverified": 3},
            hint="Re-fetch the source and cut again.",
        )
    )

    assert captured.out == ""
    assert "UNVERIFIED" in captured.err
    assert "3 of 12 cards could not be reproduced" in captured.err
    assert "unverified: 3" in captured.err
    assert "Re-fetch the source and cut again." in captured.err
    assert "exit 1" in captured.err


# ---------------------------------------------------------------------------------------------
# JSON mode
# ---------------------------------------------------------------------------------------------


def test_json_success_emits_one_envelope_and_no_table() -> None:
    captured = Captured(OutputMode.JSON)

    captured.output.success("doctor", {"python_version": "3.12.7"}, display=DOCTOR_ROWS)

    envelope = captured.envelope()
    assert set(envelope) == ENVELOPE_KEYS
    assert envelope["schema_version"] == SCHEMA_VERSION
    assert envelope["status"] == "ok"
    assert envelope["command"] == "doctor"
    assert envelope["data"] == {"python_version": "3.12.7"}
    assert envelope["error"] is None
    assert "Check" not in captured.out
    assert captured.err == ""


def test_json_success_carries_a_nested_payload_verbatim() -> None:
    captured = Captured(OutputMode.JSON)
    data = {"counts": {"verified": 9, "unverified": 3}, "providers": ["openalex", "crossref"]}

    captured.output.success("verify", data)

    assert captured.envelope()["data"] == data


def test_json_failure_emits_the_error_object() -> None:
    captured = Captured(OutputMode.JSON)

    captured.output.failure(
        CommandFailure(
            code="UNVERIFIED",
            message="3 of 12 cards could not be reproduced",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"unverified": 3, "total": 12},
        ),
        command="verify",
    )

    envelope = captured.envelope()
    assert set(envelope) == ENVELOPE_KEYS
    assert envelope["status"] == "error"
    assert envelope["command"] == "verify"
    assert envelope["data"] is None
    error = envelope["error"]
    assert set(error) == ERROR_KEYS
    assert error["code"] == "UNVERIFIED"
    assert error["exit_code"] == 1
    assert error["details"] == {"unverified": 3, "total": 12}
    assert error["hint"] is None


def test_json_failure_after_a_result_stays_off_stdout() -> None:
    """A command that has already emitted its result must not emit a second object."""
    captured = Captured(OutputMode.JSON)
    captured.output.success("verify", {"cards": 12})

    captured.output.failure(
        CommandFailure(code="INTERNAL_ERROR", message="boom", exit_code=ExitCode.INTERNAL_ERROR)
    )

    assert captured.envelope()["status"] == "ok"
    assert "boom" in captured.err


def test_reporting_twice_is_a_programming_error() -> None:
    captured = Captured(OutputMode.JSON)
    captured.output.success("doctor", {})

    with pytest.raises(RuntimeError, match="exactly one result"):
        captured.output.success("doctor", {})


# ---------------------------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [OutputMode.RICH, OutputMode.JSON])
def test_detail_is_silent_without_verbose(mode: OutputMode) -> None:
    captured = Captured(mode)

    captured.output.detail("fetching https://example.org/article")

    assert captured.err == ""
    assert captured.out == ""


@pytest.mark.parametrize("mode", [OutputMode.RICH, OutputMode.JSON])
def test_detail_and_note_go_to_stderr(mode: OutputMode) -> None:
    captured = Captured(mode, verbose=True)

    captured.output.detail("fetching https://example.org/article")
    captured.output.note("openalex dropped out of this search")

    assert "fetching https://example.org/article" in captured.err
    assert "openalex dropped out of this search" in captured.err
    assert captured.out == ""


def test_verbose_diagnostics_do_not_break_the_json_envelope() -> None:
    captured = Captured(OutputMode.JSON, verbose=True)

    captured.output.note("a warning")
    captured.output.success("doctor", {"ok": True})
    captured.output.detail("done")

    assert captured.envelope()["data"] == {"ok": True}


# ---------------------------------------------------------------------------------------------
# Exceptions become failures
# ---------------------------------------------------------------------------------------------


def test_not_found_keeps_its_facts_in_details() -> None:
    failure = CommandFailure.from_exception(NotFound("Card", "01JABCDEF"))

    assert failure.code == "NOT_FOUND"
    assert failure.exit_code is ExitCode.DOMAIN_FAILURE
    assert failure.details == {"entity": "Card", "key": "01JABCDEF"}


def test_revision_mismatch_keeps_both_revisions() -> None:
    failure = CommandFailure.from_exception(RevisionMismatch("Card", "01JABCDEF", 1, 2))

    assert failure.code == "REVISION_MISMATCH"
    assert failure.exit_code is ExitCode.DOMAIN_FAILURE
    assert failure.details["expected_revision"] == 1
    assert failure.details["actual_revision"] == 2


def test_blob_integrity_error_is_a_domain_failure() -> None:
    failure = CommandFailure.from_exception(BlobIntegrityError("sha256/ab/cd/ef", "0" * 64))

    assert failure.code == "BLOB_INTEGRITY_ERROR"
    assert failure.exit_code is ExitCode.DOMAIN_FAILURE


def test_provider_failures_are_retrieval_failures() -> None:
    unavailable = CommandFailure.from_exception(ProviderUnavailable("openalex"))
    rate_limited = CommandFailure.from_exception(ProviderRateLimited("crossref", retry_after_seconds=30.0))

    assert unavailable.code == "PROVIDER_UNAVAILABLE"
    assert unavailable.exit_code is ExitCode.RETRIEVAL_FAILURE
    assert unavailable.details == {"provider": "openalex"}
    assert rate_limited.code == "PROVIDER_RATE_LIMITED"
    assert rate_limited.exit_code is ExitCode.RETRIEVAL_FAILURE
    assert rate_limited.details["retry_after_seconds"] == 30.0


def test_an_unmodelled_exception_is_an_internal_error() -> None:
    failure = CommandFailure.from_exception(ValueError("off by one"), hint="This is a bug.")

    assert failure.code == "INTERNAL_ERROR"
    assert failure.exit_code is ExitCode.INTERNAL_ERROR
    assert failure.message == "off by one"
    assert failure.details == {"exception_type": "ValueError"}
    assert failure.hint == "This is a bug."


def test_a_usage_error_keeps_clicks_own_exit_code() -> None:
    failure = CommandFailure.from_exception(typer.BadParameter("--since is not a date"))

    assert failure.code == "USAGE_ERROR"
    assert failure.exit_code is ExitCode.USAGE_ERROR
    assert failure.details == {}


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (typer.Exit(code=0), ExitCode.OK),
        (typer.Exit(code=3), ExitCode.RETRIEVAL_FAILURE),
        (typer.Exit(code=99), ExitCode.INTERNAL_ERROR),
        (NotFound("Card", "01J"), ExitCode.DOMAIN_FAILURE),
        (ProviderUnavailable("openalex"), ExitCode.RETRIEVAL_FAILURE),
        (RuntimeError("boom"), ExitCode.INTERNAL_ERROR),
    ],
)
def test_exit_code_for(exception: BaseException, expected: ExitCode) -> None:
    assert exit_code_for(exception) is expected


def test_error_code_for_matches_the_exception_class_name() -> None:
    assert error_code_for(ProviderRateLimited("crossref")) == "PROVIDER_RATE_LIMITED"
    assert error_code_for(RuntimeError("boom")) == "INTERNAL_ERROR"


def test_the_json_envelope_is_serialisable_even_for_an_odd_detail() -> None:
    """`default=str` keeps a stray non-JSON value from failing the whole run."""
    captured = Captured(OutputMode.JSON)

    captured.output.success("doctor", {"path": object()})  # type: ignore[dict-item]

    assert isinstance(captured.envelope()["data"]["path"], str)
