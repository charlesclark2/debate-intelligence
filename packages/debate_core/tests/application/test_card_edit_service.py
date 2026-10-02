"""CardEditService: an edit is re-verified, saved once at the next revision, and logged, or nothing happens.

Every expected text, offset and span is worked out by hand from ``SOURCE`` (the same invented source as
``tests/evidence/test_edit_policy.py``, which explains each offset), never captured from the code
(`docs/process/working-agreements.md` §6). The property at the end checks random sequences of edits
against an oracle that tracks snapshot positions directly and shares no code with the policy.
"""

from __future__ import annotations

import dataclasses
import json
import os

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from tests.fixtures.verification.verification_world import VERIFIED_CITATION, VerificationWorld, run

from debate_core.application.card_edit_service import CardEditResult, CardEditService
from debate_core.application.errors import NotFound, RevisionMismatch
from debate_core.application.verify_manifest import VerifyManifest
from debate_core.domain import (
    Card,
    CardOmission,
    CardSpan,
    CitationField,
    CitationFieldSource,
    Interpolation,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)
from debate_core.evidence.edit_policy import NegationFlag
from debate_core.evidence.edits import (
    AddInterpolation,
    DeleteRange,
    EditCite,
    EditKind,
    EditProblem,
    EditTag,
    EvidenceEdit,
    EvidenceEditRefused,
    ForbiddenEvidenceEdit,
    InsertText,
    InterpolationBlocksDeletion,
    InvalidEvidenceEdit,
    MoveText,
    RemoveInterpolation,
    ReplaceText,
    SetMarkup,
)
from debate_core.evidence.manifest import CardManifest
from debate_core.evidence.markup import EvidenceMarkupSpan
from debate_core.evidence.verification_types import ReasonCode
from debate_core.testing import InMemoryCardEditLog, InMemoryCardRepository
from debate_core.testing.builders import DEFAULT_OWNER_ID, build_card_span

SOURCE = (
    "The council will not approve the new reservoir before 2030.\n\n"
    "Engineers say the old dam can hold for a decade at most.\n\n"
    "Residents don't expect rationing this summer."
)
PLAIN_TEXT = "The council will not approve the new reservoir before 2030."
CUT_RANGES = ((4, 28), (75, 117), (129, 164))
CUT_TEXT = (
    "council will not approvethe old dam can hold for a decade at most.don't expect rationing this summer."
)

ACTOR = "0ACT0000000000000000000001"
U, H = SpanStyle.UNDERLINE, SpanStyle.HIGHLIGHT
CLAIM, WARRANT, IMPACT = SpanPurpose.CLAIM, SpanPurpose.WARRANT, SpanPurpose.IMPACT


class EditWorld:
    """The verifier's world plus a card repository, an edit log and the service, wired as a composition
    root would wire them."""

    def __init__(self, cards: InMemoryCardRepository | None = None) -> None:
        self.verification = VerificationWorld()
        self.cards = cards if cards is not None else InMemoryCardRepository()
        self.log = InMemoryCardEditLog()
        self.service = CardEditService(
            cards=self.cards,
            articles=self.verification.articles,
            snapshots=self.verification.snapshots,
            verifier=self.verification.verifier,
            edit_log=self.log,
            clock=self.verification.clock,
        )
        self.source = self.verification.add_source(SOURCE)

    def store(self, card: Card) -> Card:
        """Verify ``card`` the only way a status is set, and store it at revision 1."""
        recorded, result = run(self.verification.verifier.verify_and_record(card))
        assert result.is_verified
        return run(self.cards.create(recorded))

    def plain(self) -> Card:
        return self.store(
            self.verification.cut_card(
                self.source,
                0,
                59,
                (
                    EvidenceMarkupSpan.underline(4, 28, CLAIM),
                    EvidenceMarkupSpan.highlight(17, 20, CLAIM),
                    EvidenceMarkupSpan.underline(37, 58, IMPACT),
                ),
            )
        )

    def cut_unmarked(self) -> Card:
        """The cut card with no markup: stored UNVERIFIED (CARD_INCOMPLETE), as the verifier says."""
        recorded, result = run(
            self.verification.verifier.verify_and_record(
                self.verification.cut_card_from_ranges(self.source, CUT_RANGES, ())
            )
        )
        assert result.reason_codes == (ReasonCode.CARD_INCOMPLETE,)
        return run(self.cards.create(recorded))

    def cut(self) -> Card:
        return self.store(
            self.verification.cut_card_from_ranges(
                self.source,
                CUT_RANGES,
                (
                    EvidenceMarkupSpan.underline(4, 28, CLAIM),
                    EvidenceMarkupSpan.highlight(17, 20, CLAIM),
                    EvidenceMarkupSpan.underline(75, 117, WARRANT),
                    EvidenceMarkupSpan.highlight(83, 95, WARRANT),
                    EvidenceMarkupSpan.underline(129, 164, IMPACT),
                ),
            )
        )

    def edit(
        self, card: Card, operation: EvidenceEdit, *, expected_revision: int | None = None
    ) -> CardEditResult:
        revision = card.revision if expected_revision is None else expected_revision
        return run(self.service.edit(card.card_id, operation, expected_revision=revision, actor_id=ACTOR))

    def stored(self, card: Card) -> Card:
        return run(self.cards.get(card.card_id))


@pytest.fixture
def world() -> EditWorld:
    return EditWorld()


def is_verified(card: Card) -> bool:
    return card.verification_status is VerificationStatus.VERIFIED


# =============================================================================================
# ac1: accepted edits re-verify as VERIFIED and increment the revision by one
# =============================================================================================

ACCEPTED: list[EvidenceEdit] = [
    DeleteRange(5, 9),
    SetMarkup((build_card_span(start_offset=0, end_offset=11, purpose=WARRANT),)),
    AddInterpolation(0, "the U.S."),
    RemoveInterpolation(3),
    EditTag("Water policy is stalled"),
    EditCite(
        VERIFIED_CITATION.evolve(
            author_credentials=CitationField[str](
                value="Professor of hydrology", source=CitationFieldSource.BYLINE, verified=False
            )
        )
    ),
]


@pytest.mark.parametrize("operation", ACCEPTED, ids=lambda operation: type(operation).__name__)
@pytest.mark.parametrize("shape", ["plain", "cut"])
def test_every_allowed_kind_of_edit_keeps_a_verified_card_verified_at_the_next_revision(
    world: EditWorld, shape: str, operation: EvidenceEdit
) -> None:
    card = world.plain() if shape == "plain" else world.cut()
    card = run(
        world.cards.save(
            card.evolve(interpolations=(Interpolation(anchor=3, text="note"),)), expected_revision=1
        )
    )
    assert (card.revision, is_verified(card)) == (2, True)

    result = world.edit(card, operation)

    assert is_verified(result.card)
    assert result.verification.is_verified
    assert result.reasons == ()
    assert (result.status_before, result.status_after) == (
        VerificationStatus.VERIFIED,
        VerificationStatus.VERIFIED,
    )
    assert result.card.revision == 3
    assert world.stored(card) == result.card
    assert (result.entry.revision_before, result.entry.revision_after) == (2, 3)
    assert world.log.entries == [result.entry]


def test_a_deletion_is_saved_as_the_policy_cut_it(world: EditWorld) -> None:
    """Delete "will " from the cut card (evidence 8-13, snapshot 12-17): its own omission."""
    card = world.cut()

    saved = world.edit(card, DeleteRange(8, 13)).card

    assert saved.evidence_text == (
        "council not approvethe old dam can hold for a decade at most.don't expect rationing this summer."
    )
    assert [(o.start_offset, o.end_offset) for o in saved.omitted_ranges] == [(12, 17), (28, 75), (117, 129)]
    assert saved.revision == 2
    assert is_verified(saved)


def test_successive_edits_each_add_one_revision_and_one_entry(world: EditWorld) -> None:
    card = world.cut()

    first = world.edit(card, DeleteRange(8, 13)).card
    second = world.edit(first, EditTag("Rationing is years away")).card
    third = world.edit(second, AddInterpolation(0, "the city")).card

    assert [first.revision, second.revision, third.revision] == [2, 3, 4]
    assert [(e.revision_before, e.revision_after) for e in world.log.entries] == [(1, 2), (2, 3), (3, 4)]
    assert [e.edit_kind for e in world.log.entries] == [
        EditKind.DELETE_RANGE,
        EditKind.EDIT_TAG,
        EditKind.ADD_INTERPOLATION,
    ]
    assert world.stored(card) == third


# =============================================================================================
# Re-verify, then save with the verdict, whatever it is
# =============================================================================================

V, UNV = VerificationStatus.VERIFIED, VerificationStatus.UNVERIFIED


def statuses(result: CardEditResult) -> tuple[VerificationStatus, VerificationStatus]:
    return result.entry.status_before, result.entry.status_after


def test_a_verified_card_that_loses_its_markup_is_saved_unverified_and_markup_brings_it_back(
    world: EditWorld,
) -> None:
    """Delete 4-58 of the plain card: every underlined character goes, "The " and "." stay."""
    card = world.plain()

    stripped = world.edit(card, DeleteRange(4, 58))

    assert stripped.card.evidence_text == "The ."
    assert stripped.card.spans == ()
    assert stripped.card.verification_status is UNV
    assert stripped.verification.reason_codes == (ReasonCode.CARD_INCOMPLETE,)
    assert [reason.code for reason in stripped.reasons] == [ReasonCode.CARD_INCOMPLETE]
    assert statuses(stripped) == (V, UNV)
    assert (stripped.card.revision, world.stored(card)) == (2, stripped.card)

    remarked = world.edit(stripped.card, SetMarkup((build_card_span(start_offset=0, end_offset=3),)))

    assert remarked.card.verification_status is V
    assert remarked.reasons == ()
    assert statuses(remarked) == (UNV, V)
    assert remarked.card.revision == 3
    assert [(entry.status_before, entry.status_after) for entry in world.log.entries] == [(V, UNV), (UNV, V)]


def test_clearing_the_markup_is_saved_unverified_with_the_verifiers_reason(world: EditWorld) -> None:
    card = world.cut()

    result = world.edit(card, SetMarkup(()))

    assert result.card.verification_status is UNV
    assert result.verification.reason_codes == (ReasonCode.CARD_INCOMPLETE,)
    assert world.stored(card) == result.card
    assert world.log.entries == [result.entry]


def test_a_cite_edit_that_unverifies_a_required_field_is_saved_unverified(world: EditWorld) -> None:
    """The student may change the title. Their value is unverified until the citation service
    re-resolves it (v1-e06-t01 ac5), so the card is saved UNVERIFIED with the cite reason meanwhile."""
    card = world.cut()
    title = CitationField[str](
        value="Reservoir plans stall", source=CitationFieldSource.BYLINE, verified=False
    )

    result = world.edit(card, EditCite(card.citation.evolve(title=title)))

    assert result.card.citation.title == title
    assert result.verification.reason_codes == (ReasonCode.CITATION_UNVERIFIED,)
    assert statuses(result) == (V, UNV)
    assert world.stored(card) == result.card


def test_a_changed_cite_field_claiming_verification_is_still_refused(world: EditWorld) -> None:
    card = world.cut()
    forged = CitationField[str](value="An invented title", source=CitationFieldSource.CROSSREF, verified=True)

    with pytest.raises(InvalidEvidenceEdit) as refused:
        world.edit(card, EditCite(card.citation.evolve(title=forged)))

    assert refused.value.problem is EditProblem.CITATION_CLAIMS_VERIFICATION
    assert world.stored(card) == card
    assert world.log.entries == []


def blank_card(world: EditWorld) -> Card:
    return run(
        world.cards.create(
            Card(
                owner_id=DEFAULT_OWNER_ID,
                article_id=world.source.snapshot.article_id,
                tag="A card with nothing cut yet",
                provenance_mode=world.source.snapshot.provenance_mode,
            )
        )
    )


def test_a_card_that_quotes_nothing_can_have_its_tag_and_cite_edited(world: EditWorld) -> None:
    blank = blank_card(world)
    credentials = CitationField[str](value="Hydrologist", source=CitationFieldSource.BYLINE, verified=False)

    retagged = world.edit(blank, EditTag("Still nothing cut"))
    recited = world.edit(retagged.card, EditCite(blank.citation.evolve(author_credentials=credentials)))

    assert (retagged.card.tag, retagged.card.revision, retagged.card.evidence_text) == (
        "Still nothing cut",
        2,
        "",
    )
    assert recited.card.citation.author_credentials == credentials
    assert recited.card.revision == 3
    assert statuses(retagged) == statuses(recited) == (UNV, UNV)
    assert ReasonCode.SNAPSHOT_MISSING in retagged.verification.reason_codes
    assert world.stored(blank) == recited.card
    assert len(world.log.entries) == 2


@pytest.mark.parametrize(
    "operation",
    [DeleteRange(0, 1), SetMarkup(()), AddInterpolation(0, "x"), RemoveInterpolation(0)],
    ids=lambda operation: type(operation).__name__,
)
def test_a_quotation_edit_on_a_card_that_quotes_nothing_is_refused(
    world: EditWorld, operation: EvidenceEdit
) -> None:
    blank = blank_card(world)

    with pytest.raises(InvalidEvidenceEdit) as refused:
        world.edit(blank, operation)

    assert refused.value.problem is EditProblem.CARD_HAS_NO_EVIDENCE
    assert world.stored(blank) == blank
    assert world.log.entries == []


def test_a_tag_edit_on_a_card_that_does_not_match_its_snapshot_is_saved_untouched_and_unverified(
    world: EditWorld,
) -> None:
    """The stored card claims VERIFIED but its text was altered in storage ("council" to "cooncil").
    A tag edit neither repairs nor refuses it: the quotation is saved as it was, and the verifier says
    TEXT_MISMATCH."""
    card = world.cut()
    tampered = run(world.cards.save(card.evolve(evidence_text="cooncil" + CUT_TEXT[7:]), expected_revision=1))
    assert tampered.verification_status is V

    result = world.edit(tampered, EditTag("Rationing is years away"))

    assert result.card.evidence_text == "cooncil" + CUT_TEXT[7:]
    assert result.card.tag == "Rationing is years away"
    assert result.verification.reason_codes == (ReasonCode.TEXT_MISMATCH,)
    assert statuses(result) == (V, UNV)
    assert world.stored(card) == result.card


def test_a_quotation_edit_on_that_card_is_still_refused(world: EditWorld) -> None:
    card = world.cut()
    tampered = run(world.cards.save(card.evolve(evidence_text="cooncil" + CUT_TEXT[7:]), expected_revision=1))

    with pytest.raises(InvalidEvidenceEdit) as refused:
        world.edit(tampered, DeleteRange(8, 13))

    assert refused.value.problem is EditProblem.QUOTATION_DOES_NOT_MATCH_SNAPSHOT
    assert world.stored(card) == tampered


def test_a_quotation_edit_to_a_card_whose_snapshot_is_gone_propagates_not_found(world: EditWorld) -> None:
    orphan = run(
        world.cards.create(
            world.cut().evolve(card_id="0CRD0000000000000000000099", snapshot_id="0SNP0000000000000000000099")
        )
    )

    with pytest.raises(NotFound):
        world.edit(orphan, DeleteRange(0, 4))
    assert world.log.entries == []


def test_a_tag_edit_to_that_card_loads_nothing_and_is_saved_with_snapshot_missing(world: EditWorld) -> None:
    orphan = run(
        world.cards.create(
            world.cut().evolve(card_id="0CRD0000000000000000000099", snapshot_id="0SNP0000000000000000000099")
        )
    )

    result = world.edit(orphan, EditTag("x"))

    assert result.verification.reason_codes == (ReasonCode.SNAPSHOT_MISSING,)
    assert result.card.revision == 2


# =============================================================================================
# ac2: insertions, substitutions and moves leave the stored card unchanged
# =============================================================================================


@pytest.mark.parametrize(
    "operation",
    [
        InsertText(13, "certainly "),
        ReplaceText(13, 16, "now"),
        ReplaceText(13, 16, "not"),
        MoveText(0, 8, 24),
    ],
    ids=repr,
)
def test_a_forbidden_edit_raises_and_leaves_the_stored_card_and_the_log_unchanged(
    world: EditWorld, operation: EvidenceEdit
) -> None:
    card = world.cut()

    with pytest.raises(ForbiddenEvidenceEdit) as refused:
        world.edit(card, operation)

    assert world.stored(card) == card
    assert world.log.entries == []
    payload = getattr(operation, "text", None)
    if payload is not None:
        assert payload not in str(refused.value)


# =============================================================================================
# ac3: interpolations are stored separately, rendered in brackets, excluded from verification
# =============================================================================================


def test_an_interpolation_is_saved_beside_the_quotation_and_is_not_verified(world: EditWorld) -> None:
    card = world.cut()

    saved = world.edit(card, AddInterpolation(24, "the council says")).card

    assert saved.evidence_text == CUT_TEXT
    assert saved.interpolations == (Interpolation(anchor=24, text="the council says"),)
    assert [item.rendered for item in saved.interpolations] == ["[the council says]"]
    reworded = saved.evolve(interpolations=(Interpolation(anchor=24, text="anything at all, unchecked"),))
    with_it, without_it = (
        world.verification.verify(reworded),
        world.verification.verify(saved.evolve(interpolations=())),
    )
    assert with_it.is_verified and without_it.is_verified
    assert with_it.checks_run == without_it.checks_run


def test_the_verify_manifest_carries_interpolations_untouched(world: EditWorld) -> None:
    """Its cards are domain Cards, so the field round-trips and verification ignores it."""
    saved = world.edit(world.cut(), AddInterpolation(24, "the council says")).card
    document = json.dumps(
        {
            "manifest_version": 1,
            "generated_at": "2026-10-02T12:00:00Z",
            "cards": [saved.model_dump(mode="json")],
        }
    ).encode()

    assert CardManifest.model_validate_json(document).cards[0].interpolations == saved.interpolations
    report = run(VerifyManifest(verifier=world.verification.verifier).verify(document))
    assert report.all_verified


# =============================================================================================
# ac4: a stale expected_revision raises RevisionMismatch
# =============================================================================================


def test_a_stale_revision_is_refused_and_nothing_changes(world: EditWorld) -> None:
    card = world.cut()
    world.edit(card, EditTag("Edited elsewhere first"))
    current = world.stored(card)

    with pytest.raises(RevisionMismatch) as stale:
        world.edit(card, DeleteRange(8, 13), expected_revision=1)

    assert (stale.value.expected_revision, stale.value.actual_revision) == (1, 2)
    assert world.stored(card) == current
    assert len(world.log.entries) == 1


def test_a_stale_revision_is_reported_before_the_edits_offsets_are_read(world: EditWorld) -> None:
    """The offsets index the text at the revision the student saw. After deleting 30 characters, 95-101
    is past the end of the current text; the answer is "your copy is stale", not "out of range"."""
    card = world.cut()
    world.edit(card, DeleteRange(30, 60))

    with pytest.raises(RevisionMismatch):
        world.edit(card, DeleteRange(95, 101), expected_revision=1)


class RacingCardRepository(InMemoryCardRepository):
    """Another writer saves the card between the service reading it and saving it."""

    async def get(self, card_id: str) -> Card:
        read = await super().get(card_id)
        await super().save(
            read.evolve(tag="A reprocessing job got here first"), expected_revision=read.revision
        )
        return read


def test_an_edit_that_loses_a_race_is_refused_at_the_save_and_logs_nothing() -> None:
    world = EditWorld(cards=RacingCardRepository())
    card = world.cut()

    with pytest.raises(RevisionMismatch) as raced:
        world.edit(card, DeleteRange(8, 13))

    assert (raced.value.expected_revision, raced.value.actual_revision) == (1, 2)
    stored = run(InMemoryCardRepository.get(world.cards, card.card_id))
    assert (stored.tag, stored.evidence_text) == ("A reprocessing job got here first", CUT_TEXT)
    assert world.log.entries == []


# =============================================================================================
# ac5: one audit entry per accepted edit, holding no evidence and no student data beyond the actor
# =============================================================================================


def test_an_accepted_edit_appends_one_entry_with_the_actor_kind_revisions_and_time(world: EditWorld) -> None:
    card = world.cut()

    result = world.edit(card, DeleteRange(8, 13))

    assert {field.name for field in dataclasses.fields(result.entry)} == {
        "card_id",
        "actor_id",
        "edit_kind",
        "revision_before",
        "revision_after",
        "status_before",
        "status_after",
        "recorded_at",
        "negation_flag",
    }
    assert result.entry.card_id == card.card_id
    assert result.entry.actor_id == ACTOR
    assert result.entry.edit_kind is EditKind.DELETE_RANGE
    assert (result.entry.revision_before, result.entry.revision_after) == (1, 2)
    assert (result.entry.status_before, result.entry.status_after) == (V, V)
    assert result.entry.recorded_at == world.verification.clock.now()
    assert run(world.log.entries_for(card.card_id)) == (result.entry,)


def test_no_entry_holds_evidence_a_tag_a_cite_or_an_interpolation(world: EditWorld) -> None:
    card = world.cut()
    world.edit(card, DeleteRange(13, 17))
    world.edit(world.stored(card), AddInterpolation(0, "Brightwater's"))
    world.edit(world.stored(card), EditTag("Rationing is years away"))

    logged = "".join(repr(entry) for entry in world.log.entries)

    for text in ("council", "not ", "approve", "dam", "Brightwater", "Rationing", "Invented", "example.org"):
        assert text not in logged
    assert len(world.log.entries) == 3


def test_a_refused_edit_appends_nothing(world: EditWorld) -> None:
    card = world.cut()
    refusals: list[EvidenceEdit] = [InsertText(0, "x"), DeleteRange(0, 101), AddInterpolation(0, "[x]")]
    for operation in refusals:
        with pytest.raises(EvidenceEditRefused):
            world.edit(card, operation)

    assert world.log.entries == []
    assert world.stored(card) == card


# =============================================================================================
# ac6: a dropped negation is accepted and flagged, in the result and the log
# =============================================================================================


def test_a_dropped_not_is_saved_and_flagged_in_the_result_and_the_entry(world: EditWorld) -> None:
    """Delete "not " (evidence 13-17, snapshot 17-21)."""
    card = world.cut()

    result = world.edit(card, DeleteRange(13, 17))

    flag = NegationFlag(CardOmission(start_offset=17, end_offset=21))
    assert result.negation_flag == flag
    assert result.entry.negation_flag == flag
    assert is_verified(result.card)
    assert result.card.revision == 2


def test_an_ordinary_deletion_is_saved_unflagged(world: EditWorld) -> None:
    result = world.edit(world.cut(), DeleteRange(8, 13))

    assert result.negation_flag is None
    assert result.entry.negation_flag is None


def test_only_deletions_are_ever_flagged(world: EditWorld) -> None:
    card = world.cut()
    world.edit(card, EditTag("Not no never"))
    world.edit(world.stored(card), AddInterpolation(0, "not"))

    assert [entry.negation_flag for entry in world.log.entries] == [None, None]


# =============================================================================================
# Property: any sequence of allowed edits leaves the card, and the status, an oracle predicts
# =============================================================================================

EXAMPLES = int(os.environ.get("CARD_EDIT_PROPERTY_EXAMPLES", "200"))


@dataclasses.dataclass
class Oracle:
    """What the card should be, tracked as snapshot positions, with no offset arithmetic shared with the
    code under test."""

    kept: list[int]
    marks: dict[tuple[SpanStyle, int], SpanPurpose | None]
    anchors: dict[int, str]

    @classmethod
    def of(cls, card: Card) -> Oracle:
        kept = [position for start, end in CUT_RANGES for position in range(start, end)]
        return cls(kept, marks_of(card, kept), {item.anchor: item.text for item in card.interpolations})

    def gaps(self) -> list[tuple[int, int]]:
        return [
            (left + 1, right)
            for left, right in zip(self.kept, self.kept[1:], strict=False)
            if right > left + 1
        ]

    @property
    def status(self) -> VerificationStatus:
        """The source and cite are intact, so the card verifies exactly when something is marked."""
        return V if self.marks else UNV

    def seams(self) -> list[int]:
        return [index for index in range(1, len(self.kept)) if self.kept[index] > self.kept[index - 1] + 1]


def marks_of(card: Card, kept: list[int]) -> dict[tuple[SpanStyle, int], SpanPurpose | None]:
    """Each marked character of the card, as (style, snapshot position) -> purpose."""
    return {
        (span.style, kept[index]): span.purpose
        for span in card.spans
        for index in range(span.start_offset, span.end_offset)
    }


def check_matches(result: CardEditResult, oracle: Oracle, status_before: VerificationStatus) -> None:
    card, kept = result.card, oracle.kept
    assert card.verification_status is oracle.status
    assert result.verification.reason_codes == (() if oracle.status is V else (ReasonCode.CARD_INCOMPLETE,))
    assert statuses(result) == (status_before, oracle.status)
    assert card.evidence_text == "".join(SOURCE[position] for position in kept)
    assert [p for start, end in card.quoted_ranges for p in range(start, end)] == kept
    assert (card.evidence_start_offset, card.evidence_end_offset) == (kept[0], kept[-1] + 1)
    assert [(o.start_offset, o.end_offset) for o in card.omitted_ranges] == oracle.gaps()
    assert marks_of(card, kept) == oracle.marks
    assert {item.anchor: item.text for item in card.interpolations} == oracle.anchors
    for style in SpanStyle:
        spans = card.spans_of_style(style)
        assert all(
            left.end_offset <= right.start_offset for left, right in zip(spans, spans[1:], strict=False)
        )


def evidence_offset(data: st.DataObject, oracle: Oracle, low: int) -> int:
    """An offset in [low, len], drawn often at a seam or an edge, where an off-by-one would show."""
    n = len(oracle.kept)
    special = [offset for offset in (0, *oracle.seams(), n) if offset >= low]
    if special and data.draw(st.booleans()):
        return data.draw(st.sampled_from(special))
    return data.draw(st.integers(low, n))


def draw_markup(data: st.DataObject, n: int) -> tuple[CardSpan, ...]:
    count = data.draw(st.integers(0, min(3, (n + 1) // 2)))  # 2 * count distinct points from n + 1
    points = sorted(
        data.draw(st.lists(st.integers(0, n), min_size=2 * count, max_size=2 * count, unique=True))
    )
    spans: list[CardSpan] = []
    for start, end in zip(points[::2], points[1::2], strict=True):
        purpose = data.draw(st.sampled_from([None, *SpanPurpose]))
        spans.append(CardSpan(start_offset=start, end_offset=end, style=U, purpose=purpose))
        if data.draw(st.booleans()):
            low = data.draw(st.integers(start, end - 1))
            high = data.draw(st.integers(low + 1, end))
            spans.append(CardSpan(start_offset=low, end_offset=high, style=H, purpose=purpose))
    return tuple(spans)


def step(data: st.DataObject, oracle: Oracle) -> tuple[EvidenceEdit, type[Exception] | None, Oracle]:
    """One edit, the exception the oracle expects (or None), and the oracle afterwards."""
    n = len(oracle.kept)
    kind = data.draw(st.sampled_from(["delete", "delete", "delete", "markup", "add", "remove", "tag"]))
    if kind == "delete":
        start = evidence_offset(data, oracle, 0)
        if start == n:
            start = n - 1
        end = evidence_offset(data, oracle, start + 1)
        kept = oracle.kept[:start] + oracle.kept[end:]
        if not kept:
            return DeleteRange(start, end), InvalidEvidenceEdit, oracle
        if any(start < anchor < end for anchor in oracle.anchors) or {start, end} <= oracle.anchors.keys():
            return DeleteRange(start, end), InterpolationBlocksDeletion, oracle
        marks = {key: purpose for key, purpose in oracle.marks.items() if key[1] in kept}
        anchors = {(a if a <= start else a - (end - start)): t for a, t in oracle.anchors.items()}
        event(f"delete: {'at an edge' if start == 0 or end == n else 'inside'}")
        if any(start < seam < end for seam in oracle.seams()):
            event("delete: across a cut")
        if start in oracle.seams() or end in oracle.seams():
            event("delete: touching an omission")
        if anchors != oracle.anchors:
            event("delete: moved an interpolation")
        if start in oracle.anchors or end in oracle.anchors:
            event("delete: an interpolation at its edge")
        if (
            start > 0
            and end < n
            and any(
                (style, oracle.kept[start - 1]) in oracle.marks and (style, oracle.kept[end]) in oracle.marks
                for style in SpanStyle
            )
        ):
            event("delete: cut through a marked run")
        after = Oracle(kept, marks, anchors)
        if len(after.gaps()) < len(oracle.gaps()):
            event("delete: merged omissions")
        return DeleteRange(start, end), None, after
    elif kind == "markup":
        spans = draw_markup(data, n)
        if any(
            any(start < seam < end for seam in oracle.seams())
            for start, end in ((s.start_offset, s.end_offset) for s in spans)
        ):
            event("markup: a span across a cut")
        marks = {
            (s.style, oracle.kept[i]): s.purpose for s in spans for i in range(s.start_offset, s.end_offset)
        }
        return SetMarkup(spans), None, Oracle(oracle.kept, marks, oracle.anchors)
    elif kind == "add":
        anchor = evidence_offset(data, oracle, 0)
        text = data.draw(st.text(alphabet="abc xyz'", min_size=1, max_size=8).filter(str.strip))
        if anchor in oracle.anchors:
            return AddInterpolation(anchor, text), InvalidEvidenceEdit, oracle
        return (
            AddInterpolation(anchor, text),
            None,
            Oracle(oracle.kept, oracle.marks, {**oracle.anchors, anchor: text.strip()}),
        )
    elif kind == "remove":
        existing = sorted(oracle.anchors)
        anchor = (
            data.draw(st.sampled_from(existing))
            if existing and data.draw(st.booleans())
            else data.draw(st.integers(0, n))
        )
        if anchor not in oracle.anchors:
            return RemoveInterpolation(anchor), InvalidEvidenceEdit, oracle
        return (
            RemoveInterpolation(anchor),
            None,
            Oracle(oracle.kept, oracle.marks, {a: t for a, t in oracle.anchors.items() if a != anchor}),
        )
    else:
        return (
            EditTag(data.draw(st.text(alphabet="Tag words", min_size=1, max_size=12).filter(str.strip))),
            None,
            oracle,
        )


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_any_sequence_of_allowed_edits_leaves_the_canonical_card_and_status_the_oracle_predicts(
    data: st.DataObject,
) -> None:
    world = EditWorld()
    unmarked = data.draw(st.integers(0, 3), label="start") == 0
    card = world.cut_unmarked() if unmarked else world.cut()
    event(f"start: {'UNVERIFIED, no markup' if unmarked else 'VERIFIED'}")
    oracle = Oracle.of(card)
    assert card.verification_status is oracle.status
    revision = 1
    for _ in range(data.draw(st.integers(1, 8), label="steps")):
        operation, expected, after = step(data, oracle)
        before = world.stored(card)
        if expected is None:
            result = world.edit(before, operation)
            revision += 1
            event(f"{type(operation).__name__}: accepted, {oracle.status.value} to {after.status.value}")
            status_before, oracle = oracle.status, after
            assert result.card.revision == revision
            assert world.stored(card) == result.card
            check_matches(result, oracle, status_before)
            event(f"omissions after an accepted edit: {len(result.card.omitted_ranges)}")
        else:
            with pytest.raises(expected):
                world.edit(before, operation)
            event(f"{type(operation).__name__}: refused with {expected.__name__}")
            assert world.stored(card) == before
        assert len(world.log.entries) == revision - 1
