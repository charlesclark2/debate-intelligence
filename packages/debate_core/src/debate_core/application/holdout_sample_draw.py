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
from debate_core.arguments.landscape.matcher import read_items
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape_classification import ItemKind

__all__ = ["drawn_from", "card_identities"]

_NO_FINGERPRINT_VERSION: Final = "none"


def card_identities(reading: SeedReading, occurrences: Iterable[OccurrenceRecord]) -> dict[str, CardIdentity]:
    """Every card of `reading` by item id: its read fingerprint, and its exact fingerprint and cluster from
    `occurrences` when the table holds a row for it (a card's rows agree on both, one per disclosure)."""
    by_card: dict[tuple[str, int], tuple[str, str]] = {}
    for row in occurrences:
        by_card.setdefault(
            (row.source_sha256, row.first_element_index), (row.exact_fingerprint, row.cluster_id)
        )
    names = CaselistNames(reading.caselist_names)
    identities: dict[str, CardIdentity] = {}
    for source in reading.sources:
        for item in read_items(source, names):
            if item.kind is not ItemKind.CARD or item.first_element_index is None:
                continue
            found = by_card.get((source.sha256, item.first_element_index))
            identities[item.item_id] = CardIdentity(
                item_id=item.item_id,
                source_sha256=source.sha256,
                read_fingerprint=item.fingerprint,
                exact_fingerprint=found[0] if found is not None else None,
                cluster_id=found[1] if found is not None else None,
            )
    return identities


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
