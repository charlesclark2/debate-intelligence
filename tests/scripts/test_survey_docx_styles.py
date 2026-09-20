"""Tests for `scripts/survey_docx_styles.py`, the style survey.

Each synthetic package here is one template family, built to the signature the survey keys on:
a Verbatim file that references Verbatim styles, the same file with CardMirror's `pmd-heading-`
bookmarks, a wiki-converted file that *defines* the Verbatim styles and references none of them,
and a file with neither — only outline levels, the way a Google Docs export arrives.

The privacy guard gets its own test: a style that appears in one file only is counted but never
named, because a one-off custom style is exactly where a team writes its own name.
"""

from __future__ import annotations

import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import survey_docx_styles as survey  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>
"""

#: The style set Verbatim writes, plus the two drifted ids real files pick up over a season.
VERBATIM_STYLE_DEFINITIONS = [
    ("Normal", "paragraph", "Normal", None),
    ("Heading1", "paragraph", "heading 1", "Normal"),
    ("Heading2", "paragraph", "heading 2", "Normal"),
    ("Heading3", "paragraph", "heading 3", "Normal"),
    ("Heading4", "paragraph", "heading 4", "Normal"),
    ("Analytic", "paragraph", "Analytic", "Normal"),
    ("Undertag", "paragraph", "Undertag", "Normal"),
    ("Style13ptBold", "character", "Style 13 pt Bold", "DefaultParagraphFont"),
    ("StyleUnderline", "character", "Style Underline", "DefaultParagraphFont"),
    ("Emphasis", "character", "Emphasis", "DefaultParagraphFont"),
]

DRIFTED_STYLE_DEFINITIONS = [
    ("Heading411", "paragraph", "heading 4 1 1", "Heading4"),
    ("Emphasis1", "character", "Emphasis1", "Emphasis"),
]


def styles_xml(definitions: list[tuple[str, str, str, str | None]]) -> str:
    entries = []
    for style_id, style_type, name, based_on in definitions:
        based = f'<w:basedOn w:val="{based_on}"/>' if based_on else ""
        entries.append(
            f'<w:style w:type="{style_type}" w:styleId="{style_id}"><w:name w:val="{name}"/>{based}</w:style>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W}">' + "".join(entries) + "</w:styles>"
    )


def verbatim_body(*, cardmirror_bookmarks: int = 0) -> str:
    bookmarks = "".join(
        f'<w:bookmarkStart w:id="{index}" w:name="pmd-heading-{index:08d}"/><w:bookmarkEnd w:id="{index}"/>'
        for index in range(cardmirror_bookmarks)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>'
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>{bookmarks}'
        "<w:r><w:t>Pocket</w:t></w:r></w:p>"
        '<w:p><w:pPr><w:pStyle w:val="Heading4"/></w:pPr><w:r><w:t>Tag</w:t></w:r></w:p>'
        '<w:p><w:r><w:rPr><w:rStyle w:val="Style13ptBold"/></w:rPr><w:t>Cite</w:t></w:r></w:p>'
        '<w:p><w:r><w:rPr><w:rStyle w:val="StyleUnderline"/>'
        '<w:highlight w:val="cyan"/></w:rPr><w:t>Evidence</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="Analytic"/></w:pPr><w:r><w:t>Analytic</w:t></w:r></w:p>'
        "</w:body></w:document>"
    )


def direct_formatted_body() -> str:
    """No style references at all: outline levels and direct bold, the way a wiki export arrives."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>'
        '<w:p><w:pPr><w:outlineLvl w:val="0"/></w:pPr>'
        '<w:r><w:rPr><w:b/><w:sz w:val="52"/></w:rPr><w:t>Pocket</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:outlineLvl w:val="3"/></w:pPr>'
        "<w:r><w:rPr><w:b/></w:rPr><w:t>Tag</w:t></w:r></w:p>"
        '<w:p><w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>Evidence</w:t></w:r></w:p>'
        "</w:body></w:document>"
    )


def write_docx(path: Path, *, styles: str, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/document.xml", body)
    return path


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A corpus with one file of every template family, laid out by category."""
    root = tmp_path / "corpus"
    write_docx(
        root / "team" / "verbatim.docx",
        styles=styles_xml(VERBATIM_STYLE_DEFINITIONS),
        body=verbatim_body(),
    )
    write_docx(
        root / "caselist" / "verbatim-through-cardmirror.docx",
        styles=styles_xml(VERBATIM_STYLE_DEFINITIONS),
        body=verbatim_body(cardmirror_bookmarks=3),
    )
    write_docx(
        root / "caselist" / "wiki-converted.docx",
        styles=styles_xml(VERBATIM_STYLE_DEFINITIONS),
        body=direct_formatted_body(),
    )
    write_docx(
        root / "caselist" / "google-docs-export.docx",
        styles=styles_xml([("Normal", "paragraph", "Normal", None)]),
        body=direct_formatted_body(),
    )
    return root


# --------------------------------------------------------------------------------------------
# Template families
# --------------------------------------------------------------------------------------------


def test_a_file_referencing_verbatim_paragraph_and_character_styles_is_a_verbatim_file(
    corpus: Path,
) -> None:
    usage = survey.read_file_usage(corpus / "team" / "verbatim.docx", "team")
    assert usage.template_family == "verbatim"
    assert usage.paragraph_style_references["Heading4"] == 1
    assert usage.character_style_references["StyleUnderline"] == 1
    assert usage.highlight_colors["cyan"] == 1


def test_cardmirror_heading_bookmarks_separate_cardmirror_from_plain_verbatim(corpus: Path) -> None:
    usage = survey.read_file_usage(corpus / "caselist" / "verbatim-through-cardmirror.docx", "caselist")
    assert usage.template_family == "cardmirror"
    assert usage.cardmirror_heading_bookmarks == 3


def test_verbatim_styles_defined_but_never_referenced_is_the_wiki_conversion_signature(
    corpus: Path,
) -> None:
    usage = survey.read_file_usage(corpus / "caselist" / "wiki-converted.docx", "caselist")
    assert usage.template_family == "wiki-converted"
    assert usage.paragraph_style_references == {}
    assert usage.outline_levels[0] == 1


def test_a_file_with_neither_verbatim_styles_nor_references_needs_the_heuristics(corpus: Path) -> None:
    usage = survey.read_file_usage(corpus / "caselist" / "google-docs-export.docx", "caselist")
    assert usage.template_family == "other-heuristic"


def test_an_unreadable_package_is_recorded_rather_than_raising(tmp_path: Path) -> None:
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a zip archive")
    usage = survey.read_file_usage(broken, "caselist")
    assert usage.template_family == "unreadable"
    assert usage.error == "BadZipFile"


# --------------------------------------------------------------------------------------------
# Walking a corpus and aggregating
# --------------------------------------------------------------------------------------------


def test_the_corpus_walk_takes_its_categories_from_the_top_level_directories(corpus: Path) -> None:
    categories = {category for _, category in survey.iter_corpus(corpus, "uncategorized")}
    assert categories == {"team", "caselist"}


def test_word_lock_files_are_skipped(corpus: Path) -> None:
    (corpus / "team" / "~$verbatim.docx").write_bytes(b"lock")
    paths = [path.name for path, _ in survey.iter_corpus(corpus, "uncategorized")]
    assert "~$verbatim.docx" not in paths


def test_a_missing_corpus_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(survey.SurveyError, match="corpus directory not found"):
        list(survey.iter_corpus(tmp_path / "absent", "uncategorized"))


def test_the_aggregate_counts_files_and_occurrences_separately(corpus: Path) -> None:
    aggregate = survey.survey_directory(corpus)
    assert aggregate.total_files == 4
    assert aggregate.files_by_category == {"team": 1, "caselist": 3}
    assert aggregate.families_by_category["caselist"]["cardmirror"] == 1
    assert aggregate.families_by_category["caselist"]["wiki-converted"] == 1
    assert aggregate.families_by_category["caselist"]["other-heuristic"] == 1
    # Heading1 is referenced once in each of the two files that use Verbatim styles.
    assert aggregate.paragraph_style_files["Heading1"] == 2
    assert aggregate.paragraph_style_occurrences["Heading1"] == 2


def test_based_on_links_to_verbatim_styles_are_recorded_as_alias_candidates(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    for index in range(2):
        write_docx(
            root / "team" / f"drifted-{index}.docx",
            styles=styles_xml(VERBATIM_STYLE_DEFINITIONS + DRIFTED_STYLE_DEFINITIONS),
            body=verbatim_body(),
        )
    aggregate = survey.survey_directory(root)
    assert aggregate.based_on_links[("Heading411", "Heading4")] == 2
    assert aggregate.based_on_links[("Emphasis1", "Emphasis")] == 2

    report = survey.render_report(aggregate, minimum_files=2)
    # Both are Word's numeric de-duplication of a style we already know, so both are named and
    # the report says what they resolve to.
    assert "| `Heading411` | `Heading4` | `heading4` | 2 |" in report
    assert "| `Emphasis1` | `Emphasis` | `emphasis` | 2 |" in report


# --------------------------------------------------------------------------------------------
# The report, and what it must not say
# --------------------------------------------------------------------------------------------


def test_the_report_records_the_share_of_files_per_template_family(corpus: Path) -> None:
    report = survey.render_report(
        survey.survey_directory(corpus), generated_at=datetime(2026, 9, 20, tzinfo=UTC)
    )
    assert "template family" in report
    assert "## Template families" in report
    assert "| caselist | 3 |" in report
    assert "2026-09-20" in report
    for family in survey.FAMILY_ORDER:
        assert family in report


def _corpus_with_custom_style(root: Path, file_count: int) -> Path:
    """A corpus where `file_count` files reference a style somebody named after their own team."""
    for index in range(file_count):
        write_docx(
            root / "team" / f"house-style-{index}.docx",
            styles=styles_xml(
                VERBATIM_STYLE_DEFINITIONS + [("NorthsideTag", "paragraph", "Northside Tag", "Heading4")]
            ),
            body=verbatim_body().replace('w:val="Heading4"', 'w:val="NorthsideTag"'),
        )
    write_docx(
        root / "team" / "ordinary.docx",
        styles=styles_xml(VERBATIM_STYLE_DEFINITIONS),
        body=verbatim_body(),
    )
    return root


def test_a_style_appearing_below_the_threshold_is_counted_but_never_named(tmp_path: Path) -> None:
    report = survey.render_report(
        survey.survey_directory(_corpus_with_custom_style(tmp_path / "corpus", 1)), minimum_files=2
    )
    assert "NorthsideTag" not in report
    assert "Northside" not in report
    assert "below the reporting threshold" in report
    assert "`Heading1`" in report, "published styles above the threshold are still named"


def test_a_widespread_style_somebody_named_themselves_is_counted_but_never_named(
    tmp_path: Path,
) -> None:
    """The threshold alone is not enough: `MaggieTag` is in 23 files of the real corpus."""
    report = survey.render_report(
        survey.survey_directory(_corpus_with_custom_style(tmp_path / "corpus", 5)), minimum_files=2
    )
    assert "NorthsideTag" not in report
    assert "Northside" not in report
    assert "custom or team-specific ids, not named" in report
    assert "`Heading1`" in report


def test_the_alias_section_counts_custom_ids_by_the_verbatim_style_they_inherit_from(
    tmp_path: Path,
) -> None:
    report = survey.render_report(
        survey.survey_directory(_corpus_with_custom_style(tmp_path / "corpus", 5)), minimum_files=2
    )
    assert "| `Heading4` | 1 | 5 |" in report, "one distinct custom id, seen in five files"
    assert "NorthsideTag" not in report


def test_the_report_carries_no_file_names_or_paths(corpus: Path) -> None:
    report = survey.render_report(survey.survey_directory(corpus))
    assert "verbatim.docx" not in report
    assert "google-docs-export" not in report
    assert str(corpus) not in report


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def test_the_command_line_writes_the_report_and_the_json_aggregate(
    corpus: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = tmp_path / "report" / "debate-file-style-survey.md"
    json_path = tmp_path / "report" / "survey.json"

    exit_code = survey.main(
        [
            "--input",
            str(corpus),
            "--output",
            str(report_path),
            "--json",
            str(json_path),
            "--corpus-description",
            "four synthetic files",
        ]
    )

    assert exit_code == 0
    assert "template family" in report_path.read_text(encoding="utf-8")
    assert "four synthetic files" in report_path.read_text(encoding="utf-8")
    aggregate = json.loads(json_path.read_text(encoding="utf-8"))
    assert aggregate["total_files"] == 4
    assert aggregate["cardmirror_files"] == 1
    captured = capsys.readouterr()
    assert "surveyed 4 files" in captured.out
    assert "verbatim.docx" not in captured.out


def test_the_command_line_reports_an_empty_corpus(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    exit_code = survey.main(["--input", str(empty), "--output", str(tmp_path / "report.md")])
    assert exit_code == 1
    assert "no .docx files found" in capsys.readouterr().err


def test_several_directories_can_be_surveyed_under_one_category(corpus: Path) -> None:
    aggregate = survey.survey_inputs(
        [f"season={corpus / 'team'}", f"season={corpus / 'caselist'}"],
    )
    assert aggregate.files_by_category == {"season": 4}


def test_a_file_reachable_from_two_inputs_is_counted_once(corpus: Path) -> None:
    aggregate = survey.survey_inputs([str(corpus), f"team={corpus / 'team'}"])
    assert aggregate.total_files == 4
    assert aggregate.files_by_category["team"] == 1


def test_an_over_long_style_id_is_elided_in_the_middle() -> None:
    mangled = "StyleHeading1Heading1Char1ALEXHeadingHeading1CharChar"
    elided = survey.elide_style_id(mangled)
    assert "ALEX" not in elided
    assert elided.startswith("StyleHeading1Heading")
    assert elided.endswith("ing1CharChar")
    assert survey.elide_style_id("Heading4") == "Heading4"


def test_a_word_concatenated_style_id_reaches_the_report_neither_whole_nor_in_part(
    tmp_path: Path,
) -> None:
    """Word's concatenated ids are where a first name hides; this one is not published vocabulary."""
    mangled = "StyleHeading1Heading1Char1ALEXHeadingHeading1CharChar"
    root = tmp_path / "corpus"
    for index in range(2):
        write_docx(
            root / "team" / f"drifted-{index}.docx",
            styles=styles_xml(VERBATIM_STYLE_DEFINITIONS + [(mangled, "paragraph", mangled, "Heading1")]),
            body=verbatim_body().replace('w:val="Heading1"', f'w:val="{mangled}"'),
        )
    report = survey.render_report(survey.survey_directory(root), minimum_files=2)
    assert mangled not in report
    assert "ALEX" not in report
    assert "custom or team-specific ids, not named" in report
