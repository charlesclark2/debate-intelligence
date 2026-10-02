"""Fabricated and paraphrased evidence never verifies: the pass rate is 0% (v1-e03-t04 ac5).

Two kinds of adversarial card are checked:

* the hand-written fabrications in ``tests/fixtures/verification/fabricated_evidence.json``:
  paraphrase, splices, reordering, homoglyphs, truncation, a decomposed accent, invisible and
  full-width characters, a stored ellipsis, shifted offsets and true text attributed to another
  source. Each carries its expected reason and first differing offset, written by hand;
* every single-character mutation of every honest card in that file: each character replaced by a
  look-alike (or by ``X`` where it has none), each character deleted, and ``X`` inserted at every
  position. These are generated, so they assert only that nothing verifies, not where it differs.

The honest card each fabrication is derived from must itself verify, so a suite that refused
everything would fail here rather than pass. No Hypothesis: the mutations are enumerated.

A fabrication whose text is not as long as the range it claims is refused at construction:
`v1-e03-t07` made the domain check that the envelope minus the omissions is as long as the text
(ADR-0018). That defends against an honest mistake, not a forger: a forger, or a model's output, fits
the envelope to the text, and a card can arrive unvalidated. So every fabrication is also checked in
its fitted form, which always reaches the verifier (``AdversarialWorld.fabricate(..., fitted=True)``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from tests.fixtures.verification.verification_world import VerificationWorld

from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import Card, VerificationStatus
from debate_core.evidence.markup import EvidenceMarkupSpan
from debate_core.evidence.verification_types import ReasonCode

FIXTURE = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "verification" / "fabricated_evidence.json"
)

#: Look-alikes for characters in the fixture texts. Anything not listed is replaced by "X".
LOOK_ALIKES = {
    "a": "а",  # Cyrillic a
    "e": "е",  # Cyrillic ie
    "o": "о",  # Cyrillic o
    "p": "р",  # Cyrillic er
    "c": "с",  # Cyrillic es
    "i": "і",  # Cyrillic Byelorussian-Ukrainian i
    " ": " ",  # no-break space
    "-": "‐",  # hyphen
    "—": "–",  # em dash -> en dash
    "“": '"',
    "”": '"',
    ".": "․",  # one dot leader
    "0": "O",
    "1": "l",
}


@dataclass(frozen=True)
class Fabrication:
    source: str
    card: str
    kind: str
    evidence_text: str
    claims_source: str
    claims_start: int
    claims_end: int
    first_differing_offset: int

    @property
    def same_length(self) -> bool:
        return len(self.evidence_text) == self.claims_end - self.claims_start


def _load() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(FIXTURE.read_text(encoding="utf-8")))


def _fabrications() -> Iterator[Fabrication]:
    for source in _load()["sources"]:
        for card in source["cards"]:
            for fabrication in card["fabrications"]:
                claims = fabrication.get("claims", {})
                yield Fabrication(
                    source=source["name"],
                    card=card["name"],
                    kind=fabrication["kind"],
                    evidence_text=fabrication["evidence_text"],
                    claims_source=claims.get("source", source["name"]),
                    claims_start=claims.get("start", card["start"]),
                    claims_end=claims.get("end", card["end"]),
                    first_differing_offset=fabrication["first_differing_offset"],
                )


FABRICATIONS = tuple(_fabrications())


class AdversarialWorld:
    """The fixture's sources loaded through SnapshotService, and an honest card for each fixture card."""

    def __init__(self) -> None:
        self.world = VerificationWorld()
        self.sources: dict[str, LoadedSnapshot] = {}
        self.honest: dict[tuple[str, str], Card] = {}
        for source in _load()["sources"]:
            loaded = self.world.add_source(source["extracted"])
            self.sources[source["name"]] = loaded
            for card in source["cards"]:
                start, end = card["start"], card["end"]
                # Only the first three characters are marked, so the span fits every edit of the text.
                markup = (EvidenceMarkupSpan.underline(start, start + 3),)
                self.honest[(source["name"], card["name"])] = self.world.cut_card(loaded, start, end, markup)

    def fabricate(self, fabrication: Fabrication, *, fitted: bool = False) -> Card:
        """The fabrication on the range it claims, or ``fitted``: on an envelope as long as its text.

        Fitting moves the envelope's end, as a forger would, unless that runs past the end of the
        snapshot's text; then it moves the start back instead. A same-length fabrication is already
        fitted, so ``fitted`` changes nothing for it.
        """
        claimed = self.sources[fabrication.claims_source]
        start, end = fabrication.claims_start, fabrication.claims_end
        if fitted:
            length = len(fabrication.evidence_text)
            if start + length <= len(claimed.normalized.text):
                end = start + length
            else:
                start = end - length
        return self.honest[(fabrication.source, fabrication.card)].evolve(
            evidence_text=fabrication.evidence_text,
            snapshot_id=claimed.snapshot.snapshot_id,
            normalized_text_hash=claimed.snapshot.normalized_text_hash,
            evidence_start_offset=start,
            evidence_end_offset=end,
        )


@pytest.fixture(scope="module")
def adversarial() -> AdversarialWorld:
    return AdversarialWorld()


def test_the_fixture_sources_normalize_to_their_hand_written_text(adversarial: AdversarialWorld) -> None:
    for source in _load()["sources"]:
        assert adversarial.sources[source["name"]].normalized.text == source["normalized"]


def test_every_honest_card_in_the_fixture_is_its_hand_written_text_and_verifies(
    adversarial: AdversarialWorld,
) -> None:
    """Without this, a verifier that refused everything would pass the rest of this file."""
    for source in _load()["sources"]:
        for card in source["cards"]:
            honest = adversarial.honest[(source["name"], card["name"])]
            assert honest.evidence_text == card["evidence_text"], card["name"]
            assert adversarial.world.verify(honest).status is VerificationStatus.VERIFIED, card["name"]


def test_the_fixture_covers_every_fabrication_kind_the_spec_names() -> None:
    kinds = " ".join(fabrication.kind for fabrication in FABRICATIONS)
    for named in ("paraphrase", "spliced", "reordered", "homoglyph", "truncated"):
        assert named in kinds
    assert len(FABRICATIONS) == 28


SAME_LENGTH = tuple(fabrication for fabrication in FABRICATIONS if fabrication.same_length)
LENGTH_CHANGING = tuple(fabrication for fabrication in FABRICATIONS if not fabrication.same_length)


#: The fabrications whose text is not as long as the range they claim, read off the fixture by hand:
#: each adds, removes or replaces characters with a different number of them.
CHANGES_LENGTH = {
    "negation dropped",
    "accent decomposed (NFD a + combining grave)",
    "paraphrase",
    "ellipsis stored in place of a cut",
    "trailing space appended",
    "odds changed by an inserted digit",
    "em dash written as two hyphens",
    "truncated before the comparison",
    "doubled space kept from the raw text",
    "paragraph break flattened to a space",
    "invented claim behind a true opening",
    "spliced: first and last paragraphs joined over the middle one",
    "negation inserted",
    "zero-width space inserted",
    "truncated before the date",
}


def test_the_fixture_has_fabrications_of_both_lengths() -> None:
    assert {fabrication.kind for fabrication in LENGTH_CHANGING} == CHANGES_LENGTH
    assert len(SAME_LENGTH) == 28 - 15


@pytest.mark.parametrize("fabrication", LENGTH_CHANGING, ids=lambda fabrication: fabrication.kind)
def test_a_fabrication_longer_or_shorter_than_its_claimed_range_is_refused_at_construction(
    adversarial: AdversarialWorld, fabrication: Fabrication
) -> None:
    with pytest.raises(ValidationError, match="omission\\(s\\) quotes"):
        adversarial.fabricate(fabrication)


#: The fifteen on an envelope fitted to their length, worked out by hand from the fixture's normalized
#: text: the fitted envelope, and where the reconstruction first differs (evidence-text coordinates),
#: or ``None`` where it does not differ at all.
#:
#: * Eight keep their offset. The envelope keeps its start, so the reconstruction agrees with the
#:   honest text up to the end of the shorter of the two, and the departure lies inside that. The
#:   trailing space keeps 64 for a new reason: the snapshot has "\n\n" after "2031.", not a space.
#: * Five move to 0. Their cards end at the last character of the snapshot (152 and 170), so the
#:   envelope cannot grow at the end and starts earlier instead; the reconstruction then begins with
#:   the character before the card ("\n" before "Its" at 65, ".\n\n" before "Without" at 115-118),
#:   which no fabrication starts with.
#: * Two do not differ: a truncated card is a prefix of the honest text, so on a fitted envelope it
#:   is the honest, shorter quotation of exactly those characters (66-115 and 119-161).
FITTED: dict[str, tuple[int, int, int | None]] = {
    "negation dropped": (0, 60, 44),
    "accent decomposed (NFD a + combining grave)": (0, 65, 8),
    "paraphrase": (0, 66, 24),
    "ellipsis stored in place of a cut": (0, 62, 44),
    "trailing space appended": (0, 65, 64),
    "paragraph break flattened to a space": (0, 151, 64),
    "invented claim behind a true opening": (61, 118, 14),
    "spliced: first and last paragraphs joined over the middle one": (0, 112, 61),
    "odds changed by an inserted digit": (65, 152, 0),
    "em dash written as two hyphens": (65, 152, 0),
    "doubled space kept from the raw text": (65, 152, 0),
    "negation inserted": (115, 170, 0),
    "zero-width space inserted": (118, 170, 0),
    "truncated before the comparison": (66, 115, None),
    "truncated before the date": (119, 161, None),
}
TRUNCATIONS = {kind for kind, (_, _, offset) in FITTED.items() if offset is None}


def test_every_length_changing_fabrication_has_a_hand_counted_fitted_form() -> None:
    assert set(FITTED) == CHANGES_LENGTH


@pytest.mark.parametrize(
    "fabrication",
    [fabrication for fabrication in LENGTH_CHANGING if fabrication.kind not in TRUNCATIONS],
    ids=lambda fabrication: fabrication.kind,
)
def test_a_length_changing_fabrication_on_a_fitted_envelope_is_a_text_mismatch(
    adversarial: AdversarialWorld, fabrication: Fabrication
) -> None:
    start, end, offset = FITTED[fabrication.kind]
    card = adversarial.fabricate(fabrication, fitted=True)
    assert (card.evidence_start_offset, card.evidence_end_offset) == (start, end)

    result = adversarial.world.verify(card)

    assert result.status is VerificationStatus.UNVERIFIED
    assert [(reason.code, reason.first_differing_offset) for reason in result.reasons] == [
        (ReasonCode.TEXT_MISMATCH, offset)
    ]


@pytest.mark.parametrize(
    "fabrication",
    [fabrication for fabrication in LENGTH_CHANGING if fabrication.kind in TRUNCATIONS],
    ids=lambda fabrication: fabrication.kind,
)
def test_a_truncation_on_a_fitted_envelope_is_the_honest_shorter_card_and_verifies(
    adversarial: AdversarialWorld, fabrication: Fabrication
) -> None:
    """Truncating a quotation misleads by what it leaves out, as an unfair cut does; it does not put
    words in a source's mouth. On the range it claims it is refused; on its own range it is true, and
    the verifier, which judges fidelity and not fairness, verifies it."""
    start, end, _ = FITTED[fabrication.kind]
    card = adversarial.fabricate(fabrication, fitted=True)
    assert (card.evidence_start_offset, card.evidence_end_offset) == (start, end)

    assert adversarial.world.verify(card).status is VerificationStatus.VERIFIED


@pytest.mark.parametrize("fabrication", SAME_LENGTH, ids=lambda fabrication: fabrication.kind)
def test_a_fabrication_is_unverified_with_a_text_mismatch_where_it_departs(
    adversarial: AdversarialWorld, fabrication: Fabrication
) -> None:
    result = adversarial.world.verify(adversarial.fabricate(fabrication))

    assert result.status is VerificationStatus.UNVERIFIED
    assert [(reason.code, reason.first_differing_offset) for reason in result.reasons] == [
        (ReasonCode.TEXT_MISMATCH, fabrication.first_differing_offset)
    ]


def _verdict(adversarial: AdversarialWorld, build: Any) -> str:
    """``"refused"`` if the domain will not construct the card, else the verifier's status."""
    try:
        card = cast("Card", build())
    except ValidationError:
        return "refused"
    return adversarial.world.verify(card).status.value


def test_no_fabrication_passes(adversarial: AdversarialWorld) -> None:
    """All 28 reach the verifier in their fitted form, and none verifies except the two truncations,
    which fitted are honest quotations (test above). On the ranges they claim, nothing verifies either."""
    claimed = {
        fabrication.kind: _verdict(
            adversarial, lambda fabrication=fabrication: adversarial.fabricate(fabrication)
        )
        for fabrication in FABRICATIONS
    }
    fitted = {
        fabrication.kind: _verdict(
            adversarial, lambda fabrication=fabrication: adversarial.fabricate(fabrication, fitted=True)
        )
        for fabrication in FABRICATIONS
    }

    assert [kind for kind, verdict in claimed.items() if verdict == VerificationStatus.VERIFIED.value] == []
    assert [kind for kind, verdict in fitted.items() if verdict == "refused"] == []
    assert {
        kind for kind, verdict in fitted.items() if verdict == VerificationStatus.VERIFIED.value
    } == TRUNCATIONS
    assert sum(verdict == VerificationStatus.UNVERIFIED.value for verdict in fitted.values()) == 28 - 2


def _mutations(text: str) -> Iterator[tuple[str, str]]:
    for index, character in enumerate(text):
        yield f"replace {index}", text[:index] + LOOK_ALIKES.get(character, "X") + text[index + 1 :]
        yield f"delete {index}", text[:index] + text[index + 1 :]
    for index in range(len(text) + 1):
        yield f"insert {index}", text[:index] + "X" + text[index:]


def test_no_single_character_mutation_of_any_honest_card_passes(adversarial: AdversarialWorld) -> None:
    tried = 0
    passed: list[str] = []
    refused_at_the_same_length: list[str] = []
    for (source, name), honest in adversarial.honest.items():
        for mutation, text in _mutations(honest.evidence_text):
            tried += 1
            verdict = _verdict(
                adversarial, lambda text=text, honest=honest: honest.evolve(evidence_text=text)
            )
            if verdict == VerificationStatus.VERIFIED.value:
                passed.append(f"{source}/{name}: {mutation}")
            elif verdict == "refused" and len(text) == len(honest.evidence_text):
                refused_at_the_same_length.append(f"{source}/{name}: {mutation}")

    # Honest cards of 64, 86, 152, 56, 170 and 51 characters: 3 * 579 + 6 mutations in all.
    assert tried == 3 * (64 + 86 + 152 + 56 + 170 + 51) + 6
    assert passed == []
    # The 579 replacements keep the length, so the domain has no grounds to refuse them: they must
    # have reached the verifier, which is what this test is about.
    assert refused_at_the_same_length == []
