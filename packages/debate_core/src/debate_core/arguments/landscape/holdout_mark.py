"""The mark on a held-out sample's rows file (`v1-e32-t50`): its header says `"holdout": true`.

Kept apart from :mod:`~debate_core.arguments.landscape.holdout_sample`, which draws the sample with the local
classifier's model, so that the evaluation and the CLI, which only read the mark, never load that model's
library (`packages/debate_cli/tests/test_container_factories.py`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Final, cast

__all__ = ["HOLDOUT_KEY", "holdout_header", "is_holdout"]

HOLDOUT_KEY: Final = "holdout"
"""The rows file's header key that marks a held-out sample: reported as counts and scores only."""


def holdout_header(rows: Iterable[str]) -> dict[str, Any] | None:
    """The header of a held-out sample's rows file; None for any other, the first sample's included."""
    first = next((line for line in rows if line.strip()), None)
    try:
        loaded: object = json.loads(first) if first is not None else None
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    header = cast(dict[str, Any], loaded)
    return header if header.get(HOLDOUT_KEY) is True else None


def is_holdout(rows: Iterable[str]) -> bool:
    """Whether a rows file is a held-out sample's: its header says `"holdout": true`."""
    return holdout_header(rows) is not None
