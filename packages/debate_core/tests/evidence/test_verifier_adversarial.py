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

A fabrication whose text is not as long as the range it claims is constructible today. Once
`v1-e03-t07` makes the domain check that length (ADR-0018), such a card is refused at construction,
which is also a refusal; the test counts it as one, and requires every same-length fabrication to
reach the verifier.
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

    def fabricate(self, fabrication: Fabrication) -> Card:
        claimed = self.sources[fabrication.claims_source].snapshot
        return self.honest[(fabrication.source, fabrication.card)].evolve(
            evidence_text=fabrication.evidence_text,
            snapshot_id=claimed.snapshot_id,
            normalized_text_hash=claimed.normalized_text_hash,
            evidence_start_offset=fabrication.claims_start,
            evidence_end_offset=fabrication.claims_end,
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


@pytest.mark.parametrize("fabrication", FABRICATIONS, ids=lambda fabrication: fabrication.kind)
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
    verdicts = {
        fabrication.kind: _verdict(
            adversarial, lambda fabrication=fabrication: adversarial.fabricate(fabrication)
        )
        for fabrication in FABRICATIONS
    }

    assert [kind for kind, verdict in verdicts.items() if verdict == VerificationStatus.VERIFIED.value] == []
    unverified_by_the_verifier = [fabrication.kind for fabrication in FABRICATIONS if fabrication.same_length]
    assert unverified_by_the_verifier, "no same-length fabrication, so nothing proves the verifier ran"
    assert all(verdicts[kind] == VerificationStatus.UNVERIFIED.value for kind in unverified_by_the_verifier)


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
