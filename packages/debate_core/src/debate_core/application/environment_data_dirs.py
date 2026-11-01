"""The data directory each environment resolves to, without this process's own overrides (`v1-e40-t24`).

A restore must stay out of both environments' data directories, whichever environment it runs in. The
running environment's is in its :class:`~debate_core.application.settings.Settings`. The other's is not
loaded, and is not loaded whole here either: a command-line override, a `DEBATE_*` variable and the
`.env` file are this process's, and apply to the environment it runs as only. A
`DEBATE_STORAGE__DATA_DIR` exported for a dev command says nothing about where prod keeps its data, and
loading prod's whole settings in a dev shell would apply it to prod, and every other dev override too.

So :func:`profile_data_dir` reads the two layers that are the environment's own: its committed profile
(`config/profiles/<env>.toml`, found the way :func:`~debate_core.application.settings.load_settings`
finds it: `DEBATE_PROFILE_DIR`, then an installed build's bundled configuration, then the checkout around
the working directory) and, under it, its built-in profile. The value is expanded by
:class:`~debate_core.application.settings.StorageSettings` itself, as a loaded `Settings` expands it.

A profile that cannot be read, or whose `storage.data_dir` is not a path, raises
:class:`~debate_core.application.settings.ConfigurationError`, as loading that environment would.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from debate_core.application.settings import (
    BUILTIN_PROFILES,
    ConfigurationError,
    Environment,
    StorageSettings,
    profile_path_for,
)

__all__ = ["profile_data_dir"]


def profile_data_dir(environment: Environment, *, bundled_config_root: Path | None = None) -> Path:
    """`storage.data_dir` from `environment`'s profile file, or its built-in profile. Reads, never writes.

    `bundled_config_root` is what an installed build passes to `load_settings`, so both read the same
    profile file.
    """
    profile = profile_path_for(environment, config_root=bundled_config_root)
    raw = _storage_data_dir(_profile(profile))
    source = f"profile:{profile}"
    if raw is None:
        raw = cast(Mapping[str, Any], BUILTIN_PROFILES[environment]["storage"])["data_dir"]
        source = f"built-in:{environment.value}"
    try:
        return StorageSettings.model_validate({"data_dir": raw}).data_dir
    except ValidationError as error:
        raise ConfigurationError(
            f"invalid configuration: storage.data_dir (from {source}) is not a path", field="storage.data_dir"
        ) from error


def _profile(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"{path} is not valid TOML: {error}", source=str(path)) from error
    except OSError as error:
        raise ConfigurationError(f"could not read {path}: {error}", source=str(path)) from error


def _storage_data_dir(profile: Mapping[str, Any]) -> object | None:
    storage = profile.get("storage")
    if not isinstance(storage, Mapping):
        return None
    return cast(Mapping[str, Any], storage).get("data_dir")
