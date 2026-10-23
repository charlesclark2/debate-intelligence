"""A synthetic world for the lossless card writer (`v1-e33-t02`): sources, occurrences and recipes.

The writer reads a resolved recipe and the source bytes each card's occurrence names. A test, and
the operator's script that builds the fixture files a coach opens in Word
(`scripts/build_example_evidence_files.py`), both need the same thing: synthetic source documents
built in memory with :mod:`debate_core.testing.docx_builder`, put in a blob store, parsed by the E31
parser, and each card's occurrence row made exactly as the parse pipeline would make it, fingerprint
included. That is :class:`FileBuilderWorld`.

The parser is handed in, not imported: this package may not import an adapter (the layers contract).

**Nothing here is a real debate file.** Every school, team code, tag, cite and word of evidence is
invented. The schools and team codes are the repository's existing fictional ones.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

from debate_core.application.file_recipes import Resolution, ResolvedCard, ResolvedRecipe, recipe_hash
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import (
    Disclosure,
    Event,
    RoundLabel,
    Side,
    SourceDocument,
    SourceFormat,
    SourceOrigin,
)
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.file_recipe import FileRecipe, render_location
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.testing.fakes.persistence import InMemorySnapshotStore

__all__ = ["DEFAULT_DISCLOSURE", "FileBuilderWorld", "SourceCard", "SyntheticDisclosure"]

_SOURCE_PATH: Final = "synthetic-source.docx"


@dataclass(frozen=True, slots=True)
class SyntheticDisclosure:
    """Who disclosed a synthetic source: fictional, as every fixture is."""

    school: str = "Maple Grove"
    team_code: str = "QX"
    side: Side = Side.AFF
    tournament: str | None = "Riverbend Invitational"
    round: str | None = "Round 4"
    path: str = "Maple Grove/QX/aff-riverbend-r4.docx"


#: Who disclosed a source unless a test says otherwise.
DEFAULT_DISCLOSURE: Final = SyntheticDisclosure()


@dataclass(frozen=True, slots=True)
class SourceCard:
    """One card of a source as the parser read it, its occurrence row, and who disclosed it."""

    card: ParsedCard
    occurrence: OccurrenceRecord
    disclosure: Disclosure | None

    @property
    def fingerprint(self) -> str:
        return self.occurrence.exact_fingerprint


@dataclass
class FileBuilderWorld:
    """Sources in a blob store, parsed, with an occurrence row per card, ready to resolve recipes over."""

    parser: DebateFileParser
    caselist: str = "hspolicy26"
    event: Event = Event.POLICY
    snapshot: date = date(2026, 9, 15)
    last_snapshot: date = date(2026, 9, 22)
    snapshots: InMemorySnapshotStore = field(default_factory=InMemorySnapshotStore)
    documents: dict[str, ParsedDocument] = field(default_factory=lambda: {})

    async def add_source(
        self, content: bytes, *, disclosure: SyntheticDisclosure | None = DEFAULT_DISCLOSURE
    ) -> tuple[SourceCard, ...]:
        """Store `content`, parse it, and return each of its cards with its occurrence row.

        With `disclosure=None` the occurrence has a disclosure digest but nothing on record for it,
        which is the case t01's AUTO falls back to only when no attributed occurrence remains.
        """
        sha = await self.snapshots.put(content)
        source = SourceDocument(
            sha256=sha,
            byte_size=len(content),
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist=self.caselist,
            first_seen_snapshot=self.snapshot,
            last_seen_snapshot=self.last_snapshot,
        )
        parsed = self.parser.parse(content, source, source_path=_SOURCE_PATH, snapshot=self.snapshot)
        if not isinstance(parsed, ParsedDocument):
            raise ValueError(f"the synthetic source does not parse: {parsed.reason} {parsed.detail}")
        self.documents[sha] = parsed
        path = disclosure.path if disclosure is not None else _SOURCE_PATH
        record = None if disclosure is None else self._disclosure(sha, disclosure)
        cards: list[SourceCard] = []
        for card in parsed.cards:
            fingerprint = card_fingerprint(card).exact_fingerprint
            occurrence = OccurrenceRecord(
                caselist=self.caselist,
                snapshot=self.snapshot.isoformat(),
                last_snapshot=self.last_snapshot.isoformat(),
                source_sha256=sha,
                parser_version=self.parser.parser_version,
                profile_version=self.parser.profile_version,
                fingerprint_version=FINGERPRINT_VERSION,
                disclosure=disclosure_digest(self.caselist, path),
                first_element_index=card.provenance.first_element_index,
                last_element_index=card.provenance.last_element_index,
                exact_fingerprint=fingerprint,
                cluster_id=fingerprint,
                membership=ClusterMembership.UNLINKED,
                completeness=card.completeness,
            )
            cards.append(SourceCard(card=card, occurrence=occurrence, disclosure=record))
        return tuple(cards)

    def _disclosure(self, sha: str, disclosure: SyntheticDisclosure) -> Disclosure:
        return Disclosure(
            source_sha256=sha,
            caselist=self.caselist,
            snapshot=self.last_snapshot,
            event=self.event,
            school=disclosure.school,
            team_code=disclosure.team_code,
            side=disclosure.side,
            tournament=disclosure.tournament,
            round_label=RoundLabel.from_raw(disclosure.round) if disclosure.round else None,
            source_path=disclosure.path,
        )

    def resolve(
        self,
        recipe: FileRecipe,
        cards: Mapping[str, SourceCard],
        *,
        pinned: Sequence[str] = (),
    ) -> ResolvedRecipe:
        """The recipe resolved to `cards`, by fingerprint, as t01's resolver would resolve it."""
        resolved: list[ResolvedCard] = []
        for location, ref in recipe.card_refs():
            card = cards[ref.fingerprint]
            resolved.append(
                ResolvedCard(
                    path=render_location(location),
                    fingerprint=ref.fingerprint,
                    tag_override=ref.tag_override,
                    resolution=Resolution.PINNED if ref.fingerprint in pinned else Resolution.AUTO,
                    occurrence=card.occurrence,
                    disclosure=card.disclosure,
                )
            )
        return ResolvedRecipe(
            recipe=recipe,
            recipe_hash=recipe_hash(recipe),
            versions={self.caselist: self.parser.parser_version},
            cards=tuple(resolved),
            errors=(),
        )

    def recipe(
        self,
        blocks: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
        *,
        title: str = "Synthetic file",
        side: Side = Side.AFF,
    ) -> FileRecipe:
        """A recipe of one pocket and one hat holding `blocks`: `(heading, items)` in order."""
        return FileRecipe.model_validate(
            {
                "schema_version": 1,
                "title": title,
                "topic": "synthetic-topic",
                "format": str(self.event),
                "caselist": self.caselist,
                "position": "synthetic-position",
                "side": str(side),
                "fingerprint_version": FINGERPRINT_VERSION,
                "structure": [
                    {
                        "pocket": "Synthetic pocket",
                        "hats": [
                            {
                                "hat": "Synthetic hat",
                                "blocks": [
                                    {"block": heading, "items": list(items)} for heading, items in blocks
                                ],
                            }
                        ],
                    }
                ],
            }
        )
