"""The analytic-text cache as a file under `<data_dir>/landscape/` (`v1-e32-t11`).

The filesystem implementation of
:class:`~debate_core.application.ports.analytic_text_store.AnalyticTextStore`::

    <data_dir>/landscape/analytic_texts/<caselist>.jsonl    one source's reading per line

Beside `v1-e32-t09`'s plan-text cache, and written the same way: whole or not at all, to a temporary
file renamed into place, as compact sorted JSON lines, so the same readings always write the same bytes.
It holds digests, indexes and ids only.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.ports.analytic_text_store import CachedAnalyticTexts
from debate_core.integrations.file_streaming import atomic_replacement
from debate_core.integrations.landscape.classification_store import LANDSCAPE_DIRECTORY
from debate_core.integrations.local.refusals import refused_as_access_denied

__all__ = ["ANALYTIC_TEXTS_DIRECTORY", "LocalAnalyticTextStore"]

ANALYTIC_TEXTS_DIRECTORY: Final = "analytic_texts"
_ROLE: Final = "the landscape analytic-text cache"


class LocalAnalyticTextStore:
    """The analytic-text cache files of one data directory."""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / LANDSCAPE_DIRECTORY / ANALYTIC_TEXTS_DIRECTORY

    def _path(self, caselist: str) -> Path:
        return self._root / f"{caselist}.jsonl"

    async def read(self, caselist: str) -> tuple[CachedAnalyticTexts, ...]:
        path = self._path(caselist)
        with refused_as_access_denied("read", _ROLE):
            if not path.is_file():
                return ()
            with path.open(encoding="utf-8") as stream:
                entries: list[CachedAnalyticTexts] = []
                for number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        entries.append(CachedAnalyticTexts.model_validate_json(line))
                    except ValidationError as error:
                        raise ValueError(
                            f"line {number} of the {caselist} analytic-text cache is not a reading: "
                            f"{error.error_count()} errors"
                        ) from error
                return tuple(entries)

    async def replace(self, caselist: str, entries: Sequence[CachedAnalyticTexts]) -> None:
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
