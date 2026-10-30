"""`debate-research doctor`: what this installation is, before anything else is blamed.

The first question about a failed run is which CLI, which Python and which configuration produced
it, and on a student's laptop the answer is rarely the one assumed. `doctor` answers it in both
output modes, and in doing so is the worked example of the command pattern: parse nothing, ask the
composition root, render through :mod:`debate_cli.output`.

It reports what exists today. The checks that need settings — which data directory is in use,
which providers have credentials, whether the evidence store is reachable — are added here as
their tasks land, starting with v1-e02-t05 (settings) and v1-e01-t09 (environment profiles).

## The evidence profiles, when asked (`v1-e34-t22`)

`doctor --evidence-profiles` adds one more check: each AWS profile this environment's settings name
for the evidence bucket, the everyday one (`storage.s3.aws_profile`) and the takedown one when
`DEBATE_REMOVAL_PROFILE` is set. For each it reports whether this machine's AWS config defines it
and which permission set it is signed in as, and it fails on a profile that is **not defined**:
that is the setting that stops every command that reaches the bucket before it starts, the weekly
pull among them (`v1-e29-t07`). An expired session is reported as expired, with the login, and is
not a failure; nor is an account that did not answer, or a profile signed in as a permission set
nobody expected. The check is :class:`~debate_core.application.evidence_profiles.EvidenceProfileCheck`;
this module only renders it.

**It is an option, and plain `doctor` does not make it.** Plain `doctor` loads no settings, reads no
AWS config and reaches no network, and it has to stay that way: `scripts/install_channel.sh` runs
it on every install, and `validate-dev` runs it against every pre-release, on machines that have no
AWS config at all. A `doctor` that failed there for want of an operator's profile would refuse
every build. With the option it loads settings, reads the AWS config, and makes one call to AWS for
each profile that is defined (`GetCallerIdentity`, which needs no grant and changes nothing).
`ops/launchd/install.sh --check-launchd` runs it under launchd, as the agent will run.

**What "reaches no network" means** (`v1-e05-t09`, the PM's ruling). Plain `doctor` makes no network
call and binds nothing but loopback. It does open one socket: importing the AWS SDK, which the
integration check below does for every adapter built on it, imports urllib3, and urllib3 binds a
loopback socket to `::1` once to learn whether the machine has IPv6. Nothing is sent, no name is
looked up, and urllib3 swallows the failure where IPv6 is off, so no network is touched. The check
keeps its real imports for that: it is what catches an adapter installed but broken on import.
`tests/commands/test_plain_doctor_reaches_no_network.py` runs plain `doctor` in a fresh interpreter
with every connect, send and lookup refused, and every bind but a loopback one.

**The model profile** (`v1-e05-t08`), `models.aws_profile`, the profile every Bedrock call is
signed with, is checked beside them and reported in the same words, on a `Model profile` row. It
never fails the check, even when it is not defined: no command calls a model yet, and this check is
what the weekly run's `--check` and `ops/launchd/install.sh --check-launchd` run before a pull,
which needs no model. A model profile that is not defined is said on its row, with its fix.

It names a profile, the setting that holds its name and a permission set. Never an account, a
role's full identifier, the address a session is started at, or where the AWS config is.

## The search index stores, when asked (`v1-e34-t30`)

`doctor --search-index` adds a check for the weekly run's search index stage (`v1-e39-t09`): each
store the stage would index, the caselists in `caselist.sync_caselists` and `openev`, and whether
this build's parser has parsed it, which is whether `<data_dir>/parsed/<store>/` holds a version
directory of the parser version this build runs. A store that has none fails it, named with the
command that parses it, `debate-research caselist parse --caselist <store>`: without it the run
ends without a current index, and on a fresh installation that is the first Wednesday. Where the
run has no such stage, because `caselist.refresh_search_index` is off or the environment names no
bucket, the check says it does not apply and why, reads nothing, and passes. The check is
:class:`~debate_core.application.search_index_store_check.SearchIndexStoreCheck`; this module only
renders it.

Like `--evidence-profiles` it is an option, for the same reason: with it `doctor` loads settings,
and plain `doctor` must not. It reads this machine's directories and reaches no network. The two
options can be given together, and `ops/launchd/install.sh --check-launchd` gives both, with the
agent's caselists as `caselist.sync_caselists`, so the check runs as the agent will.

It names a store, which is a caselist slug or `openev`, and the parser version. Never a path, a
school, a team code or a file name.

## The routing file, when asked (`v1-e05-t09`)

`doctor --routing-file` adds a check of the model-routing file this environment's settings name,
`models.routing_file`: whether it loads, and the task classes it routes. A file that is missing, is
not YAML or does not match the schema fails it, with the refusal every command that reads settings
would stop with (`v1-e05-t03` ac6), naming the file and the offending key. The check is
:func:`~debate_core.integrations.models.routing_policy.check_routing_file`; this module only renders it.

Like the options above it is an option because it loads settings, and plain `doctor` must not: a
bad routing file does not stop plain `doctor`, on purpose. It reads one file and reaches no network.

## Exit codes

`doctor` fails on two checks only, the ones it can state precisely, and on three more when asked:

* **The Unicode database** (`v1-e01-t14`). Under any database but the one the current evidence
  normalizer is pinned to, `normalize` refuses to run (`UnicodeDatabaseMismatchError`), so every
  command that touches evidence text would fail on first use. The error names both versions and the
  policy page, `docs/evidence/normalization.md`.
* **The wired integrations** (`v1-e01-t22`). Every `debate_core.integrations` module the composition
  root imports must import. The list and the imports are :func:`debate_cli.installation.check_installation`,
  the same logic as the installer's post-install check, so there is no second list to keep up. Each
  module that does not import is named, with why, and a command that uses it would fail.

* **The evidence profiles**, with `--evidence-profiles` only: every configured profile must be
  defined in this machine's AWS config. One that is not is named, with its setting.
* **The search index stores**, with `--search-index` only, where the weekly run has the stage:
  every store it would index must have been parsed by this build's parser. One that has not is
  named, with the command that parses it. It is a precise prediction that the next weekly run ends
  without a current index.
* **The routing file**, with `--routing-file` only: the file `models.routing_file` names must load.
  One that does not is named, with the offending key when there is one.

* `0`: the report was produced, and every check that was made passed.
* `1` (`DOMAIN_FAILURE`): a check failed. One failure has its own code, `UNICODE_DATABASE_MISMATCH`,
  `INTEGRATIONS_DO_NOT_IMPORT`, `STORE_PROFILE_NOT_CONFIGURED` (the code a command stopped by the
  same setting reports), `SEARCH_INDEX_STORE_NOT_READY` (the code the search index stage fails
  with) or `ROUTING_CONFIG_ERROR` (the code a command stopped by the same file reports); more than
  one are `INSTALLATION_CHECKS_FAILED`, with every message.
  `--json` carries the whole report in `error.details`. `scripts/install_channel.sh` runs `doctor`
  before it replaces an install, so a build that fails either check is refused there.
* `70` (`INTERNAL_ERROR`): `doctor` could not establish a check at all: the normalizer's pinned
  version is unknown, or the container wires an integration in a way an import statement does not
  show (:class:`~debate_cli.installation.UnfollowableWiring`). Only a broken build causes either.
  That is a bug, not a verdict on the installation, so it surfaces through the root handler like any
  other unmodelled exception, with its "This is a bug" hint.

Every other fact is description and never changes the exit status: an unloaded settings file, an
unknown package version, an unexpected Python version or platform, a Python that uv does not
manage, and a declared `debate-core` extra whose distributions are not installed. That last one is
not a failure `doctor` can state precisely: nothing breaks until a wired integration needs the
distribution, and then the integration check names it. The installer's own check
(`python -m debate_cli.installation`) holds a build to everything it declares and refuses it at
install. A `doctor` that guessed would be worse than one that only describes.

## Whether uv manages this Python

`python_uv_managed` (`v1-e01-t23`) says whether the running interpreter is one uv manages. Such a
Python changes only through uv, when the build is reinstalled or a `uv python` command is run on
purpose; a `conda update` or a `brew upgrade` cannot change it under the installed build.
`scripts/install_channel.sh` asks uv for such a Python and refuses a build that is not on one; a
checkout's `.venv` or a hand-run install can be on any Python. It is decided by place, as uv
decides it. :func:`uv_python_directory` works out the directory `uv python dir` would name, from
this process's environment; the interpreter is uv's when its base prefix (`sys.base_prefix`, the
installation behind a virtual environment), every link followed, lies strictly inside that
directory, every link followed too (:func:`is_uv_managed`). The report carries all three. An
installation made with a `UV_PYTHON_INSTALL_DIR` that `doctor`'s environment does not set is
reported as not managed. Either answer leaves the exit status alone.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Annotated, cast

import typer

from debate_cli import installation, package_version
from debate_cli.container import SERVICE_NAMES, ServiceContainer
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.errors import StoreProfileNotConfigured, error_code_of_class
from debate_core.application.evidence_profiles import MODEL_PROFILE_SETTING
from debate_core.application.ports.model_router import RoutingConfigError
from debate_core.application.search_index_build import SearchIndexStoreNotReady
from debate_core.evidence.normalization import NORMALIZER_VERSION, pinned_unicode_version

__all__ = ["doctor"]

UNICODE_DATABASE_MISMATCH_CODE = "UNICODE_DATABASE_MISMATCH"
INTEGRATIONS_DO_NOT_IMPORT_CODE = "INTEGRATIONS_DO_NOT_IMPORT"
INSTALLATION_CHECKS_FAILED_CODE = "INSTALLATION_CHECKS_FAILED"
PROFILE_NOT_DEFINED_CODE = error_code_of_class(StoreProfileNotConfigured)
"""`STORE_PROFILE_NOT_CONFIGURED`: the code of the error a command stopped by the same setting reports."""
NORMALIZATION_POLICY_PAGE = "docs/evidence/normalization.md"
_MISMATCH_FACTS = ("normalizer_version", "normalizer_unicode_version", "python_unicode_version")
EVIDENCE_PROFILES = "evidence_profiles"
"""The report's key for the profile check's findings. Absent unless `--evidence-profiles` was given."""
SEARCH_INDEX = "search_index"
"""The report's key for the search index store check's findings. Absent unless `--search-index` was given."""
STORE_NOT_PARSED_CODE = error_code_of_class(SearchIndexStoreNotReady)
"""`SEARCH_INDEX_STORE_NOT_READY`: the code the search index stage fails with on a store never parsed."""
ROUTING_FILE = "routing_file"
"""The report's key for the routing file check's finding. Absent unless `--routing-file` was given."""
ROUTING_FILE_DOES_NOT_LOAD_CODE = error_code_of_class(RoutingConfigError)
"""`ROUTING_CONFIG_ERROR`: the code of the error a command stopped by the same routing file reports."""


def doctor(
    ctx: typer.Context,
    evidence_profiles: Annotated[
        bool,
        typer.Option(
            "--evidence-profiles",
            help=(
                "Also check each AWS profile this environment is configured to reach the evidence "
                "bucket with, and the one Bedrock calls are signed with (models.aws_profile): whether "
                "this machine's AWS config defines it, and which permission set it is signed in as. "
                "Fails on an evidence profile that is not defined; an expired session, and the model "
                "profile, are reported and do not fail. Reads the AWS config and asks AWS who each "
                "profile is; without this option doctor does neither."
            ),
        ),
    ] = False,
    search_index: Annotated[
        bool,
        typer.Option(
            "--search-index",
            help=(
                "Also check each store the weekly run's search index stage would index, the "
                "caselists in caselist.sync_caselists and openev: whether this build's parser has "
                "parsed it. Fails on one that has not, naming the caselist parse command that "
                "parses it; does not apply, and passes, where the run has no such stage. Loads "
                "settings and reads the parsed store's directories; without this option doctor "
                "does neither."
            ),
        ),
    ] = False,
    routing_file: Annotated[
        bool,
        typer.Option(
            "--routing-file",
            help=(
                "Also check the model-routing file this environment's settings name "
                "(models.routing_file): whether it loads, and which task classes it routes. Fails "
                "on a file that is missing, is not YAML or does not match the schema, naming the "
                "offending key. Loads settings and reads that file; without this option doctor "
                "does neither."
            ),
        ),
    ] = False,
) -> None:
    """Report the versions, interpreter and wiring this installation is running with.

    Exit codes:
    0   the report was produced, this Python's Unicode database is the one the evidence
        normalizer is pinned to, and every integration the CLI wires imports
    1   a check failed: the Unicode databases differ, so commands that normalize evidence text
        would refuse to run (the error names both versions and docs/evidence/normalization.md),
        or a wired integration does not import (the error names each one, with why), or, with
        --evidence-profiles, a configured evidence profile is not defined in this machine's AWS
        config (the error names the profile and the setting that holds its name), or, with
        --search-index, a store the weekly run's search index stage would index has not been
        parsed by this build's parser (the error names each, and the hint the command that
        parses it), or, with --routing-file, the model-routing file the settings name does not
        load (the error names the file and the offending key)
    70  a check could not be made at all (the pinned version is unknown, or the CLI wires an
        integration in a way that cannot be followed), which is a bug in the build
    Every other fact is reported for information and never fails the command, including a
    declared extra whose packages are missing.
    """
    cli = cli_context(ctx)
    cli.output.detail("collecting environment facts")
    report = environment_report(cli.services)
    if routing_file:
        cli.output.detail("loading the model-routing file the settings name")
        report[ROUTING_FILE] = cast("JsonValue", cli.services.routing_file_finding().as_json())
    if evidence_profiles:
        cli.output.detail("asking AWS which permission set each configured evidence profile is signed in as")
        report[EVIDENCE_PROFILES] = evidence_profile_findings(cli.services)
    if search_index:
        cli.output.detail("checking which stores the weekly search index stage would find unparsed")
        report[SEARCH_INDEX] = search_index_store_findings(cli.services)
    failure = doctor_failure(report)
    # A program gets one envelope: the report under `data`, or under `error.details` on a failure.
    # A person gets the table either way, then the failure's panel.
    if failure is None or not cli.output.is_json:
        cli.output.success(
            command_name(ctx),
            report,
            display=TableSpec(columns=("Check", "Value"), rows=_rows(report), title="debate-research doctor"),
        )
    if failure is not None:
        if not cli.output.is_json:
            # The table above already lists every fact; the panel names only what failed.
            failure = replace(failure, details=_failed_facts(report))
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)


def environment_report(services: ServiceContainer) -> dict[str, JsonValue]:
    """The facts `doctor` reports, as the `--json` envelope's `data`."""
    pinned = pinned_unicode_version(NORMALIZER_VERSION)
    running = unicodedata.unidata_version
    integrations = installation.check_installation()
    uv_pythons = uv_python_directory(os.environ)
    return {
        "cli_version": package_version("debate-cli"),
        "core_version": package_version("debate-core"),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "python_base_prefix": sys.base_prefix,
        "uv_python_directory": str(uv_pythons),
        "python_uv_managed": is_uv_managed(sys.base_prefix, uv_pythons),
        "platform": platform.platform(),
        "settings_configured": services.settings_configured,
        "services": list(SERVICE_NAMES),
        "normalizer_version": NORMALIZER_VERSION,
        "normalizer_unicode_version": pinned,
        "python_unicode_version": running,
        "unicode_database_matches": running == pinned,
        "integrations_wired": list(integrations.wired),
        "integrations_failed": dict(integrations.failed),
        "integrations_import": not integrations.failed,
        "extras_missing_distributions": dict(integrations.missing_distributions),
    }


def evidence_profile_findings(services: ServiceContainer) -> list[JsonValue]:
    """What the profile check found for each configured evidence profile, in the settings' order.

    One object a profile: the setting that names it, its name, whether it is defined, what asking
    AWS learnt, the permission set it is signed in as, and a sentence and a fix for a person.
    """
    found = asyncio.run(services.evidence_profile_check().run())
    return [cast("JsonValue", one.as_json()) for one in found]


def search_index_store_findings(services: ServiceContainer) -> JsonValue:
    """What the search index store check found: why it does not apply, or each store in the stage's order."""
    found = asyncio.run(services.search_index_store_check().run())
    return cast("JsonValue", found.as_json())


def uv_python_directory(environ: Mapping[str, str], *, windows: bool = os.name == "nt") -> Path:
    """The directory where uv keeps the Pythons it manages, found the way `uv python dir` finds it.

    `UV_PYTHON_INSTALL_DIR` when it is set and not empty, against the working directory if it is
    relative. Otherwise, on macOS and Linux, `$XDG_DATA_HOME/uv/python` when `XDG_DATA_HOME` is an
    absolute path, and `$HOME/.local/share/uv/python` when it is not. Measured against uv 0.11.7.
    On Windows, `%APPDATA%\\uv\\data\\python`, from uv's documentation and not measured.
    """
    configured = environ.get("UV_PYTHON_INSTALL_DIR", "")
    if configured:
        return Path(os.path.abspath(configured))
    if windows:
        return Path(environ.get("APPDATA", "")) / "uv" / "data" / "python"
    data_home = environ.get("XDG_DATA_HOME", "")
    if os.path.isabs(data_home):
        return Path(data_home) / "uv" / "python"
    return Path(environ.get("HOME") or Path.home()) / ".local" / "share" / "uv" / "python"


def is_uv_managed(base_prefix: str, uv_pythons: Path) -> bool:
    """Whether the Python installed at `base_prefix` lies inside `uv_pythons`, every link followed."""
    installed = Path(os.path.realpath(base_prefix))
    directory = Path(os.path.realpath(uv_pythons))
    return installed != directory and installed.is_relative_to(directory)


def doctor_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """What `doctor` reports as its failure, or None: every check it fails on, together."""
    failures = [
        failure
        for failure in (
            unicode_database_failure(report),
            integration_failure(report),
            evidence_profile_failure(report),
            search_index_failure(report),
            routing_file_failure(report),
        )
        if failure is not None
    ]
    if len(failures) <= 1:
        return failures[0] if failures else None
    return CommandFailure(
        code=INSTALLATION_CHECKS_FAILED_CODE,
        message=" ".join(failure.message for failure in failures),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=" ".join(_as_sentence(failure.hint) for failure in failures if failure.hint),
    )


def _as_sentence(text: str) -> str:
    """`text`, ending with a full stop, so that hints run together read as sentences."""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def unicode_database_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The one failure `doctor` reports, or None: the two Unicode databases differ."""
    pinned = report["normalizer_unicode_version"]
    running = report["python_unicode_version"]
    if running == pinned:
        return None
    return CommandFailure(
        code=UNICODE_DATABASE_MISMATCH_CODE,
        message=(
            f"This Python's Unicode database is {running}, but {report['normalizer_version']} is pinned "
            f"to Unicode {pinned}, so every command that normalizes evidence text will refuse to run. "
            f"See {NORMALIZATION_POLICY_PAGE}."
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=(
            "Install debate-research with scripts/install_channel.sh, which runs it on a Python uv "
            "manages that debate_core's Requires-Python admits. In a checkout, `uv sync` uses "
            ".python-version."
        ),
    )


def integration_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The integrations the CLI wires that do not import, each named with why, or None."""
    failed = _failed_integrations(report)
    if not failed:
        return None
    wired = report["integrations_wired"]
    total = len(wired) if isinstance(wired, list) else len(failed)
    named = "; ".join(f"{module} ({reason})" for module, reason in sorted(failed.items()))
    return CommandFailure(
        code=INTEGRATIONS_DO_NOT_IMPORT_CODE,
        message=(
            f"{len(failed)} of the {total} integrations debate-research wires do not import: {named}. "
            "Every command that uses one of them will fail."
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=(
            "Reinstall a complete build with `scripts/install_channel.sh <tag>` at a fixed release tag, "
            "never by adding packages by hand. In a checkout, run `uv sync --all-packages` from the "
            "workspace root."
        ),
    )


def evidence_profile_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The configured evidence profiles this machine's AWS config does not define, or None.

    None too when the profiles were not checked. Nothing else the check finds is a failure: an
    expired session has a login to cure it and does not stop the weekly run capturing, and an
    account that did not answer says nothing about the profile.
    """
    missing = _profiles_not_defined(report)
    if not missing:
        return None
    named = " and ".join(
        f"AWS profile {str(one['profile'])!r}, named by {one['setting']}," for one in missing
    )
    one_or_more = ("is", "it") if len(missing) == 1 else ("are", "them")
    fixes = dict.fromkeys(str(one["hint"]) for one in missing if one["hint"])
    return CommandFailure(
        code=PROFILE_NOT_DEFINED_CODE,
        message=(
            f"{named} {one_or_more[0]} not defined in this machine's AWS config, so every command "
            f"that uses {one_or_more[1]} will refuse to start."
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=". ".join(fixes) or None,
    )


def search_index_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The stores the weekly run's search index stage would index that this build has not parsed, or None.

    None too when the stores were not checked, and when the check does not apply.
    """
    found = _search_index(report)
    unparsed = [str(one["store"]) for one in _search_index_stores(found) if one["parsed"] is False]
    if not unparsed:
        return None
    one_or_more = "store has" if len(unparsed) == 1 else "stores have"
    fixes = " and ".join(f"`{one['fix']}`" for one in _search_index_stores(found) if one["parsed"] is False)
    return CommandFailure(
        code=STORE_NOT_PARSED_CODE,
        message=(
            f"{len(unparsed)} {one_or_more} not been parsed by this build's parser, "
            f"{found['parser_version']}: {', '.join(unparsed)}. The weekly run's search index stage "
            "indexes them, so the next run will end without a current search index."
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=f"Run {fixes} before the next weekly run.",
    )


def routing_file_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The routing file the settings name, when it does not load, or None.

    None too when the file was not checked.
    """
    found = _routing_file(report)
    if found.get("loads") is not False:
        return None
    field = found.get("field")
    return CommandFailure(
        code=ROUTING_FILE_DOES_NOT_LOAD_CODE,
        message=(
            f"The model-routing file does not load, so every command that reads settings will refuse "
            f"to start: {found['problem']}"
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=(f"Fix `{field}` in {found['routing_file']}" if field else f"Fix {found['routing_file']}")
        + ", or point models.routing_file at a file that loads.",
    )


def _routing_file(report: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """The routing file check's finding in `report`: empty when the check was not asked for."""
    found = report.get(ROUTING_FILE)
    return found if isinstance(found, Mapping) else {}


def _search_index(report: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """The search index store check's findings in `report`: empty when the check was not asked for."""
    found = report.get(SEARCH_INDEX)
    return found if isinstance(found, Mapping) else {}


def _search_index_stores(found: Mapping[str, JsonValue]) -> list[Mapping[str, JsonValue]]:
    stores = found.get("stores")
    if not isinstance(stores, list):
        return []
    return [one for one in stores if isinstance(one, Mapping)]


def _evidence_profiles(report: Mapping[str, JsonValue]) -> list[Mapping[str, JsonValue]]:
    """The profile check's findings in `report`: none when the check was not asked for."""
    found = report.get(EVIDENCE_PROFILES)
    if not isinstance(found, list):
        return []
    return [one for one in found if isinstance(one, Mapping)]


def _profiles_not_defined(report: Mapping[str, JsonValue]) -> list[Mapping[str, JsonValue]]:
    """The evidence profiles that are not defined. The model profile never fails the check."""
    return [
        one
        for one in _evidence_profiles(report)
        if one["defined"] is False and one["setting"] != MODEL_PROFILE_SETTING
    ]


def _failed_integrations(report: Mapping[str, JsonValue]) -> dict[str, str]:
    failed = report["integrations_failed"]
    if not isinstance(failed, Mapping):  # pragma: no cover - environment_report always writes one
        raise TypeError(f"integrations_failed is {type(failed).__name__}, not a mapping")
    return {str(module): str(reason) for module, reason in failed.items()}


def _failed_facts(report: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """For a person's panel: the two databases if they differ, and each integration that failed.

    A profile that is not defined adds nothing here: the failure's own sentence names the profile
    and its setting, and the row above it says the same.
    """
    facts: dict[str, JsonValue] = {}
    if unicode_database_failure(report) is not None:
        facts.update({key: report[key] for key in _MISMATCH_FACTS})
    facts.update(_failed_integrations(report))
    return facts


def _rows(report: dict[str, JsonValue]) -> list[list[str]]:
    """One `label, value` row per fact, in the order :func:`environment_report` lists them."""
    labels = {
        "cli_version": "debate-cli",
        "core_version": "debate-core",
        "python_version": "Python",
        "python_executable": "Interpreter",
        "python_base_prefix": "Base interpreter",
        "uv_python_directory": "uv's Pythons",
        "python_uv_managed": "Managed by uv",
        "platform": "Platform",
        "settings_configured": "Settings loaded",
        "services": "Services wired",
        "normalizer_version": "Evidence normalizer",
        "normalizer_unicode_version": "Normalizer's Unicode",
        "python_unicode_version": "Python's Unicode",
        "unicode_database_matches": "Unicode matches pin",
        "integrations_wired": "Integrations wired",
        "integrations_failed": "Integrations failing",
        "integrations_import": "Integrations import",
        "extras_missing_distributions": "Extras' packages missing",
    }
    rows = [
        [labels.get(key, key), _as_text(value)]
        for key, value in report.items()
        if key not in (EVIDENCE_PROFILES, SEARCH_INDEX, ROUTING_FILE)
    ]
    return rows + _profile_rows(report) + _search_index_rows(report) + _routing_file_rows(report)


def _profile_rows(report: Mapping[str, JsonValue]) -> list[list[str]]:
    """One row for each evidence profile that was checked; no row at all when none was asked about.

    The login that renews an expired session follows its sentence. The fix for a profile that is
    not defined does not: it is the failure's own hint, in the panel under the table.
    """
    if EVIDENCE_PROFILES not in report:
        return []
    found = _evidence_profiles(report)
    if not found:
        return [["Evidence profiles", "none configured for this environment"]]
    return [
        [
            "Model profile" if one["setting"] == MODEL_PROFILE_SETTING else "Evidence profile",
            f"{one['profile']} ({one['setting']}): {one['summary']}"
            + (f" ({one['hint']})" if one["hint"] and _fix_is_the_rows(one) else ""),
        ]
        for one in found
    ]


def _fix_is_the_rows(one: Mapping[str, JsonValue]) -> bool:
    """Whether a profile's fix follows its row: always for one that is defined, and for the model
    profile, which never fails, so no panel under the table says it."""
    return one["defined"] is True or one["setting"] == MODEL_PROFILE_SETTING


def _search_index_rows(report: Mapping[str, JsonValue]) -> list[list[str]]:
    """The caselists, then one row for each store; one row saying why when the check does not apply.

    The command that parses a store that is not parsed does not follow its row: it is the failure's
    own hint, in the panel under the table.
    """
    if SEARCH_INDEX not in report:
        return []
    found = _search_index(report)
    if found.get("does_not_apply") is not None:
        return [["Search index stores", f"does not apply: {found['does_not_apply']}"]]
    caselists = found.get("caselists")
    configured = (
        _as_text(caselists)
        if isinstance(caselists, list) and caselists
        else "none configured (caselist.sync_caselists), so openev alone is checked"
    )
    version = found["parser_version"]
    return [["Search index caselists", configured]] + [
        [
            "Search index store",
            f"{one['store']}: parsed by {version}"
            if one["parsed"]
            else f"{one['store']}: not parsed by this build's parser, {version}",
        ]
        for one in _search_index_stores(found)
    ]


def _routing_file_rows(report: Mapping[str, JsonValue]) -> list[list[str]]:
    """One row for the routing file, when it was checked: what it routes, or the key that stops it.

    Why it does not load is not repeated here: it is the failure's own message, in the panel under the table.
    """
    if ROUTING_FILE not in report:
        return []
    found = _routing_file(report)
    if found.get("loads") is True:
        return [["Routing file", f"{found['routing_file']}: loads; routes {_as_text(found['routes'])}"]]
    where = f" at {found['field']}" if found.get("field") else ""
    return [["Routing file", f"{found['routing_file']}: does not load{where}"]]


def _as_text(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    if isinstance(value, Mapping):
        return "; ".join(f"{key} ({item})" for key, item in value.items()) if value else "none"
    return str(value)
