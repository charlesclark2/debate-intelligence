"""Property-based and golden tests for evidence text normalization (`v1-e03-t01-text-normalization`).

The properties are the claims examples cannot support: idempotence and determinism over arbitrary
Unicode (ac1), paragraph IDs that survive whitespace edits (ac2), and an offset map that carries
any normalized range back to raw text holding the same characters (ac3). The generated text is
real Unicode, not ASCII. It is hypothesis's full character range mixed with the code points the
rules single out: combining marks that compose or reorder, Hangul jamo, NFC singletons and
exclusions, every whitespace, line-break and removed code point in the policy, joiners, bidi
controls, and the code points on either side of the surrogate block.

The golden test (ac4) pins v1's output on an invented corpus whose expectations were written by
hand (`tests/fixtures/normalization/`).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from debate_core.evidence.normalization import (
    NORMALIZER_VERSION,
    InvalidTextError,
    NormalizedText,
    OffsetSegment,
    character_rules,
    normalize,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_CORPUS = REPO_ROOT / "tests" / "fixtures" / "normalization" / "golden-evidence-normalizer-v1.json"
V1 = "evidence-normalizer-v1"

RULES = character_rules(V1)
WHITESPACE = RULES.horizontal_whitespace | RULES.line_breaks | RULES.paragraph_separators
POLICY_CHARACTERS = WHITESPACE | RULES.removed

PROPERTY_SETTINGS = settings(
    max_examples=400,
    deadline=None,  # the first call builds the cached Unicode tables
    suppress_health_check=[HealthCheck.too_slow],
)

# ---------------------------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------------------------

INTERESTING_CHARACTERS = sorted(
    {
        # Combining marks that compose with a base, and ones that only reorder.
        *"̧̨̖̣̀́̂̃̇̈̊̌ͅ",
        *"̈́̀́̓",  # non-starter decompositions, replaced by NFC
        *"़াৗାාཱིီ゙゚",  # other composing marks
        *"aeiouAEIOUnNcCsSzZ",  # bases they compose with
        *"कকେෙཀဥかハ",  # non-Latin bases that compose
        *"ᄀ하ᅵᆨᇂ가각힣",  # Hangul jamo and syllables
        *"ÅΩक़ʹ;豈鶴",  # NFC singletons and exclusions
        "\U0002f800",
        *POLICY_CHARACTERS,
        *"‌‍",  # joiners, kept
        *"؜‎‏‪‫‬‭‮⁦⁧⁨⁩",  # bidi
        *"\u001c\u001f᠎͏\u0000",  # isspace()-true or format characters, kept
        *"퟿�￾￿\U0010ffff\U000e0001",  # around the surrogate block
        *"ﬁﬂ²½Ａ",  # compatibility characters, kept
        *"‘’“”–—−-'\"",  # quotes and dashes, kept
    }
)

any_character = st.characters(exclude_categories=["Cs"])
unicode_text = st.text(
    st.one_of(any_character, st.sampled_from(INTERESTING_CHARACTERS)),
    max_size=80,
)
content_character = st.one_of(any_character, st.sampled_from(INTERESTING_CHARACTERS)).filter(
    lambda character: character not in POLICY_CHARACTERS
)
content_text = st.text(content_character, max_size=40)

LINE_BREAK_ELEMENTS = ["\n", "\r\n", "\r", "\u000b", "\u000c", "\u0085", " "]
horizontal_filler = st.text(st.sampled_from(sorted(RULES.horizontal_whitespace | RULES.removed)), max_size=4)


@st.composite
def intra_paragraph_gap(draw: st.DrawFn) -> str:
    """Whitespace that stays inside a paragraph: never two line breaks, never U+2029."""
    before = draw(horizontal_filler)
    line_break = draw(st.sampled_from(["", *LINE_BREAK_ELEMENTS]))
    after = draw(horizontal_filler)
    return before + line_break + after


@st.composite
def paragraph_break_gap(draw: st.DrawFn) -> str:
    """Whitespace holding a blank line: two line breaks, or U+2029."""
    if draw(st.booleans()):
        middle = draw(st.sampled_from([" ", "  "]))
    else:
        first = draw(st.sampled_from(LINE_BREAK_ELEMENTS))
        second = draw(st.sampled_from(LINE_BREAK_ELEMENTS))
        if first == "\r" and second.startswith("\n"):
            first = "\r\n"  # a bare CR followed by LF would be one line break, not two
        middle = first + draw(horizontal_filler) + second
    return draw(horizontal_filler) + middle + draw(horizontal_filler)


word = st.text(content_character, min_size=1, max_size=8)
paragraph_words = st.lists(word, min_size=1, max_size=6)


def key(text: str) -> str:
    """Text with every whitespace and removed code point dropped, in NFC: what must be preserved."""
    return unicodedata.normalize(
        "NFC", "".join(character for character in text if character not in POLICY_CHARACTERS)
    )


# ---------------------------------------------------------------------------------------------
# ac1: idempotent and deterministic
# ---------------------------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(unicode_text)
def test_normalize_is_idempotent(raw: str) -> None:
    once = normalize(raw, V1)
    twice = normalize(once.text, V1)
    assert twice.text == once.text
    assert twice.paragraphs == once.paragraphs
    expected_map = (OffsetSegment(0, len(once.text), 0, len(once.text), exact=True),) if once.text else ()
    assert twice.offset_map.segments == expected_map


@PROPERTY_SETTINGS
@given(unicode_text)
def test_normalize_is_deterministic(raw: str) -> None:
    assert normalize(raw, V1) == normalize(raw, V1)


def _corpus_digest() -> str:
    digest = hashlib.sha256()
    for case in json.loads(GOLDEN_CORPUS.read_text(encoding="utf-8"))["cases"]:
        result = normalize(case["raw"], V1)
        digest.update(repr((result.text, result.paragraphs, result.offset_map.segments)).encode())
    return digest.hexdigest()


def test_normalize_is_deterministic_across_hash_seeds() -> None:
    # Set and dict ordering of strings changes with PYTHONHASHSEED; none of it may reach the output.
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from test_normalization_props import _corpus_digest; print(_corpus_digest())"
    )
    digests = {_corpus_digest()}
    for seed in ("0", "1", "4242"):
        completed = subprocess.run(
            [sys.executable, "-c", script, str(Path(__file__).parent)],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        digests.add(completed.stdout.strip())
    assert len(digests) == 1


@PROPERTY_SETTINGS
@given(unicode_text)
def test_normalized_text_is_nfc_with_only_space_and_paragraph_breaks(raw: str) -> None:
    text = normalize(raw, V1).text
    assert unicodedata.is_normalized("NFC", text)
    assert not any(c in POLICY_CHARACTERS for c in text if c not in " \n")
    assert text == text.strip(" \n")
    assert "  " not in text
    assert text.replace("\n\n", "").count("\n") == 0
    assert "\n\n\n" not in text and " \n" not in text and "\n " not in text


@PROPERTY_SETTINGS
@given(unicode_text)
def test_normalize_changes_only_whitespace_and_listed_code_points(raw: str) -> None:
    assert key(normalize(raw, V1).text) == key(raw)


@PROPERTY_SETTINGS
@given(content_text)
def test_text_without_policy_characters_is_exactly_nfc(raw: str) -> None:
    # Content is normalized run by run for the offset map; the runs must add up to whole-text NFC.
    assert normalize(raw, V1).text == unicodedata.normalize("NFC", raw)


@PROPERTY_SETTINGS
@given(st.text(st.characters(min_codepoint=0xD800, max_codepoint=0xDFFF), min_size=1, max_size=3))
def test_lone_surrogates_are_rejected(surrogates: str) -> None:
    with pytest.raises(InvalidTextError):
        normalize(f"before{surrogates}after", V1)


# ---------------------------------------------------------------------------------------------
# ac2: paragraph IDs survive whitespace edits inside paragraphs
# ---------------------------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(st.lists(paragraph_words, min_size=1, max_size=5), st.data())
def test_paragraph_ids_survive_whitespace_edits_inside_paragraphs(
    paragraphs: list[list[str]], data: st.DataObject
) -> None:
    plain = "\n\n".join(" ".join(words) for words in paragraphs)

    def edited_paragraph(words: list[str]) -> str:
        pieces: list[str] = [data.draw(horizontal_filler)]
        for index, text in enumerate(words):
            if index:
                pieces.append(data.draw(intra_paragraph_gap()))
            if len(text) >= 2:
                # Strictly inside the word, so it never meets the gap beside it and doubles a break.
                split = data.draw(st.integers(1, len(text) - 1))
                text = text[:split] + data.draw(intra_paragraph_gap()) + text[split:]
            pieces.append(text)
        pieces.append(data.draw(horizontal_filler))
        return "".join(pieces)

    edited = data.draw(paragraph_break_gap()).join(edited_paragraph(w) for w in paragraphs)

    before = normalize(plain, V1)
    after = normalize(edited, V1)
    assert len(after.paragraphs) == len(before.paragraphs) == len(paragraphs)
    assert [p.paragraph_id for p in after.paragraphs] == [p.paragraph_id for p in before.paragraphs]
    for paragraph in before.paragraphs:
        assert key(after.paragraph_text(paragraph.paragraph_id)) == key(
            before.paragraph_text(paragraph.paragraph_id)
        )


# ---------------------------------------------------------------------------------------------
# ac3: the offset map
# ---------------------------------------------------------------------------------------------


def _check_segments(raw: str, result: NormalizedText) -> None:
    for segment in result.offset_map.segments:
        raw_piece = raw[segment.raw_start : segment.raw_end]
        normalized_piece = result.text[segment.normalized_start : segment.normalized_end]
        if segment.exact:
            assert raw_piece == normalized_piece
        assert key(raw_piece) == key(normalized_piece)


@PROPERTY_SETTINGS
@given(unicode_text)
def test_offset_segments_align_the_same_characters(raw: str) -> None:
    _check_segments(raw, normalize(raw, V1))


@PROPERTY_SETTINGS
@given(unicode_text, st.data())
def test_offset_map_carries_any_normalized_range_to_raw_text_with_the_same_characters(
    raw: str, data: st.DataObject
) -> None:
    result = normalize(raw, V1)
    start = data.draw(st.integers(0, len(result.text)))
    end = data.draw(st.integers(start, len(result.text)))

    raw_start, raw_end = result.to_raw_range(start, end)
    assert 0 <= raw_start <= raw_end <= len(raw)
    if start == end:
        # An empty range has no characters to carry. Inside a replaced unit it sits at the unit's
        # raw start, since the unit has no finer raw positions.
        assert raw_start == raw_end
        return

    # Back again: the raw range covers the normalized range, widened only to whole segments.
    covered_start, covered_end = result.to_normalized_range(raw_start, raw_end)
    assert covered_start <= start and end <= covered_end
    assert key(raw[raw_start:raw_end]) == key(result.text[covered_start:covered_end])

    # Tight: a range that starts or ends on content starts or ends on raw content, never on
    # whitespace or a deleted character next to it.
    if result.text[start] not in " \n":
        assert raw[raw_start] not in POLICY_CHARACTERS
    if result.text[end - 1] not in " \n":
        assert raw[raw_end - 1] not in POLICY_CHARACTERS


@PROPERTY_SETTINGS
@given(st.lists(word, min_size=1, max_size=8), st.data())
def test_offset_map_round_trips_exactly_between_segment_boundaries(
    words: list[str], data: st.DataObject
) -> None:
    raw = "".join(data.draw(intra_paragraph_gap()) + w for w in words)
    result = normalize(raw, V1)
    boundaries = sorted(
        {s.normalized_start for s in result.offset_map.segments}
        | {s.normalized_end for s in result.offset_map.segments}
    )
    assume(len(boundaries) >= 2)
    start = data.draw(st.sampled_from(boundaries))
    end = data.draw(st.sampled_from([b for b in boundaries if b >= start]))
    assert result.to_normalized_range(*result.to_raw_range(start, end)) == (start, end)


@PROPERTY_SETTINGS
@given(unicode_text, st.data())
def test_offset_map_carries_any_raw_range_to_exactly_the_normalized_text_it_became(
    raw: str, data: st.DataObject
) -> None:
    result = normalize(raw, V1)
    start = data.draw(st.integers(0, len(raw)))
    end = data.draw(st.integers(start, len(raw)))
    normalized_start, normalized_end = result.to_normalized_range(start, end)
    assert 0 <= normalized_start <= normalized_end <= len(result.text)
    # A normalized character is inside the range exactly when the raw text it came from overlaps
    # [start, end): nothing the raw range produced is left out, and nothing else is let in.
    for position in range(len(result.text)):
        origin_start, origin_end = result.to_raw_range(position, position + 1)
        overlaps = start < end and origin_start < end and start < origin_end
        assert overlaps == (normalized_start <= position < normalized_end)


# ---------------------------------------------------------------------------------------------
# ac4: golden corpus
# ---------------------------------------------------------------------------------------------


def _golden_cases() -> list[dict[str, Any]]:
    corpus = json.loads(GOLDEN_CORPUS.read_text(encoding="utf-8"))
    assert corpus["normalizer_version"] == V1
    cases: list[dict[str, Any]] = corpus["cases"]
    return cases


def test_golden_corpus_covers_news_pdf_and_think_tank_text() -> None:
    assert {case["genre"] for case in _golden_cases()} == {"news", "pdf", "think-tank"}


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda case: case["name"])
def test_golden_v1_output(case: dict[str, Any]) -> None:
    result = normalize(case["raw"], V1)
    expected_paragraphs: list[str] = case["expected_paragraphs"]
    assert result.text == "\n\n".join(expected_paragraphs)
    assert [p.paragraph_id for p in result.paragraphs] == [
        f"p{number:04d}" for number in range(1, len(expected_paragraphs) + 1)
    ]
    for paragraph, expected_text, expected_raw in zip(
        result.paragraphs, expected_paragraphs, case["expected_raw_paragraphs"], strict=True
    ):
        assert result.paragraph_text(paragraph.paragraph_id) == expected_text
        raw_start, raw_end = result.to_raw_range(paragraph.start, paragraph.end)
        assert case["raw"][raw_start:raw_end] == expected_raw
    _check_segments(case["raw"], result)


def test_golden_corpus_is_pinned_to_v1_not_the_current_version() -> None:
    # When v2 ships, NORMALIZER_VERSION moves on and this corpus keeps testing v1.
    assert json.loads(GOLDEN_CORPUS.read_text(encoding="utf-8"))["normalizer_version"] == V1
    assert V1 == "evidence-normalizer-v1"
    assert NORMALIZER_VERSION.startswith("evidence-normalizer-v")
