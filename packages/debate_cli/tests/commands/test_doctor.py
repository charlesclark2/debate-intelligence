"""`debate-research doctor` can say "this is broken", and says it only about what it can state precisely.

Two checks fail `doctor`, each a fact it can state exactly:

* **The Unicode database** (`v1-e01-t14`): the running interpreter's, against the version the
  evidence normalizer is pinned to. On any other database `normalize` refuses to run
  (`UnicodeDatabaseMismatchError`), so an install on the wrong interpreter works until the first
  pipeline that touches evidence text.
* **The wired integrations** (`v1-e01-t22`): every `debate_core.integrations` module the CLI's
  composition root imports, found and imported by :mod:`debate_cli.installation`, the logic the
  installer's post-install check uses. One that does not import is named, with why.

Every other fact `doctor` reports is description, and a test below changes each of them and checks
the exit status stays 0. That includes a declared extra whose distributions are missing: the
installer refuses such a build, but a running build without them only fails if a wired integration
then does not import, which is the second check.

Whether the running Python is one uv manages (`v1-e01-t23`) is one of those facts. It is decided by
place, as uv decides it: the interpreter's base prefix, links followed, lies inside the directory
`uv python dir` names. The tests point `sys.base_prefix` and `UV_PYTHON_INSTALL_DIR` at temporary
directories, and the directory rules are written by hand from what uv 0.11.7's `uv python dir`
printed.

The mismatch is faked by patching `unicodedata.unidata_version`, which both `doctor` and the
normalizer read at call time. An integration that does not import is made by putting `None` in
`sys.modules` for it, so the real import machinery raises the `ModuleNotFoundError`.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from hypothesis import event, given
from hypothesis import strategies as st
from typer.testing import CliRunner, Result

from debate_cli import UNKNOWN_VERSION, installation
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


# Read by hand from debate_cli/container.py, as tests/test_installation.py does.
WIRED_INTEGRATIONS = [
    "debate_core.integrations.local",
    "debate_core.integrations.local.fs_version_store",
    "debate_core.integrations.local.macos_notifier",
    "debate_core.integrations.local.sqlite_caselist_repository",
    "debate_core.integrations.local.suppression_list",
    "debate_core.integrations.opencaselist",
    "debate_core.integrations.s3",
]
S3 = "debate_core.integrations.s3"
OPENCASELIST = "debate_core.integrations.opencaselist"


@pytest.fixture
def other_unicode_database(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(unicodedata, "unidata_version", OTHER_DATABASE)
    return OTHER_DATABASE


def make_unimportable(monkeypatch: pytest.MonkeyPatch, *modules: str) -> None:
    """`import module` now raises ModuleNotFoundError, through the real import machinery."""
    for module in modules:
        monkeypatch.setitem(sys.modules, module, None)


@pytest.fixture
def s3_and_opencaselist_do_not_import(monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    make_unimportable(monkeypatch, S3, OPENCASELIST)
    return (S3, OPENCASELIST)


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
    # The table already listed every fact; the panel does not repeat them.
    assert "python_executable" not in result.stderr


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
# The wired integrations (v1-e01-t22)
# ---------------------------------------------------------------------------------------------


def test_doctor_reports_every_wired_integration_and_that_each_imports() -> None:
    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data["integrations_wired"] == WIRED_INTEGRATIONS
    assert data["integrations_failed"] == {}
    assert data["integrations_import"] is True
    assert data["extras_missing_distributions"] == {}


def test_an_integration_that_does_not_import_fails_doctor_naming_each_one(
    s3_and_opencaselist_do_not_import: tuple[str, ...],
) -> None:
    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "INTEGRATIONS_DO_NOT_IMPORT"
    assert error["exit_code"] == ExitCode.DOMAIN_FAILURE
    for module in s3_and_opencaselist_do_not_import:
        assert module in error["message"]
    assert "2 of the 7 integrations" in error["message"]
    assert error["details"]["integrations_import"] is False
    assert error["details"]["integrations_failed"] == {
        OPENCASELIST: f"ModuleNotFoundError: no module named {OPENCASELIST!r}",
        S3: f"ModuleNotFoundError: no module named {S3!r}",
    }
    assert error["details"]["integrations_wired"] == WIRED_INTEGRATIONS
    # The Unicode check passed, and is still reported.
    assert error["details"]["unicode_database_matches"] is True
    assert "install_channel.sh" in error["hint"]


def test_a_person_sees_the_report_and_then_each_integration_that_does_not_import(
    s3_and_opencaselist_do_not_import: tuple[str, ...],
) -> None:
    result = runner.invoke(create_app(), ["doctor"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "debate-research doctor" in result.stdout
    assert "Integrations import" in result.stdout
    flat = " ".join(result.stderr.split())
    assert "INTEGRATIONS_DO_NOT_IMPORT" in flat
    for module in s3_and_opencaselist_do_not_import:
        assert f"{module}: ModuleNotFoundError" in flat
    assert "python_executable" not in flat


def test_both_checks_failing_are_both_reported(
    other_unicode_database: str, s3_and_opencaselist_do_not_import: tuple[str, ...]
) -> None:
    as_json = runner.invoke(create_app(), ["--json", "doctor"])
    for_a_person = runner.invoke(create_app(), ["doctor"])

    assert as_json.exit_code == for_a_person.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(as_json)["error"]
    assert error["code"] == "INSTALLATION_CHECKS_FAILED"
    assert other_unicode_database in error["message"]
    assert POLICY_PAGE in error["message"]
    for module in s3_and_opencaselist_do_not_import:
        assert module in error["message"]
    flat = " ".join(for_a_person.stderr.split())
    assert f"python_unicode_version: {other_unicode_database}" in flat
    assert f"{S3}: ModuleNotFoundError" in flat


def test_wiring_doctor_cannot_follow_is_a_bug_not_a_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same refusal the installer's check makes: a dynamic import in the container would wire an
    # integration no one could check, so doctor cannot say the integrations import. Exit 70.
    monkeypatch.setattr(
        installation, "_container_source", lambda: "import importlib\nimportlib.import_module('anything')\n"
    )

    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    assert envelope_of(result)["error"]["code"] == "INTERNAL_ERROR"


def test_a_missing_extra_distribution_is_informational_here_and_refused_by_the_installers_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Nothing wired imports lxml yet (the docx parser is not wired), so every integration still
    # imports and every command still runs. doctor reports the gap; the installer's check, which
    # holds a build to everything it declares, refuses it.
    monkeypatch.setattr(installation, "_installed", lambda distribution: distribution != "lxml")

    result = runner.invoke(create_app(), ["--json", "doctor"])

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data["extras_missing_distributions"] == {"lxml": "docx"}
    assert data["integrations_import"] is True
    assert installation.main([]) == 1
    assert "lxml (debate-core[docx])  MISSING" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------
# Whether the running Python is one uv manages (v1-e01-t23): reported, never failed
# ---------------------------------------------------------------------------------------------


def python_installed_at(monkeypatch: pytest.MonkeyPatch, base_prefix: Path, uv_pythons: Path) -> None:
    """doctor now runs on the Python installed at `base_prefix`, and uv keeps its own in `uv_pythons`."""
    base_prefix.mkdir(parents=True, exist_ok=True)
    uv_pythons.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sys, "base_prefix", str(base_prefix))
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(uv_pythons))


@pytest.mark.parametrize(
    ("installation", "managed", "shown"),
    [
        pytest.param(
            "uv-pythons/cpython-3.12.13-macos-aarch64-none", True, "yes", id="inside uv's directory"
        ),
        pytest.param("anaconda3", False, "no", id="anaconda"),
        pytest.param(
            "homebrew/Cellar/python@3.12/3.12.7/Frameworks/Python.framework/Versions/3.12",
            False,
            "no",
            id="homebrew",
        ),
    ],
)
def test_doctor_reports_whether_its_python_is_one_uv_manages_and_exits_0_either_way(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installation: str, managed: bool, shown: str
) -> None:
    python_installed_at(monkeypatch, tmp_path / installation, tmp_path / "uv-pythons")

    as_json = runner.invoke(create_app(), ["--json", "doctor"])
    for_a_person = runner.invoke(create_app(), ["doctor"])

    assert as_json.exit_code == for_a_person.exit_code == ExitCode.OK, as_json.output + for_a_person.output
    data = envelope_of(as_json)["data"]
    assert data["python_base_prefix"] == str(tmp_path / installation)
    assert data["uv_python_directory"] == str(tmp_path / "uv-pythons")
    assert data["python_uv_managed"] is managed
    rows = {" ".join(line.split()) for line in for_a_person.stdout.splitlines()}
    assert any(f"Managed by uv │ {shown} │" in row for row in rows), for_a_person.stdout


def test_the_managed_fact_follows_links_and_compares_whole_path_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    uv_pythons = tmp_path / "data" / "uv" / "python"
    installed = uv_pythons / "cpython-3.12.13-macos-aarch64-none"
    installed.mkdir(parents=True)
    # uv's own minor-version link, which a tool environment's base prefix can name.
    (uv_pythons / "cpython-3.12-macos-aarch64-none").symlink_to(installed)
    (tmp_path / "linked-uv-pythons").symlink_to(uv_pythons)
    sibling = tmp_path / "data" / "uv" / "python-elsewhere" / "cpython-3.12.13-macos-aarch64-none"
    sibling.mkdir(parents=True)

    assert doctor_module.is_uv_managed(str(installed), uv_pythons)
    assert doctor_module.is_uv_managed(str(uv_pythons / "cpython-3.12-macos-aarch64-none"), uv_pythons)
    assert doctor_module.is_uv_managed(str(installed), tmp_path / "linked-uv-pythons")
    assert not doctor_module.is_uv_managed(str(sibling), uv_pythons)
    assert not doctor_module.is_uv_managed(str(uv_pythons), uv_pythons)
    assert not doctor_module.is_uv_managed(str(tmp_path / "missing"), tmp_path / "also-missing")


# Written by hand from `uv python dir` under uv 0.11.7 with each environment (session report).
@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        pytest.param(
            {"UV_PYTHON_INSTALL_DIR": "/x/y", "XDG_DATA_HOME": "/xdg"},
            "/x/y",
            id="UV_PYTHON_INSTALL_DIR wins",
        ),
        pytest.param(
            {"UV_PYTHON_INSTALL_DIR": ""}, "/h/.local/share/uv/python", id="an empty one is ignored"
        ),
        pytest.param({"XDG_DATA_HOME": "/xdg"}, "/xdg/uv/python", id="an absolute XDG_DATA_HOME"),
        pytest.param(
            {"XDG_DATA_HOME": "relxdg"}, "/h/.local/share/uv/python", id="a relative XDG_DATA_HOME is ignored"
        ),
        pytest.param({}, "/h/.local/share/uv/python", id="the default under HOME"),
    ],
)
def test_uvs_python_directory_is_found_as_uv_finds_it(environment: dict[str, str], expected: str) -> None:
    found = doctor_module.uv_python_directory({"HOME": "/h", **environment}, windows=False)

    assert found == Path(expected)


def test_a_relative_uv_python_install_dir_is_taken_from_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # uv printed `rel` as given, a path it resolves against the working directory.
    monkeypatch.chdir(tmp_path)

    found = doctor_module.uv_python_directory({"UV_PYTHON_INSTALL_DIR": "rel", "HOME": "/h"}, windows=False)

    assert found == Path.cwd() / "rel"


def test_on_windows_the_directory_is_the_one_uvs_documentation_gives() -> None:
    # Not measured, for want of a Windows machine; `uv help python dir` gives %APPDATA%/uv/data/python.
    environment = {"APPDATA": "C:/Users/coach/AppData/Roaming", "XDG_DATA_HOME": "/xdg"}

    found = doctor_module.uv_python_directory(environment, windows=True)

    assert found == Path("C:/Users/coach/AppData/Roaming") / "uv" / "data" / "python"


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


def _missing_extra_distributions(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reported as missing, while every wired integration still imports from this checkout.
    monkeypatch.setattr(
        installation, "_installed", lambda distribution: distribution not in {"lxml", "boto3"}
    )


def _unmanaged_python(monkeypatch: pytest.MonkeyPatch) -> None:
    # The coach's case before v1-e01-t23: the build's base Python was anaconda's.
    monkeypatch.setattr(sys, "base_prefix", "/Users/coach/anaconda3")
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "/Users/coach/.local/share/uv/python")


def _managed_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys, "base_prefix", "/Users/coach/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none"
    )
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "/Users/coach/.local/share/uv/python")


def _nothing_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    # A container that imports no integration has nothing that can fail to import. The installer's
    # check refuses it (nothing was covered); doctor states only what does not import.
    monkeypatch.setattr(installation, "_container_source", lambda: '"""No integrations."""\n')


@pytest.mark.parametrize(
    "change",
    [
        _unconfigured_settings,
        _unknown_package_versions,
        _unexpected_python,
        _unexpected_platform,
        _no_services,
        _missing_extra_distributions,
        _unmanaged_python,
        _managed_python,
        _nothing_wired,
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
_REASON = st.sampled_from(
    [
        "ModuleNotFoundError: no module named 'boto3'",
        "ModuleNotFoundError: needs boto3 (debate-core[aws])",
        "ImportError",
    ]
)


@st.composite
def _integrations(draw: st.DrawFn) -> tuple[list[str], dict[str, str]]:
    """Some of the wired integrations, and which of them failed to import, with why."""
    wired = draw(st.lists(st.sampled_from(WIRED_INTEGRATIONS), unique=True).map(sorted))
    failing = draw(st.lists(st.sampled_from(wired), unique=True) if wired else st.just([]))
    return wired, {module: draw(_REASON) for module in sorted(failing)}


@given(
    other_facts=st.fixed_dictionaries(
        {
            key: _FACT
            for key in (
                "cli_version",
                "core_version",
                "python_version",
                "python_executable",
                "python_base_prefix",
                "uv_python_directory",
                "python_uv_managed",
                "platform",
                "settings_configured",
                "services",
            )
        }
    ),
    pinned=_DATABASE,
    running=_DATABASE,
    integrations=_integrations(),
    missing_distributions=st.dictionaries(
        st.sampled_from(["boto3", "lxml", "httpx", "keyring", "python-docx"]),
        st.sampled_from(["aws", "docx", "opencaselist"]),
        max_size=3,
    ),
)
def test_doctor_fails_exactly_when_the_database_differs_or_an_integration_does_not_import(
    other_facts: dict[str, Any],
    pinned: str,
    running: str,
    integrations: tuple[list[str], dict[str, str]],
    missing_distributions: dict[str, str],
) -> None:
    wired, failed = integrations
    report = {
        **other_facts,
        "normalizer_version": NORMALIZER_VERSION,
        "normalizer_unicode_version": pinned,
        "python_unicode_version": running,
        "unicode_database_matches": pinned == running,
        "integrations_wired": wired,
        "integrations_failed": failed,
        "integrations_import": not failed,
        "extras_missing_distributions": missing_distributions,
    }

    event("databases match" if pinned == running else "databases differ")
    event("an integration fails" if failed else "every integration imports")
    event("distributions missing" if missing_distributions else "no distribution missing")
    event("settings not configured" if other_facts.get("settings_configured") is False else "settings other")
    event(
        "python not uv-managed" if other_facts.get("python_uv_managed") is False else "python managed other"
    )

    failure = doctor_module.doctor_failure(report)

    assert (failure is None) == (pinned == running and not failed)
    if failure is None:
        return
    assert failure.exit_code == ExitCode.DOMAIN_FAILURE
    assert failure.code == (
        "INSTALLATION_CHECKS_FAILED"
        if pinned != running and failed
        else "UNICODE_DATABASE_MISMATCH"
        if pinned != running
        else "INTEGRATIONS_DO_NOT_IMPORT"
    )
    if pinned != running:
        assert pinned in failure.message
        assert running in failure.message
    for module, reason in failed.items():
        assert f"{module} ({reason})" in failure.message
    assert failure.details == report
