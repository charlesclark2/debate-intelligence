"""Tests for `scripts/compare_docx_roundtrip.py`, the CardMirror round-trip comparison.

Every document here is synthesized in-process from raw WordprocessingML, so the suite is
offline, fast, and carries no real debate evidence into the repository. The synthetic
files use the same style ids Verbatim, Advanced Verbatim and CardMirror write
(`Heading1`-`Heading4`, `Analytic`, `Undertag`, `Style13ptBold`, `StyleUnderline`), so
the assertions are about the comparison logic, not about a fixture's quirks.
"""

from __future__ import annotations

import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import compare_docx_roundtrip as comparison  # noqa: E402

# --------------------------------------------------------------------------------------
# A minimal .docx writer. Only what these tests exercise: paragraph styles, outline
# levels, runs, and the run properties the comparison reads.
# --------------------------------------------------------------------------------------

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>
"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
    Target="styles.xml"/>
</Relationships>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
</w:styles>
"""


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool | None = None
    underline: str | None = None
    highlight: str | None = None
    size_half_points: int | None = None
    character_style: str | None = None

    def to_xml(self) -> str:
        properties: list[str] = []
        if self.character_style is not None:
            properties.append(f'<w:rStyle w:val="{self.character_style}"/>')
        if self.bold is not None:
            properties.append("<w:b/>" if self.bold else '<w:b w:val="0"/>')
        if self.underline is not None:
            properties.append(f'<w:u w:val="{self.underline}"/>')
        if self.highlight is not None:
            properties.append(f'<w:highlight w:val="{self.highlight}"/>')
        if self.size_half_points is not None:
            properties.append(f'<w:sz w:val="{self.size_half_points}"/>')
        run_properties = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
        return f'{"<w:r>"}{run_properties}<w:t xml:space="preserve">{self.text}</w:t></w:r>'


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Run, ...] = ()
    style: str | None = None
    outline_level: int | None = None
    deleted_runs: tuple[Run, ...] = ()

    def to_xml(self) -> str:
        properties: list[str] = []
        if self.style is not None:
            properties.append(f'<w:pStyle w:val="{self.style}"/>')
        if self.outline_level is not None:
            properties.append(f'<w:outlineLvl w:val="{self.outline_level}"/>')
        paragraph_properties = f"<w:pPr>{''.join(properties)}</w:pPr>" if properties else ""
        body = "".join(run.to_xml() for run in self.runs)
        if self.deleted_runs:
            body += "<w:del>" + "".join(run.to_xml() for run in self.deleted_runs) + "</w:del>"
        return f"<w:p>{paragraph_properties}{body}</w:p>"


def write_docx(path: Path, paragraphs: list[Paragraph]) -> Path:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(paragraph.to_xml() for paragraph in paragraphs) + "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        archive.writestr("word/styles.xml", STYLES)
        archive.writestr("word/document.xml", document)
    return path


def a_card(tag_text: str = "Warming is real", body_text: str = "Temperatures rose.") -> list[Paragraph]:
    """A conventional Verbatim card: pocket, hat, block, tag, cite, body."""
    return [
        Paragraph((Run("Warming Advantage"),), style="Heading1"),
        Paragraph((Run("1AC"),), style="Heading2"),
        Paragraph((Run("Uniqueness"),), style="Heading3"),
        Paragraph((Run(tag_text, underline="single"),), style="Heading4"),
        Paragraph((Run("Smith 24", character_style="Style13ptBold"), Run(" (journal)"))),
        Paragraph(
            (
                Run("Lead-in. "),
                Run(body_text, character_style="StyleUnderline", highlight="yellow"),
                Run(" Trailing."),
            )
        ),
    ]


# --------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------


def test_identical_document_has_no_differences(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card())
    roundtripped = write_docx(tmp_path / "roundtripped.docx", a_card())

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"
    assert result.differences == []
    assert result.original_paragraphs == result.roundtripped_paragraphs == 6


def test_resplit_runs_with_the_same_formatting_stay_clean(tmp_path: Path) -> None:
    """Editors split and merge runs freely; only the formatted character range matters."""
    original = write_docx(
        tmp_path / "original.docx",
        [Paragraph((Run("Lead-in. "), Run("Underlined body text.", underline="single")))],
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx",
        [
            Paragraph(
                (
                    Run("Lead-"),
                    Run("in. "),
                    Run("Underlined ", underline="single"),
                    Run("body text.", underline="single"),
                )
            )
        ],
    )

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"


def test_dropped_highlight_is_reported_as_a_highlight_span(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card())
    lost_highlight = a_card()
    lost_highlight[5] = Paragraph(
        (
            Run("Lead-in. "),
            Run("Temperatures rose.", character_style="StyleUnderline"),
            Run(" Trailing."),
        )
    )
    roundtripped = write_docx(tmp_path / "roundtripped.docx", lost_highlight)

    result = comparison.compare_file(original, roundtripped, "caselist")

    assert result.status == "differences"
    categories = [difference.category for difference in result.differences]
    assert categories == ["highlight_span"]
    detail = result.differences[0].detail
    assert detail["original"] == [[9, 27, "yellow"]]
    assert detail["roundtripped"] == []


def test_changed_heading_level_is_reported_as_a_structural_unit(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card())
    demoted = a_card()
    demoted[1] = Paragraph((Run("1AC"),), style="Heading3")
    roundtripped = write_docx(tmp_path / "roundtripped.docx", demoted)

    result = comparison.compare_file(original, roundtripped, "caselist")

    differences = [d for d in result.differences if d.category == "structural_unit"]
    assert len(differences) == 1
    assert differences[0].detail == {"original": "hat", "roundtripped": "block"}


def test_changed_paragraph_text_is_reported_without_quoting_the_text(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card(body_text="Temperatures rose sharply."))
    roundtripped = write_docx(tmp_path / "roundtripped.docx", a_card(body_text="Temperatures rose slowly."))

    result = comparison.compare_file(original, roundtripped, "camp")

    differences = [d for d in result.differences if d.category == "paragraph_text"]
    assert len(differences) == 1
    detail = differences[0].detail
    assert set(detail) == {"originalLength", "roundtrippedLength", "firstDifferingOffset"}
    assert "sharply" not in json.dumps(detail)


def test_lost_cite_styling_is_reported(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card())
    lost_cite = a_card()
    lost_cite[4] = Paragraph((Run("Smith 24"), Run(" (journal)")))
    roundtripped = write_docx(tmp_path / "roundtripped.docx", lost_cite)

    result = comparison.compare_file(original, roundtripped, "caselist")

    categories = {difference.category for difference in result.differences}
    assert "cite_span" in categories
    # The cite character style also carries bold, so the bold coverage changes with it.
    assert "bold_span" in categories


def test_underline_encoding_swap_is_a_normalization_not_a_difference(tmp_path: Path) -> None:
    """CardMirror rewrites a named-style underline in a structural slot as a direct
    `w:u` (and the reverse in body slots). The underlined range is unchanged, so the
    swap is recorded as a normalization."""
    original = write_docx(
        tmp_path / "original.docx",
        [Paragraph((Run("Warming is real", character_style="StyleUnderline"),), style="Heading4")],
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx",
        [Paragraph((Run("Warming is real", underline="single"),), style="Heading4")],
    )

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"
    assert [note.category for note in result.normalizations] == ["underline_encoding_changed"]


def test_removed_paragraph_keeps_the_rest_aligned(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card())
    without_block = [paragraph for index, paragraph in enumerate(a_card()) if index != 2]
    roundtripped = write_docx(tmp_path / "roundtripped.docx", without_block)

    result = comparison.compare_file(original, roundtripped, "caselist-non-verbatim")

    categories = [difference.category for difference in result.differences]
    assert categories == ["paragraph_removed"]
    assert result.differences[0].detail == {"structuralUnit": "block"}


def test_empty_body_paragraphs_are_ignored_but_empty_headings_are_kept(tmp_path: Path) -> None:
    with_spacers = [
        Paragraph((Run(""),), style="Heading1"),
        Paragraph(),
        Paragraph((Run("Body."),)),
        Paragraph(),
    ]
    without_spacers = [
        Paragraph((Run(""),), style="Heading1"),
        Paragraph((Run("Body."),)),
    ]
    original = write_docx(tmp_path / "original.docx", with_spacers)
    roundtripped = write_docx(tmp_path / "roundtripped.docx", without_spacers)

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"
    assert result.original_paragraphs == 2


def test_outline_level_classifies_a_file_with_no_verbatim_styles(tmp_path: Path) -> None:
    """Wiki-converted and Google Docs exports often carry outline levels but no
    Heading style ids."""
    paragraphs = [
        Paragraph((Run("Warming Advantage"),), outline_level=0),
        Paragraph((Run("Body."),)),
    ]
    path = write_docx(tmp_path / "wiki.docx", paragraphs)

    snapshots = comparison.read_paragraphs(path)

    assert [snapshot.structural_unit for snapshot in snapshots] == ["pocket", "body"]


def test_redundant_bold_on_a_tag_is_not_a_difference(tmp_path: Path) -> None:
    """Tags are bold by definition; dropping an explicit `<w:b/>` changes nothing."""
    original = write_docx(
        tmp_path / "original.docx", [Paragraph((Run("Warming is real", bold=True),), style="Heading4")]
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx", [Paragraph((Run("Warming is real"),), style="Heading4")]
    )

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"


def test_bold_turned_off_in_a_tag_is_a_difference(tmp_path: Path) -> None:
    original = write_docx(
        tmp_path / "original.docx", [Paragraph((Run("Warming is real"),), style="Heading4")]
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx",
        [Paragraph((Run("Warming is real", bold=False),), style="Heading4")],
    )

    result = comparison.compare_file(original, roundtripped, "team")

    assert [difference.category for difference in result.differences] == ["bold_span"]


def test_deleted_revision_runs_are_ignored_on_both_sides(tmp_path: Path) -> None:
    """Word keeps tracked deletions in the file; CardMirror drops them on import."""
    original = write_docx(
        tmp_path / "original.docx",
        [Paragraph((Run("Kept text."),), deleted_runs=(Run("Struck text."),))],
    )
    roundtripped = write_docx(tmp_path / "roundtripped.docx", [Paragraph((Run("Kept text."),))])

    result = comparison.compare_file(original, roundtripped, "camp")

    assert result.status == "clean"


def test_summary_keys_files_by_sha256_prefix_and_holds_no_document_text(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card(tag_text="Nuclear war is unlikely"))
    changed = a_card(tag_text="Nuclear war is unlikely")
    changed[3] = Paragraph((Run("Nuclear war is unlikely"),), style="Heading4")
    roundtripped = write_docx(tmp_path / "roundtripped.docx", changed)

    result = comparison.compare_file(original, roundtripped, "caselist-wiki")
    summary = comparison.summarize([result], cardmirror_commit="bc92e6b")
    rendered = json.dumps(summary)

    assert summary["files"][0]["sha256Prefix"] == comparison.sha256_prefix(original)
    assert len(summary["files"][0]["sha256Prefix"]) == 8
    assert summary["categories"]["caselist-wiki"]["withDifferences"] == 1
    assert summary["cardmirrorCommit"] == "bc92e6b"
    for document_text in ("Nuclear", "Warming", "Smith", "original.docx", str(tmp_path)):
        assert document_text not in rendered


def test_summary_counts_clean_and_error_files_separately(tmp_path: Path) -> None:
    clean = comparison.compare_file(
        write_docx(tmp_path / "a.docx", a_card()), write_docx(tmp_path / "b.docx", a_card()), "team"
    )
    broken_path = tmp_path / "broken.docx"
    broken_path.write_bytes(b"not a zip archive")
    broken = comparison.compare_file(broken_path, broken_path, "team")

    summary = comparison.summarize([clean, broken])

    assert summary["totals"] == {"files": 2, "clean": 1, "withDifferences": 0, "errors": 1}
    assert broken.status == "error"
    assert broken.error is not None


def test_cli_compares_a_single_pair_and_writes_the_summary(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", a_card())
    roundtripped = write_docx(tmp_path / "roundtripped.docx", a_card())
    output = tmp_path / "summary.json"

    exit_code = comparison.main(
        [
            "--pair",
            str(original),
            str(roundtripped),
            "--category",
            "team",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    summary = json.loads(output.read_text())
    assert summary["totals"]["clean"] == 1
    assert summary["categories"]["team"]["files"] == 1


def test_cli_reads_a_roundtrip_manifest(tmp_path: Path) -> None:
    write_docx(tmp_path / "original.docx", a_card())
    write_docx(tmp_path / "original.roundtripped.docx", a_card())
    manifest = tmp_path / "roundtrip-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cardmirrorCommit": "bc92e6b",
                "files": [
                    {
                        "status": "ok",
                        "fileCategory": "camp",
                        "originalPath": "original.docx",
                        "roundtrippedPath": "original.roundtripped.docx",
                    },
                    {"status": "failed", "fileCategory": "camp"},
                ],
            }
        )
    )
    output = tmp_path / "summary.json"

    assert comparison.main(["--manifest", str(manifest), "--output", str(output)]) == 0

    summary = json.loads(output.read_text())
    assert summary["totals"]["files"] == 1
    assert summary["cardmirrorCommit"] == "bc92e6b"


@pytest.mark.parametrize(
    ("style_id", "expected"),
    [
        ("Heading1", "pocket"),
        ("Heading 2", "hat"),
        ("heading-3", "block"),
        ("Heading4", "tag"),
        ("Analytic", "analytic"),
        ("Undertag", "undertag"),
        ("BodyText", "body"),
        (None, "body"),
    ],
)
def test_style_ids_map_to_structural_units(style_id: str | None, expected: str) -> None:
    assert comparison.structural_unit_for(style_id, None) == expected


def test_named_plus_direct_underline_is_its_own_encoding(tmp_path: Path) -> None:
    """CardMirror's exporter writes `StyleUnderline` *and* a direct `<w:u>` on body
    runs. That is a third encoding, not the named style and not the direct one."""
    original = write_docx(
        tmp_path / "original.docx",
        [Paragraph((Run("Body text.", character_style="StyleUnderline"),))],
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx",
        [Paragraph((Run("Body text.", character_style="StyleUnderline", underline="single"),))],
    )

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"
    note = result.normalizations[0]
    assert note.category == "underline_encoding_changed"
    assert note.detail["original"] == [[0, 10, "named_style"]]
    assert note.detail["roundtripped"] == [[0, 10, "both"]]


def test_dropped_soft_hyphens_are_a_normalization_not_a_text_difference(tmp_path: Path) -> None:
    """CardMirror drops U+00AD on import. The visible text is unchanged, so this is
    counted and reported, not treated as evidence loss."""
    original = write_docx(
        tmp_path / "original.docx",
        [Paragraph((Run("Inter­national secur­ity guarantees."),))],
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx",
        [Paragraph((Run("International security guarantees."),))],
    )

    result = comparison.compare_file(original, roundtripped, "team")

    assert result.status == "clean"
    assert [note.category for note in result.normalizations] == ["soft_hyphens_dropped"]
    assert result.normalizations[0].detail == {"original": 2, "roundtripped": 0}


def test_dropped_soft_hyphens_do_not_shift_formatting_spans(tmp_path: Path) -> None:
    """Stripping U+00AD from both sides keeps character offsets comparable, so an
    underlined range that contains a soft hyphen still lines up."""
    original = write_docx(
        tmp_path / "original.docx",
        [
            Paragraph(
                (
                    Run("Lead-in. "),
                    Run("Inter­national law", underline="single"),
                    Run(" Trailing."),
                )
            )
        ],
    )
    roundtripped = write_docx(
        tmp_path / "roundtripped.docx",
        [Paragraph((Run("Lead-in. "), Run("International law", underline="single"), Run(" Trailing.")))],
    )

    result = comparison.compare_file(original, roundtripped, "caselist")

    assert result.differences == []
    snapshots = comparison.read_paragraphs(original)
    assert snapshots[0].spans("underline") == ((9, 26, True),)


def test_a_soft_hyphen_and_a_real_text_change_are_reported_separately(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", [Paragraph((Run("Inter­national law."),))])
    roundtripped = write_docx(tmp_path / "roundtripped.docx", [Paragraph((Run("International lw."),))])

    result = comparison.compare_file(original, roundtripped, "camp")

    assert [d.category for d in result.differences] == ["paragraph_text"]
    assert [n.category for n in result.normalizations] == ["soft_hyphens_dropped"]


def test_summary_counts_normalizations_by_category(tmp_path: Path) -> None:
    original = write_docx(tmp_path / "original.docx", [Paragraph((Run("Inter­national law."),))])
    roundtripped = write_docx(tmp_path / "roundtripped.docx", [Paragraph((Run("International law."),))])

    result = comparison.compare_file(original, roundtripped, "team")
    summary = comparison.summarize([result])

    assert summary["totals"]["clean"] == 1
    assert summary["categories"]["team"]["normalizationsByCategory"] == {"soft_hyphens_dropped": 1}
    assert summary["categories"]["team"]["differencesByCategory"] == {}
