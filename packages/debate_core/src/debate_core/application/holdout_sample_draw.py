"""The held-out sample's reading half (`v1-e32-t50`): each card's identity, from one reading and its table.

:func:`~debate_core.arguments.landscape.holdout_sample.holdout_sample` keeps every card of the first sample
out of the held-out one by the parser's card identity and the matcher's. This module reads both for every card
of a :class:`~debate_core.application.landscape_seeding.SeedReading`:

* the matcher's: each card as :func:`~debate_core.arguments.landscape.matcher.read_items` reads it, by the
  same item id the feature table and the sample's rows file use, with its
  :attr:`~debate_core.arguments.landscape.matcher.MatchItem.fingerprint`;
* the parser's: the card's exact fingerprint and near-duplicate cluster, from the occurrence table of the
  reading's own version directory, joined on the source's digest and the card's first paragraph, as a
  landscape run joins them (:func:`~debate_core.application.landscape_report.landscape_cards`). Cluster ids
  are comparable only inside one table, so the first sample's cards and the candidates are named from the
  same one.

Nothing here keeps a tag, heading or team: digests and ids only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.parsed_store import OccurrenceRecord, parse_version_directory
from debate_core.arguments.landscape.holdout_sample import CardIdentity

__all__ = ["drawn_from", "card_identities"]

_NO_FINGERPRINT_VERSION: Final = "none"


def card_identities(reading: SeedReading, occurrences: Iterable[OccurrenceRecord]) -> dict[str, CardIdentity]:
    """Every card of `reading` by item id: its read fingerprint, and its exact fingerprint and cluster from
    `occurrences` when the table holds a row for it (a card's rows agree on both, one per disclosure)."""
    return {}  # skeleton: no identity read yet


def drawn_from(
    reading: SeedReading, occurrences: Iterable[OccurrenceRecord], *, snapshot: str
) -> Mapping[str, object]:
    """What a held-out sample was drawn from, for its rows file's header: the snapshot, the store's version
    directory and its parser version, and the fingerprint versions the occurrence table was written under."""
    versions = sorted({row.fingerprint_version for row in occurrences}) or [_NO_FINGERPRINT_VERSION]
    return {
        "caselist": reading.caselist,
        "topic_id": reading.topic_id,
        "snapshot": snapshot,
        "version": reading.version,
        "parser_version": parse_version_directory(reading.version)[0],
        "fingerprint_versions": versions,
    }
