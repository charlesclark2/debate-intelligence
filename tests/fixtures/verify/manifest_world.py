"""The manifests `debate-research verify` is tested on, and the snapshots they are checked against.

One scenario serves every level of the verify tests:

* the use case's tests verify the committed manifests against a :class:`ManifestWorld` held in
  memory;
* the CLI's tests and `tests/integration/test_verify_cli.py` verify them against a data directory
  that :func:`build_fixture_data_dir` writes with the real local adapters (SQLite and the
  filesystem blob store), so the command reads snapshots exactly as it does on a student's laptop;
* `uv run python -m tests.fixtures.verify.manifest_world` writes the committed manifests, and a test
  fails if building the scenario again does not reproduce them byte for byte.

Snapshots go the way production's do: ``SnapshotService.create`` stores them and the record is saved
through the article repository. Cards are cut by ``EvidenceExtractor`` and put on a card by
``place_evidence_on_card``, the production mapping (ADR-0018), as
`tests/fixtures/verification/verification_world.py` does; its constants and its ``run`` helper are
reused here. That world is not reused whole because its stores are typed as the in-memory fakes,
which its own tests depend on (``world.blobs.corrupt``), and this scenario also has to be written to
disk. Every id comes from a sequential generator and every hash from fixed text, so building twice
gives the same bytes.

Every source text is invented. The verdict each card should get is written by hand in the tests,
never read back from a run.

The three manifests:

* ``all_verified.json``: the whole first sentence, the same sentence with a cut, and the second
  paragraph. Every card verifies.
* ``tampered.json``: ``all_verified.json`` with one character of the third card changed (``had`` to
  ``has``), so its length still fits its envelope.
* ``mixed.json``: the two honest cards, the tampered card, a card whose text no longer fits its
  envelope (it passes the manifest schema and fails the domain's length invariant), and a card cut
  from a snapshot this data directory has never held.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.fixtures.verification.verification_world import (
    ARTICLE_ID,
    CANONICAL_URL,
    EXTRACTOR_VERSION,
    RETRIEVED_AT,
    VERIFIED_CITATION,
    run,
)

from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports import ArticleRepository, SnapshotStore
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.application.verify_manifest import ManifestVerificationReport, VerifyManifest
from debate_core.domain import AccessStatus, Card, ProvenanceMode, SpanPurpose
from debate_core.evidence.card_mapping import place_evidence_on_card
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.manifest import CardManifest
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan
from debate_core.evidence.selection import EvidenceSelection
from debate_core.integrations.local import FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.sqlite_repos import SqliteArticleRepository
from debate_core.testing import (
    FixedClock,
    InMemoryArticleRepository,
    InMemorySnapshotStore,
    SequentialIdGenerator,
)
from debate_core.testing.builders import DEFAULT_OWNER_ID

FIXTURE_DIR = Path(__file__).resolve().parent
ALL_VERIFIED = FIXTURE_DIR / "all_verified.json"
TAMPERED = FIXTURE_DIR / "tampered.json"
MIXED = FIXTURE_DIR / "mixed.json"

GENERATED_AT_TEXT = "2026-10-01T12:00:00Z"
CARDS_WRITTEN_AT = datetime(2026, 10, 1, 11, 0, tzinfo=UTC)

WELLS = "Wells across the invented Marrow basin ran dry in 2031.\n\nNobody in the basin had planned for it."
"""The one source the fixture data directory holds. First sentence 0-55, second paragraph 57-96."""

FENN = "Reservoirs in the invented Fenn valley held water through 2040."
"""A source that was snapshotted somewhere else: the data directory never holds it."""


class ManifestWorld:
    """A snapshot service, the verifier and the use case over whichever stores it is given."""

    def __init__(self, *, blobs: SnapshotStore, articles: ArticleRepository, id_prefix: str = "") -> None:
        self.clock = FixedClock()
        self.articles = articles
        self.snapshots = SnapshotService(
            blobs=blobs, clock=self.clock, id_generator=SequentialIdGenerator(f"{id_prefix}SNAP")
        )
        self.verifier = EvidenceVerifier(articles=articles, snapshots=self.snapshots, clock=self.clock)
        self.use_case = VerifyManifest(verifier=self.verifier)
        self._card_ids = SequentialIdGenerator(f"{id_prefix}CARD")
        self._span_ids = SequentialIdGenerator(f"{id_prefix}SPAN")

    @classmethod
    def in_memory(cls, *, id_prefix: str = "") -> ManifestWorld:
        return cls(blobs=InMemorySnapshotStore(), articles=InMemoryArticleRepository(), id_prefix=id_prefix)

    def add_source(self, extracted_text: str) -> LoadedSnapshot:
        """Create, save and load a snapshot of ``extracted_text``, as an article service would."""
        snapshot = run(
            self.snapshots.create(
                article_id=ARTICLE_ID,
                raw_bytes=extracted_text.encode("utf-8"),
                extracted_text=extracted_text,
                canonical_url=CANONICAL_URL,
                retrieved_at=RETRIEVED_AT,
                extractor_version=EXTRACTOR_VERSION,
                provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
                access_status=AccessStatus.ACCESSIBLE,
            )
        )
        run(self.articles.save_snapshot(snapshot))
        return run(self.snapshots.load(snapshot))

    def cut(self, source: LoadedSnapshot, ranges: tuple[tuple[int, int], ...], tag: str) -> Card:
        """A card quoting ``ranges`` of ``source`` (omitting what lies between), each piece underlined."""
        evidence = EvidenceExtractor().extract(
            source.snapshot, source.normalized, EvidenceSelection.of_offsets(*ranges)
        )
        spans = tuple(
            EvidenceMarkupSpan.underline(segment.start, segment.end, SpanPurpose.CLAIM)
            for segment in evidence.segments
        )
        blank = Card(
            card_id=self._card_ids.new_id(),
            owner_id=DEFAULT_OWNER_ID,
            article_id=source.snapshot.article_id,
            tag=tag,
            citation=VERIFIED_CITATION,
            provenance_mode=ProvenanceMode.PASTED,  # replaced by the snapshot's, by the mapping
            created_at=CARDS_WRITTEN_AT,
            updated_at=CARDS_WRITTEN_AT,
        )
        card = place_evidence_on_card(blank, CardMarkup(evidence, spans))
        # The mapping mints span ids as ULIDs; numbered instead, so a rebuild gives the same bytes.
        return card.evolve(spans=tuple(span.evolve(span_id=self._span_ids.new_id()) for span in card.spans))

    def verify(self, document: bytes) -> ManifestVerificationReport:
        return run(self.use_case.verify(document))


@dataclass(frozen=True)
class FixtureManifests:
    """The scenario's three manifests, as the bytes committed beside this module."""

    all_verified: bytes
    tampered: bytes
    mixed: bytes


def build_fixture_manifests(world: ManifestWorld) -> FixtureManifests:
    """Snapshot ``WELLS`` into ``world``, cut the scenario's cards from it, and write the manifests.

    The card from ``FENN`` is cut in a world of its own, so ``world`` never holds its snapshot.
    """
    wells = world.add_source(WELLS)
    sentence = world.cut(wells, ((0, 55),), "Marrow basin wells ran dry in 2031")
    with_cut = world.cut(wells, ((0, 6), (33, 55)), "Wells ran dry in 2031, with where cut out")
    planned = world.cut(wells, ((57, 96),), "Nobody in the basin planned for it")
    tampered = planned.evolve(evidence_text=planned.evidence_text.replace("had", "has"))
    overlong = world.cut(wells, ((0, 55),), "A card whose text no longer fits its envelope")
    elsewhere = ManifestWorld.in_memory(id_prefix="AWAY")
    fenn = elsewhere.cut(elsewhere.add_source(FENN), ((0, 63),), "Fenn valley reservoirs held water")

    # The domain refuses this card, so it can only exist as JSON: ten characters longer than its
    # envelope, which the manifest schema cannot see and Card's length invariant can.
    overlong_entry: dict[str, Any] = overlong.model_dump(mode="json")
    overlong_entry["evidence_text"] = overlong.evidence_text.replace("2031.", "2031, not 2035.")

    return FixtureManifests(
        all_verified=_manifest(sentence, with_cut, planned),
        tampered=_manifest(sentence, with_cut, tampered),
        mixed=_manifest(sentence, with_cut, tampered, overlong_entry, fenn),
    )


def build_fixture_data_dir(data_dir: Path) -> FixtureManifests:
    """Write the scenario's snapshots into ``data_dir`` with the real local adapters."""
    database = SqliteDatabase.open(data_dir)
    try:
        world = ManifestWorld(blobs=FsSnapshotStore(data_dir), articles=SqliteArticleRepository(database))
        return build_fixture_manifests(world)
    finally:
        database.close()


def _manifest(*cards: Card | dict[str, Any]) -> bytes:
    """A manifest of ``cards`` in the form the committed files take: indented, keys in model order."""
    entries = [card if isinstance(card, dict) else card.model_dump(mode="json") for card in cards]
    document = {"manifest_version": 1, "generated_at": GENERATED_AT_TEXT, "cards": entries}
    # Every honest card also goes through the model, so the fixtures cannot drift from what a
    # writer of CardManifest produces.
    honest = tuple(card for card in cards if isinstance(card, Card))
    CardManifest.model_validate({**document, "cards": honest})
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str]) -> int:
    """Rewrite the committed manifests: `uv run python -m tests.fixtures.verify.manifest_world`."""
    manifests = build_fixture_manifests(ManifestWorld.in_memory())
    for path, content in (
        (ALL_VERIFIED, manifests.all_verified),
        (TAMPERED, manifests.tampered),
        (MIXED, manifests.mixed),
    ):
        path.write_bytes(content)
        print(f"wrote {path.relative_to(FIXTURE_DIR.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
