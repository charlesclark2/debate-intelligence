"""`debate-research doctor` can say "this is broken", and says it about one thing only (`v1-e01-t14`).

The one check `doctor` fails on is the one it can state precisely: the running interpreter's Unicode
database against the version the evidence normalizer is pinned to. On any other database
`normalize` refuses to run (`UnicodeDatabaseMismatchError`), so an install on the wrong interpreter
works until the first pipeline that touches evidence text. Every other fact `doctor` reports is
description, and a test below changes each of them and checks the exit status stays 0.

The mismatch is faked by patching `unicodedata.unidata_version`, which both `doctor` and the
normalizer read at call time.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

import pytest
from hypothesis import event, given
from hypothesis import strategies as st
from typer.testing import CliRunner, Result

from debate_cli import UNKNOWN_VERSION
from debate_cli.app import create_app
from debate_cli.commands import doctor as doctor_module
from debate_cli.exit_codes import ExitCode
from debate_core.evidence.normalization import NORMALIZER_VERSION, pinned_unicode_version

runner = CliRunner()

PINNED = pinned_unicode_version(NORMALIZER_VERSION)
POLICY_PAGE = "docs/evidence/normalization.md"
# A database no Python the normalizer supports ships; any value other than the pin would do.
OTHER_DATABASE = "15.1.0" if PINNED != "15.1.0" else "16.0.0"


def envelope_of(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


@pytest.fixture
def other_unicode_database(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(unicodedata, "unidata_version", OTHER_DATABASE)
    return OTHER_DATABASE


# ---------------------------------------------------------------------------------------------
# The check, both ways
# ---------------------------------------------------------------------------------------------


def test_doctor_reports_the_running_database_beside_the_normalizers_pin() -> None:
    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data["normalizer_version"] == NORMALIZER_VERSION
    assert data["normalizer_unicode_version"] == PINNED
    assert data["python_unicode_version"] == unicodedata.unidata_version
    assert data["unicode_database_matches"] is True


def test_another_unicode_database_fails_doctor_naming_both_versions_and_the_policy(
    other_unicode_database: str,
) -> None:
    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    envelope = envelope_of(result)
    assert envelope["status"] == "error"
    error = envelope["error"]
    assert error["code"] == "UNICODE_DATABASE_MISMATCH"
    assert error["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert PINNED in error["message"]
    assert other_unicode_database in error["message"]
    assert POLICY_PAGE in error["message"]
    # A program that reads the failure still gets every fact doctor collected.
    assert error["details"]["normalizer_unicode_version"] == PINNED
    assert error["details"]["python_unicode_version"] == other_unicode_database
    assert error["details"]["unicode_database_matches"] is False
    assert error["details"]["cli_version"]


def test_a_person_sees_the_report_and_then_the_mismatch(other_unicode_database: str) -> None:
    result = runner.invoke(create_app(), ["doctor"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "debate-research doctor" in result.stdout
    assert "Interpreter" in result.stdout
    assert PINNED in result.stderr
    assert other_unicode_database in result.stderr
    assert POLICY_PAGE in result.stderr


def test_an_unreadable_pin_is_a_bug_not_a_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # If the build cannot say what its own normalizer is pinned to, the build is broken: exit 70
    # through the root handler, never 1, so no one is told to fix their interpreter for it.
    monkeypatch.setattr(doctor_module, "NORMALIZER_VERSION", "evidence-normalizer-v0")

    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    error = envelope_of(result)["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "bug in debate-research" in error["hint"]


# ---------------------------------------------------------------------------------------------
# Every other fact stays informational
# ---------------------------------------------------------------------------------------------


def _unconfigured_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("debate_cli.app.settings_loader", lambda: None)


def _unknown_package_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor_module, "package_version", lambda _distribution: UNKNOWN_VERSION)


def _unexpected_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.python_version", lambda: "2.7.18")


def _unexpected_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.platform", lambda: "Plan9-4e-386")


def _no_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor_module, "SERVICE_NAMES", ())


@pytest.mark.parametrize(
    "change",
    [
        _unconfigured_settings,
        _unknown_package_versions,
        _unexpected_python,
        _unexpected_platform,
        _no_services,
    ],
    ids=lambda change: change.__name__.lstrip("_"),
)
@pytest.mark.parametrize("mode", [["--json"], []], ids=["json", "human"])
def test_every_other_fact_is_reported_and_never_fails_doctor(
    monkeypatch: pytest.MonkeyPatch, change: Any, mode: list[str]
) -> None:
    change(monkeypatch)

    result = runner.invoke(create_app(), [*mode, "doctor"])

    assert result.exit_code == ExitCode.OK, result.output
    if mode:
        assert envelope_of(result)["status"] == "ok"


_FACT = st.one_of(
    # The values a real report carries when something is missing, which random text rarely hits.
    st.sampled_from([UNKNOWN_VERSION, False, "", []]),
    st.booleans(),
    st.text(max_size=12),
    st.lists(st.text(max_size=6), max_size=3),
)
_DATABASE = st.sampled_from(["15.0.0", "15.1.0", "16.0.0", "14.0.0", ""])


@given(
    other_facts=st.dictionaries(
        st.sampled_from(
            [
                "cli_version",
                "core_version",
                "python_version",
                "python_executable",
                "platform",
                "settings_configured",
                "services",
            ]
        ),
        _FACT,
    ),
    pinned=_DATABASE,
    running=_DATABASE,
)
def test_doctor_fails_exactly_when_the_running_database_is_not_the_pin(
    other_facts: dict[str, Any], pinned: str, running: str
) -> None:
    report = {
        **other_facts,
        "normalizer_version": NORMALIZER_VERSION,
        "normalizer_unicode_version": pinned,
        "python_unicode_version": running,
        "unicode_database_matches": pinned == running,
    }

    event("databases match" if pinned == running else "databases differ")
    event("settings not configured" if other_facts.get("settings_configured") is False else "settings other")

    failure = doctor_module.unicode_database_failure(report)

    assert (failure is None) == (pinned == running)
    if failure is not None:
        assert failure.exit_code == ExitCode.DOMAIN_FAILURE
        assert pinned in failure.message
        assert running in failure.message
