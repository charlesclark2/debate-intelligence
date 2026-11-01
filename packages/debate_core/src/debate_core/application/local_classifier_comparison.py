"""The local classifier comparison's reading half: a caselist's cards as feature rows (`v1-e32-t21`).

`scripts/compare_local_classifier.py` compares a local text classifier
(:mod:`~debate_core.arguments.landscape.local_classifier`) with the deterministic placements. It
reads the store once into a feature table, then trains and scores from that table as often as it is
asked. This module builds the table and says when it no longer stands:

* :func:`build_feature_table` places every card of a
  :class:`~debate_core.application.landscape_seeding.SeedReading` with the topic's
  :class:`~debate_core.arguments.landscape.matcher.PositionMatcher`, exactly as the classification
  service does, without its cache and without writing anything. It takes every team code of the
  caselist out of each tag, and keeps each disclosing team only as a digest keyed by a salt it draws
  for the build and keeps nowhere, so the table counts teams and names none;
* :func:`sources_no_longer_live` names the table's sources that a removal has since reached: no longer
  parsed in the store's version, or under a suppression the table was not built under. A table with
  any is read no further; the caller builds it again from the store, which no longer holds them.

The table is derived from caselist data. Its caller keeps it under the data directory and never in
the repository, and nothing here logs or returns a heading, tag or team in a `repr`.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, cast

from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.parsed_store import ParsedStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.application.review_queue_order import sources_a_removal_reached
from debate_core.arguments.landscape.local_classifier import (
    FeatureRow,
    code_words,
    feature_rows,
    row_from_json,
    row_to_json,
)
from debate_core.arguments.landscape.matcher import PositionMatcher
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD
from debate_core.arguments.landscape.source_headings import CaselistNames

__all__ = [
    "FEATURE_TABLE_SCHEMA",
    "FeatureTable",
    "build_feature_table",
    "feature_table_lines",
    "read_feature_table",
    "sources_no_longer_live",
    "suppressed_disclosures",
]

FEATURE_TABLE_SCHEMA: Final = "local-classifier-features-1"


@dataclass(frozen=True, slots=True)
class FeatureTable:
    """Every on-topic card of one caselist reading, as the classifier reads it, and what it was read from."""

    caselist: str
    version: str
    topic_id: str
    taxonomy_version: str
    through: date | None
    review_threshold: float
    suppressed_at_build: tuple[tuple[str, str], ...]
    """`(sha256, disclosure digest)` of every disclosure suppression of a table source when it was built."""
    rows: tuple[FeatureRow, ...] = field(repr=False)

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(row.source_sha256 for row in self.rows)


async def suppressed_disclosures(
    suppression: SuppressionList, sources: Iterable[str]
) -> tuple[tuple[str, str], ...]:
    """The disclosure suppressions in force on `sources`, sorted."""
    wanted = frozenset(sources)
    state = await load_suppression_state(suppression)
    return tuple(sorted(pair for pair in state.disclosures if pair[0] in wanted))


async def build_feature_table(
    reading: SeedReading,
    taxonomies: TaxonomyRepository,
    suppression: SuppressionList,
    *,
    through: date | None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> FeatureTable:
    """Every card of `reading` placed under its topic's taxonomy and overrides, as feature rows."""
    taxonomy = taxonomies.taxonomy(reading.topic_id)
    matcher = PositionMatcher(taxonomy, taxonomies.overrides(reading.topic_id))
    names = CaselistNames(reading.caselist_names)
    codes = code_words(reading.caselist_names)
    salt = secrets.token_bytes(16)
    rows = tuple(
        row
        for source in reading.sources
        for row in feature_rows(
            source, names, matcher, team_salt=salt, codes=codes, review_threshold=review_threshold
        )
    )
    return FeatureTable(
        caselist=reading.caselist,
        version=reading.version,
        topic_id=reading.topic_id,
        taxonomy_version=taxonomy.taxonomy_version,
        through=through,
        review_threshold=review_threshold,
        suppressed_at_build=await suppressed_disclosures(
            suppression, (source.sha256 for source in reading.sources)
        ),
        rows=rows,
    )


async def sources_no_longer_live(
    table: FeatureTable, *, store: ParsedStore, suppression: SuppressionList
) -> frozenset[str]:
    """The table's sources a removal has reached since it was built.

    One is no longer live when the store's version no longer holds it parsed, when it is suppressed
    whole, or when one of its disclosures is suppressed that was not when the table was built
    (:func:`~debate_core.application.review_queue_order.sources_a_removal_reached`, which the review
    queue's order model trained from a table is refused by too).
    """
    return await sources_a_removal_reached(
        table.caselist,
        table.version,
        table.sources,
        table.suppressed_at_build,
        store=store,
        suppression=suppression,
    )


def feature_table_lines(table: FeatureTable) -> Iterator[str]:
    """The table as JSON lines: a header naming what it was read from, then one row per card."""
    header = {
        "schema": FEATURE_TABLE_SCHEMA,
        "caselist": table.caselist,
        "version": table.version,
        "topic_id": table.topic_id,
        "taxonomy_version": table.taxonomy_version,
        "through": None if table.through is None else table.through.isoformat(),
        "review_threshold": table.review_threshold,
        "suppressed_at_build": [list(pair) for pair in table.suppressed_at_build],
        "rows": len(table.rows),
    }
    yield json.dumps(header, sort_keys=True, separators=(",", ":")) + "\n"
    for row in table.rows:
        yield row_to_json(row) + "\n"


def read_feature_table(lines: Iterable[str]) -> FeatureTable:
    """A table :func:`feature_table_lines` wrote. Raises `ValueError` on another schema or a short file."""
    read = iter(lines)
    header = cast(dict[str, Any], json.loads(next(read, "{}")))
    if header.get("schema") != FEATURE_TABLE_SCHEMA:
        raise ValueError(f"not a {FEATURE_TABLE_SCHEMA} feature table")
    rows = tuple(row_from_json(line) for line in read if line.strip())
    if len(rows) != header["rows"]:
        raise ValueError(f"the feature table names {header['rows']} rows and holds {len(rows)}")
    through = header["through"]
    return FeatureTable(
        caselist=str(header["caselist"]),
        version=str(header["version"]),
        topic_id=str(header["topic_id"]),
        taxonomy_version=str(header["taxonomy_version"]),
        through=None if through is None else date.fromisoformat(str(through)),
        review_threshold=float(header["review_threshold"]),
        suppressed_at_build=tuple(
            (str(sha), str(disclosure)) for sha, disclosure in header["suppressed_at_build"]
        ),
        rows=rows,
    )
