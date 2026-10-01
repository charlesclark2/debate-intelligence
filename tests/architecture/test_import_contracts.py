"""Every import-linter contract in pyproject.toml fails when the rule it states is broken.

A contract that is configured but never seen to fail is decoration: a typo in a module name, a
layer listed in the wrong order or an `ignore_imports` entry that matches too much all leave
`lint-imports` green. So each case here copies the four real package trees into `tmp_path`, adds
one import that breaks one rule, and runs `lint-imports` against the repository's own
`[tool.importlinter]` section with the copy first on `PYTHONPATH`. It asserts the run fails and
that the contract meant to catch it is reported BROKEN by name, because a failure that does not
say which rule broke sends the next reader through the whole configuration.

The violating imports and the contract each should break are written by hand. The last test
checks that every configured contract has at least one case here, so a contract added without one
fails this suite.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGES = ("debate_core", "debate_cli", "debate_api", "debate_workers")
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"
# A contract's verdict line: "<name> BROKEN", with "(N ignored imports)" after it when it has any.
BROKEN_VERDICT = re.compile(r"^(?P<name>.+) BROKEN(?: \(\d+ ignored imports?\))?$", re.MULTILINE)

AWS_SDK = "The AWS SDK never reaches the domain, the application layer or the other adapters"
HTTP_CLIENT = "The HTTP client and the keychain library stay inside debate_core.integrations.opencaselist"
CLI_HTTP_CLIENT = "The CLI reaches httpx and keyring only through debate_core.integrations.opencaselist"
CLI_AWS_SDK = "The CLI reaches the AWS SDK only through debate_core.integrations.s3"
DOCUMENT_LIBRARIES = "Document libraries stay inside debate_core.integrations.docx_parser"
CORE_LAYERS = "debate_core layers: integrations and testing above application above evidence above domain"
DELIVERY_FRAMEWORKS = "The domain and application layers never import a delivery framework"
CORE_NEVER_IMPORTS_DELIVERY = "debate_core never imports a delivery package"
DELIVERY_INDEPENDENCE = "The delivery packages are independent of one another"
COMPOSITION_ROOT = "Delivery packages reach debate_core.integrations only through their composition root"
DELIVERY_NEVER_IMPORTS_TESTING = "Delivery packages never import debate_core.testing"


@dataclass(frozen=True)
class Violation:
    """One module added to the copied tree, and the contract that must report it."""

    module: str
    source: str
    broken_contract: str
    as_package: bool = False

    def __str__(self) -> str:
        return f"{self.module}: {self.source}"


VIOLATIONS = [
    # The AWS SDK, httpx and document libraries outside their adapters.
    Violation("debate_core.application.boundary_probe", "import boto3", AWS_SDK),
    Violation("debate_core.domain.boundary_probe", "import botocore", AWS_SDK),
    Violation("debate_api.boundary_probe", "import boto3", AWS_SDK),
    Violation("debate_core.domain.boundary_probe", "import httpx", HTTP_CLIENT),
    Violation("debate_core.testing.boundary_probe", "import keyring", HTTP_CLIENT),
    Violation("debate_cli.commands.boundary_probe", "import httpx", CLI_HTTP_CLIENT),
    Violation("debate_cli.commands.boundary_probe", "import boto3", CLI_AWS_SDK),
    Violation("debate_core.application.boundary_probe", "import lxml", DOCUMENT_LIBRARIES),
    # The layers inside debate_core, in each direction a dependency can point the wrong way.
    Violation("debate_core.domain.boundary_probe", "import debate_core.application", CORE_LAYERS),
    Violation("debate_core.domain.boundary_probe", "import debate_core.evidence", CORE_LAYERS),
    Violation("debate_core.evidence.boundary_probe", "import debate_core.application.settings", CORE_LAYERS),
    Violation("debate_core.application.boundary_probe", "import debate_core.integrations.local", CORE_LAYERS),
    Violation("debate_core.application.boundary_probe", "import debate_core.testing.fakes", CORE_LAYERS),
    Violation("debate_core.integrations.boundary_probe", "import debate_core.testing.fakes", CORE_LAYERS),
    # A new debate_core subpackage that no layer names: `exhaustive` rejects it.
    Violation("debate_core.unplaced_layer", "import debate_core.domain", CORE_LAYERS, as_package=True),
    # Delivery frameworks in the core. fastapi is not installed yet and must still be caught.
    Violation("debate_core.application.boundary_probe", "import typer", DELIVERY_FRAMEWORKS),
    Violation("debate_core.domain.boundary_probe", "from rich.console import Console", DELIVERY_FRAMEWORKS),
    Violation("debate_core.evidence.boundary_probe", "import click", DELIVERY_FRAMEWORKS),
    Violation("debate_core.application.boundary_probe", "from fastapi import APIRouter", DELIVERY_FRAMEWORKS),
    # The core pointing back at a front end, and front ends importing each other.
    Violation(
        "debate_core.application.boundary_probe", "import debate_cli.output", CORE_NEVER_IMPORTS_DELIVERY
    ),
    Violation(
        "debate_core.integrations.boundary_probe", "import debate_workers", CORE_NEVER_IMPORTS_DELIVERY
    ),
    Violation("debate_api.boundary_probe", "import debate_cli.output", DELIVERY_INDEPENDENCE),
    Violation("debate_cli.boundary_probe", "import debate_workers", DELIVERY_INDEPENDENCE),
    # A command or route constructing an adapter instead of asking the composition root for it.
    Violation(
        "debate_cli.commands.boundary_probe",
        "from debate_core.integrations.local import fs_object_store",
        COMPOSITION_ROOT,
    ),
    # The same adapter module the grandfathered caselist edge names, from a different command.
    Violation(
        "debate_cli.commands.boundary_probe",
        "from debate_core.integrations.local.archive_reader import read_archive",
        COMPOSITION_ROOT,
    ),
    Violation("debate_api.boundary_probe", "import debate_core.integrations.s3", COMPOSITION_ROOT),
    # Test support in a front end, where build_card could hand out VERIFIED cards (v1-e03-t04).
    Violation(
        "debate_cli.commands.boundary_probe",
        "from debate_core.testing.builders import build_card",
        DELIVERY_NEVER_IMPORTS_TESTING,
    ),
    Violation("debate_api.boundary_probe", "import debate_core.testing", DELIVERY_NEVER_IMPORTS_TESTING),
    Violation(
        "debate_workers.boundary_probe",
        "from debate_core.testing import fakes",
        DELIVERY_NEVER_IMPORTS_TESTING,
    ),
]


@pytest.fixture
def package_copy(tmp_path: Path) -> Path:
    """The four packages' source trees, copied so a test can add a module to them."""
    root = tmp_path / "src"
    for package in PACKAGES:
        shutil.copytree(
            REPO_ROOT / "packages" / package / "src" / package,
            root / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    return root


def add_module(root: Path, violation: Violation) -> None:
    """Write the violation's module into the copied tree, next to modules that already exist."""
    *parents, name = violation.module.split(".")
    directory = root.joinpath(*parents)
    assert directory.is_dir(), f"{'.'.join(parents)} is not a package in the copy"
    target = directory / name / "__init__.py" if violation.as_package else directory / f"{name}.py"
    assert not target.exists(), f"{violation.module} already exists in the copy"
    target.parent.mkdir(exist_ok=True)
    target.write_text(violation.source + "\n")


@dataclass(frozen=True)
class LintResult:
    returncode: int
    output: str

    @property
    def broken(self) -> set[str]:
        return {match["name"] for match in BROKEN_VERDICT.finditer(self.output)}


def lint_imports(root: Path, config: Path = PYPROJECT) -> LintResult:
    """Run the repository's import contracts (or those in `config`) over the packages under `root`."""
    env = {
        **os.environ,
        # Ahead of site-packages, and so of the .pth entries that point at the real packages.
        "PYTHONPATH": str(root),
        # Wide enough that rich never wraps a contract name across two lines.
        "COLUMNS": "500",
        "NO_COLOR": "1",
    }
    completed = subprocess.run(
        [str(LINT_IMPORTS), "--config", str(config), "--no-cache", "--no-logo"],
        cwd=root.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return LintResult(completed.returncode, completed.stdout + completed.stderr)


def configured_contracts() -> list[str]:
    config = tomllib.loads(PYPROJECT.read_text())
    return [contract["name"] for contract in config["tool"]["importlinter"]["contracts"]]


def test_the_unmodified_copy_keeps_every_contract(package_copy: Path) -> None:
    """The control: whatever a case below breaks, it is the added import and not the copy."""
    result = lint_imports(package_copy)

    assert result.returncode == 0, result.output
    assert f"Contracts: {len(configured_contracts())} kept, 0 broken." in result.output


@pytest.mark.parametrize("violation", VIOLATIONS, ids=str)
def test_a_violating_import_breaks_its_contract_by_name(package_copy: Path, violation: Violation) -> None:
    add_module(package_copy, violation)

    result = lint_imports(package_copy)

    assert result.returncode != 0, result.output
    assert violation.broken_contract in result.broken, result.output


def test_an_exception_that_no_longer_matches_an_import_fails(package_copy: Path, tmp_path: Path) -> None:
    """Fixing a grandfathered command without deleting its ignore_imports line is itself a failure.

    The repository has no grandfathered command left (v1-e01-t13-composition-root-cleanup), so the
    stale entry is added to a copy of the configuration: the edge the last one named, which the
    command no longer has.
    """
    stale = "debate_cli.commands.caselist_auth -> debate_core.integrations.opencaselist.auth"
    root_only = '    "debate_cli.container -> debate_core.integrations.**",\n'
    configuration = PYPROJECT.read_text()
    assert root_only in configuration
    config = tmp_path / "pyproject.toml"
    config.write_text(configuration.replace(root_only, f'{root_only}    "{stale}",\n'))

    result = lint_imports(package_copy, config)

    assert result.returncode != 0, result.output
    assert stale in result.output


def test_every_configured_contract_is_proven_to_fail() -> None:
    assert {violation.broken_contract for violation in VIOLATIONS} == set(configured_contracts())
