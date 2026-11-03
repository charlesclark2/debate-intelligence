"""The plan-text cache as a file under `<data_dir>/landscape/` (`v1-e32-t09`).

The filesystem implementation of :class:`~debate_core.application.ports.plan_text_store.PlanTextStore`::

    <data_dir>/landscape/plan_texts/<caselist>.jsonl    one source's reading per line

Written whole or not at all, to a temporary file renamed into place, as compact sorted JSON lines, so
the same readings always write the same bytes. It holds digests, indexes and ids only, and lives in
this machine's data directory beside t02's classification cache.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.ports.plan_text_store import CachedPlanText
from debate_core.integrations.file_streaming import atomic_replacement
from debate_core.integrations.landscape.classification_store import LANDSCAPE_DIRECTORY
from debate_core.integrations.local.refusals import refused_as_access_denied

__all__ = ["PLAN_TEXTS_DIRECTORY", "LocalPlanTextStore"]

PLAN_TEXTS_DIRECTORY: Final = "plan_texts"
_ROLE: Final = "the landscape plan-text cache"


class LocalPlanTextStore:
    """The plan-text cache files of one data directory."""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / LANDSCAPE_DIRECTORY / PLAN_TEXTS_DIRECTORY

    def _path(self, caselist: str) -> Path:
        return self._root / f"{caselist}.jsonl"

    async def read(self, caselist: str) -> tuple[CachedPlanText, ...]:
        path = self._path(caselist)
        with refused_as_access_denied("read", _ROLE):
            if not path.is_file():
                return ()
            with path.open(encoding="utf-8") as stream:
                entries: list[CachedPlanText] = []
                for number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        entries.append(CachedPlanText.model_validate_json(line))
                    except ValidationError as error:
                        raise ValueError(
                            f"line {number} of the {caselist} plan-text cache is not a reading: "
                            f"{error.error_count()} errors"
                        ) from error
                return tuple(entries)

    async def replace(self, caselist: str, entries: Sequence[CachedPlanText]) -> None:
        lines = sorted(
            json.dumps(
                entry.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            for entry in entries
        )
        path = self._path(caselist)
        with refused_as_access_denied("write", _ROLE):
            path.parent.mkdir(parents=True, exist_ok=True)
            with atomic_replacement(path) as incoming:
                incoming.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
