"""Exact card fingerprints, cutter marks and abbreviated-card linking (`v1-e31-t04`).

Every card here is invented. The authors, journals and arguments do not exist, and no text was
taken from a real debate file (`docs/policies/caselist-data-use.md`). Where a test needs a cutter
mark it uses one that is obviously synthetic (`zzTEST`), never a plausible student's initials.

Expected digests are computed from a normalized string written out by hand in the test, not from
the function under test, so a normalization bug cannot make its own expectation agree with it
(`docs/process/working-agreements.md` §6).
"""

from __future__ import annotations

import hashlib
from datetime import date

import pytest

from debate_core.domain.card_occurrence import FingerprintBasis
from debate_core.domain.caselist import SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FormattingSpan,
    ParsedCard,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.evidence.fingerprints import (
    FINGERPRINT_VERSION,
    card_fingerprint,
    extract_cutter_mark,
    fingerprint_text,
    normalize_for_matching,
)

SOURCE_SHA256 = "a" * 64

BODY = (
    "The Varrow Commission found that municipal \u201cheat islands\u201d raise night-time "
    "temperatures by as much as four degrees \u2014 enough, it said, to double emergency "
    "admissions among residents over seventy."
)


def parsed_card(
    evidence_text: str = BODY,
    *,
    tag: str = "Heat islands kill",
    short_cite: str | None = "Pellam 26",
    full_cite: str = "Pellam 26 (Oriel Pellam, Fictional Review of Urban Climate, 2 March 2026)",
    completeness: CardCompleteness = CardCompleteness.FULL,
    formatting_spans: tuple[FormattingSpan, ...] = (),
) -> ParsedCard:
    """A synthetic parsed card, varying only what a test asks for."""
    return ParsedCard(
        tag=tag,
        short_cite=short_cite,
        full_cite=full_cite,
        evidence_text=evidence_text,
        completeness=completeness,
        formatting_spans=formatting_spans,
        match_source=StyleMatchSource.VERBATIM,
        confidence=1.0,
        provenance=FileImportProvenance(
            source_sha256=SOURCE_SHA256,
            source_path="Maple Grove/QX/Maple Grove-QX-Aff-Invented Invitational-Round 1.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist="testcl26",
            snapshot=date(2026, 9, 1),
            first_element_index=4,
            last_element_index=6,
            parser_version="test-parser",
            profile_version="test-profile",
        ),
    )


def highlight(start: int, end: int, colour: str = "cyan") -> FormattingSpan:
    return FormattingSpan(
        emphasis=RunEmphasis.HIGHLIGHT,
        start_offset=start,
        end_offset=end,
        highlight_color=colour,
        rule_id="test-highlight",
        match_source=StyleMatchSource.VERBATIM,
    )


# ------------------------------------------------------------------------------------------------
# The normalization, against strings a person normalized by hand
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "normalized_by_hand"),
    [
        ("\u201cHeat\u201d  Islands", '"heat" islands'),
        ("residents\u2019 \u2018risk\u2019", "residents' 'risk'"),
        ("four degrees \u2014 enough \u2013 or more", "four degrees - enough - or more"),
        ("line one\nline two\r\n\tline three", "line one line two line three"),
        ("non\u00a0breaking and\u2009thin", "non breaking and thin"),
        ("the \ufb01rst \uff21\uff22", "the first ab"),
        ("soft\u00adhyphen and zero\u200bwidth", "softhyphen and zerowidth"),
        ("  STRASSE and stra\u00dfe  ", "strasse and strasse"),
    ],
)
def test_exact_normalization_matches_hand_written_forms(raw: str, normalized_by_hand: str) -> None:
    assert normalize_for_matching(raw) == normalized_by_hand


def test_exact_fingerprint_is_sha256_of_the_hand_normalized_body() -> None:
    by_hand = (
        'the varrow commission found that municipal "heat islands" raise night-time temperatures by '
        "as much as four degrees - enough, it said, to double emergency admissions among residents "
        "over seventy."
    )
    expected = hashlib.sha256(by_hand.encode("utf-8")).hexdigest()

    fingerprint = card_fingerprint(parsed_card())

    assert fingerprint.exact_fingerprint == expected
    assert fingerprint.basis is FingerprintBasis.EVIDENCE_BODY
    assert fingerprint.fingerprint_version == FINGERPRINT_VERSION == "card-fingerprint-v1"


# ------------------------------------------------------------------------------------------------
# ac1: identical across tag, cite, highlighting, quotes and whitespace
# ------------------------------------------------------------------------------------------------


def test_exact_fingerprint_ignores_tag_and_cite() -> None:
    original = parsed_card()
    retagged = parsed_card(
        tag="Urban heat is the impact that outweighs",
        short_cite="Pellam '26",
        full_cite="Pellam '26 [Oriel Pellam, professor of invented studies] accessed 9-3-26 //zzTEST",
    )
    assert card_fingerprint(retagged) == card_fingerprint(original)


def test_exact_fingerprint_ignores_highlighting() -> None:
    plain = parsed_card()
    highlighted = parsed_card(formatting_spans=(highlight(4, 20), highlight(60, 75, "yellow")))
    assert card_fingerprint(highlighted) == card_fingerprint(plain)


def test_exact_fingerprint_ignores_smart_versus_straight_quotes_and_dashes() -> None:
    straight = BODY.replace("\u201c", '"').replace("\u201d", '"').replace("\u2014", "-")
    assert straight != BODY
    assert card_fingerprint(parsed_card(straight)) == card_fingerprint(parsed_card())


def test_exact_fingerprint_ignores_whitespace_and_line_breaks() -> None:
    reflowed = BODY.replace(" temperatures ", "\ntemperatures  ").replace(" to ", "\u00a0to\t")
    assert card_fingerprint(parsed_card("  " + reflowed + "\n")) == card_fingerprint(parsed_card())


# ------------------------------------------------------------------------------------------------
# ac1: different when a word of evidence changes
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changed",
    [
        BODY.replace("four degrees", "five degrees"),
        BODY.replace("double", "triple"),
        BODY.replace(" municipal", ""),
        BODY.replace("seventy.", "seventy-five."),
        BODY + " It did not say so again.",
    ],
)
def test_exact_fingerprint_differs_when_a_word_changes(changed: str) -> None:
    assert card_fingerprint(parsed_card(changed)) != card_fingerprint(parsed_card())


def test_exact_fingerprint_never_alters_the_card_it_reads() -> None:
    card = parsed_card()
    before = card.model_dump()
    card_fingerprint(card)
    assert card.model_dump() == before
    assert card.evidence_text == BODY


def test_exact_fingerprint_of_a_cite_only_card_covers_its_cite_line() -> None:
    cite = "Pellam 26 (Oriel Pellam, Fictional Review of Urban Climate) The Varrow \u2026 over seventy."
    cite_only = parsed_card("", full_cite=cite, completeness=CardCompleteness.CITE_ONLY)
    other_cite_only = parsed_card(
        "", full_cite=cite.replace("Varrow", "Tamsin"), completeness=CardCompleteness.CITE_ONLY
    )

    fingerprint = card_fingerprint(cite_only)

    assert fingerprint.basis is FingerprintBasis.CITE_LINE
    assert fingerprint != card_fingerprint(other_cite_only)
    # A cite line's digest can never equal a body's digest over the same characters.
    assert fingerprint.exact_fingerprint != fingerprint_text(cite)


def test_exact_fingerprint_is_the_same_in_a_fresh_process() -> None:
    """No process-seeded hash: the digest is a pure function of the text."""
    import subprocess
    import sys

    script = (
        "from debate_core.evidence.fingerprints import fingerprint_text; "
        "print(fingerprint_text('Heat islands \u2014 four degrees'))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"},
        ).stdout.strip()
        for seed in ("1", "2")
    }
    assert outputs == {hashlib.sha256(b"heat islands - four degrees").hexdigest()}


# ------------------------------------------------------------------------------------------------
# Cutter marks: recorded verbatim, only in the explicit `//` convention
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("full_cite", "mark"),
    [
        ("Pellam 26 (Oriel Pellam, Fictional Review, 2026) //zzTEST", "zzTEST"),
        ("Pellam 26 (Oriel Pellam, Fictional Review, 2026) // zzTEST ", "zzTEST"),
        ("Pellam 26 (Oriel Pellam) https://invented.example/a //zz/qq", "zz/qq"),
        ("Pellam 26\nOriel Pellam, Fictional Review, 2026 //zzTEST", "zzTEST"),
    ],
)
def test_cutter_mark_is_read_verbatim_from_the_cite_tail(full_cite: str, mark: str) -> None:
    assert extract_cutter_mark(full_cite) == mark


@pytest.mark.parametrize(
    "full_cite",
    [
        "Pellam 26 (Oriel Pellam, Fictional Review, 2026)",
        "Pellam 26 (Oriel Pellam) https://invented.example/review",
        "Pellam 26 (Oriel Pellam, Fictional Review, 2026) zzTEST",
        "Pellam 26 //zzTEST (Oriel Pellam, Fictional Review, 2026)",
        "Pellam 26 (Oriel Pellam) //averyveryverylongtokenthatisnotamark",
        "",
    ],
)
def test_cutter_mark_is_not_guessed(full_cite: str) -> None:
    assert extract_cutter_mark(full_cite) is None
