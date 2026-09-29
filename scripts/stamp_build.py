#!/usr/bin/env python3
"""Stamp a checkout into a published build, and check the wheels it produced (v1-e01-t09).

The dev-prerelease workflow runs this on a throwaway CI checkout, never in a working tree anyone
keeps: `stamp` edits tracked files (both pyproject versions) and writes two gitignored ones.

    stamp_build.py stamp --version 0.1.0.dev3 --tag v0.1.0-dev.3 --channel dev \\
        --commit <sha> --run-id <id> --dist dist
    uv build --package debate-core --package debate-cli --wheel --out-dir dist
    stamp_build.py check-wheels --version 0.1.0.dev3 --dist dist

What `stamp` does, and why:

* **Version.** Sets `[project] version` in the debate_core and debate_cli pyprojects to the PEP 440
  dev version, and pins debate_cli's `debate-core` requirement to exactly that version, so
  `uv tool install debate-cli==0.1.0.dev3` can only ever pair it with the debate_core built beside
  it.
* **Build info.** Writes `debate_cli/_build_info.py` (version, channel, commit, build time, workflow
  run, tag), which `debate_cli.build_info` and `debate-research --version` read, and the same
  values to `<dist>/build-info.json`, a release asset.
* **Configuration.** Copies the committed `config/profiles/*.toml` and `config/model_routing.*.yaml`
  into `debate_cli/_bundled_config/config/`, so an installed build reads the profiles it was built
  and validated with (including the `[caselist] api_enabled` gate) from any working directory.

`check-wheels` refuses a build that is not exactly the two expected wheels at the stamped version,
whose debate_cli does not pin debate_core, that lacks the build info or bundled profiles, or that
contains anything that looks like a secret or local data: `.env` files, a `secrets/` directory, a
`caselist_token`, SQLite files, a `.debate-research` data directory.

Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import email.message
import email.parser
import json
import re
import shutil
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

CORE_PYPROJECT = Path("packages/debate_core/pyproject.toml")
CLI_PYPROJECT = Path("packages/debate_cli/pyproject.toml")
CLI_PACKAGE = Path("packages/debate_cli/src/debate_cli")
BUILD_INFO_MODULE = CLI_PACKAGE / "_build_info.py"
BUNDLED_CONFIG = CLI_PACKAGE / "_bundled_config"
BUILD_INFO_ASSET = "build-info.json"

CHANNELS = ("dev", "stable")
PEP440_RELEASE_OR_DEV = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(\.dev[1-9]\d*)?$")
PROJECT_VERSION_LINE = re.compile(r'^version = "[^"]*"$', re.MULTILINE)
CORE_REQUIREMENT = re.compile(r'"debate-core(\[[^\]]*\])?"')

WHEEL_DISTRIBUTIONS = ("debate_core", "debate_cli")
"""The wheels a pre-release publishes, by their normalised file-name prefix."""

REQUIRED_CLI_MEMBERS = (
    "debate_cli/_build_info.py",
    "debate_cli/_bundled_config/config/profiles/dev.toml",
    "debate_cli/_bundled_config/config/profiles/prod.toml",
    "debate_cli/_bundled_config/config/model_routing.dev.yaml",
    "debate_cli/_bundled_config/config/model_routing.prod.yaml",
)

FORBIDDEN_DIRECTORY_NAMES = frozenset({"secrets", ".debate-research", ".data", ".venv"})
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite3", ".db")


class StampError(Exception):
    """The build cannot be stamped or its wheels are not publishable; the message says why."""


# ------------------------------------------------------------------------------------------------
# stamp
# ------------------------------------------------------------------------------------------------


def build_info(
    *, version: str, tag: str, channel: str, commit: str, run_id: str, built_at: str
) -> dict[str, str]:
    """The build's identity, as both `_build_info.py` and `build-info.json` carry it."""
    if not PEP440_RELEASE_OR_DEV.match(version):
        raise StampError(f"--version must be X.Y.Z or X.Y.Z.devN, got {version!r}")
    if channel not in CHANNELS:
        raise StampError(f"--channel must be one of {', '.join(CHANNELS)}, got {channel!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise StampError(f"--commit must be a full 40-character SHA, got {commit!r}")
    expected_tag = "v" + re.sub(r"\.dev(\d+)$", r"-dev.\1", version)
    if tag != expected_tag:
        raise StampError(f"--tag {tag!r} does not name version {version} (expected {expected_tag})")
    return {
        "version": version,
        "tag": tag,
        "channel": channel,
        "commit": commit,
        "built_at": built_at,
        "run_id": run_id,
    }


def set_project_version(text: str, version: str, *, path: Path) -> str:
    """Replace the one `version = "..."` line of a pyproject."""
    replaced, count = PROJECT_VERSION_LINE.subn(f'version = "{version}"', text)
    if count != 1:
        raise StampError(f"{path} must have exactly one top-level `version = ...` line, found {count}")
    return replaced


def pin_core_requirement(text: str, version: str, *, path: Path) -> str:
    """Turn debate_cli's `"debate-core[extra]"` requirement into `"debate-core[extra]==version"`."""
    replaced, count = CORE_REQUIREMENT.subn(
        lambda match: f'"debate-core{match.group(1) or ""}=={version}"', text
    )
    if count != 1:
        raise StampError(f"{path} must declare exactly one unpinned debate-core requirement, found {count}")
    return replaced


def render_build_info_module(info: Mapping[str, str]) -> str:
    return (
        '"""Written by scripts/stamp_build.py for a published build. Never committed."""\n\n'
        f"BUILD_INFO = {json.dumps(dict(info), indent=4)}\n"
    )


def bundle_configuration(repository: Path) -> list[Path]:
    """Copy the committed profiles and routing files into the CLI package; return what was copied."""
    source = repository / "config"
    destination = repository / BUNDLED_CONFIG / "config"
    if destination.parent.exists():
        shutil.rmtree(destination.parent)
    (destination / "profiles").mkdir(parents=True)
    copied: list[Path] = []
    for pattern, subdirectory in (("profiles/*.toml", "profiles"), ("model_routing.*.yaml", "")):
        for file in sorted(source.glob(pattern)):
            target = destination / subdirectory / file.name
            shutil.copyfile(file, target)
            copied.append(target.relative_to(repository))
    if not any(path.name == "dev.toml" for path in copied):
        raise StampError(f"no config/profiles/dev.toml under {repository}; nothing to bundle")
    return copied


def stamp(repository: Path, info: Mapping[str, str], dist: Path) -> list[Path]:
    """Stamp `repository` in place and write `build-info.json` into `dist`; return what changed."""
    version = info["version"]
    changed: list[Path] = []
    for relative in (CORE_PYPROJECT, CLI_PYPROJECT):
        path = repository / relative
        text = set_project_version(path.read_text(encoding="utf-8"), version, path=relative)
        if relative == CLI_PYPROJECT:
            text = pin_core_requirement(text, version, path=relative)
        path.write_text(text, encoding="utf-8")
        changed.append(relative)

    (repository / BUILD_INFO_MODULE).write_text(render_build_info_module(info), encoding="utf-8")
    changed.append(BUILD_INFO_MODULE)
    changed.extend(bundle_configuration(repository))

    dist.mkdir(parents=True, exist_ok=True)
    (dist / BUILD_INFO_ASSET).write_text(json.dumps(dict(info), indent=2) + "\n", encoding="utf-8")
    return changed


# ------------------------------------------------------------------------------------------------
# check-wheels
# ------------------------------------------------------------------------------------------------


def forbidden_member(name: str) -> str | None:
    """Why a wheel member must not be published, or `None` if it is fine."""
    path = PurePosixPath(name)
    for part in path.parts[:-1]:
        if part in FORBIDDEN_DIRECTORY_NAMES:
            return f"inside a {part}/ directory"
    if path.name == ".env" or path.name.startswith(".env."):
        return "a .env file"
    if "caselist_token" in path.name:
        return "a caselist_token file"
    if path.name.endswith(FORBIDDEN_SUFFIXES):
        return "a database file"
    return None


def _metadata(archive: zipfile.ZipFile) -> email.message.Message:
    names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    if len(names) != 1:
        raise StampError(f"{archive.filename}: expected one METADATA file, found {len(names)}")
    return email.parser.Parser().parsestr(archive.read(names[0]).decode("utf-8"))


def check_wheels(dist: Path, version: str) -> list[str]:
    """Every reason the wheels in `dist` are not publishable as `version`; empty when they are."""
    problems: list[str] = []
    wheels = sorted(dist.glob("*.whl"))
    by_distribution = {wheel.name.split("-", 1)[0]: wheel for wheel in wheels}
    if sorted(by_distribution) != sorted(WHEEL_DISTRIBUTIONS) or len(wheels) != len(WHEEL_DISTRIBUTIONS):
        problems.append(
            f"expected exactly the wheels {', '.join(WHEEL_DISTRIBUTIONS)}; found "
            f"{', '.join(wheel.name for wheel in wheels) or 'none'}"
        )

    for distribution, wheel in by_distribution.items():
        with zipfile.ZipFile(wheel) as archive:
            metadata = _metadata(archive)
            if metadata["Version"] != version:
                problems.append(
                    f"{wheel.name}: METADATA says version {metadata['Version']}, expected {version}"
                )
            for name in archive.namelist():
                reason = forbidden_member(name)
                if reason is not None:
                    problems.append(f"{wheel.name}: {name} is {reason}")
            if distribution != "debate_cli":
                continue
            requirements = metadata.get_all("Requires-Dist") or []
            core = [requirement for requirement in requirements if requirement.startswith("debate-core")]
            if not any(requirement.split(";")[0].strip().endswith(f"=={version}") for requirement in core):
                problems.append(
                    f"{wheel.name}: debate-core is not pinned to =={version} ({core or 'absent'})"
                )
            members = set(archive.namelist())
            problems.extend(
                f"{wheel.name}: missing {member}" for member in REQUIRED_CLI_MEMBERS if member not in members
            )
            if "debate_cli/_build_info.py" in members:
                stamped = _stamped_build_info(archive.read("debate_cli/_build_info.py").decode("utf-8"))
                if stamped.get("version") != version:
                    problems.append(
                        f"{wheel.name}: _build_info.py says {stamped.get('version')}, expected {version}"
                    )
    return problems


def _stamped_build_info(source: str) -> dict[str, object]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "BUILD_INFO" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return value if isinstance(value, dict) else {}
    return {}


# ------------------------------------------------------------------------------------------------
# Command line
# ------------------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    stamp_command = commands.add_parser("stamp", help="stamp the checkout for a published build")
    stamp_command.add_argument("--version", required=True, help="PEP 440 version, e.g. 0.1.0.dev3")
    stamp_command.add_argument("--tag", required=True, help="git tag, e.g. v0.1.0-dev.3")
    stamp_command.add_argument("--channel", required=True, choices=CHANNELS)
    stamp_command.add_argument("--commit", required=True, help="full SHA of the tagged commit")
    stamp_command.add_argument("--run-id", required=True, help="the GitHub Actions run id")
    stamp_command.add_argument("--built-at", help="ISO 8601 UTC time; defaults to now")
    stamp_command.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    stamp_command.add_argument("--dist", type=Path, required=True)
    check = commands.add_parser("check-wheels", help="refuse wheels that are not publishable")
    check.add_argument("--version", required=True)
    check.add_argument("--dist", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "stamp":
            built_at = arguments.built_at or dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            info = build_info(
                version=arguments.version,
                tag=arguments.tag,
                channel=arguments.channel,
                commit=arguments.commit,
                run_id=arguments.run_id,
                built_at=built_at,
            )
            for path in stamp(arguments.repository, info, arguments.dist):
                print(f"stamped {path}")
            return 0
        problems = check_wheels(arguments.dist, arguments.version)
        for problem in problems:
            print(f"stamp_build: {problem}", file=sys.stderr)
        if problems:
            return 1
        print(f"wheels in {arguments.dist} are publishable as {arguments.version}")
        return 0
    except StampError as error:
        print(f"stamp_build: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
