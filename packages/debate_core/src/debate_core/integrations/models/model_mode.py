"""The one control for whether real model calls are recorded, replayed or made live.

Every CLI, eval runner and test in the project reads the mode the same way, through
:func:`resolve_model_mode` (v1-e05-t03-fake-replay-models):

1. the `--model-mode record|replay|live` option, when the program has one and it was given;
2. otherwise the `DEBATE_MODEL_MODE` environment variable;
3. otherwise **replay**, so that a program nobody configured never reaches a real model.

There is no other flag, variable or setting for it, and settings never choose replay:
`models.provider` only says whether the router is the fixture-keyed fake or a real provider, and
the mode applies to the real one. An argparse-based program, such as an eval runner, adds the
option with :func:`add_model_mode_option`.

The mode is read from the process environment, never from `.env`. `.env` holds settings, and the
mode is deliberately not one.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from debate_core.integrations.models.errors import ModelModeError

__all__ = [
    "CI_VARIABLE",
    "DEFAULT_MODEL_MODE",
    "MODEL_MODE_OPTION",
    "MODEL_MODE_VARIABLE",
    "ModelMode",
    "add_model_mode_option",
    "resolve_model_mode",
    "running_in_ci",
]

MODEL_MODE_VARIABLE: Final = "DEBATE_MODEL_MODE"
"""The environment variable that chooses the mode when no option does."""

MODEL_MODE_OPTION: Final = "--model-mode"
"""The command-line option that chooses the mode, and wins over the variable."""

CI_VARIABLE: Final = "CI"
"""Set to `true` by CI services, GitHub Actions among them; record mode refuses to run under it."""

_TRUE_VALUES: Final = frozenset({"true", "1", "yes"})


class ModelMode(StrEnum):
    """What a :class:`~debate_core.integrations.models.record_replay.RecordReplayModelRouter` does."""

    RECORD = "record"
    """Call the real router and write each request and response to a reviewable cassette."""

    REPLAY = "replay"
    """Serve recorded cassettes; any call nobody recorded is an error. The default."""

    LIVE = "live"
    """Call the real router and record nothing."""


DEFAULT_MODEL_MODE: Final = ModelMode.REPLAY
"""The mode when neither the option nor the variable is given."""


def resolve_model_mode(
    option: str | ModelMode | None = None, *, environ: Mapping[str, str] | None = None
) -> ModelMode:
    """The mode this run uses: `option` if given, else `DEBATE_MODEL_MODE`, else replay.

    `environ` defaults to the process environment. Raises :class:`ModelModeError`, naming where
    the value came from, for anything but record, replay or live; a variable set to the empty
    string is such a value, not an unset one.
    """
    if option is not None:
        return _parse(str(option), source=MODEL_MODE_OPTION)
    environment = os.environ if environ is None else environ
    value = environment.get(MODEL_MODE_VARIABLE)
    if value is None:
        return DEFAULT_MODEL_MODE
    return _parse(value, source=f"env:{MODEL_MODE_VARIABLE}")


def add_model_mode_option(parser: argparse.ArgumentParser) -> None:
    """Give an argparse program the `--model-mode` option; read it back with :func:`resolve_model_mode`.

    The parsed value is `args.model_mode`, `None` when the option was not given, so that
    `resolve_model_mode(args.model_mode)` falls through to the variable and then to replay.
    """
    parser.add_argument(
        MODEL_MODE_OPTION,
        dest="model_mode",
        choices=[mode.value for mode in ModelMode],
        default=None,
        help=(
            f"record, replay or live for real model calls (default: ${MODEL_MODE_VARIABLE}, "
            f"else {DEFAULT_MODEL_MODE.value}). Record is refused when {CI_VARIABLE}=true."
        ),
    )


def running_in_ci(environ: Mapping[str, str] | None = None) -> bool:
    """Whether `CI` is set to a true value (`true`, `1` or `yes`, in any case)."""
    environment = os.environ if environ is None else environ
    return environment.get(CI_VARIABLE, "").strip().lower() in _TRUE_VALUES


def _parse(value: str, *, source: str) -> ModelMode:
    try:
        return ModelMode(value.strip().lower())
    except ValueError:
        allowed = ", ".join(mode.value for mode in ModelMode)
        raise ModelModeError(
            f"invalid model mode {value!r} from {source}: expected one of {allowed}",
            field="model_mode",
            source=source,
        ) from None
