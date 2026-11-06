"""The aggregate rebuild as `v1-e31-t10` found it, kept as the oracle of that task's tests.

By the PM's ruling of 2026-11-06, the rebuild that places cards from the placement state replaces this
one, and this one stays reachable only from the tests. Copied from the commit the task started from
(`81ed12e`), with only names changed:

* :class:`CardPlacerAtStart` is `caselist_card_stats.CardPlacer`;
* :func:`aggregates_at_start` is `CaselistParseService._rebuild` with `_occurrence_rows`, `_cards_of`,
  `_disclosure_spans`, `_index_rows` and `_failure_rows`, returning the bytes
  `LocalParsedStore.write_aggregates` would write for the index, the failures file and the table;
* the clusterer is :mod:`..evidence.near_duplicates_at_start`, the whole module as it was.

It is the old code, not the code under test, so it can disagree with it (working agreement 6). Do
not change it to follow the rebuild: a change to the rules belongs in a test of its own.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence

from debate_core.application.caselist.parse_sources import (
    DisclosureKey,
    EnumeratedSource,
    camp_path_digests,
    disclosure_key,
    is_aggregated,
    live_disclosures,
)
from debate_core.application.caselist_card_stats import ClusterPlacement
from debate_core.application.ports.parsed_store import (
    FAILURES_NAME,
    INDEX_NAME,
    OCCURRENCES_NAME,
    OccurrenceRecord,
    ParsedStore,
    SourceOutcome,
    StoreRecord,
)
from debate_core.application.ports.suppression import SuppressionState
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.debate_files import CardCompleteness, ParsedCard
from debate_core.evidence.abbreviated_links import (
    AbbreviationAnchor,
    FullCardWords,
    abbreviation_anchor,
    group_unmatched_abbreviations,
    link_abbreviated,
    matching_full_cards,
    short_cite_key,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint

from ..evidence.near_duplicates_at_start import BodyWords, NearDuplicateThresholds, cluster_near_duplicates

__all__ = ["CardPlacerAtStart", "aggregates_at_start", "rendered"]


class CardPlacerAtStart:
    """`caselist_card_stats.CardPlacer` at `81ed12e`."""

    def __init__(self, thresholds: NearDuplicateThresholds, markers: tuple[str, ...] | None) -> None:
        self._thresholds = thresholds
        self._markers = markers
        self._fingerprints: list[str] = []
        self._known: dict[str, str] = {}
        self._anchors: dict[int, AbbreviationAnchor | None] = {}
        self._bodies: dict[str, str] = {}
        self._copies: Counter[tuple[str, str | None]] = Counter()

    def add(self, card: ParsedCard) -> None:
        fingerprint = card_fingerprint(card).exact_fingerprint
        fingerprint = self._known.setdefault(fingerprint, fingerprint)
        if card.completeness is CardCompleteness.FULL:
            self._bodies.setdefault(fingerprint, card.evidence_text)
            self._copies[(fingerprint, short_cite_key(card.short_cite))] += 1
        else:
            self._anchors[len(self._fingerprints)] = abbreviation_anchor(card, self._markers)
        self._fingerprints.append(fingerprint)

    def placements(self) -> list[ClusterPlacement]:
        words = BodyWords(self._bodies)
        clusters = cluster_near_duplicates(self._bodies, self._thresholds, words=words)
        full_by_cite: defaultdict[str | None, dict[str, FullCardWords]] = defaultdict(dict)
        for (fingerprint, key), copies in self._copies.items():
            full_by_cite[key][fingerprint] = FullCardWords(
                clusters[fingerprint], key, words.spelled(fingerprint), copies
            )

        linked: dict[int, str] = {}
        keys: defaultdict[str, set[AbbreviationAnchor]] = defaultdict(set)
        not_grouped: set[str] = set()
        for position, anchor in self._anchors.items():
            if anchor is None:
                continue
            fingerprint = self._fingerprints[position]
            matches = matching_full_cards(anchor, full_by_cite[anchor.short_cite_key].values())
            cluster = link_abbreviated(anchor, matches)
            if cluster is not None:
                linked[position] = cluster
                continue
            keys[fingerprint].add(anchor)
            if matches:
                not_grouped.add(fingerprint)
        groups = group_unmatched_abbreviations(
            {
                fingerprint: next(iter(anchors))
                for fingerprint, anchors in keys.items()
                if len(anchors) == 1 and fingerprint not in not_grouped
            }
        )

        placed: list[ClusterPlacement] = []
        for position, fingerprint in enumerate(self._fingerprints):
            if position not in self._anchors:
                placed.append(
                    ClusterPlacement(fingerprint, clusters[fingerprint], ClusterMembership.NEAR_DUPLICATE)
                )
            elif position in linked:
                placed.append(
                    ClusterPlacement(fingerprint, linked[position], ClusterMembership.ABBREVIATED_LINK)
                )
            elif fingerprint in groups:
                placed.append(
                    ClusterPlacement(fingerprint, groups[fingerprint], ClusterMembership.ABBREVIATED_LINK)
                )
            else:
                placed.append(ClusterPlacement(fingerprint, fingerprint, ClusterMembership.UNLINKED))
        return placed


def rendered(records: Sequence[StoreRecord]) -> bytes:
    """What `LocalParsedStore` writes for `records`: one compact, key-sorted JSON line each."""
    return "".join(
        json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
        for record in records
    ).encode("utf-8")


async def aggregates_at_start(
    store: ParsedStore,
    *,
    caselist: str,
    version: str,
    parser_version: str,
    profile_version: str,
    sources: Sequence[EnumeratedSource],
    state: SuppressionState,
    markers: tuple[str, ...],
    thresholds: NearDuplicateThresholds | None = None,
) -> dict[str, bytes]:
    """The index, failures file and occurrence table today's rebuild writes for the directory, as bytes."""
    held = {source.sha256: source for source in sources}
    entries = await store.read_entries(caselist, version)
    index = [entry for entry in entries if is_aggregated(held.get(entry.source_sha256), state)]
    failures = [
        entry
        for entry in entries
        if entry.outcome is not SourceOutcome.PARSED and is_aggregated(held.get(entry.source_sha256), state)
    ]
    placer = CardPlacerAtStart(thresholds or NearDuplicateThresholds(), markers)
    cards: list[tuple[EnumeratedSource, int, int, CardCompleteness]] = []
    for entry in sorted(entries, key=lambda entry: entry.source_sha256):
        source = held.get(entry.source_sha256)
        if entry.outcome is not SourceOutcome.PARSED or source is None:
            continue
        live = live_disclosures(source, state)
        if not live:
            continue
        record = await store.read_document(caselist, version, source.sha256)
        assert record is not None
        document = record.to_parsed_document(live[0].path)
        for card in sorted(document.cards, key=lambda card: card.provenance.first_element_index):
            placer.add(card)
            provenance = card.provenance
            cards.append(
                (source, provenance.first_element_index, provenance.last_element_index, card.completeness)
            )
    placements = placer.placements()
    spans: dict[str, list[tuple[str | None, str, str, tuple[str, ...]]]] = {}
    order: list[tuple[str, str, int, str, str, int, int]] = []
    for position, ((source, first_element, _, _), placement) in enumerate(
        zip(cards, placements, strict=True)
    ):
        if source.sha256 not in spans:
            spans[source.sha256] = _disclosure_spans(source, state)
        for span, (disclosure, first, _, _) in enumerate(spans[source.sha256]):
            order.append(
                (placement.cluster_id, source.sha256, first_element, first, disclosure or "", position, span)
            )
    order.sort()
    rows: list[OccurrenceRecord] = []
    for *_, position, span in order:
        source, first_element, last_element, completeness = cards[position]
        placement = placements[position]
        disclosure, first, last, camp_paths = spans[source.sha256][span]
        rows.append(
            OccurrenceRecord(
                caselist=caselist,
                snapshot=first,
                last_snapshot=last,
                source_sha256=source.sha256,
                parser_version=parser_version,
                profile_version=profile_version,
                fingerprint_version=FINGERPRINT_VERSION,
                disclosure=disclosure,
                camp=source.camp,
                first_element_index=first_element,
                last_element_index=last_element,
                exact_fingerprint=placement.fingerprint,
                cluster_id=placement.cluster_id,
                membership=placement.membership,
                completeness=completeness,
                camp_path_disclosures=camp_paths,
            )
        )
    return {
        INDEX_NAME: rendered(index),
        FAILURES_NAME: rendered(failures),
        OCCURRENCES_NAME: rendered(rows),
    }


def _disclosure_spans(
    source: EnumeratedSource, state: SuppressionState
) -> list[tuple[str | None, str, str, tuple[str, ...]]]:
    spans: dict[DisclosureKey, tuple[str, str]] = {}
    for disclosed in live_disclosures(source, state):
        key = disclosure_key(source, disclosed)
        first, last = spans.get(key, (disclosed.snapshot, disclosed.snapshot))
        spans[key] = (min(first, disclosed.snapshot), max(last, disclosed.snapshot))
    return [
        (disclosure, first, last, camp_path_digests(source, state, first))
        for (disclosure, _), (first, last) in spans.items()
    ]
