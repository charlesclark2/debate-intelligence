"""Evidence text normalization, example by example (`v1-e03-t01-text-normalization`).

Every expected string below was written by hand from the rules in `docs/evidence/normalization.md`,
never produced by running the normalizer (`docs/process/working-agreements.md` §6). Test names
carry the word the spec's node criteria select on: `chars` for the character rules, `paragraph`
and `offset` for segmentation and the offset map. The property-based and golden tests are in
`test_normalization_props.py`.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from debate_core.evidence.normalization import (
    NORMALIZER_VERSION,
    SUPPORTED_NORMALIZER_VERSIONS,
    InvalidTextError,
    UnicodeDatabaseMismatchError,
    UnknownNormalizerVersionError,
    UnknownParagraphError,
    character_rules,
    nfc_composing_code_points,
    nfc_replaced_code_points,
    normalize,
    normalize_chars,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
POLICY = REPO_ROOT / "docs" / "evidence" / "normalization.md"
V1 = "evidence-normalizer-v1"


def chars(text: str) -> str:
    return normalize_chars(text, V1).text


# ---------------------------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------------------------


def test_chars_v1_is_current_and_stays_supported() -> None:
    assert NORMALIZER_VERSION == V1
    assert V1 in SUPPORTED_NORMALIZER_VERSIONS
    assert SUPPORTED_NORMALIZER_VERSIONS[0] == V1


def test_chars_result_records_the_version_it_ran_under() -> None:
    assert normalize_chars("text", V1).normalizer_version == V1
    assert normalize("text", V1).normalizer_version == V1


@pytest.mark.parametrize("version", ["", "v1", "evidence-normalizer-v2", "card-fingerprint-v1"])
def test_chars_unknown_version_is_refused_not_defaulted(version: str) -> None:
    with pytest.raises(UnknownNormalizerVersionError):
        normalize("text", version)


def test_chars_refuses_to_run_under_another_unicode_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(unicodedata, "unidata_version", "16.0.0")
    with pytest.raises(UnicodeDatabaseMismatchError, match="15.0.0"):
        normalize("text", V1)


def test_chars_v1_is_pinned_to_the_unicode_database_of_python_312() -> None:
    assert character_rules(V1).unicode_version == "15.0.0"
    assert unicodedata.unidata_version == "15.0.0"


# ---------------------------------------------------------------------------------------------
# Unicode canonical normalization
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("café", "café"),  # e + COMBINING ACUTE -> e-acute
        ("Å", "Å"),  # ANGSTROM SIGN -> A-ring
        ("Ω", "Ω"),  # OHM SIGN -> GREEK CAPITAL OMEGA
        ("क़", "क़"),  # DEVANAGARI QA, a composition exclusion
        ("q̣̇", "q̣̇"),  # already in canonical order, no composite
        ("q̣̇", "q̣̇"),  # dot below (220) reordered before dot above (230)
        ("각", "각"),  # Hangul jamo L V T -> syllable GAG
        ("각", "각"),  # LV syllable + T -> LVT syllable
    ],
)
def test_chars_apply_nfc(raw: str, expected: str) -> None:
    assert chars(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ﬁnancial ﬂow",  # fi and fl ligatures: only NFKC would expand them
        "x² and ½",  # superscript two, vulgar fraction one half
        "ＡＢＣ",  # full-width A B C
        "① first",  # circled digit one
    ],
)
def test_chars_do_not_apply_compatibility_normalization(raw: str) -> None:
    assert chars(raw) == raw


# ---------------------------------------------------------------------------------------------
# Letters, quotes and dashes are left alone
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "“Rising seas,” she wrote, ‘won’t wait.’",
        "1990–2020 — a lost generation ‒ or not",
        "well-known ‐ non‑breaking − minus ― bar",
        "STRASSE Straße İstanbul Σίσυφος",
        "the 5′ and 3″ primes",
    ],
)
def test_chars_keep_quotes_dashes_and_letter_case(raw: str) -> None:
    assert chars(raw) == raw


def test_chars_do_not_rejoin_a_hyphen_at_a_line_end() -> None:
    assert chars("eco-\nnomic and well-\nknown") == "eco- nomic and well- known"


@pytest.mark.parametrize(
    "raw",
    [
        "می‌خواهم",  # Persian with ZERO WIDTH NON-JOINER
        "\U0001f469‍\U0001f52c",  # woman scientist, an emoji ZWJ sequence
        "‏right-to-left mark‎ and ‪embedding‬ ⁧isolate⁩ ؜",
    ],
)
def test_chars_keep_joiners_and_bidirectional_controls(raw: str) -> None:
    assert chars(raw) == raw


@pytest.mark.parametrize(
    "raw",
    [
        "a\u001cb\u001fc",  # information separators: str.isspace() says yes, the policy says no
        "a᠎b",  # MONGOLIAN VOWEL SEPARATOR
        "a͏b",  # COMBINING GRAPHEME JOINER
        "a\u0000b\u0007c",  # other C0 controls
        "�￿\U0010ffff",  # private use, replacement character, noncharacters
    ],
)
def test_chars_keep_characters_outside_the_policy_tables(raw: str) -> None:
    assert chars(raw) == raw


# ---------------------------------------------------------------------------------------------
# Removed invisible characters
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("invisible", ["­", "​", "⁠", "﻿"])
def test_chars_remove_invisible_characters_and_join_the_word(invisible: str) -> None:
    assert chars(f"eco{invisible}nomic") == "economic"
    assert chars(f"{invisible}start") == "start"
    assert chars(f"end{invisible}") == "end"


def test_chars_compose_across_a_removed_character() -> None:
    assert chars("e​́") == "é"
    assert chars("ᄀ­ᅡ") == "가"


def test_chars_removed_characters_never_separate_words() -> None:
    assert chars("two​⁠words") == "twowords"


# ---------------------------------------------------------------------------------------------
# Whitespace gaps
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gap",
    [
        " ",
        "   ",
        "\t",
        " ",
        " ",
        "　",
        " ",
        " ",
        " ",
        " ",
        " ",
        "  \t ",
        "\n",
        "\r\n",
        "\r",
        "\u000b",
        "\u000c",
        "\u0085",
        " ",
        " \n ",
        "­ ",
        " ​",
    ],
)
def test_chars_collapse_a_gap_without_a_blank_line_to_one_space(gap: str) -> None:
    assert chars(f"left{gap}right") == "left right"


@pytest.mark.parametrize(
    "gap",
    [
        "\n\n",
        "\r\n\r\n",
        "\r\r",
        "\n\r",
        "\n \t\n",
        "\n \n",
        "\n­\n",
        "\n\n\n\n",
        " ",
        "   ",
        "  ",
        "\u000c\n",
    ],
)
def test_chars_make_a_gap_with_a_blank_line_one_paragraph_break(gap: str) -> None:
    assert chars(f"left{gap}right") == "left\n\nright"


def test_chars_trim_gaps_at_both_ends() -> None:
    assert chars(" \n\t Body text.\n\n ​") == "Body text."


@pytest.mark.parametrize("raw", ["", " ", "\n\n\n", "­​", "   ﻿"])
def test_chars_text_with_no_content_normalizes_to_empty(raw: str) -> None:
    assert chars(raw) == ""


def test_chars_reject_a_lone_surrogate() -> None:
    with pytest.raises(InvalidTextError):
        normalize("broken \ud800 text", V1)


# ---------------------------------------------------------------------------------------------
# The policy document and the implementation agree
# ---------------------------------------------------------------------------------------------


def _policy_section(heading: str) -> str:
    text = POLICY.read_text(encoding="utf-8")
    start = text.index(f"### {heading}\n")
    following = text.find("\n#", start + 1)
    return text[start : following if following != -1 else len(text)]


def _code_points_in_table(section: str) -> set[int]:
    code_points: set[int] = set()
    for match in re.finditer(r"^\| U\+([0-9A-F]{4,6})(?:–U\+([0-9A-F]{4,6}))? \|", section, re.M):
        first = int(match.group(1), 16)
        last = int(match.group(2), 16) if match.group(2) else first
        code_points.update(range(first, last + 1))
    return code_points


def _as_code_points(characters: frozenset[str]) -> set[int]:
    return {ord(character) for character in characters}


def test_chars_policy_tables_list_exactly_the_implemented_classes() -> None:
    rules = character_rules(V1)
    assert _code_points_in_table(_policy_section("Rule 1: horizontal whitespace")) == (
        _as_code_points(rules.horizontal_whitespace)
    )
    assert _code_points_in_table(_policy_section("Rule 2: line breaks")) == _as_code_points(rules.line_breaks)
    assert _code_points_in_table(_policy_section("Rule 3: paragraph separator")) == (
        _as_code_points(rules.paragraph_separators)
    )
    assert _code_points_in_table(_policy_section("Rule 4: removed invisible characters")) == (
        _as_code_points(rules.removed)
    )


def test_chars_policy_tables_match_the_hand_written_v1_classes() -> None:
    # Pinned independently of the policy page, so an edit to both at once still fails here.
    rules = character_rules(V1)
    assert len(rules.horizontal_whitespace) == 18
    assert _as_code_points(rules.line_breaks) == {0x0A, 0x0B, 0x0C, 0x0D, 0x85, 0x2028}
    assert _as_code_points(rules.paragraph_separators) == {0x2029}
    assert _as_code_points(rules.removed) == {0x00AD, 0x200B, 0x2060, 0xFEFF}


def test_chars_policy_appendix_lists_every_code_point_nfc_replaces() -> None:
    listed = _code_points_in_table(_policy_section("Code points NFC always replaces"))
    assert len(listed) == 1120
    assert listed == nfc_replaced_code_points()


def test_chars_policy_appendix_lists_every_code_point_nfc_composes() -> None:
    listed = _code_points_in_table(_policy_section("Code points NFC may compose with a preceding character"))
    assert len(listed) == 111
    assert listed == nfc_composing_code_points()


def test_chars_policy_names_the_current_version() -> None:
    text = POLICY.read_text(encoding="utf-8")
    assert "NORMALIZER_VERSION" in text
    assert f"`{NORMALIZER_VERSION}`" in text


# ---------------------------------------------------------------------------------------------
# Paragraphs
# ---------------------------------------------------------------------------------------------


def test_paragraph_ids_number_paragraphs_in_order() -> None:
    result = normalize("First one.\n\nSecond one.\n\n\n\nThird one.", V1)
    assert [p.paragraph_id for p in result.paragraphs] == ["p0001", "p0002", "p0003"]
    assert result.paragraph_text("p0001") == "First one."
    assert result.paragraph_text("p0002") == "Second one."
    assert result.paragraph_text("p0003") == "Third one."


def test_paragraph_spans_index_the_normalized_text() -> None:
    result = normalize("Alpha beta.\n\nGamma.", V1)
    assert [(p.start, p.end) for p in result.paragraphs] == [(0, 11), (13, 19)]


def test_paragraph_ids_keep_counting_past_four_digits() -> None:
    result = normalize("\n\n".join(["x"] * 10001), V1)
    assert result.paragraphs[9998].paragraph_id == "p9999"
    assert result.paragraphs[9999].paragraph_id == "p10000"
    assert result.paragraphs[10000].paragraph_id == "p10001"


def test_paragraph_hard_wrapped_lines_stay_one_paragraph() -> None:
    result = normalize("A line wrapped\nby a PDF\nextractor.\n\nNext.", V1)
    assert [p.paragraph_id for p in result.paragraphs] == ["p0001", "p0002"]
    assert result.paragraph_text("p0001") == "A line wrapped by a PDF extractor."


def test_paragraph_ids_ignore_whitespace_edits_inside_a_paragraph() -> None:
    before = normalize("One two three.\n\nFour five.", V1)
    after = normalize("  One \t two  three.  \n \n\nFour\nfive. ", V1)
    assert after.text == before.text
    assert after.paragraphs == before.paragraphs


def test_paragraph_empty_text_has_no_paragraphs() -> None:
    assert normalize("", V1).paragraphs == ()
    assert normalize(" \n\n​ ", V1).paragraphs == ()


def test_paragraph_unknown_id_is_an_error() -> None:
    with pytest.raises(UnknownParagraphError):
        normalize("Only one.", V1).paragraph("p0002")


# ---------------------------------------------------------------------------------------------
# Offset map
# ---------------------------------------------------------------------------------------------


def test_offset_map_is_the_identity_on_already_normalized_text() -> None:
    raw = "Already normal.\n\nSecond paragraph."
    result = normalize(raw, V1)
    assert result.text == raw
    for start in range(len(raw) + 1):
        for end in range(start, len(raw) + 1):
            assert result.to_raw_range(start, end) == (start, end)
            assert result.to_normalized_range(start, end) == (start, end)


def test_offset_map_widens_a_collapsed_gap_to_the_whole_raw_run() -> None:
    raw = "rising \t  seas"
    result = normalize(raw, V1)
    assert result.text == "rising seas"
    assert result.to_raw_range(6, 7) == (6, 10)  # the one normalized space
    assert raw[slice(*result.to_raw_range(0, 11))] == raw
    assert result.to_normalized_range(8, 9) == (6, 7)  # any raw character of the gap


def test_offset_map_leaves_out_deleted_characters_at_the_range_edges() -> None:
    raw = "﻿eco­nomic"
    result = normalize(raw, V1)
    assert result.text == "economic"
    assert result.to_raw_range(0, 3) == (1, 4)  # "eco", without the BOM or the soft hyphen
    assert result.to_raw_range(3, 8) == (5, 10)  # "nomic"
    assert result.to_raw_range(0, 8) == (1, 10)  # the soft hyphen inside is taken in
    assert result.to_normalized_range(0, 1) == (0, 0)  # the BOM alone produced nothing
    assert result.to_normalized_range(4, 5) == (3, 3)  # nor did the soft hyphen


def test_offset_map_treats_a_composed_character_as_a_unit() -> None:
    raw = "café au lait"
    result = normalize(raw, V1)
    assert result.text == "café au lait"
    assert result.to_raw_range(3, 4) == (3, 5)  # e-acute came from e + combining acute
    assert result.to_normalized_range(4, 5) == (3, 4)  # the combining acute alone
    assert result.to_normalized_range(0, 3) == (0, 3)  # "caf" is still one to one


def test_offset_map_widens_a_range_ending_inside_a_replaced_character() -> None:
    raw = "x क़ y"  # DEVANAGARI QA becomes KA + NUKTA: one raw character, two normalized
    result = normalize(raw, V1)
    assert result.text == "x क़ y"
    assert result.to_raw_range(3, 4) == (2, 3)  # just the nukta still maps to the whole QA
    assert result.to_raw_range(2, 3) == (2, 3)
    assert result.to_normalized_range(2, 3) == (2, 4)


def test_offset_map_carries_a_paragraph_back_to_its_raw_text() -> None:
    raw = "  Heading line\r\n\r\n“Quoted  body,”\nwrapped.\r\n"
    result = normalize(raw, V1)
    paragraph = result.paragraph("p0002")
    assert result.paragraph_text("p0002") == "“Quoted body,” wrapped."
    raw_start, raw_end = result.to_raw_range(paragraph.start, paragraph.end)
    assert raw[raw_start:raw_end] == "“Quoted  body,”\nwrapped."


def test_offset_map_empty_ranges() -> None:
    result = normalize("  ab­cd  ", V1)
    assert result.text == "abcd"
    assert result.to_raw_range(2, 2) == (5, 5)
    assert result.to_raw_range(4, 4) == (7, 7)
    assert result.to_normalized_range(0, 0) == (0, 0)
    assert result.to_normalized_range(9, 9) == (4, 4)
    assert normalize("", V1).to_raw_range(0, 0) == (0, 0)


@pytest.mark.parametrize(("start", "end"), [(-1, 1), (2, 1), (0, 5)])
def test_offset_map_rejects_ranges_outside_the_text(start: int, end: int) -> None:
    result = normalize("abcd", V1)
    with pytest.raises(ValueError, match="outside"):
        result.to_raw_range(start, end)
    with pytest.raises(ValueError, match="outside"):
        result.to_normalized_range(start, end)
