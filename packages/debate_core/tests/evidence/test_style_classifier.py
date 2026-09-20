"""Tests for the non-Verbatim paragraph and run classifier.

The paragraphs described here are the shapes real files arrive in: a Verbatim-styled card, a
Google Docs export whose only structural signal is an outline level, an opencaselist wiki
conversion that records a card's first and last words with an ellipsis between them, and a
document somebody direct-formatted by hand. Each one is described in code rather than built as a
`.docx`, because the classifier's whole point is that it does not know what OOXML is; the
fixture-backed tests that read real `.docx` files live at the bottom of this module.

Two properties get their own tests and matter more than any single rule: the classifier is
deterministic, and it is conservative. An ordinary Word document that merely uses outline levels
must not come out as a stack of pockets.
"""

from __future__ import annotations

import pytest

from debate_core.domain.style_profile import (
    RunEmphasis,
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
)
from debate_core.evidence.style_classifier import (
    MAXIMUM_HEADING_CHARACTERS,
    ParagraphDescription,
    RunDescription,
    classify_paragraph,
    classify_run,
)
from debate_core.evidence.style_profile_loader import load_style_profile

# Real card text is never committed to this repository. These sentences are written for the tests.
EVIDENCE_SENTENCE = (
    "Grid operators in the region reported that demand from new data centres rose faster than any "
    "other load category last year, and that the increase outpaced every scenario the utility had "
    "planned against, leaving the reserve margin thinner than at any point in the past decade."
)


@pytest.fixture(scope="module")
def profile() -> StyleProfile:
    return load_style_profile()


def paragraph(
    *runs: RunDescription,
    style_id: str | None = None,
    style_name: str | None = None,
    style_based_on: tuple[str, ...] = (),
    outline_level: int | None = None,
    in_table: bool = False,
) -> ParagraphDescription:
    return ParagraphDescription(
        runs=runs,
        style_id=style_id,
        style_name=style_name,
        style_based_on=style_based_on,
        outline_level=outline_level,
        in_table=in_table,
    )


def run(
    text: str,
    *,
    style: str | None = None,
    bold: bool | None = None,
    underline: str | None = None,
    highlight: str | None = None,
    half_points: int | None = None,
) -> RunDescription:
    return RunDescription(
        text=text,
        character_style_id=style,
        bold=bold,
        underline=underline,
        highlight=highlight,
        half_points=half_points,
    )


# --------------------------------------------------------------------------------------------
# A styled file still resolves through the profile, not the heuristics
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("style_id", "unit"),
    [
        ("Heading1", StructuralUnit.POCKET),
        ("Heading2", StructuralUnit.HAT),
        ("Heading3", StructuralUnit.BLOCK),
        ("Heading4", StructuralUnit.TAG),
        ("Analytic", StructuralUnit.ANALYTIC),
        ("Undertag", StructuralUnit.UNDERTAG),
    ],
)
def test_a_verbatim_styled_paragraph_never_reaches_the_heuristics(
    profile: StyleProfile, style_id: str, unit: StructuralUnit
) -> None:
    result = classify_paragraph(paragraph(run("Extinction is likely"), style_id=style_id), profile)
    assert result.unit is unit
    assert result.match_source is StyleMatchSource.VERBATIM
    assert result.confidence == 1.0


def test_a_cite_character_style_identifies_a_cite_with_no_paragraph_style(
    profile: StyleProfile,
) -> None:
    """Verbatim gives cites no paragraph style, so this is how nearly every real cite is found."""
    result = classify_paragraph(
        paragraph(run("Okonkwo 26", style="Style13ptBold"), run(", Professor of Energy Policy")),
        profile,
    )
    assert result.unit is StructuralUnit.CITE
    assert result.rule_id == "verbatim-cite-run-style"
    assert result.match_source is StyleMatchSource.VERBATIM_ALIAS


def test_a_long_paragraph_with_a_stray_cite_style_is_not_called_a_cite(
    profile: StyleProfile,
) -> None:
    long_text = EVIDENCE_SENTENCE * 8
    assert len(long_text) > profile.cite.maximum_cite_characters
    result = classify_paragraph(paragraph(run(long_text, style="Style13ptBold")), profile)
    assert result.unit is not StructuralUnit.CITE


# --------------------------------------------------------------------------------------------
# ac3 — outline levels, cite lines and evidence in files with no Verbatim styles
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outline_level", "half_points", "underline", "unit"),
    [
        (0, 52, None, StructuralUnit.POCKET),
        (1, 44, None, StructuralUnit.HAT),
        (2, 32, "single", StructuralUnit.BLOCK),
        (3, 26, None, StructuralUnit.TAG),
    ],
)
def test_an_outline_level_with_the_formatting_that_goes_with_it_is_promoted(
    profile: StyleProfile,
    outline_level: int,
    half_points: int,
    underline: str | None,
    unit: StructuralUnit,
) -> None:
    result = classify_paragraph(
        paragraph(
            run("Advantage one is the grid", bold=True, half_points=half_points, underline=underline),
            outline_level=outline_level,
        ),
        profile,
    )
    assert result.unit is unit
    assert result.rule_id == f"heuristic-outline-level-{outline_level}"
    assert result.match_source is StyleMatchSource.HEURISTIC
    assert 0.0 < result.confidence < 1.0


def test_an_outline_level_with_none_of_the_formatting_is_not_promoted(
    profile: StyleProfile,
) -> None:
    """The guard that keeps an ordinary Word document from parsing as a stack of pockets."""
    result = classify_paragraph(
        paragraph(run("Course outline for the autumn term"), outline_level=0), profile
    )
    assert result.unit is not StructuralUnit.POCKET


def test_an_outline_level_zero_paragraph_that_is_bold_but_small_is_not_a_pocket(
    profile: StyleProfile,
) -> None:
    result = classify_paragraph(
        paragraph(run("Section heading", bold=True, half_points=24), outline_level=0), profile
    )
    assert result.unit is not StructuralUnit.POCKET


def test_a_block_needs_its_underline(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("AT: Grid tradeoff", bold=True, half_points=32), outline_level=2), profile
    )
    assert result.unit is not StructuralUnit.BLOCK


def test_a_wiki_converted_cite_entry_is_recognised_by_its_ellipsis(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("Okonkwo 26 — Grid operators in the region … thinner than at any point.")),
        profile,
    )
    assert result.unit is StructuralUnit.CITE
    assert result.rule_id == "heuristic-wiki-cite-entry"
    assert result.match_source is StyleMatchSource.HEURISTIC


def test_an_ellipsis_with_no_author_and_year_is_not_a_cite(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run("and so on … and so forth")), profile)
    assert result.unit is not StructuralUnit.CITE


@pytest.mark.parametrize(
    "line",
    [
        "Okonkwo 26, Professor of Energy Policy, University of Lagos",
        "Okonkwo '26",
        "Okonkwo et al. 2026",
        "Okonkwo and Halvorsen 26, senior fellows",
    ],
)
def test_a_line_that_opens_with_a_short_cite_is_a_cite(profile: StyleProfile, line: str) -> None:
    result = classify_paragraph(paragraph(run(line)), profile)
    assert result.unit is StructuralUnit.CITE
    assert result.rule_id == "heuristic-cite-line-author-year"
    assert result.match_source is StyleMatchSource.HEURISTIC


def test_prose_that_merely_mentions_a_year_is_not_a_cite(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run(EVIDENCE_SENTENCE)), profile)
    assert result.unit is not StructuralUnit.CITE


def test_underlined_body_text_is_evidence(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(
            run("Grid operators in the region reported that "),
            run("demand rose faster than any other load category", underline="single"),
            run(" last year."),
        ),
        profile,
    )
    assert result.unit is StructuralUnit.EVIDENCE
    assert result.rule_id == "heuristic-marked-up-body-text"
    assert result.match_source is StyleMatchSource.HEURISTIC


def test_highlighted_body_text_is_evidence(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run("demand rose faster than planned", highlight="cyan")), profile)
    assert result.unit is StructuralUnit.EVIDENCE
    assert result.rule_id == "heuristic-marked-up-body-text"


def test_shrunk_unread_text_is_still_evidence(profile: StyleProfile) -> None:
    """The unread remainder of a card is evidence; being small is formatting, not a reason to drop it."""
    result = classify_paragraph(paragraph(run(EVIDENCE_SENTENCE, half_points=16)), profile)
    assert result.unit is StructuralUnit.EVIDENCE
    assert result.rule_id == "heuristic-shrunk-body-text"


def test_plain_prose_is_evidence_with_the_lowest_confidence_of_the_three(
    profile: StyleProfile,
) -> None:
    marked_up = classify_paragraph(paragraph(run(EVIDENCE_SENTENCE, underline="single")), profile)
    plain = classify_paragraph(paragraph(run(EVIDENCE_SENTENCE, half_points=22)), profile)
    assert plain.unit is StructuralUnit.EVIDENCE
    assert plain.rule_id == "heuristic-prose-paragraph"
    assert plain.confidence < marked_up.confidence


def test_a_heading_with_no_outline_level_at_all_is_recognised_from_its_size(
    profile: StyleProfile,
) -> None:
    """The case CardMirror leaves flat, and the one wiki conversions produce."""
    result = classify_paragraph(paragraph(run("1AC — Grid", bold=True, half_points=52)), profile)
    assert result.unit is StructuralUnit.POCKET
    assert result.rule_id == "heuristic-direct-formatted-heading-pocket"
    assert result.match_source is StyleMatchSource.HEURISTIC
    assert result.confidence < 0.8, "weaker evidence than an outline level, and it says so"


def test_a_bold_body_sized_line_with_no_outline_level_is_a_tag(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("Data centre demand collapses the reserve margin", bold=True, half_points=26)),
        profile,
    )
    assert result.unit is StructuralUnit.TAG
    assert result.rule_id == "heuristic-direct-formatted-heading-tag"


def test_a_long_bold_paragraph_is_not_a_heading(profile: StyleProfile) -> None:
    long_text = EVIDENCE_SENTENCE * 3
    assert len(long_text) > MAXIMUM_HEADING_CHARACTERS
    result = classify_paragraph(paragraph(run(long_text, bold=True, half_points=52)), profile)
    assert result.unit is StructuralUnit.EVIDENCE


def test_a_paragraph_with_one_bold_word_is_not_a_heading(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(
            run("Grid operators ", half_points=22),
            run("reported", bold=True, half_points=22),
            run(" that demand rose.", half_points=22),
        ),
        profile,
    )
    assert result.unit is not StructuralUnit.POCKET
    assert result.unit is not StructuralUnit.TAG


# --------------------------------------------------------------------------------------------
# The paragraphs that are OTHER whatever they look like
# --------------------------------------------------------------------------------------------


def test_a_table_cell_is_other_even_when_it_looks_like_a_heading(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run("Round 3", bold=True, half_points=52), in_table=True), profile)
    assert result.unit is StructuralUnit.OTHER
    assert result.rule_id == "heuristic-table-cell"


def test_a_styled_heading_inside_a_table_still_resolves_through_the_profile(
    profile: StyleProfile,
) -> None:
    result = classify_paragraph(
        paragraph(run("Pocket"), style_id="Heading1", in_table=True), profile
    )
    assert result.unit is StructuralUnit.POCKET


def test_an_empty_unstyled_paragraph_is_other(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run("   ")), profile)
    assert result.unit is StructuralUnit.OTHER
    assert result.rule_id == "heuristic-empty-paragraph"


def test_an_empty_heading_is_still_a_pocket(profile: StyleProfile) -> None:
    """An empty Heading 1 is how debate files separate two documents packed into one."""
    result = classify_paragraph(paragraph(style_id="Heading1"), profile)
    assert result.unit is StructuralUnit.POCKET


def test_a_short_unremarkable_line_falls_through_to_other(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run("continued on the next page")), profile)
    assert result.unit is StructuralUnit.OTHER
    assert result.rule_id == "heuristic-unclassified-paragraph"


# --------------------------------------------------------------------------------------------
# Determinism, which the acceptance criterion asks for by name
# --------------------------------------------------------------------------------------------


def test_the_same_paragraph_always_classifies_the_same_way(profile: StyleProfile) -> None:
    description = paragraph(
        run("Okonkwo 26 — Grid operators … reserve margin.", half_points=22),
        run(" continued", underline="single"),
    )
    results = [classify_paragraph(description, profile) for _ in range(50)]
    assert all(result == results[0] for result in results)


def test_every_classification_names_a_rule_and_a_match_source(profile: StyleProfile) -> None:
    descriptions = [
        paragraph(run("Pocket"), style_id="Heading1"),
        paragraph(run("Okonkwo 26")),
        paragraph(run(EVIDENCE_SENTENCE, underline="single")),
        paragraph(run("1AC", bold=True, half_points=52)),
        paragraph(run("   ")),
        paragraph(run("x"), in_table=True),
    ]
    for description in descriptions:
        result = classify_paragraph(description, profile)
        assert result.rule_id
        assert result.match_source in set(StyleMatchSource)
        assert 0.0 < result.confidence <= 1.0


def test_a_heuristic_match_is_never_reported_as_a_verbatim_match(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("1AC — Grid", bold=True, half_points=52), outline_level=0), profile
    )
    assert result.match_source is StyleMatchSource.HEURISTIC
    assert result.rule_id.startswith("heuristic-")


# --------------------------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------------------------


def test_a_run_carrying_both_underline_encodings_is_underlined_once(profile: StyleProfile) -> None:
    """What CardMirror writes on every body run it exports, per ADR-0014."""
    matches = classify_run(
        RunDescription(text="demand rose", character_style_id="StyleUnderline", underline="single"),
        profile,
    )
    underlines = [match for match in matches if match.emphasis is RunEmphasis.UNDERLINE]
    assert len(underlines) == 1
    assert underlines[0].rule_id == "verbatim-style-id:StyleUnderline"


def test_a_direct_underline_in_a_structural_slot_is_the_expected_encoding(
    profile: StyleProfile,
) -> None:
    matches = classify_run(RunDescription(text="Tag", underline="single"), profile, slot=StructuralUnit.TAG)
    assert [match.rule_id for match in matches] == ["direct-underline"]
    assert matches[0].match_source is StyleMatchSource.VERBATIM


def test_a_direct_underline_in_a_body_slot_is_recorded_as_the_other_encoding(
    profile: StyleProfile,
) -> None:
    matches = classify_run(
        RunDescription(text="body", underline="single"), profile, slot=StructuralUnit.EVIDENCE
    )
    assert [match.rule_id for match in matches] == ["direct-underline-in-body-slot"]


@pytest.mark.parametrize("value", ["none", "0", "false", None])
def test_an_underline_switched_off_is_not_an_underline(profile: StyleProfile, value: str | None) -> None:
    matches = classify_run(RunDescription(text="body", underline=value), profile)
    assert not any(match.emphasis is RunEmphasis.UNDERLINE for match in matches)


def test_a_run_can_carry_several_emphases_at_once(profile: StyleProfile) -> None:
    matches = classify_run(
        RunDescription(
            text="the reserve margin collapses",
            character_style_id="StyleUnderline",
            highlight="cyan",
            bold=True,
            half_points=22,
        ),
        profile,
    )
    assert {match.emphasis for match in matches} == {
        RunEmphasis.UNDERLINE,
        RunEmphasis.HIGHLIGHT,
        RunEmphasis.BOLD,
    }


def test_small_unread_text_is_reported_as_shrunk(profile: StyleProfile) -> None:
    matches = classify_run(RunDescription(text="unread remainder", half_points=16), profile)
    assert [match.emphasis for match in matches] == [RunEmphasis.SHRUNK]
    assert matches[0].match_source is StyleMatchSource.HEURISTIC


def test_small_underlined_text_is_not_shrunk(profile: StyleProfile) -> None:
    matches = classify_run(RunDescription(text="read aloud", underline="single", half_points=16), profile)
    assert not any(match.emphasis is RunEmphasis.SHRUNK for match in matches)


def test_a_highlight_colour_the_profile_does_not_know_is_ignored(profile: StyleProfile) -> None:
    matches = classify_run(RunDescription(text="x", highlight="chartreuse"), profile)
    assert not any(match.emphasis is RunEmphasis.HIGHLIGHT for match in matches)


def test_run_classification_is_deterministic(profile: StyleProfile) -> None:
    description = RunDescription(
        text="x", character_style_id="Emphasis", underline="single", highlight="green", bold=True
    )
    results = [classify_run(description, profile) for _ in range(50)]
    assert all(result == results[0] for result in results)
