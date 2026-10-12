"""The classifier's cite rules, at the shapes the first corpus parses raised (`v1-e31-t12`).

Described in code, as in `test_style_classifier.py`: the classifier does not know what OOXML is.
The files these shapes come from, and the cards they belong to, are in
`packages/debate_core/tests/integrations/docx_parser/test_cite_detection.py`. Every sentence and
every name here is invented.
"""

from __future__ import annotations

import pytest

from debate_core.domain.style_profile import StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.evidence.style_classifier import (
    MAXIMUM_CITE_LINE_CHARACTERS,
    MAXIMUM_CUTTER_SIGNATURE_CHARACTERS,
    MAXIMUM_LONG_CITE_LINE_CHARACTERS,
    MAXIMUM_STYLED_CITE_CHARACTERS,
    NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS,
    WORDS_THAT_OPEN_A_SENTENCE,
    ParagraphDescription,
    RunDescription,
    classify_paragraph,
    first_name_and_year,
    is_a_cite_wholly_in_brackets,
)
from debate_core.evidence.style_profile_loader import load_style_profile

CITE = StructuralUnit.CITE

SENTENCE = (
    "Grid operators in the region reported that demand from new data centres rose faster than any "
    "other load category last year, and the increase outpaced every scenario the utility had "
    "planned against."
)
CREDENTIALS = (
    "Adaeze Okonkwo is a professor of energy policy at the Invented Institute of Grid Studies and "
    "a senior fellow at the Fictional Centre for Reliability Research, "
)


@pytest.fixture(scope="module")
def profile() -> StyleProfile:
    return load_style_profile()


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


def paragraph(*runs: RunDescription, paragraph_bold: bool | None = None) -> ParagraphDescription:
    return ParagraphDescription(runs=runs, paragraph_bold=paragraph_bold)


def padded(opening: str, total: int, closing: str = "") -> str:
    """`opening`, invented credentials, `closing`: exactly `total` characters."""
    filler = total - len(opening) - len(closing)
    assert filler > 0
    text = (CREDENTIALS * (filler // len(CREDENTIALS) + 1))[:filler]
    return opening + text[:-1] + "s" + closing


# --------------------------------------------------------------------------------------------
# A word that opens a sentence is not an author
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opening",
    [
        "In 2019, the regional operator revised its forecast.",
        "Since 2001 the margin has narrowed every year.",
        "By 2030, a third of the fleet is due to retire.",
        "During 2020 the auditors reviewed every assumption.",
        "After 1994, the region stopped publishing its margin.",
        "The 2022 auction cleared at a record price.",
        "A 2024 review reached the same conclusion.",
        "From 2015 to 2020 the reserve fell by half.",
        "Between 2008 and 2012, no new unit entered service.",
        "About 40 plants are due to close.",
        "Early 2021 brought the first emergency order.",
        "Nearly 30 states have adopted the standard.",
        "Figure 12 shows the margin by season.",
        "Table 14 lists the retirements.",
        "Footnote 23 gives the source of the estimate.",
        "Q1 2025 was the tightest quarter on record.",
        "In 26 states the standard is already law.",
    ],
)
def test_a_line_that_opens_with_a_sentence_opener_and_a_number_is_not_a_cite(
    profile: StyleProfile, opening: str
) -> None:
    assert opening.split()[0] in WORDS_THAT_OPEN_A_SENTENCE

    result = classify_paragraph(paragraph(run(opening)), profile)

    assert result.unit is not CITE


def test_underlined_it_is_evidence_and_plain_and_short_it_is_nothing(profile: StyleProfile) -> None:
    """It falls to whatever its formatting says, as any other paragraph does."""
    text = "In 2019, the regional operator revised its forecast."
    underlined = classify_paragraph(paragraph(run(text[:20]), run(text[20:], underline="single")), profile)
    plain = classify_paragraph(paragraph(run(text)), profile)

    assert underlined.rule_id == "heuristic-marked-up-body-text"
    assert plain.rule_id == "heuristic-unclassified-paragraph"


@pytest.mark.parametrize(
    "line",
    [
        "May 26, Professor of Engineering at an invented university",
        "March 25, senior fellow at a fictional centre",
        "An 26, an invented economist",
        "So 24, a fictional regulator",
        "To 25, Professor of Law",
        "Page 26, reporter for an invented newsroom",
        "Winter 24, a fictional historian",
        "Law 25, Professor of Engineering",
    ],
)
def test_a_word_that_is_also_a_surname_is_still_an_author(profile: StyleProfile, line: str) -> None:
    """Months, seasons and the short surnames are left off the list: the cost of a miss is a real cite."""
    assert line.split()[0] not in WORDS_THAT_OPEN_A_SENTENCE

    result = classify_paragraph(paragraph(run(line)), profile)

    assert result.unit is CITE
    assert result.rule_id == "heuristic-cite-line-author-year"


@pytest.mark.parametrize(
    "line", ["WHO 24, an invented health body", "IN 25, a fictional state agency", "US 26"]
)
def test_an_acronym_spelled_like_a_sentence_opener_is_still_an_author(
    profile: StyleProfile, line: str
) -> None:
    result = classify_paragraph(paragraph(run(line)), profile)

    assert result.unit is CITE


def test_a_sentence_opener_that_opens_in_bold_is_left_to_the_old_reading(profile: StyleProfile) -> None:
    """Bold is how a cite is written. 160 such lines in the corpus cannot be told apart from here."""
    result = classify_paragraph(
        paragraph(run("The 74", bold=True, half_points=26), run(", an invented education newsroom")),
        profile,
    )

    assert result.unit is CITE
    assert result.rule_id == "heuristic-cite-line-author-year"


def test_bold_on_the_paragraph_mark_counts_as_opening_in_bold(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("The 74, an invented education newsroom"), paragraph_bold=True), profile
    )

    assert result.unit is CITE


def test_bold_further_in_does_not(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("In 2019, the operator "), run("revised its forecast", bold=True), run(" twice.")),
        profile,
    )

    assert result.unit is not CITE


def test_two_authors_whose_first_is_a_listed_word_are_still_authors(profile: StyleProfile) -> None:
    """Only a lone word is weighed. *Early and Okonkwo 26* names two people."""
    result = classify_paragraph(paragraph(run("Early and Okonkwo 26, invented co-authors")), profile)

    assert result.unit is CITE


def test_the_list_holds_no_month_and_no_season() -> None:
    for word in ("January", "March", "April", "May", "June", "August", "Spring", "Summer", "Fall", "Winter"):
        assert word not in WORDS_THAT_OPEN_A_SENTENCE


# --------------------------------------------------------------------------------------------
# first_name_and_year
# --------------------------------------------------------------------------------------------


def test_the_first_name_and_year_is_where_the_pattern_first_matches(profile: StyleProfile) -> None:
    found = first_name_and_year("Adaeze Okonkwo 26, professor", profile)

    assert found is not None
    assert (found.start(), found.group(0)) == (7, "Okonkwo 26")


def test_a_sentence_opener_and_a_year_is_passed_over(profile: StyleProfile) -> None:
    found = first_name_and_year("In 2019, the review by Lindqvist 2019 found the same.", profile)

    assert found is not None
    assert found.group(0) == "Lindqvist 2019"


def test_text_with_no_name_and_year_has_none(profile: StyleProfile) -> None:
    assert first_name_and_year("In 2019, the operator revised its forecast.", profile) is None
    assert first_name_and_year(SENTENCE, profile) is None


# --------------------------------------------------------------------------------------------
# The cite character style, past the profile's bound
# --------------------------------------------------------------------------------------------

PAST_THE_PROFILE_BOUND = "verbatim-cite-run-style-past-the-profile-bound"


def styled(
    total: int, *, before: str = "", short: str = "Okonkwo 26", highlight: bool = False
) -> ParagraphDescription:
    rest = padded(" [", total - len(before) - len(short), "] KR")
    runs = [run(before)] if before else []
    runs.append(run(short, style="Style13ptBold"))
    if highlight:
        runs += [run(rest[:200]), run(rest[200:300], highlight="cyan"), run(rest[300:])]
    else:
        runs.append(run(rest))
    return paragraph(*runs)


def test_a_styled_cite_within_the_profile_bound_is_read_as_it_always_was(profile: StyleProfile) -> None:
    result = classify_paragraph(styled(profile.cite.maximum_cite_characters), profile)

    assert (result.unit, result.rule_id) == (CITE, "verbatim-cite-run-style")


def test_a_styled_cite_past_the_profile_bound_is_a_cite(profile: StyleProfile) -> None:
    result = classify_paragraph(styled(profile.cite.maximum_cite_characters + 1), profile)

    assert (result.unit, result.rule_id) == (CITE, PAST_THE_PROFILE_BOUND)
    assert result.match_source is StyleMatchSource.VERBATIM_ALIAS
    assert result.confidence == 1.0


def test_it_is_a_cite_up_to_the_longest_styled_cite_and_not_past_it(profile: StyleProfile) -> None:
    assert MAXIMUM_STYLED_CITE_CHARACTERS == 4_000

    at_the_bound = classify_paragraph(styled(MAXIMUM_STYLED_CITE_CHARACTERS), profile)
    past_it = classify_paragraph(styled(MAXIMUM_STYLED_CITE_CHARACTERS + 1), profile)

    assert at_the_bound.unit is CITE
    assert past_it.unit is not CITE


def test_highlighting_anywhere_in_it_leaves_it_as_it_was(profile: StyleProfile) -> None:
    result = classify_paragraph(styled(1_400, highlight=True), profile)

    assert result.rule_id == "heuristic-marked-up-body-text"


def test_the_name_and_year_may_sit_behind_a_first_name(profile: StyleProfile) -> None:
    result = classify_paragraph(styled(1_400, before="Adaeze "), profile)

    assert result.rule_id == PAST_THE_PROFILE_BOUND


def test_the_name_and_year_must_start_within_the_head(profile: StyleProfile) -> None:
    assert NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS == 40
    at_the_head = styled(1_400, before="x" * 39 + " ")
    past_the_head = styled(1_400, before="x" * 40 + " ")

    assert classify_paragraph(at_the_head, profile).unit is CITE
    assert classify_paragraph(past_the_head, profile).unit is not CITE


def test_leading_white_space_does_not_move_the_head(profile: StyleProfile) -> None:
    """The head is measured over the text as a reader sees it."""
    result = classify_paragraph(styled(1_400, before="   " + "x" * 39 + " "), profile)

    assert result.unit is CITE


def test_leading_white_space_does_not_move_the_style_off_the_name(profile: StyleProfile) -> None:
    """The style is looked for where the name is in the paragraph, white space included."""
    result = classify_paragraph(styled(1_400, before=" " * 20), profile)

    assert result.rule_id == PAST_THE_PROFILE_BOUND


def test_the_style_must_touch_the_name_and_year(profile: StyleProfile) -> None:
    """A plain name and year at the head, and the cite style on a phrase 600 characters in."""
    text = padded("Okonkwo 26 argues that ", 1_400, " in every season.")
    described = paragraph(run(text[:600]), run(text[600:660], style="Style13ptBold"), run(text[660:]))

    assert classify_paragraph(described, profile).unit is not CITE


def test_the_style_on_part_of_the_name_and_year_is_enough(profile: StyleProfile) -> None:
    rest = padded(" [", 1_390, "] KR")
    described = paragraph(run("Okonkwo", style="Style13ptBold"), run(" 26" + rest))

    assert classify_paragraph(described, profile).rule_id == PAST_THE_PROFILE_BOUND


def test_a_styled_run_that_ends_where_the_name_begins_does_not_touch_it(profile: StyleProfile) -> None:
    rest = padded(" [", 1_380, "] KR")
    described = paragraph(run("Professor ", style="Style13ptBold"), run("Okonkwo 26" + rest))

    assert classify_paragraph(described, profile).unit is not CITE


def test_a_styled_run_that_starts_where_the_year_ends_does_not_touch_it(profile: StyleProfile) -> None:
    rest = padded(" [", 1_380, "] KR")
    described = paragraph(run("Okonkwo 26"), run(", Professor", style="Style13ptBold"), run(rest))

    assert classify_paragraph(described, profile).unit is not CITE


def test_a_sentence_opener_in_the_cite_style_is_not_a_name_and_year(profile: StyleProfile) -> None:
    text = "In 2019, " + SENTENCE * 8
    described = paragraph(run(text[:7], style="Style13ptBold"), run(text[7:]))

    assert classify_paragraph(described, profile).unit is not CITE


# --------------------------------------------------------------------------------------------
# A cite line longer than 400 characters: a bold name and year
# --------------------------------------------------------------------------------------------

BOLD_CITE_LINE = "heuristic-cite-line-bold-author-year"


def bold_line(
    total: int, *, short: str = "Okonkwo 26", bold: bool | None = True, highlight: bool = False
) -> ParagraphDescription:
    rest = padded(", ", total - len(short), ", Journal of Grid Studies")
    runs = [run(short, bold=bold, half_points=26)]
    if highlight:
        runs += [run(rest[:100]), run(rest[100:200], highlight="cyan"), run(rest[200:])]
    else:
        runs.append(run(rest))
    return paragraph(*runs)


def test_the_bounds_are_the_ones_the_corpus_gave() -> None:
    assert MAXIMUM_CITE_LINE_CHARACTERS == 400
    assert MAXIMUM_LONG_CITE_LINE_CHARACTERS == 2_000
    assert MAXIMUM_CUTTER_SIGNATURE_CHARACTERS == 30


def test_a_bold_name_and_year_open_a_cite_line_past_400_characters(profile: StyleProfile) -> None:
    at_the_old_bound = classify_paragraph(bold_line(MAXIMUM_CITE_LINE_CHARACTERS), profile)
    past_it = classify_paragraph(bold_line(MAXIMUM_CITE_LINE_CHARACTERS + 1), profile)

    assert (at_the_old_bound.unit, at_the_old_bound.rule_id) == (CITE, "heuristic-cite-line-author-year")
    assert (past_it.unit, past_it.rule_id) == (CITE, BOLD_CITE_LINE)
    assert past_it.match_source is StyleMatchSource.HEURISTIC
    assert past_it.confidence == 0.6


def test_a_long_cite_line_ends_at_2000_characters(profile: StyleProfile) -> None:
    at_the_bound = classify_paragraph(bold_line(MAXIMUM_LONG_CITE_LINE_CHARACTERS), profile)
    past_it = classify_paragraph(bold_line(MAXIMUM_LONG_CITE_LINE_CHARACTERS + 1), profile)

    assert at_the_bound.unit is CITE
    assert past_it.unit is not CITE


@pytest.mark.parametrize("bold", [False, None])
def test_a_name_and_year_that_do_not_open_in_bold_do_not(profile: StyleProfile, bold: bool | None) -> None:
    assert classify_paragraph(bold_line(700, bold=bold), profile).unit is not CITE


def test_a_highlighted_paragraph_behind_a_bold_name_is_left_as_it_was(profile: StyleProfile) -> None:
    result = classify_paragraph(bold_line(700, highlight=True), profile)

    assert result.rule_id == "heuristic-marked-up-body-text"


def test_a_bold_sentence_opener_does_not_open_a_long_cite_line(profile: StyleProfile) -> None:
    assert classify_paragraph(bold_line(700, short="In 2019"), profile).unit is not CITE


def test_a_bold_opening_with_no_name_and_year_does_not(profile: StyleProfile) -> None:
    described = paragraph(run("Reserve margins fell", bold=True), run(" " + SENTENCE * 3))

    assert classify_paragraph(described, profile).unit is not CITE


# --------------------------------------------------------------------------------------------
# A cite line longer than 400 characters: one bracket to the end
# --------------------------------------------------------------------------------------------

BRACKETED_CITE_LINE = "heuristic-cite-line-bracketed"


def bracketed(
    total: int = 700, *, opening: str = "Okonkwo 26 [", closing: str = "] KR", highlight: bool = False
) -> ParagraphDescription:
    text = padded(opening, total, closing)
    if highlight:
        return paragraph(run(text[:100]), run(text[100:200], highlight="cyan"), run(text[200:]))
    return paragraph(run(text))


@pytest.mark.parametrize(
    "closing",
    [
        "]",
        "] KR",
        "] kr",
        "]KR",
        "] //KR",
        "]//kr",
        "] -- KR",
        "]|kr",
        "] KR + MW",
        "] recut KR",
        "].",
        ") kr",
    ],
)
def test_a_name_and_year_then_one_bracket_to_the_end_is_a_cite_line(
    profile: StyleProfile, closing: str
) -> None:
    opening = "Okonkwo 26 (" if closing.startswith(")") else "Okonkwo 26 ["

    result = classify_paragraph(bracketed(opening=opening, closing=closing), profile)

    assert (result.unit, result.rule_id) == (CITE, BRACKETED_CITE_LINE)
    assert result.match_source is StyleMatchSource.HEURISTIC
    assert result.confidence == 0.6


@pytest.mark.parametrize(
    "opening",
    [
        "Okonkwo 26[",
        "Okonkwo 26 [",
        "Okonkwo 26, [",
        "Okonkwo 26 - [",
        "Okonkwo 26 – [",
        "Okonkwo 26 — [",
        "Okonkwo 26: [",
        "Okonkwo 26; [",
        "Okonkwo 26. [",
        "Okonkwo '26 [",
    ],
)
def test_only_punctuation_and_space_may_stand_between_the_year_and_the_bracket(
    profile: StyleProfile, opening: str
) -> None:
    assert classify_paragraph(bracketed(opening=opening), profile).unit is CITE


def test_a_word_between_the_year_and_the_bracket_leaves_it_as_it_was(profile: StyleProfile) -> None:
    assert classify_paragraph(bracketed(opening="Okonkwo 26 writes ["), profile).unit is not CITE


def test_the_signature_is_at_most_30_characters(profile: StyleProfile) -> None:
    thirty = "] " + "k" * 30
    thirty_one = "] " + "k" * 31

    assert classify_paragraph(bracketed(closing=thirty), profile).unit is CITE
    assert classify_paragraph(bracketed(closing=thirty_one), profile).unit is not CITE


def test_the_bracket_that_closes_it_is_the_one_that_opened_it(profile: StyleProfile) -> None:
    """A bracket inside the bracket closes only itself, and a round one does not close a square one."""
    nested = bracketed(opening="Okonkwo 26 [formerly [until 2024] at the regulator; ")
    early = bracketed(opening="Okonkwo 26 [the first study] found that ", closing=" in every season.")
    never = bracketed(closing=") KR")

    assert classify_paragraph(nested, profile).unit is CITE
    assert classify_paragraph(early, profile).unit is not CITE
    assert classify_paragraph(never, profile).unit is not CITE


def test_a_bracketed_cite_line_ends_at_2000_characters(profile: StyleProfile) -> None:
    assert classify_paragraph(bracketed(MAXIMUM_LONG_CITE_LINE_CHARACTERS), profile).unit is CITE
    assert classify_paragraph(bracketed(MAXIMUM_LONG_CITE_LINE_CHARACTERS + 1), profile).unit is not CITE


def test_a_highlighted_bracketed_paragraph_is_left_as_it_was(profile: StyleProfile) -> None:
    assert classify_paragraph(bracketed(highlight=True), profile).rule_id == "heuristic-marked-up-body-text"


def test_a_sentence_opener_and_a_year_before_a_bracket_are_not_a_cite_line(profile: StyleProfile) -> None:
    assert classify_paragraph(bracketed(opening="In 2019 ["), profile).unit is not CITE


def test_a_bold_name_before_the_bracket_is_read_by_the_bold_rule(profile: StyleProfile) -> None:
    """Either rule would take it. The bold one is tried first, and the card names it."""
    text = padded("Okonkwo 26 [", 700, "] KR")
    described = paragraph(run(text[:10], bold=True), run(text[10:]))

    assert classify_paragraph(described, profile).rule_id == BOLD_CITE_LINE


# --------------------------------------------------------------------------------------------
# is_a_cite_wholly_in_brackets
# --------------------------------------------------------------------------------------------


def wholly(
    total: int = 500, *, opening: str = "[Okonkwo 26, ", closing: str = "] KR"
) -> ParagraphDescription:
    return paragraph(run(padded(opening, total, closing), half_points=16))


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("[Okonkwo 26, ", "] KR"),
        ("[Okonkwo 26, ", "]"),
        ("(Okonkwo 26, ", ") kr"),
        ("[Adaeze Okonkwo 26, ", "]//KR"),
        ("(Adaeze Okonkwo, 2026, ", ")."),
    ],
)
def test_a_paragraph_inside_one_bracket_behind_a_name_and_year_is_a_cite_wholly_in_brackets(
    profile: StyleProfile, opening: str, closing: str
) -> None:
    assert is_a_cite_wholly_in_brackets(wholly(opening=opening, closing=closing), profile)


def test_the_classifier_itself_does_not_call_it_a_cite(profile: StyleProfile) -> None:
    """Where it stands decides, and only the assembly knows that. Inside a body it is a reference."""
    assert classify_paragraph(wholly(), profile).rule_id == "heuristic-shrunk-body-text"


@pytest.mark.parametrize(
    ("opening", "closing", "why"),
    [
        ("[The 2019 survey covered ", "]", "a sentence opener and a year is not a name and a year"),
        ("[Marked for the second speech, ", "]", "no name and year at all"),
        ("Okonkwo 26 [", "] KR", "it does not open with the bracket"),
        ("[Okonkwo 26, ", ") KR", "the bracket never closes"),
        ("[Okonkwo 26] argues that ", " in every season.", "the bracket closes early"),
        ("[Okonkwo 26, ", "] " + "k" * 31, "what follows the bracket is longer than a signature"),
        ("[" + "x" * 40 + " Okonkwo 26, ", "] KR", "the name and year start past the head"),
    ],
)
def test_what_is_not_a_cite_wholly_in_brackets(
    profile: StyleProfile, opening: str, closing: str, why: str
) -> None:
    assert not is_a_cite_wholly_in_brackets(wholly(opening=opening, closing=closing), profile), why


def test_a_name_and_year_40_characters_in_are_at_its_head(profile: StyleProfile) -> None:
    described = wholly(opening="[" + "x" * 38 + " Okonkwo 26, ")

    assert described.text.index("Okonkwo 26") == 40
    assert is_a_cite_wholly_in_brackets(described, profile)


def test_it_ends_at_2000_characters(profile: StyleProfile) -> None:
    assert is_a_cite_wholly_in_brackets(wholly(MAXIMUM_LONG_CITE_LINE_CHARACTERS), profile)
    assert not is_a_cite_wholly_in_brackets(wholly(MAXIMUM_LONG_CITE_LINE_CHARACTERS + 1), profile)


def test_a_highlighted_one_is_not(profile: StyleProfile) -> None:
    text = padded("[Okonkwo 26, ", 500, "] KR")
    described = paragraph(run(text[:100]), run(text[100:200], highlight="cyan"), run(text[200:]))

    assert not is_a_cite_wholly_in_brackets(described, profile)
