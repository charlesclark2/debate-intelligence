"""Which build of `debate-research` this is: version, release channel, commit (v1-e01-t09).

A published build — a dev pre-release `vX.Y.Z-dev.N`, or later a stable `vX.Y.Z` — is stamped by
`scripts/stamp_build.py` before its wheel is built. The stamp adds two things to this package that
a source checkout never has (both are gitignored):

* `_build_info.py`, holding the version, channel, commit SHA, build time, workflow run id and tag;
* `_bundled_config/config/`, a copy of the committed profiles and routing files, so that an
  installed build reads the configuration it was built and validated with from any working
  directory — the launchd agent runs from `$HOME`, where there is no checkout to find.

A source checkout has neither, and reports channel `local` with the commit from `git rev-parse`.

What the channel changes: with `DEBATE_ENV` unset, a dev pre-release runs as `dev` and a stable
build as `prod` (:func:`debate_core.application.settings.environment_for_build_channel`), and an
installed build loads its bundled profiles rather than a checkout's. Both are passed to
`load_settings` by :func:`settings_loader`; nothing here decides them.
"""

from __future__ import annotations

import functools
import importlib
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from debate_cli import package_version
from debate_core.application.settings import Settings, load_settings

__all__ = [
    "LOCAL_CHANNEL",
    "BuildInfo",
    "build_channel",
    "bundled_config_root",
    "current_build_info",
    "settings_loader",
]

LOCAL_CHANNEL = "local"
"""The channel of code run from a source checkout rather than an installed, published build."""

_STAMPED_MODULE = "debate_cli._build_info"
_PACKAGE_DIRECTORY = Path(__file__).resolve().parent
_BUNDLED_CONFIG = _PACKAGE_DIRECTORY / "_bundled_config"
_GIT_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class BuildInfo:
    """The identity of the running build, as `--version --json` reports it."""

    version: str
    channel: str
    commit: str | None
    """Full SHA of the commit the build was made from; `None` when it cannot be determined."""
    tag: str | None
    """The release tag, e.g. `v0.1.0-dev.3`; `None` for a source checkout."""
    built_at: str | None
    run_id: str | None
    """The GitHub Actions run that built it; `None` for a source checkout."""

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _stamped() -> Mapping[str, Any] | None:
    """The stamped build info, or `None` in a source checkout."""
    try:
        module = importlib.import_module(_STAMPED_MODULE)
    except ModuleNotFoundError:
        return None
    info = getattr(module, "BUILD_INFO", None)
    return info if isinstance(info, Mapping) else None


def build_channel() -> str:
    """`dev` or `stable` for a published build, :data:`LOCAL_CHANNEL` for a source checkout."""
    stamped = _stamped()
    channel = stamped.get("channel") if stamped is not None else None
    return channel if isinstance(channel, str) and channel else LOCAL_CHANNEL


def bundled_config_root() -> Path | None:
    """The configuration a published build carries, laid out like a checkout; `None` otherwise."""
    if _stamped() is None or not (_BUNDLED_CONFIG / "config" / "profiles").is_dir():
        return None
    return _BUNDLED_CONFIG


def current_build_info() -> BuildInfo:
    """This build's identity, from the stamp or, in a source checkout, from git."""
    stamped = _stamped()
    if stamped is None:
        return BuildInfo(
            version=package_version(),
            channel=LOCAL_CHANNEL,
            commit=_checkout_commit(),
            tag=None,
            built_at=None,
            run_id=None,
        )
    return BuildInfo(
        version=_text(stamped.get("version")) or package_version(),
        channel=_text(stamped.get("channel")) or LOCAL_CHANNEL,
        commit=_text(stamped.get("commit")),
        tag=_text(stamped.get("tag")),
        built_at=_text(stamped.get("built_at")),
        run_id=_text(stamped.get("run_id")),
    )


def settings_loader() -> Callable[[], Settings]:
    """`load_settings`, told which channel this build is and where its bundled configuration is."""
    return functools.partial(
        load_settings, build_channel=build_channel(), bundled_config_root=bundled_config_root()
    )


def _checkout_commit() -> str | None:
    """`git rev-parse HEAD` for the checkout this package is imported from, if it is one."""
    try:
        result = subprocess.run(
            ["git", "-C", str(_PACKAGE_DIRECTORY), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
