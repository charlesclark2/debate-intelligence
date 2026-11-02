"""The linker reads full cards' words from the clusterer's word numbers (`v1-e40-t39`).

Until this task :meth:`CardPlacer.placements` made a tuple of strings of every distinct full body's
words for the linker, after the clusterer returned: about 2 GB over the whole `hspolicy26` store
(`docs/data/caselist-rebuild-memory.md`). Now it reads them from the
:class:`~debate_core.evidence.near_duplicates.BodyWords` the clusterer was given, four bytes a word.

* **What linking holds grows by a few bytes a word.** Traced with `tracemalloc` from the moment the
  placer is asked to place until the linker is first asked about an abbreviated card: for four
  times the bodies, under 16 bytes a word added. The tuples of strings grew by about 60.
* **It links as before**: t36's byte tests (`test_caselist_parse_streams_occurrence_rows.py`) compare
  the rebuild with the one before both tasks, whose linker read tuples of strings.

Every body here is synthetic: invented words, no real card's text.
"""

from __future__ import annotations

import gc
import random
import tracemalloc
from collections.abc import Iterable
from datetime import date
from typing import Final

import pytest

import debate_core.application.caselist_card_stats as caselist_card_stats
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.domain.caselist import SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.abbreviated_links import AbbreviationAnchor, FullCardWords
from debate_core.evidence.near_duplicates import matching_words
from debate_core.testing.fakes.caselist import build_fake_caselist_repository

#: Invented words: `w` and a number, so no body here is anyone's evidence.
WORDS: Final = tuple(f"w{number}" for number in range(3000))
MARKERS: Final = ("…",)
SOURCE: Final = "c" * 64


def card(text: str, element: int, completeness: CardCompleteness = CardCompleteness.FULL) -> ParsedCard:
    return ParsedCard(
        tag="An invented claim",
        short_cite="Quillon 26",
        full_cite="Quillon 26 (Invented Author, Fictional Quarterly, 2026)",
        evidence_text=text,
        completeness=completeness,
        match_source=StyleMatchSource.VERBATIM,
        confidence=1.0,
        provenance=FileImportProvenance(
            source_sha256=SOURCE,
            source_path="Synthetic/Path.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist="synthcl26",
            snapshot=date(2026, 9, 1),
            first_element_index=element,
            last_element_index=element + 1,
            parser_version="2031.01.01-synthetic-1",
            profile_version="synthetic-profile-1",
        ),
    )


def cards(bodies: int, seed: int = 39, words: int = 400) -> list[ParsedCard]:
    """`bodies` distinct full cards of invented words under one short cite, and an abbreviated card
    of the first, which sends the linker to every one of them."""
    chosen = random.Random(seed)
    texts = [" ".join(chosen.choice(WORDS) for _ in range(words)) for _ in range(bodies)]
    first = texts[0].split(" ")
    abbreviated = f"{' '.join(first[:6])} … {' '.join(first[-6:])}"
    return [
        *(card(text, element) for element, text in enumerate(texts)),
        card(abbreviated, bodies, CardCompleteness.ABBREVIATED),
    ]


def held_while_linking(monkeypatch: pytest.MonkeyPatch, given: list[ParsedCard]) -> int:
    """Traced bytes added between asking the placer to place and the linker's first question."""
    placer = CaselistCardStatsService(build_fake_caselist_repository(), ellipsis_markers=MARKERS).placer()
    for one in given:
        placer.add(one)
    original = caselist_card_stats.matching_full_cards
    at_link: list[int] = []

    def first_question(anchor: AbbreviationAnchor, full_cards: Iterable[FullCardWords]) -> list[FullCardWords]:
        if not at_link:
            gc.collect()
            at_link.append(tracemalloc.get_traced_memory()[0])
        return original(anchor, full_cards)

    monkeypatch.setattr(caselist_card_stats, "matching_full_cards", first_question)
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        placed = placer.placements()
    finally:
        tracemalloc.stop()
    assert placed[-1].membership.value == "ABBREVIATED_LINK"  # the linker was asked, and linked it
    (linking,) = at_link
    return linking - before


def test_what_linking_holds_grows_by_a_few_bytes_a_word(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty full bodies, then eighty: 24,000 words more. Measured when it was written: the tuples
    of strings grew by about 60 bytes a word, the word numbers by under 8."""
    fewer, more = cards(20), cards(80)
    added_words = sum(len(matching_words(one.evidence_text)) for one in more[20:80])

    growth = held_while_linking(monkeypatch, more) - held_while_linking(monkeypatch, fewer)

    assert growth / added_words < 16, (growth, added_words)
