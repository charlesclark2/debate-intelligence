"""The classification cache and the review queue as files under `<data_dir>/landscape/` (`v1-e32-t02`).

The filesystem implementation of
:class:`~debate_core.application.ports.classification_store.ClassificationStore`::

    <data_dir>/landscape/classifications/<caselist>.jsonl              one cached result per line
    <data_dir>/landscape/review/<caselist>/<topic id>-review-queue.csv  the latest review queue

Both are written whole or not at all, to a temporary file renamed into place, with compact sorted
JSON lines so the same cache always writes the same bytes. Both live in this machine's data
directory and nowhere else: the queue holds headings teams wrote, so it is never written into the
repository. A refused directory is reported as the store's, never by path.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.ports.classification_store import CachedClassification
from debate_core.arguments.landscape.review_queue import ReviewRow, write_review_queue_csv
from debate_core.integrations.file_streaming import atomic_replacement
from debate_core.integrations.local.refusals import refused_as_access_denied

__all__ = [
    "CLASSIFICATIONS_DIRECTORY",
    "LANDSCAPE_DIRECTORY",
    "REVIEW_DIRECTORY",
    "LocalClassificationStore",
    "review_queue_path",
]

LANDSCAPE_DIRECTORY: Final = "landscape"
CLASSIFICATIONS_DIRECTORY: Final = "classifications"
REVIEW_DIRECTORY: Final = "review"
_ROLE: Final = "the landscape classification cache"


def review_queue_path(data_dir: Path, caselist: str, topic_id: str) -> Path:
    """`<data_dir>/landscape/review/<caselist>/<topic id>-review-queue.csv`."""
    return data_dir / LANDSCAPE_DIRECTORY / REVIEW_DIRECTORY / caselist / f"{topic_id}-review-queue.csv"


class LocalClassificationStore:
    """The cache and queue files of one data directory."""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / LANDSCAPE_DIRECTORY
        self._data_dir = data_dir

    def _cache_path(self, caselist: str) -> Path:
        return self._root / CLASSIFICATIONS_DIRECTORY / f"{caselist}.jsonl"

    async def read(self, caselist: str) -> tuple[CachedClassification, ...]:
        path = self._cache_path(caselist)
        with refused_as_access_denied("read", _ROLE):
            if not path.is_file():
                return ()
            with path.open(encoding="utf-8") as stream:
                entries: list[CachedClassification] = []
                for number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        entries.append(CachedClassification.model_validate_json(line))
                    except ValidationError as error:
                        raise ValueError(
                            f"line {number} of the {caselist} classification cache is not a cached result: "
                            f"{error.error_count()} errors"
                        ) from error
                return tuple(entries)

    async def replace(self, caselist: str, entries: Sequence[CachedClassification]) -> None:
        lines = sorted(
            json.dumps(
                entry.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            for entry in entries
        )
        path = self._cache_path(caselist)
        with refused_as_access_denied("write", _ROLE):
            path.parent.mkdir(parents=True, exist_ok=True)
            with atomic_replacement(path) as incoming:
                incoming.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    async def write_review_queue(self, caselist: str, topic_id: str, rows: Sequence[ReviewRow]) -> str:
        buffer = io.StringIO(newline="")
        write_review_queue_csv(rows, buffer)
        path = review_queue_path(self._data_dir, caselist, topic_id)
        with refused_as_access_denied("write", _ROLE):
            path.parent.mkdir(parents=True, exist_ok=True)
            with atomic_replacement(path) as incoming:
                incoming.write_text(buffer.getvalue(), encoding="utf-8", newline="")
        return str(path)
