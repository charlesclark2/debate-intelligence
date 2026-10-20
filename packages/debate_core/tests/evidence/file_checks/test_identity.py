"""The evidence-identity check (`v1-e33-t04`, node identity-check).

Built on a real file from `v1-e33-t02`'s writer (the `standard` fixture), with the built cards or the
sidecar changed as values, one change per test. The same changes made to the `.docx` itself are the
mutation suite in `tests/application/test_file_quality_mutations.py`.
"""

from __future__ import annotations

from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.domain.file_provenance import FileProvenanceEntry, formatting_sha256, text_sha256
from debate_core.domain.style_profile import RunEmphasis
from debate_core.evidence.file_checks.identity import SourceCardReading, check_identity
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck

Checked = tuple[BuiltEvidenceFile, ParsedDocument, dict[int, SourceCardReading]]


def _run(
    standard: Checked,
    *,
    cards: dict[int, ParsedCard] | None = None,
    entries: dict[int, FileProvenanceEntry] | None = None,
    sources: dict[int, SourceCardReading] | None = None,
    built_cards: list[ParsedCard] | None = None,
) -> list[CheckResult]:
    """The check over the standard file with some built cards, entries or sources replaced, by position."""
    built, document, readings = standard
    built_list = list(document.cards) if built_cards is None else built_cards
    for position, card in (cards or {}).items():
        built_list[position - 1] = card
    manifest_entries = [(entries or {}).get(entry.position, entry) for entry in built.manifest.cards]
    return check_identity(manifest_entries, built_list, {**readings, **(sources or {})})


def _failures(results: list[CheckResult], position: int) -> list[str]:
    return [
        result.message
        for result in results
        if result.card_position == position and result.status is CheckStatus.FAIL
    ]


def _card(standard: Checked, position: int) -> ParsedCard:
    return standard[1].cards[position - 1]


def _flip(text: str, at: int) -> str:
    """`text` with one character changed and its length kept, so every span still fits."""
    return text[:at] + ("x" if text[at] != "x" else "y") + text[at + 1 :]


def test_every_card_of_a_built_file_is_its_source_card(standard: Checked) -> None:
    results = _run(standard)
    assert [(result.card_position, result.status) for result in results] == [
        (1, CheckStatus.PASS),
        (2, CheckStatus.PASS),
        (3, CheckStatus.PASS),
        (4, CheckStatus.PASS),
    ]
    assert {result.check for result in results} == {QualityCheck.EVIDENCE_IDENTITY}
    assert [result.fingerprint for result in results] == [
        entry.fingerprint for entry in standard[0].manifest.cards
    ]


def test_one_changed_character_of_evidence_fails_the_card(standard: Checked) -> None:
    card = _card(standard, 2)
    results = _run(standard, cards={2: card.evolve(evidence_text=_flip(card.evidence_text, 10))})
    failures = _failures(results, 2)
    assert any("evidence text" in message for message in failures), failures
    assert any("fingerprint" in message for message in failures), failures
    assert not _failures(results, 1)


def test_one_lost_underline_fails_the_card_on_its_formatting_alone(standard: Checked) -> None:
    card = _card(standard, 1)
    underline = next(span for span in card.formatting_spans if span.emphasis is RunEmphasis.UNDERLINE)
    spans = tuple(span for span in card.formatting_spans if span is not underline)
    failures = _failures(_run(standard, cards={1: card.evolve(formatting_spans=spans)}), 1)
    assert len(failures) == 1, failures
    assert "formatting" in failures[0]


def test_a_changed_highlight_colour_fails_the_card_on_its_formatting(standard: Checked) -> None:
    card = _card(standard, 1)
    spans = tuple(
        span.evolve(highlight_color="yellow") if span.highlight_color == "cyan" else span
        for span in card.formatting_spans
    )
    assert spans != card.formatting_spans, "the card has a cyan highlight to change"
    failures = _failures(_run(standard, cards={1: card.evolve(formatting_spans=spans)}), 1)
    assert len(failures) == 1, failures
    assert "formatting" in failures[0]


def test_a_changed_font_size_fails_the_card_on_its_formatting(standard: Checked) -> None:
    card = _card(standard, 1)
    sizes = tuple(size.evolve(half_points=size.half_points + 2) for size in card.font_size_spans[:1])
    failures = _failures(
        _run(standard, cards={1: card.evolve(font_size_spans=sizes + card.font_size_spans[1:])}), 1
    )
    assert len(failures) == 1, failures
    assert "formatting" in failures[0]


def test_a_changed_cite_fails_the_card(standard: Checked) -> None:
    card = _card(standard, 3)
    failures = _failures(_run(standard, cards={3: card.evolve(full_cite=_flip(card.full_cite, 2))}), 3)
    assert len(failures) == 1, failures
    assert "cite" in failures[0]


def test_a_lost_cite_fails_the_card(standard: Checked) -> None:
    card = _card(standard, 1)
    failures = _failures(_run(standard, cards={1: card.evolve(full_cite="", short_cite=None)}), 1)
    assert any("cite" in message for message in failures), failures


def test_a_changed_completeness_fails_the_card(standard: Checked) -> None:
    card = _card(standard, 1)
    failures = _failures(_run(standard, cards={1: card.evolve(completeness=CardCompleteness.ABBREVIATED)}), 1)
    assert len(failures) == 1, failures
    assert "completeness" in failures[0]


def test_a_card_missing_from_the_built_file_fails_its_entry(standard: Checked) -> None:
    results = _run(standard, built_cards=list(standard[1].cards[:3]))
    assert _failures(results, 4) == ["the built file has no card at this position"]
    assert not _failures(results, 3)


def test_a_card_in_another_cards_place_fails_both(standard: Checked) -> None:
    one, two, *rest = standard[1].cards
    results = _run(standard, built_cards=[two, one, *rest])
    assert _failures(results, 1) and _failures(results, 2)
    assert not _failures(results, 3)


def test_a_retagged_tag_the_sidecar_does_not_record_as_the_coachs_fails(standard: Checked) -> None:
    card = _card(standard, 1)
    assert card.tag is not None
    failures = _failures(_run(standard, cards={1: card.evolve(tag=_flip(card.tag, 0))}), 1)
    assert len(failures) == 1, failures
    assert "tag" in failures[0]


def test_a_coach_override_must_record_the_digest_of_the_tag_it_replaced(standard: Checked) -> None:
    entry = standard[0].manifest.cards[2]
    assert entry.tag_overridden
    assert not _failures(_run(standard), 3), "the standard file's override is recorded correctly"
    failures = _failures(_run(standard, entries={3: entry.evolve(original_tag_sha256="0" * 64)}), 3)
    assert len(failures) == 1, failures
    assert "tag" in failures[0]


# -- the sidecar is a claim: checked against the source, never trusted ------------------------


def test_each_sidecar_digest_is_checked_against_the_source_card_re_parsed(standard: Checked) -> None:
    entry = standard[0].manifest.cards[0]
    for field in ("evidence_sha256", "cite_sha256", "formatting_sha256"):
        failures = _failures(_run(standard, entries={1: entry.evolve(**{field: "0" * 64})}), 1)
        assert len(failures) == 1, (field, failures)
        assert "sidecar" in failures[0], (field, failures)


def test_a_sidecar_that_agrees_with_a_tampered_card_does_not_make_it_pass(standard: Checked) -> None:
    """The forbidden list's first item: the writer's digests are never the answer."""
    card = _card(standard, 2)
    tampered = card.evolve(evidence_text=_flip(card.evidence_text, 4))
    entry = (
        standard[0]
        .manifest.cards[1]
        .evolve(
            evidence_sha256=text_sha256(tampered.evidence_text),
            formatting_sha256=formatting_sha256(tampered.formatting_spans, tampered.font_size_spans),
        )
    )
    failures = _failures(_run(standard, cards={2: tampered}, entries={2: entry}), 2)
    assert any("evidence text" in message for message in failures), failures


def test_a_source_that_cannot_be_read_fails_the_card(standard: Checked) -> None:
    unreadable = SourceCardReading(card=None, problem="the source's bytes are not in the blob store")
    failures = _failures(_run(standard, sources={2: unreadable}), 2)
    assert failures == ["the source card cannot be read: the source's bytes are not in the blob store"]


def test_a_source_card_without_the_sidecars_fingerprint_fails(standard: Checked) -> None:
    other = standard[2][1]
    failures = _failures(_run(standard, sources={2: other}), 2)
    assert any("fingerprint" in message for message in failures), failures


def test_a_failure_is_never_a_warning_and_never_quotes_the_card(standard: Checked) -> None:
    card = _card(standard, 1)
    assert card.tag is not None
    tamperings: list[dict[int, ParsedCard]] = [
        {1: card.evolve(evidence_text=_flip(card.evidence_text, 3))},
        {1: card.evolve(full_cite=_flip(card.full_cite, 3))},
        {1: card.evolve(tag=_flip(card.tag, 3))},
        {1: card.evolve(formatting_spans=card.formatting_spans[1:])},
    ]
    words = {
        word
        for text in (card.evidence_text, card.full_cite, card.tag)
        for word in text.split()
        if len(word) > 4
    }
    for cards in tamperings:
        results = _run(standard, cards=cards)
        assert {result.status for result in results} == {CheckStatus.PASS, CheckStatus.FAIL}
        for message in _failures(results, 1):
            assert not any(word in message for word in words), message
