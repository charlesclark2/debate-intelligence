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

import json
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

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
from debate_core.evidence.style_profile_loader import load_style_profile, resolve_based_on_chain

REPO_ROOT = Path(__file__).resolve().parents[4]

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
    result = classify_paragraph(paragraph(run("Pocket"), style_id="Heading1", in_table=True), profile)
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


# --------------------------------------------------------------------------------------------
# The fixture files, read back from disk
# --------------------------------------------------------------------------------------------
#
# The tests above describe paragraphs in code. These read the real `.docx` fixtures in
# tests/fixtures/debate_files/style_profile/ and check every paragraph against the expectations
# committed beside them — expectations written by hand in scripts/generate_style_fixtures.py, not
# produced by running this classifier.
#
# The reader below is the smallest thing that turns a `w:p` into a ParagraphDescription. It is a
# test helper, not a parser: v1-e31-t03 builds the real one, against the same fixtures.

FIXTURE_DIRECTORY = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "style_profile"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _qualified(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def _style_table(styles_root: ElementTree.Element) -> dict[str, tuple[str, str | None]]:
    """`styleId -> (name, basedOn)` from a fixture's `word/styles.xml`."""
    table: dict[str, tuple[str, str | None]] = {}
    for style in styles_root.findall(_qualified("style")):
        style_id = style.get(_qualified("styleId"))
        if not style_id:
            continue
        name_element = style.find(_qualified("name"))
        based_on_element = style.find(_qualified("basedOn"))
        table[style_id] = (
            (name_element.get(_qualified("val")) or "") if name_element is not None else "",
            based_on_element.get(_qualified("val")) if based_on_element is not None else None,
        )
    return table


def _attribute(properties: ElementTree.Element | None, tag: str) -> str | None:
    if properties is None:
        return None
    element = properties.find(_qualified(tag))
    if element is None:
        return None
    return element.get(_qualified("val")) or "on"


def _read_paragraphs(docx_path: Path) -> list[ParagraphDescription]:
    """Turn a fixture's paragraphs into descriptions.

    The stdlib parser rather than lxml: it is fully typed, and this helper needs nothing lxml
    offers. It reads only the fixtures in this directory, which this repository generates.
    """
    with zipfile.ZipFile(docx_path) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
        styles = _style_table(ElementTree.fromstring(archive.read("word/styles.xml")))

    def ancestors(style_id: str | None) -> tuple[str, ...]:
        return resolve_based_on_chain(style_id or "", {key: value[1] for key, value in styles.items()})

    descriptions: list[ParagraphDescription] = []
    for index, element in enumerate(document.iter(_qualified("p"))):
        paragraph_properties = element.find(_qualified("pPr"))
        style_id = _attribute(paragraph_properties, "pStyle")
        outline = _attribute(paragraph_properties, "outlineLvl")
        runs: list[RunDescription] = []
        for run_element in element.iter(_qualified("r")):
            run_properties = run_element.find(_qualified("rPr"))
            bold_value = _attribute(run_properties, "b")
            size_value = _attribute(run_properties, "sz")
            character_style = _attribute(run_properties, "rStyle")
            runs.append(
                RunDescription(
                    text="".join(node.text or "" for node in run_element.iter(_qualified("t"))),
                    character_style_id=character_style,
                    character_style_name=styles.get(character_style or "", ("", None))[0] or None,
                    character_style_based_on=ancestors(character_style),
                    bold=None if bold_value is None else bold_value not in ("0", "false"),
                    underline=_attribute(run_properties, "u"),
                    highlight=_attribute(run_properties, "highlight"),
                    half_points=int(size_value) if size_value and size_value.isdigit() else None,
                )
            )
        descriptions.append(
            ParagraphDescription(
                runs=tuple(runs),
                style_id=style_id,
                style_name=styles.get(style_id or "", ("", None))[0] or None,
                style_based_on=ancestors(style_id),
                outline_level=int(outline) if outline and outline.isdigit() else None,
                element_index=index,
            )
        )
    return descriptions


def _fixture_names() -> list[str]:
    return sorted(path.name for path in FIXTURE_DIRECTORY.glob("*.docx"))


def test_the_fixture_directory_holds_the_documents_the_manifest_describes() -> None:
    """Guards the parametrized tests below: an empty directory would make them pass vacuously."""
    names = _fixture_names()
    assert len(names) >= 5
    assert (FIXTURE_DIRECTORY / "MANIFEST.md").is_file()
    for name in names:
        expected = FIXTURE_DIRECTORY / f"{name.removesuffix('.docx')}.expected.json"
        assert expected.is_file(), f"{name} has no committed expectations"


@pytest.mark.parametrize("fixture_name", _fixture_names())
def test_every_fixture_paragraph_classifies_as_its_expectations_say(
    profile: StyleProfile, fixture_name: str
) -> None:
    expectations = json.loads(
        (FIXTURE_DIRECTORY / f"{fixture_name.removesuffix('.docx')}.expected.json").read_text(
            encoding="utf-8"
        )
    )
    paragraphs = _read_paragraphs(FIXTURE_DIRECTORY / fixture_name)
    assert len(paragraphs) == len(expectations["paragraphs"])

    for description, expected in zip(paragraphs, expectations["paragraphs"], strict=True):
        result = classify_paragraph(description, profile)
        where = f"{fixture_name} paragraph {expected['index']}: {expected['text'][:60]!r}"
        assert result.unit.value == expected["expected_unit"], where
        assert result.rule_id == expected["expected_rule_id"], where
        assert result.match_source.value == expected["expected_match_source"], where


@pytest.mark.parametrize(
    "fixture_name",
    ["outline-levels-only.docx", "direct-formatting-only.docx", "wiki-converted-cite-entries.docx"],
)
def test_the_heuristic_fixtures_are_classified_without_a_single_verbatim_style(
    profile: StyleProfile, fixture_name: str
) -> None:
    """The criterion in the task spec: headings, cite lines and evidence, all `HEURISTIC`."""
    paragraphs = _read_paragraphs(FIXTURE_DIRECTORY / fixture_name)
    results = [classify_paragraph(description, profile) for description in paragraphs]

    assert all(result.match_source is StyleMatchSource.HEURISTIC for result in results)
    assert all(result.rule_id.startswith("heuristic-") for result in results)
    units = {result.unit for result in results}
    assert units & {StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.TAG}, "no heading"
    assert StructuralUnit.CITE in units, "no cite line"
    assert StructuralUnit.EVIDENCE in units or fixture_name == "wiki-converted-cite-entries.docx"


def test_the_ordinary_word_document_is_not_promoted_to_debate_structure(
    profile: StyleProfile,
) -> None:
    """The negative fixture. A syllabus that uses outline levels is not a stack of pockets."""
    paragraphs = _read_paragraphs(FIXTURE_DIRECTORY / "ordinary-document-with-outline-levels.docx")
    units = {classify_paragraph(description, profile).unit for description in paragraphs}
    assert units.isdisjoint(
        {StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK, StructuralUnit.TAG}
    )


def test_classifying_a_fixture_twice_gives_the_same_answer(profile: StyleProfile) -> None:
    paragraphs = _read_paragraphs(FIXTURE_DIRECTORY / "verbatim-cut-card.docx")
    first = [classify_paragraph(description, profile) for description in paragraphs]
    second = [classify_paragraph(description, profile) for description in paragraphs]
    assert first == second


def test_the_fixtures_were_generated_from_the_profile_that_is_committed(
    profile: StyleProfile,
) -> None:
    """A fixture generated under an older profile is a fixture that has stopped testing anything."""
    for fixture_name in _fixture_names():
        expectations = json.loads(
            (FIXTURE_DIRECTORY / f"{fixture_name.removesuffix('.docx')}.expected.json").read_text(
                encoding="utf-8"
            )
        )
        assert expectations["profile_version"] == profile.profile_version, (
            f"{fixture_name} was generated under profile {expectations['profile_version']}; "
            f"rerun `uv run python scripts/generate_style_fixtures.py`"
        )


# --------------------------------------------------------------------------------------------
# The edges of each rule
# --------------------------------------------------------------------------------------------


def test_a_paragraph_with_no_visible_runs_takes_its_boldness_from_the_paragraph_mark() -> None:
    assert ParagraphDescription(runs=(run("  "),), paragraph_bold=True).effective_bold is True
    assert ParagraphDescription(runs=()).effective_bold is False


def test_a_paragraph_size_set_on_the_paragraph_mark_is_used_when_no_run_says() -> None:
    description = ParagraphDescription(runs=(run("Heading"),), paragraph_half_points=52)
    assert description.effective_half_points == 52


def test_an_outline_level_the_profile_has_no_threshold_for_is_left_alone(
    profile: StyleProfile,
) -> None:
    """Verbatim's Analytic sits at outline level 4, and no heuristic promotes that level."""
    result = classify_paragraph(
        paragraph(run("Their author concedes this.", bold=True, half_points=26), outline_level=4),
        profile,
    )
    assert result.unit is not StructuralUnit.TAG
    assert result.rule_id != "heuristic-outline-level-4"


def test_a_bold_line_with_no_size_at_all_is_not_promoted_to_a_heading(
    profile: StyleProfile,
) -> None:
    """Nothing says how big it is, so nothing says it is a heading."""
    result = classify_paragraph(paragraph(run("Contention one", bold=True)), profile)
    assert result.unit is StructuralUnit.OTHER


def test_a_block_sized_bold_line_without_an_underline_falls_through_to_the_tag_rule(
    profile: StyleProfile,
) -> None:
    """A block needs its underline at every level of the classifier, not only the outline rule."""
    result = classify_paragraph(paragraph(run("AT: Grid turn", bold=True, half_points=32)), profile)
    assert result.unit is StructuralUnit.TAG
    assert result.rule_id == "heuristic-direct-formatted-heading-tag"


def test_a_block_sized_bold_underlined_line_is_a_block(profile: StyleProfile) -> None:
    result = classify_paragraph(
        paragraph(run("AT: Grid turn", bold=True, half_points=32, underline="single")), profile
    )
    assert result.unit is StructuralUnit.BLOCK
    assert result.rule_id == "heuristic-direct-formatted-heading-block"


def test_a_bold_line_smaller_than_body_text_is_not_a_heading(profile: StyleProfile) -> None:
    result = classify_paragraph(paragraph(run("small print", bold=True, half_points=14)), profile)
    assert result.unit is not StructuralUnit.TAG


def test_prose_that_never_finishes_a_sentence_is_not_called_evidence(
    profile: StyleProfile,
) -> None:
    unfinished = (EVIDENCE_SENTENCE.rstrip(".") + " and ") * 2
    result = classify_paragraph(paragraph(run(unfinished, half_points=22)), profile)
    assert result.unit is StructuralUnit.OTHER
    assert result.rule_id == "heuristic-unclassified-paragraph"
