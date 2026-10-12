"""An installation holds what the CLI wires, and says how to fix itself when it does not (v1-e01-t17).

Three things are pinned here. The post-install check's list of integrations is the container's,
and grimp, the import graph import-linter is built on, agrees with it. `debate-cli`'s declared
extras supply every third-party module a wired integration imports, which is the fast,
checkout-side twin of the post-install check and catches a dropped extra at PR time. And a
missing optional dependency is reported as reinstall-at-a-tag to an installed build and as
`uv sync` to a checkout, never the other way round.

Every expected value below is written by hand from the container and the pyprojects, not read back
from the code under test.
"""

from __future__ import annotations

import ast
import json
import sys
import tomllib
import types
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path
from typing import Any

import grimp
import pytest
import typer
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from typer.testing import CliRunner

from debate_cli import installation
from debate_cli.app import create_app
from debate_cli.build_info import BuildInfo
from debate_cli.exit_codes import ExitCode
from debate_cli.installation import (
    InstallationReport,
    UnfollowableWiring,
    check_installation,
    incomplete_installation_failure,
    wired_integrations,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLI_PYPROJECT = REPOSITORY_ROOT / "packages/debate_cli/pyproject.toml"
CORE_PYPROJECT = REPOSITORY_ROOT / "packages/debate_core/pyproject.toml"
CORE_SOURCE = REPOSITORY_ROOT / "packages/debate_core/src"

CHECKOUT = BuildInfo(version="0.1.0", channel="local", commit=None, tag=None, built_at=None, run_id=None)
INSTALLED = BuildInfo(
    version="0.1.0.dev40",
    channel="dev",
    commit="0" * 40,
    tag="v0.1.0-dev.40",
    built_at="2026-10-01T12:00:00Z",
    run_id="1",
)

runner = CliRunner()


# ---------------------------------------------------------------------------------------------
# Which integrations the container wires
# ---------------------------------------------------------------------------------------------


def test_the_container_wires_these_integrations() -> None:
    # Read by hand from debate_cli/container.py: four module-level imports from `local`, the
    # `local` package itself, `macos_notifier` inside sync_notifier, `docx_parser` inside the parse
    # factory, `opencaselist` under TYPE_CHECKING and inside two factories, and `s3` inside four
    # factories.
    assert wired_integrations() == (
        "debate_core.integrations.docx_parser",
        "debate_core.integrations.local",
        "debate_core.integrations.local.fs_version_store",
        "debate_core.integrations.local.macos_notifier",
        "debate_core.integrations.local.parsed_store",
        "debate_core.integrations.local.sqlite_caselist_repository",
        "debate_core.integrations.local.suppression_list",
        "debate_core.integrations.opencaselist",
        "debate_core.integrations.s3",
    )


def test_grimp_sees_the_same_integrations_in_the_container() -> None:
    """An independent reading of the same imports: import-linter's graph library."""
    graph = grimp.build_graph("debate_cli", "debate_core", cache_dir=None)
    seen = {
        module
        for module in graph.find_modules_directly_imported_by("debate_cli.container")
        if module.startswith("debate_core.integrations.")
    }
    ours = set(wired_integrations())

    # grimp names `local.archive_reader` for `from debate_core.integrations.local import
    # archive_reader`; importing `local` is what imports it, so its parent standing in is enough.
    assert {module for module in seen if module not in ours and module.rsplit(".", 1)[0] not in ours} == set()
    assert {module for module in ours if module not in seen} == set()


SYNTHETIC_CONTAINER = '''
"""Mentions debate_core.integrations.docx_parser in a docstring, which wires nothing."""
from typing import TYPE_CHECKING

from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations import s3

if TYPE_CHECKING:
    from debate_core.integrations.opencaselist import OpenCaselistClient

NOTE = 1
"""An attribute docstring naming debate_core.integrations.local.macos_notifier."""


class Container:
    def notifier(self):
        """Builds the notifier from debate_core.integrations.local.macos_notifier."""
        import debate_core.integrations.local.macos_notifier
        return debate_core.integrations.local.macos_notifier
'''


def test_every_kind_of_import_statement_counts_and_docstrings_do_not() -> None:
    assert wired_integrations(SYNTHETIC_CONTAINER) == (
        "debate_core.integrations.local",
        "debate_core.integrations.local.macos_notifier",
        "debate_core.integrations.opencaselist",
        "debate_core.integrations.s3",
    )


@pytest.mark.parametrize(
    "wiring",
    [
        'importlib.import_module("debate_core.integrations.docx_parser")',
        "import_module(name)",
        '__import__("debate_core.integrations.s3")',
        'ADAPTER = "debate_core.integrations.docx_parser"',
    ],
)
def test_wiring_the_check_cannot_follow_is_refused_not_skipped(wiring: str) -> None:
    with pytest.raises(UnfollowableWiring):
        wired_integrations(f"import importlib\n{wiring}\n")


# ---------------------------------------------------------------------------------------------
# The post-install check
# ---------------------------------------------------------------------------------------------


def test_this_checkout_is_a_complete_installation() -> None:
    report = check_installation()

    assert report.complete, report.as_dict()
    assert report.declared_extras == ("aws", "docx", "opencaselist")


def test_an_integration_that_does_not_import_makes_the_installation_incomplete() -> None:
    def no_boto3(module: str) -> object:
        if module == "debate_core.integrations.s3":
            # What debate_core.integrations.s3 raises without boto3: no `name`, a checkout's advice.
            raise ModuleNotFoundError(
                "debate_core.integrations.s3 needs boto3, which is an optional dependency of "
                "debate-core: install it with `uv sync --all-packages --extra aws` from the workspace root"
            )
        return object()

    report = check_installation(import_module=no_boto3, installed=lambda name: name != "boto3")

    assert report.covered
    assert not report.complete
    assert report.failed == {
        "debate_core.integrations.s3": "ModuleNotFoundError: needs boto3 (debate-core[aws])"
    }
    assert report.missing_distributions == {"boto3": "aws"}
    assert "uv sync" not in json.dumps(report.as_dict())


def test_a_declared_extra_whose_distributions_are_absent_makes_it_incomplete() -> None:
    report = check_installation(installed=lambda name: name != "lxml")

    assert report.failed == {}
    assert report.missing_distributions == {"lxml": "docx"}
    assert not report.complete


@pytest.mark.parametrize(
    ("imported", "failed", "covered"),
    [
        (("a", "b", "c"), {}, True),
        (("a", "b"), {"c": "ModuleNotFoundError"}, True),
        (("a", "b"), {}, False),
        ((), {}, False),
    ],
)
def test_coverage_means_every_wired_integration_was_tried(
    imported: tuple[str, ...], failed: dict[str, str], covered: bool
) -> None:
    wired = ("a", "b", "c") if imported or failed else ()
    report = InstallationReport(wired=wired, imported=imported, failed=failed)

    assert report.covered is covered
    assert report.complete is (covered and not failed)


def test_the_check_exits_zero_and_reports_json_for_this_checkout(capsys: pytest.CaptureFixture[str]) -> None:
    assert installation.main(["--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is True
    assert report["covered"] is True
    assert len(report["imported"]) == len(report["wired"]) == 9


# ---------------------------------------------------------------------------------------------
# The declaration supplies what the wired integrations import (the PR-time guard)
# ---------------------------------------------------------------------------------------------


def undeclared_imports(cli_dependencies: Iterable[str], wired: Iterable[str]) -> dict[str, set[str]]:
    """Third-party distributions each wired integration imports that `cli_dependencies` do not provide."""
    provided = _provided_distributions(cli_dependencies)
    owners = metadata.packages_distributions()
    gaps: dict[str, set[str]] = {}
    for module in wired:
        for top_level in _third_party_imports(module):
            for distribution in owners.get(top_level, [top_level]):
                if canonicalize_name(distribution) not in provided:
                    gaps.setdefault(module, set()).add(canonicalize_name(distribution))
    return gaps


def _cli_dependencies() -> list[str]:
    return list(tomllib.loads(CLI_PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"])


def _with_core_extras(extras: str) -> list[str]:
    return [
        f"debate-core[{extras}]" if canonicalize_name(Requirement(line).name) == "debate-core" else line
        for line in _cli_dependencies()
    ]


def _provided_distributions(cli_dependencies: Iterable[str]) -> set[str]:
    core = tomllib.loads(CORE_PYPROJECT.read_text(encoding="utf-8"))["project"]
    pending: list[Requirement] = []
    for line in cli_dependencies:
        requirement = Requirement(line)
        if canonicalize_name(requirement.name) == "debate-core":
            pending += [Requirement(dependency) for dependency in core["dependencies"]]
            for extra in requirement.extras:
                pending += [Requirement(dependency) for dependency in core["optional-dependencies"][extra]]
        else:
            pending.append(requirement)
    provided: set[str] = set()
    seen: set[tuple[str, frozenset[str]]] = set()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        if (name, frozenset(requirement.extras)) in seen:
            continue
        seen.add((name, frozenset(requirement.extras)))
        provided.add(name)
        for line in metadata.requires(name) or ():
            dependency = Requirement(line)
            if dependency.marker is None or any(
                dependency.marker.evaluate({"extra": extra}) for extra in requirement.extras or {""}
            ):
                pending.append(dependency)
    return provided


def _third_party_imports(module: str) -> set[str]:
    """Top-level third-party modules imported anywhere in `module` (the whole package if it is one)."""
    path = CORE_SOURCE / Path(*module.split("."))
    files = sorted(path.rglob("*.py")) if path.is_dir() else [path.with_suffix(".py")]
    found: set[str] = set()
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        type_checking = {
            id(child)
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test)
            for statement in node.body
            for child in ast.walk(statement)
        }
        for node in ast.walk(tree):
            if id(node) in type_checking:
                continue
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return {name for name in found if name not in sys.stdlib_module_names and name not in {"debate_core"}}


def test_debate_cli_declares_every_distribution_its_wired_integrations_import() -> None:
    assert undeclared_imports(_cli_dependencies(), wired_integrations()) == {}


def test_dropping_the_aws_extra_leaves_the_s3_adapter_without_boto3() -> None:
    gaps = undeclared_imports(_with_core_extras("docx,opencaselist"), wired_integrations())

    assert gaps == {"debate_core.integrations.s3": {"boto3", "botocore"}}


def test_dropping_the_opencaselist_extra_leaves_the_client_without_httpx_and_keyring() -> None:
    gaps = undeclared_imports(_with_core_extras("aws,docx"), wired_integrations())

    assert gaps == {"debate_core.integrations.opencaselist": {"httpx", "keyring"}}


def test_once_the_docx_parser_is_wired_dropping_the_docx_extra_is_caught() -> None:
    """The container does not wire the parser yet (v1-e31-t06 will); when it does, this applies."""
    wired = (*wired_integrations(), "debate_core.integrations.docx_parser")

    assert undeclared_imports(_with_core_extras("aws,opencaselist"), wired) == {
        "debate_core.integrations.docx_parser": {"lxml"}
    }
    assert undeclared_imports(_cli_dependencies(), wired) == {}


# ---------------------------------------------------------------------------------------------
# The message a missing optional dependency produces (ac3)
# ---------------------------------------------------------------------------------------------


def test_a_checkout_is_told_which_uv_sync_to_run() -> None:
    failure = incomplete_installation_failure(
        ModuleNotFoundError("No module named 'lxml'", name="lxml"), CHECKOUT
    )

    assert failure is not None
    message, hint, details = failure
    assert message == (
        "This checkout's environment does not include lxml (debate-core's `docx` extra), "
        "which this command needs."
    )
    assert hint == "From the workspace root, run `uv sync --all-packages --extra docx`."
    assert details == {"missing": "lxml", "extras": "docx", "installation": "checkout"}


def test_an_installed_build_is_told_to_reinstall_at_a_fixed_tag_and_never_to_run_uv_sync() -> None:
    error = ModuleNotFoundError(
        "debate_core.integrations.s3 needs boto3: install it with `uv sync --all-packages --extra aws`"
    )
    failure = incomplete_installation_failure(error, INSTALLED, installed=lambda name: name != "boto3")

    assert failure is not None
    message, hint, details = failure
    assert message == (
        "This installed build of debate-research (v0.1.0-dev.40, dev channel) is incomplete: it does "
        "not include boto3 (debate-core's `aws` extra), which this command needs."
    )
    assert hint == (
        "Reinstall a complete build with `scripts/install_channel.sh <tag>` at a fixed release tag: "
        "`v0.1.0-dev.40` again if a package was removed from it by hand, or a newer tag if this build "
        "was published without it (`gh release list` shows them)."
    )
    assert details == {"missing": "boto3", "extras": "aws", "installation": "installed build"}
    assert "uv sync" not in message + hint + json.dumps(details)


def test_a_module_no_extra_provides_is_still_reported_as_a_bug() -> None:
    error = ModuleNotFoundError("No module named 'shrubbery'", name="shrubbery")

    assert incomplete_installation_failure(error, INSTALLED) is None
    assert incomplete_installation_failure(error, CHECKOUT) is None


def test_an_unnamed_error_with_every_optional_dependency_present_is_a_bug() -> None:
    assert incomplete_installation_failure(ModuleNotFoundError("something else"), INSTALLED) is None


def missing_lxml() -> None:
    """A command that reaches the docx parser in an installation without lxml."""
    raise ModuleNotFoundError("No module named 'lxml'", name="lxml")


@pytest.fixture
def pull_without_lxml() -> typer.Typer:
    app = create_app()
    app.command("pull")(missing_lxml)
    return app


def _stamp(monkeypatch: pytest.MonkeyPatch, info: BuildInfo) -> None:
    """Make this process look like a published build, as test_version.py does."""
    module = types.ModuleType("debate_cli._build_info")
    module.BUILD_INFO = {key: value for key, value in info.as_dict().items() if value is not None}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "debate_cli._build_info", module)


def _error_of(result: Any) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, lines
    envelope = json.loads(lines[0])
    assert isinstance(envelope, dict)
    error = envelope["error"]
    assert isinstance(error, dict)
    return error


def test_the_cli_tells_an_installed_build_to_reinstall(
    pull_without_lxml: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stamp(monkeypatch, INSTALLED)

    result = runner.invoke(pull_without_lxml, ["--json", "pull"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    error = _error_of(result)
    assert error["code"] == "INTERNAL_ERROR"
    assert error["details"]["installation"] == "installed build"
    assert "scripts/install_channel.sh" in error["hint"]
    assert "v0.1.0-dev.40" in error["hint"]
    assert "uv sync" not in result.stdout + result.stderr
    assert "bug" not in error["hint"]


def test_the_cli_tells_a_checkout_to_sync(pull_without_lxml: typer.Typer) -> None:
    result = runner.invoke(pull_without_lxml, ["--json", "pull"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    error = _error_of(result)
    assert error["details"]["installation"] == "checkout"
    assert error["hint"] == "From the workspace root, run `uv sync --all-packages --extra docx`."
    assert "install_channel.sh" not in result.stdout


def test_the_human_form_for_an_installed_build_names_the_fix(
    pull_without_lxml: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stamp(monkeypatch, INSTALLED)

    result = runner.invoke(pull_without_lxml, ["pull"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    flat = " ".join(result.stderr.split())
    assert "is incomplete" in flat
    assert "install_channel.sh" in flat
    assert "uv sync" not in flat
