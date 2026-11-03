"""`--config-dir`: the directory holding the landscape's `topics.yaml`, or the checkout's own.

Taken by `landscape report`, `landscape evaluate` and `files suggest`. It lived in
:mod:`debate_cli.commands.landscape` until v1-e01-t32.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import typer

from debate_core.application.settings import find_repository_root

__all__ = ["LANDSCAPE_CONFIG", "landscape_config_dir"]

LANDSCAPE_CONFIG: Final = Path("config") / "landscape"


def landscape_config_dir(given: Path | None) -> Path:
    """`--config-dir`, or `config/landscape` in the checkout around the working directory."""
    if given is not None:
        return given
    root = find_repository_root()
    if root is None or not (root / LANDSCAPE_CONFIG).is_dir():
        raise typer.BadParameter(
            "no config/landscape/ in a checkout around this directory; name the directory holding "
            "topics.yaml with --config-dir",
            param_hint="--config-dir",
        )
    return root / LANDSCAPE_CONFIG
