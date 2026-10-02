"""Whether this installation of `debate-research` holds what its commands are wired to use (v1-e01-t17).

Two things live here, and both are about the gap between the code and the environment it was
installed into, which no unit test run in a checkout can see.

**The post-install check.** `scripts/install_channel.sh` runs ``python -m debate_cli.installation``
with the freshly installed tool environment's own interpreter. It imports every
`debate_core.integrations` module the composition root (:mod:`debate_cli.container`) imports,
and fails unless it imported all of them. The list is read from the container's source, not
written down here, so an integration a later task wires is checked from the day it is wired. The
import-linter contract "Delivery packages reach debate_core.integrations only through their
composition root" is what makes the container the whole of the CLI's integration surface. It also
checks that every distribution behind the `debate-core` extras `debate-cli` declares was actually
installed.

The check exists because the channel's earlier verification, `--version --json`, imports none of
the integrations. v0.1.0-dev.33 passed it while every `caselist pull` failed on a missing boto3.

**The missing-dependency message.** When a command does reach an optional dependency that is not
installed, :func:`incomplete_installation_failure` says how to fix *this kind* of installation.
An installed build (a stamped dev or stable build, :func:`~debate_cli.build_info.build_channel`)
is told to reinstall with `scripts/install_channel.sh` at a fixed tag. A source checkout (channel
`local`) is told which `uv sync` to run. The adapters' own messages are written for a checkout,
so they are not repeated to an installed build.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Final

from debate_cli import DISTRIBUTION_NAME
from debate_cli.build_info import LOCAL_CHANNEL, BuildInfo

__all__ = [
    "CONTAINER_MODULE",
    "CORE_DISTRIBUTION",
    "INTEGRATIONS_PACKAGE",
    "InstallationReport",
    "UnfollowableWiring",
    "check_installation",
    "declared_core_extras",
    "incomplete_installation_failure",
    "main",
    "optional_core_dependencies",
    "wired_integrations",
]

CONTAINER_MODULE: Final = "debate_cli.container"
INTEGRATIONS_PACKAGE: Final = "debate_core.integrations"
CORE_DISTRIBUTION: Final = "debate-core"

_REQUIREMENT = re.compile(r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[(?P<extras>[^\]]*)\])?")
_EXTRA_MARKER = re.compile(r"""\bextra\s*==\s*["'](?P<extra>[^"']+)["']""")


class UnfollowableWiring(RuntimeError):
    """The composition root reaches an integration in a way an import statement does not show.

    A dynamic import, or a module name held in a string, could wire an integration this check
    would never import. Rather than pass without it, the check refuses until the container says
    what it wires with an import statement.
    """


def wired_integrations(source: str | None = None) -> tuple[str, ...]:
    """Every `debate_core.integrations` module the composition root imports, sorted.

    Read from the container's source with :mod:`ast`, so a module-level import, an import inside a
    factory (where the optional ones are) and an import under `TYPE_CHECKING` all count. A string
    that names an integration outside a docstring, or any `importlib.import_module` or
    `__import__` call, raises :class:`UnfollowableWiring`.
    """
    text = source if source is not None else _container_source()
    tree = ast.parse(text)
    documentation = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    wired: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            wired.update(alias.name for alias in node.names if _is_integration(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if node.module == INTEGRATIONS_PACKAGE:
                wired.update(f"{INTEGRATIONS_PACKAGE}.{alias.name}" for alias in node.names)
            elif _is_integration(node.module):
                wired.add(node.module)
        elif isinstance(node, ast.Call) and _is_dynamic_import(node.func):
            raise UnfollowableWiring(
                f"{CONTAINER_MODULE} line {node.lineno} imports a module dynamically; wire "
                "integrations with an import statement so the post-install check can follow them"
            )
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and INTEGRATIONS_PACKAGE in node.value
            and id(node) not in documentation
        ):
            raise UnfollowableWiring(
                f"{CONTAINER_MODULE} line {node.lineno} names {INTEGRATIONS_PACKAGE} in a string; "
                "the post-install check cannot tell whether that wires an integration"
            )
    return tuple(sorted(wired))


@dataclass(frozen=True)
class InstallationReport:
    """What :func:`check_installation` found, as the check prints it."""

    wired: tuple[str, ...]
    """The integrations the composition root imports, from :func:`wired_integrations`."""
    imported: tuple[str, ...]
    failed: Mapping[str, str] = field(default_factory=dict)
    """Integration module → the import error it raised."""
    declared_extras: tuple[str, ...] = ()
    missing_distributions: Mapping[str, str] = field(default_factory=dict)
    """Distribution → the declared `debate-core` extra that should have installed it."""

    @property
    def covered(self) -> bool:
        """Every wired integration was tried, and there was at least one to try."""
        return bool(self.wired) and set(self.imported) | set(self.failed) == set(self.wired)

    @property
    def complete(self) -> bool:
        return self.covered and not self.failed and not self.missing_distributions

    def as_dict(self) -> dict[str, object]:
        return {
            "complete": self.complete,
            "covered": self.covered,
            "wired": list(self.wired),
            "imported": list(self.imported),
            "failed": dict(self.failed),
            "declared_extras": list(self.declared_extras),
            "missing_distributions": dict(self.missing_distributions),
        }


def check_installation() -> InstallationReport:
    """Import every wired integration and look for every declared extra's distributions."""
    wired = wired_integrations()
    imported: list[str] = []
    failed: dict[str, str] = {}
    for module in wired:
        try:
            importlib.import_module(module)
        except ImportError as error:
            failed[module] = _import_failure(error)
        else:
            imported.append(module)
    extras = declared_core_extras()
    requirements = _core_extra_requirements()
    missing: dict[str, str] = {}
    for extra in extras:
        if extra not in requirements:
            missing[f"{CORE_DISTRIBUTION}[{extra}] (no such extra)"] = extra
        for distribution in requirements.get(extra, ()):
            if not _installed(distribution):
                missing[distribution] = extra
    return InstallationReport(
        wired=wired,
        imported=tuple(imported),
        failed=failed,
        declared_extras=extras,
        missing_distributions=missing,
    )


def declared_core_extras() -> tuple[str, ...]:
    """The extras of `debate-core` that the installed `debate-cli` requires, sorted."""
    for line in metadata.requires(DISTRIBUTION_NAME) or ():
        match = _REQUIREMENT.match(line)
        if match is not None and _canonical(match["name"]) == CORE_DISTRIBUTION:
            return tuple(
                sorted(_canonical(extra) for extra in (match["extras"] or "").split(",") if extra.strip())
            )
    return ()


def optional_core_dependencies() -> dict[str, str]:
    """Each distribution an extra of the installed `debate-core` adds → that extra's name."""
    return {
        distribution: extra
        for extra, distributions in _core_extra_requirements().items()
        for distribution in distributions
    }


def incomplete_installation_failure(
    error: ModuleNotFoundError, build: BuildInfo
) -> tuple[str, str, dict[str, str]] | None:
    """The message, hint and details for `error` if it is a missing optional dependency.

    `None` when it is not one: a module this installation was never meant to have is a bug, and
    is reported as one. When the error names its module, that module decides; when it does not
    (`debate_core.integrations.s3` raises its own, unnamed, error before boto3 is imported), every
    optional dependency that is not installed is reported.
    """
    optional = optional_core_dependencies()
    if error.name:
        distribution = _canonical(error.name.split(".", 1)[0])
        missing = [distribution] if distribution in optional else []
    else:
        missing = sorted(distribution for distribution in optional if not _installed(distribution))
    if not missing:
        return None
    extras = sorted({optional[distribution] for distribution in missing})
    described = ", ".join(
        f"{distribution} (debate-core's `{optional[distribution]}` extra)" for distribution in missing
    )
    details = {
        "missing": ", ".join(missing),
        "extras": ", ".join(extras),
        "installation": "checkout" if build.channel == LOCAL_CHANNEL else "installed build",
    }
    if build.channel == LOCAL_CHANNEL:
        message = f"This checkout's environment does not include {described}, which this command needs."
        flags = " ".join(f"--extra {extra}" for extra in extras)
        hint = f"From the workspace root, run `uv sync --all-packages {flags}`."
        return message, hint, details
    release = build.tag or build.version
    message = (
        f"This installed build of debate-research ({release}, {build.channel} channel) is incomplete: "
        f"it does not include {described}, which this command needs."
    )
    hint = (
        "Reinstall a complete build with `scripts/install_channel.sh <tag>` at a fixed release tag: "
        f"`{release}` again if a package was removed from it by hand, or a newer tag if this build "
        "was published without it (`gh release list` shows them)."
    )
    return message, hint, details


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m debate_cli.installation [--json]`: exit 0 only for a complete installation."""
    parser = argparse.ArgumentParser(
        prog="python -m debate_cli.installation",
        description="Import every integration debate-research's composition root wires.",
    )
    parser.add_argument("--json", action="store_true", help="print the report as one JSON object")
    arguments = parser.parse_args(argv)
    try:
        report = check_installation()
    except UnfollowableWiring as error:
        print(f"installation check: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps(report.as_dict(), sort_keys=True))
    else:
        _print_report(report)
    if not report.covered:
        print(
            f"installation check: tried {len(report.imported) + len(report.failed)} of the "
            f"{len(report.wired)} integrations {CONTAINER_MODULE} wires; every one must be checked",
            file=sys.stderr,
        )
    return 0 if report.complete else 1


def _print_report(report: InstallationReport) -> None:
    for module in report.wired:
        outcome = "ok" if module in report.imported else f"FAILED  {report.failed.get(module, 'not checked')}"
        print(f"  {module:<60} {outcome}")
    for distribution, extra in report.missing_distributions.items():
        print(f"  {distribution} (debate-core[{extra}])  MISSING")
    print(
        f"{len(report.imported)}/{len(report.wired)} wired integrations import; declared extras: "
        f"{', '.join(report.declared_extras) or 'none'}; "
        f"{'complete' if report.complete else 'INCOMPLETE'}"
    )


def _import_failure(error: ImportError) -> str:
    """Why an integration did not import, in words that suit any installation.

    Not the error's own message: `debate_core.integrations.s3` tells its reader to run `uv sync`,
    which an installed build cannot do (task spec, forbidden list).
    """
    if isinstance(error, ModuleNotFoundError):
        if error.name:
            return f"ModuleNotFoundError: no module named {error.name!r}"
        optional = optional_core_dependencies()
        absent = sorted(name for name in optional if not _installed(name))
        if absent:
            return "ModuleNotFoundError: needs " + ", ".join(
                f"{name} (debate-core[{optional[name]}])" for name in absent
            )
    return type(error).__name__


def _container_source() -> str:
    spec = importlib.util.find_spec(CONTAINER_MODULE)
    if spec is None or spec.origin is None:  # pragma: no cover - the package itself is broken
        raise UnfollowableWiring(f"cannot find the source of {CONTAINER_MODULE}")
    return Path(spec.origin).read_text(encoding="utf-8")


def _core_extra_requirements() -> dict[str, tuple[str, ...]]:
    """Each extra of the installed `debate-core` → the distributions it adds."""
    found: dict[str, list[str]] = {}
    for line in metadata.requires(CORE_DISTRIBUTION) or ():
        requirement, _, marker = line.partition(";")
        extra = _EXTRA_MARKER.search(marker)
        name = _REQUIREMENT.match(requirement)
        if extra is not None and name is not None:
            found.setdefault(_canonical(extra["extra"]), []).append(_canonical(name["name"]))
    return {extra: tuple(names) for extra, names in found.items()}


def _installed(distribution: str) -> bool:
    try:
        metadata.distribution(distribution)
    except metadata.PackageNotFoundError:
        return False
    return True


def _is_integration(module: str) -> bool:
    return module.startswith(f"{INTEGRATIONS_PACKAGE}.")


def _is_dynamic_import(function: ast.expr) -> bool:
    name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", None)
    return name in {"import_module", "__import__"}


def _canonical(name: str) -> str:
    """PEP 503 normalisation, so `Debate_Core` and `debate-core` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()


if __name__ == "__main__":
    sys.exit(main())
