"""The verifier honours a card's omissions (`v1-e03-t07` ac7, ADR-0018).

A card cut with omissions by ``place_evidence_on_card`` verifies. Change any one of its omissions and
either the domain refuses the card, because the envelope minus the omissions is no longer as long as
the text, or the verifier finds the text no longer comes back out of the snapshot and reports
``TEXT_MISMATCH``. To reach the verifier, a changed omission is given an envelope whose end moves by
however many characters the change removed or restored, so the card stays constructible.

Expected offsets are worked out by hand from ``NORMALIZED`` (`docs/process/working-agreements.md` §6).
The exhaustive section compares the verifier with an oracle written here, a slice-and-join of the
snapshot text, and its counts are derived by hand in the comments.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from tests.fixtures.verification.verification_world import VerificationWorld

from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import Card, CardOmission, VerificationStatus
from debate_core.evidence.verification_types import ReasonCode, VerificationCheck

EXTRACTED = (
    "Groundwater in the Tessaly basin fell 4 metres in a decade.\n\n"
    "Farmers there now pump twice what the aquifer recharges.\n\n"
    "Without new limits, the wells will run dry by 2040.\n"
)
NORMALIZED = (
    "Groundwater in the Tessaly basin fell 4 metres in a decade.\n\n"
    "Farmers there now pump twice what the aquifer recharges.\n\n"
    "Without new limits, the wells will run dry by 2040."
)

# The honest card: kept 61-68 "Farmers", 78-89 " pump twice", 119-138 "Without new limits,"; omitted
# 68-78 " there now" and 89-119 " what the aquifer recharges.\n\n". Envelope 61-138 (77) less 40
# omitted is 37 characters.
KEPT = ((61, 68), (78, 89), (119, 138))
OMITTED = ((68, 78), (89, 119))
CUT_TEXT = "Farmers pump twiceWithout new limits,"


@pytest.fixture
def world() -> VerificationWorld:
    return VerificationWorld()


@pytest.fixture
def source(world: VerificationWorld) -> LoadedSnapshot:
    return world.add_source(EXTRACTED)


@pytest.fixture
def honest(world: VerificationWorld, source: LoadedSnapshot) -> Card:
    return world.cut_card_from_ranges(source, KEPT)


def with_omissions(card: Card, omitted: tuple[tuple[int, int], ...], *, fit_envelope: bool) -> Card:
    """``card`` claiming ``omitted`` instead of its own omissions, text unchanged.

    With ``fit_envelope``, the envelope's end moves by the change in what is omitted, so the envelope
    minus the omissions stays as long as the text.
    """
    assert card.evidence_start_offset is not None and card.evidence_end_offset is not None
    end = card.evidence_end_offset
    if fit_envelope:
        end = (
            card.evidence_start_offset
            + len(card.evidence_text)
            + sum(stop - start for start, stop in omitted)
        )
    return card.evolve(
        omitted_ranges=tuple(CardOmission(start_offset=start, end_offset=stop) for start, stop in omitted),
        evidence_end_offset=end,
    )


def test_the_fixture_normalizes_to_the_hand_written_text(source: LoadedSnapshot) -> None:
    assert source.normalized.text == NORMALIZED


def test_a_card_cut_with_omissions_by_the_mapping_is_verified(world: VerificationWorld, honest: Card) -> None:
    assert honest.evidence_text == CUT_TEXT
    assert [(omission.start_offset, omission.end_offset) for omission in honest.omitted_ranges] == list(
        OMITTED
    )

    result = world.verify(honest)

    assert result.status is VerificationStatus.VERIFIED
    assert result.reasons == ()
    assert result.checks_run == frozenset(VerificationCheck)


# =============================================================================================
# One omission widened, narrowed, removed or added
# =============================================================================================
# Each change by hand, with the envelope fitted, and where the reconstruction first departs from
# CUT_TEXT:
#   widen the first cut's end by one (68-79), envelope 61-139: "Farmerspump twice..." differs at 7
#   narrow the second cut's start by one (90-119), envelope 61-137: "...pump twice Without..." at 18
#   remove the first cut, envelope 61-128: "Farmers there now..." differs at 8 ("t" for "p")
#   add a cut over the "t" at 125, envelope 61-139: "...twiceWithou new..." differs at 24
#   shift the second cut one left (88-118), envelope 61-138: "...pump twic\nWithout..." differs at 17

CHANGED = [
    pytest.param(((68, 79), (89, 119)), 7, id="first-cut-widened"),
    pytest.param(((68, 78), (90, 119)), 18, id="second-cut-narrowed"),
    pytest.param(((89, 119),), 8, id="first-cut-removed"),
    pytest.param(((68, 78), (89, 119), (125, 126)), 24, id="cut-added"),
    pytest.param(((68, 78), (88, 118)), 17, id="second-cut-shifted-left"),
]


@pytest.mark.parametrize(("omitted", "first_differing_offset"), CHANGED)
def test_a_changed_omission_is_a_text_mismatch_where_the_text_departs(
    world: VerificationWorld, honest: Card, omitted: tuple[tuple[int, int], ...], first_differing_offset: int
) -> None:
    result = world.verify(with_omissions(honest, omitted, fit_envelope=True))

    assert result.status is VerificationStatus.UNVERIFIED
    assert [(reason.code, reason.first_differing_offset) for reason in result.reasons] == [
        (ReasonCode.TEXT_MISMATCH, first_differing_offset)
    ]


@pytest.mark.parametrize(
    ("omitted", "first_differing_offset"),
    [parameter for parameter in CHANGED if parameter.id != "second-cut-shifted-left"],
)
def test_a_changed_omission_on_the_original_envelope_is_refused_at_construction(
    honest: Card, omitted: tuple[tuple[int, int], ...], first_differing_offset: int
) -> None:
    """Widening, narrowing, removing or adding a cut changes how much is omitted; without moving the
    envelope too, the length invariant refuses the card before the verifier sees it."""
    with pytest.raises(ValidationError, match="omission\\(s\\) quotes"):
        with_omissions(honest, omitted, fit_envelope=False)


def test_moving_the_first_cut_one_right_quotes_the_same_text_and_verifies(
    world: VerificationWorld, honest: Card
) -> None:
    """Cutting "there now " (69-79) instead of " there now" (68-78) moves a space from after
    "Farmers" to before "pump": the same 37 characters come back. The card's claim is true, so it
    verifies. An omission's position is fixed by the text only up to where the text repeats."""
    moved = with_omissions(honest, ((69, 79), (89, 119)), fit_envelope=False)

    assert world.verify(moved).status is VerificationStatus.VERIFIED


# =============================================================================================
# Every single-omission change, against an oracle
# =============================================================================================


def _replace(index: int, replacement: tuple[int, int] | None) -> tuple[tuple[int, int], ...]:
    rest = OMITTED[:index] + OMITTED[index + 1 :]
    return tuple(sorted(rest if replacement is None else (*rest, replacement)))


def single_omission_changes() -> Iterator[tuple[str, tuple[tuple[int, int], ...]]]:
    """Each cut widened, narrowed or shifted by 1-3 at either end, or removed; or one new cut of one or
    two characters strictly inside a kept piece.

    Count, by hand: per cut, 6 widenings, 6 narrowings (both cuts are longer than 3) and 6 shifts and
    1 removal, so 38. New cuts inside 61-68, 78-89 and 119-138: 5 + 9 + 17 of one character and
    4 + 8 + 16 of two, so 59. 97 in all, every one canonical.
    """
    for index, (start, end) in enumerate(OMITTED):
        for by in (1, 2, 3):
            yield f"cut {index} widened left by {by}", _replace(index, (start - by, end))
            yield f"cut {index} widened right by {by}", _replace(index, (start, end + by))
            yield f"cut {index} narrowed left by {by}", _replace(index, (start + by, end))
            yield f"cut {index} narrowed right by {by}", _replace(index, (start, end - by))
            yield f"cut {index} shifted left by {by}", _replace(index, (start - by, end - by))
            yield f"cut {index} shifted right by {by}", _replace(index, (start + by, end + by))
        yield f"cut {index} removed", _replace(index, None)
    for kept_start, kept_end in KEPT:
        for at in range(kept_start + 1, kept_end):
            for length in (1, 2):
                if at + length < kept_end:
                    yield f"cut added at {at} for {length}", tuple(sorted((*OMITTED, (at, at + length))))


def _oracle(omitted: tuple[tuple[int, int], ...]) -> str:
    """The snapshot text from 61 to the fitted envelope's end, less ``omitted``: slicing, written here."""
    end = 61 + len(CUT_TEXT) + sum(stop - start for start, stop in omitted)
    return "".join(
        character
        for position, character in enumerate(NORMALIZED[61:end], start=61)
        if not any(start <= position < stop for start, stop in omitted)
    )


def _first_difference(claimed: str, actual: str) -> int:
    for index, (left, right) in enumerate(zip(claimed, actual, strict=False)):
        if left != right:
            return index
    return min(len(claimed), len(actual))


def test_no_single_omission_change_verifies_unless_it_quotes_the_same_text(
    world: VerificationWorld, honest: Card
) -> None:
    changes = list(single_omission_changes())
    assert len(changes) == 97

    verified: list[str] = []
    wrong: list[str] = []
    refused_unfitted = 0
    for name, omitted in changes:
        omitted_now = sum(stop - start for start, stop in omitted)
        if omitted_now != 40:
            try:
                with_omissions(honest, omitted, fit_envelope=False)
            except ValidationError:
                refused_unfitted += 1
            else:
                wrong.append(f"{name}: constructible on the original envelope")
        result = world.verify(with_omissions(honest, omitted, fit_envelope=True))
        expected = _oracle(omitted)
        if result.status is VerificationStatus.VERIFIED:
            verified.append(name)
            if expected != CUT_TEXT:
                wrong.append(f"{name}: VERIFIED, but the snapshot gives other text")
        elif [(reason.code, reason.first_differing_offset) for reason in result.reasons] != [
            (ReasonCode.TEXT_MISMATCH, _first_difference(CUT_TEXT, expected))
        ]:
            wrong.append(f"{name}: {result.reasons}")

    assert wrong == []
    # Shifts keep the amount omitted; the other 12 + 12 + 2 + 59 = 85 changes do not.
    assert refused_unfitted == 85
    # The one change that quotes the same text, explained in the test above.
    assert verified == ["cut 0 shifted right by 1"]


# =============================================================================================
# Omissions the domain never validated are refused, not read some other way
# =============================================================================================
# ``model_copy`` skips validation, as ``model_construct`` and any unvalidated load would. The text
# is unchanged and the envelope is fitted to each set, so only the form of the omissions is wrong.
# The last case, a cut of nothing inside " pump twice", leaves two kept ranges that touch; the
# extractor would join them and the text would come back intact, so it is refused because the
# evidence does not come back cut where the card says it was.


@pytest.mark.parametrize(
    ("omitted", "problem"),
    [
        pytest.param(((89, 119), (68, 78)), "reversed_range", id="out-of-order"),
        pytest.param(((68, 78), (78, 108)), "empty_range", id="adjacent"),
        pytest.param(((61, 71), (89, 119)), "empty_range", id="touching-the-start"),
        pytest.param(((68, 78), (84, 84), (89, 119)), "segments_touch", id="removes-nothing"),
    ],
)
def test_omissions_that_are_not_canonical_are_span_out_of_range(
    world: VerificationWorld, honest: Card, omitted: tuple[tuple[int, int], ...], problem: str
) -> None:
    end = 61 + len(CUT_TEXT) + sum(stop - start for start, stop in omitted)
    unvalidated = honest.model_copy(
        update={
            "omitted_ranges": tuple(
                CardOmission.model_construct(start_offset=a, end_offset=b) for a, b in omitted
            ),
            "evidence_end_offset": end,
        }
    )

    result = world.verify(unvalidated)

    assert result.reason_codes == (ReasonCode.SPAN_OUT_OF_RANGE,)
    assert f"less {len(omitted)} omitted range(s) do not select evidence" in result.reasons[0].detail
    assert problem in result.reasons[0].detail
