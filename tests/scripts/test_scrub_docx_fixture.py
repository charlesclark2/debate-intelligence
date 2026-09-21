"""Tests for `scripts/scrub_docx_fixture.py`, the fixture scrub gate.

Every document here is synthesized in-process from raw WordprocessingML, so the suite is offline,
fast, and carries no real debate evidence into the repository. The synthetic package deliberately
hides the seeded name in all six places a real Word file hides one: visible paragraph text, text
Word split across runs, a tracked-change author attribute, a comment thread, `docProps` metadata,
and the bytes of an embedded image.

The headline test is the one the task's acceptance criterion names: after a scrub, the seeded name
appears nowhere in the output package.
"""

from __future__ import annotations

import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scrub_docx_fixture as scrub  # noqa: E402

# The name and team code seeded into every synthetic package, and what the replacement list turns
# them into. Both are invented: no student is called either thing.
SEEDED_NAME = "Jamie Okafor"
SEEDED_TEAM_CODE = "WFB"
REPLACEMENT_NAME = "Rowan Fields"
REPLACEMENT_TEAM_CODE = "Northside"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/comments.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
  <Override PartName="/word/commentsExtended.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"/>
  <Override PartName="/word/people.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.people+xml"/>
  <Override PartName="/customXml/item1.xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml"
    ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml"
    ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/custom.xml"
    ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
</Types>
"""

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    Target="docProps/core.xml"/>
  <Relationship Id="rId3"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extendedProperties"
    Target="docProps/app.xml"/>
  <Relationship Id="rId4"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customProperties"
    Target="docProps/custom.xml"/>
  <Relationship Id="rId5"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
    Target="customXml/item1.xml"/>
</Relationships>
"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
    Target="styles.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
    Target="comments.xml"/>
  <Relationship Id="rId3"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/people"
    Target="people.xml"/>
  <Relationship Id="rId4"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
    Target="media/image1.png"/>
</Relationships>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/></w:style>
</w:styles>
"""

CORE_PROPERTIES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
  xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{SEEDED_TEAM_CODE} Neg File</dc:title>
  <dc:creator>{SEEDED_NAME}</dc:creator>
  <cp:lastModifiedBy>{SEEDED_NAME}</cp:lastModifiedBy>
  <cp:keywords>{SEEDED_TEAM_CODE}</cp:keywords>
  <cp:lastPrinted>2026-01-14T18:00:00Z</cp:lastPrinted>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-01-02T12:00:00Z</dcterms:created>
</cp:coreProperties>
"""

APP_PROPERTIES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties
  xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Office Word</Application>
  <Company>{SEEDED_TEAM_CODE} Debate</Company>
  <Manager>{SEEDED_NAME}</Manager>
  <Template>C:\\Users\\{SEEDED_NAME}\\AppData\\Verbatim.dotm</Template>
</Properties>
"""

CUSTOM_PROPERTIES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <property fmtid="{{D5CDD505-2E9C-101B-9397-08002B2CF9AE}}" pid="2" name="Debater">
    <vt:lpwstr>{SEEDED_NAME}</vt:lpwstr>
  </property>
</Properties>
"""

CUSTOM_XML_ITEM = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<roster xmlns="urn:school:roster"><debater>{SEEDED_NAME}</debater></roster>
"""

COMMENTS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="{W}">
  <w:comment w:id="1" w:author="{SEEDED_NAME}" w:initials="JO" w:date="2026-01-03T09:00:00Z">
    <w:p><w:r><w:t>Re-cut this card before the next tournament.</w:t></w:r></w:p>
  </w:comment>
</w:comments>
"""

COMMENTS_EXTENDED = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
  <w15:commentEx w15:paraId="00000001" w15:done="0"/>
</w15:commentsEx>
"""

PEOPLE = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w15:people xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
  <w15:person w15:author="{SEEDED_NAME}">
    <w15:presenceInfo w15:providerId="None" w15:userId="{SEEDED_NAME}"/>
  </w15:person>
</w15:people>
"""

# A stand-in for an embedded image: a binary part that must be copied through untouched. The
# test that seeds a name into one of these lives further down.
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"tEXtSoftware" + b"Microsoft Office" + b"\x00\x00"


@dataclass(frozen=True)
class Run:
    """One `w:r`, with just enough run properties to prove formatting survives a replacement."""

    text: str
    bold: bool = False
    underline: bool = False
    character_style: str | None = None

    def to_xml(self) -> str:
        properties: list[str] = []
        if self.character_style is not None:
            properties.append(f'<w:rStyle w:val="{self.character_style}"/>')
        if self.bold:
            properties.append("<w:b/>")
        if self.underline:
            properties.append('<w:u w:val="single"/>')
        run_properties = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
        return f'<w:r>{run_properties}<w:t xml:space="preserve">{self.text}</w:t></w:r>'


def paragraph_xml(runs: list[Run], style: str | None = None, extra: str = "") -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{properties}{''.join(run.to_xml() for run in runs)}{extra}</w:p>"


def build_document_xml() -> str:
    """A body that hides the seeded name in text, in split runs, in a tracked change and a comment."""
    tag_paragraph = paragraph_xml(
        [Run(f"{SEEDED_TEAM_CODE} Neg — prepared by ", underline=True), Run(SEEDED_NAME, bold=True)],
        style="Heading4",
    )
    # The same name, split across three runs the way Word splits one after a spell-check pass.
    split_paragraph = paragraph_xml(
        [
            Run("Cut by ", underline=True),
            Run("Jam", bold=True),
            Run("ie Okafor", bold=True),
            Run(" during camp.", character_style="Emphasis"),
        ]
    )
    # A non-breaking space between the given and family name: the same person, different bytes.
    nonbreaking_paragraph = paragraph_xml([Run("Contact Jamie\u00a0Okafor for the block.")])
    tracked_paragraph = (
        "<w:p>"
        f'<w:ins w:id="7" w:author="{SEEDED_NAME}" w:date="2026-02-01T10:00:00Z">'
        "<w:r><w:t>Newly inserted warrant. </w:t></w:r></w:ins>"
        f'<w:del w:id="8" w:author="{SEEDED_NAME}" w:date="2026-02-01T10:05:00Z">'
        "<w:r><w:delText>Struck sentence.</w:delText></w:r></w:del>"
        "</w:p>"
    )
    commented_paragraph = (
        "<w:p>"
        '<w:commentRangeStart w:id="1"/>'
        "<w:r><w:t>Evidence paragraph under review.</w:t></w:r>"
        '<w:commentRangeEnd w:id="1"/>'
        '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="1"/></w:r>'
        "</w:p>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>'
        + tag_paragraph
        + split_paragraph
        + nonbreaking_paragraph
        + tracked_paragraph
        + commented_paragraph
        + "</w:body></w:document>"
    )


def write_seeded_docx(path: Path) -> Path:
    """Write the synthetic package every test in this module starts from."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        archive.writestr("word/document.xml", build_document_xml())
        archive.writestr("word/styles.xml", STYLES)
        archive.writestr("word/comments.xml", COMMENTS)
        archive.writestr("word/commentsExtended.xml", COMMENTS_EXTENDED)
        archive.writestr("word/people.xml", PEOPLE)
        archive.writestr("word/media/image1.png", IMAGE_BYTES)
        archive.writestr("customXml/item1.xml", CUSTOM_XML_ITEM)
        archive.writestr("docProps/core.xml", CORE_PROPERTIES)
        archive.writestr("docProps/app.xml", APP_PROPERTIES)
        archive.writestr("docProps/custom.xml", CUSTOM_PROPERTIES)
    return path


def write_replacement_list(path: Path) -> Path:
    path.write_text(
        "version: 1\n"
        "replacements:\n"
        f"  - find: {SEEDED_NAME}\n"
        f"    replace: {REPLACEMENT_NAME}\n"
        f"  - find: {SEEDED_TEAM_CODE}\n"
        f"    replace: {REPLACEMENT_TEAM_CODE}\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def seeded_docx(tmp_path: Path) -> Path:
    return write_seeded_docx(tmp_path / "team-file.docx")


@pytest.fixture
def replacements(tmp_path: Path) -> scrub.ReplacementList:
    return scrub.load_replacement_list(write_replacement_list(tmp_path / "replacements.yaml"))


def part_names(package: Path) -> set[str]:
    with zipfile.ZipFile(package) as archive:
        return {info.filename for info in archive.infolist() if not info.is_dir()}


def part_text(package: Path, name: str) -> str:
    with zipfile.ZipFile(package) as archive:
        return archive.read(name).decode("utf-8")


def package_text(package: Path) -> str:
    """Every part of the package as one string, with XML tags stripped and whitespace collapsed."""
    with zipfile.ZipFile(package) as archive:
        parts = [archive.read(info.filename) for info in archive.infolist() if not info.is_dir()]
    return " ".join(scrub._readable_text(data) for data in parts)


# --------------------------------------------------------------------------------------------
# The acceptance criterion: a seeded name does not survive anywhere in the output package
# --------------------------------------------------------------------------------------------


def test_seeded_name_and_team_code_appear_nowhere_in_the_scrubbed_package(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    scrub.scrub_package(seeded_docx, output, replacements)

    with zipfile.ZipFile(output) as archive:
        for info in archive.infolist():
            raw = archive.read(info.filename)
            decoded = raw.decode("utf-8", errors="ignore")
            readable = scrub._readable_text(raw)
            for seeded in (SEEDED_NAME, SEEDED_TEAM_CODE):
                assert seeded.lower() not in decoded.lower(), f"{seeded!r} survives in {info.filename}"
                assert seeded.lower() not in readable.lower(), f"{seeded!r} survives in {info.filename}"
                assert seeded.lower() not in info.filename.lower()
    assert scrub.verify_scrubbed(output, replacements) == []


def test_the_seeded_package_really_does_contain_the_name_before_scrubbing(seeded_docx: Path) -> None:
    """Guards the test above: a scrub of an already-clean file would prove nothing."""
    assert SEEDED_NAME.lower() in package_text(seeded_docx).lower()
    assert SEEDED_TEAM_CODE.lower() in package_text(seeded_docx).lower()


# --------------------------------------------------------------------------------------------
# Parts, relationships and content types
# --------------------------------------------------------------------------------------------


def test_identity_parts_and_their_relationships_are_dropped(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    result = scrub.scrub_package(seeded_docx, output, replacements)

    names = part_names(output)
    for dropped in (
        "word/comments.xml",
        "word/commentsExtended.xml",
        "word/people.xml",
        "customXml/item1.xml",
        "docProps/custom.xml",
    ):
        assert dropped not in names
        assert dropped in result.dropped_parts
    assert "word/document.xml" in names
    assert "word/styles.xml" in names
    assert "word/media/image1.png" in names

    document_rels = part_text(output, "word/_rels/document.xml.rels")
    assert "comments.xml" not in document_rels
    assert "people.xml" not in document_rels
    assert "styles.xml" in document_rels
    assert "media/image1.png" in document_rels

    package_rels = part_text(output, "_rels/.rels")
    assert "docProps/custom.xml" not in package_rels
    assert "customXml/item1.xml" not in package_rels
    assert "docProps/core.xml" in package_rels

    content_types = part_text(output, "[Content_Types].xml")
    assert "/word/comments.xml" not in content_types
    assert "/customXml/item1.xml" not in content_types
    assert "/word/document.xml" in content_types


def test_comment_markup_is_removed_from_the_body(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    result = scrub.scrub_package(seeded_docx, output, replacements)

    document = part_text(output, "word/document.xml")
    assert "commentRangeStart" not in document
    assert "commentRangeEnd" not in document
    assert "commentReference" not in document
    assert "Evidence paragraph under review." in document
    assert result.removed_comment_elements == 3


# --------------------------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------------------------


def test_document_properties_are_blanked_but_the_parts_remain_valid(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    scrub.scrub_package(seeded_docx, output, replacements)

    core = part_text(output, "docProps/core.xml")
    assert "<dc:creator/>" in core or "<dc:creator></dc:creator>" in core
    assert "lastModifiedBy/>" in core or "lastModifiedBy></cp:lastModifiedBy>" in core
    assert "lastPrinted" not in core
    assert "dcterms:created" in core, "creation timestamps are not identity and are kept"

    app = part_text(output, "docProps/app.xml")
    assert "Verbatim.dotm" not in app, "the template path carries a Windows user name"
    assert "Microsoft Office Word" in app


def test_tracked_change_authors_are_redacted_and_their_dates_dropped(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    result = scrub.scrub_package(seeded_docx, output, replacements)

    document = part_text(output, "word/document.xml")
    assert f'w:author="{scrub.REDACTED_AUTHOR}"' in document
    assert "w:date=" not in document
    assert "Newly inserted warrant." in document, "the revision itself is preserved; only its author goes"
    assert result.redacted_author_attributes == 2
    assert result.dropped_identity_attributes == 2


# --------------------------------------------------------------------------------------------
# Replacement across runs, and the formatting it must not disturb
# --------------------------------------------------------------------------------------------


def test_a_name_split_across_runs_is_replaced_and_neighbouring_runs_keep_their_formatting(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    scrub.scrub_package(seeded_docx, output, replacements)

    document = part_text(output, "word/document.xml")
    assert REPLACEMENT_NAME in document
    assert "Jam" not in document
    # The runs that do not overlap the match are untouched, formatting and all.
    assert "Cut by " in document
    assert " during camp." in document
    assert '<w:rStyle w:val="Emphasis"/>' in document
    assert '<w:u w:val="single"/>' in document


def test_a_name_separated_by_a_non_breaking_space_is_replaced(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    output = tmp_path / "scrubbed.docx"
    scrub.scrub_package(seeded_docx, output, replacements)

    document = part_text(output, "word/document.xml")
    assert "Okafor" not in document
    assert f"Contact {REPLACEMENT_NAME} for the block." in document


def test_scrubbing_is_deterministic_and_a_second_pass_changes_nothing(
    seeded_docx: Path, replacements: scrub.ReplacementList, tmp_path: Path
) -> None:
    first = tmp_path / "first.docx"
    second = tmp_path / "second.docx"
    scrub.scrub_package(seeded_docx, first, replacements)
    scrub.scrub_package(seeded_docx, second, replacements)
    assert part_text(first, "word/document.xml") == part_text(second, "word/document.xml")

    rescrubbed = tmp_path / "rescrubbed.docx"
    scrub.scrub_package(first, rescrubbed, replacements)
    assert part_text(rescrubbed, "word/document.xml") == part_text(first, "word/document.xml")


# --------------------------------------------------------------------------------------------
# Failing loudly
# --------------------------------------------------------------------------------------------


def test_a_name_surviving_in_a_binary_part_fails_the_scrub_and_deletes_the_output(
    tmp_path: Path, replacements: scrub.ReplacementList
) -> None:
    source = write_seeded_docx(tmp_path / "with-image.docx")
    output = tmp_path / "scrubbed.docx"

    # Word writes an author name into a PNG `tEXt` chunk. Nothing in the XML scrub touches binary
    # parts, so verification is what has to catch it — loudly, rather than quietly shipping it.
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr(
            "word/media/image2.png", b"\x89PNG\r\n\x1a\ntEXtAuthor" + SEEDED_NAME.encode("utf-8")
        )

    with pytest.raises(scrub.ScrubError, match="verification"):
        scrub.scrub_package(source, output, replacements)
    assert not output.exists(), "a half-scrubbed file must never be left behind"


def test_an_unreadable_package_is_reported_rather_than_partially_scrubbed(
    tmp_path: Path, replacements: scrub.ReplacementList
) -> None:
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a zip archive")
    with pytest.raises(scrub.ScrubError, match="not a readable .docx"):
        scrub.scrub_package(broken, tmp_path / "out.docx", replacements)


def test_a_missing_input_is_reported(tmp_path: Path, replacements: scrub.ReplacementList) -> None:
    with pytest.raises(scrub.ScrubError, match="input file not found"):
        scrub.scrub_package(tmp_path / "absent.docx", tmp_path / "out.docx", replacements)


def test_verify_scrubbed_names_every_survivor(seeded_docx: Path, replacements: scrub.ReplacementList) -> None:
    violations = scrub.verify_scrubbed(seeded_docx, replacements)
    assert any(SEEDED_NAME in violation for violation in violations)
    assert any("should have been dropped" in violation for violation in violations)


# --------------------------------------------------------------------------------------------
# The replacement list
# --------------------------------------------------------------------------------------------


def test_a_missing_replacement_list_says_where_to_keep_one(tmp_path: Path) -> None:
    with pytest.raises(scrub.ScrubError, match="outside the repository"):
        scrub.load_replacement_list(tmp_path / "absent.yaml")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("version: 2\nreplacements: [{find: a, replace: b}]\n", "version"),
        ("version: 1\nreplacements: []\n", "non-empty"),
        ("version: 1\n", "non-empty"),
        ("- just\n- a\n- list\n", "must be a mapping"),
        ("version: 1\nreplacements: [{find: '', replace: b}]\n", "non-empty `find`"),
        ("version: 1\nreplacements: [{find: a, note: b}]\n", "unknown key"),
    ],
)
def test_a_malformed_replacement_list_is_rejected_by_name(tmp_path: Path, body: str, message: str) -> None:
    path = tmp_path / "replacements.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(scrub.ScrubError, match=message):
        scrub.load_replacement_list(path)


def test_a_replacement_that_reintroduces_another_listed_string_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "replacements.yaml"
    path.write_text(
        "version: 1\nreplacements:\n"
        "  - find: Jamie Okafor\n    replace: Northside Okafor\n"
        "  - find: Okafor\n    replace: Fields\n",
        encoding="utf-8",
    )
    with pytest.raises(scrub.ScrubError, match="never converge"):
        scrub.load_replacement_list(path)


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def test_the_command_line_scrubs_a_file_and_reports_counts_without_document_text(
    seeded_docx: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "scrubbed.docx"
    list_path = write_replacement_list(tmp_path / "replacements.yaml")

    exit_code = scrub.main([str(seeded_docx), "--output", str(output), "--replacements", str(list_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output.is_file()
    assert "parts dropped:" in captured.out
    assert "name/team-code replacements:" in captured.out
    assert SEEDED_NAME not in captured.out
    assert "Evidence paragraph" not in captured.out, "the summary never prints document text"


def test_the_command_line_reports_a_missing_replacement_list_and_exits_non_zero(
    seeded_docx: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = scrub.main(
        [
            str(seeded_docx),
            "--output",
            str(tmp_path / "out.docx"),
            "--replacements",
            str(tmp_path / "absent.yaml"),
        ]
    )
    assert exit_code == 1
    assert "replacement list not found" in capsys.readouterr().err


# --------------------------------------------------------------------------------------------
# A replacement may not begin or end inside a word
# --------------------------------------------------------------------------------------------
#
# Cutter marks — the initials a debater puts at the end of a cite — are routinely two letters.
# `PT`, `AD`, `TM`, `EA` and `RP` are all real ones from a real team's files. An unanchored match
# rewrites them inside ordinary words, silently, in quoted evidence.


@pytest.mark.parametrize(
    ("find", "text", "expected"),
    [
        ("AD", "THE ADVANTAGE IS UNIQUE; AD", "THE ADVANTAGE IS UNIQUE; <cutter>"),
        ("PT", "they will CAPTURE the market; PT", "they will CAPTURE the market; <cutter>"),
        ("EA", "the other TEAM conceded; EA", "the other TEAM conceded; <cutter>"),
        ("TM", "the ITEM was priced; TM", "the ITEM was priced; <cutter>"),
        ("RP", "a SHARP decline followed; RP", "a SHARP decline followed; <cutter>"),
    ],
)
def test_a_two_letter_cutter_mark_is_not_matched_inside_a_word(find: str, text: str, expected: str) -> None:
    assert scrub.Replacement(find=find, replace="<cutter>").pattern.sub("<cutter>", text) == expected


def test_a_cutter_mark_is_replaced_without_touching_a_person_named_in_the_evidence() -> None:
    """The case from a real file: `Charlie C.` cut the card; `Charlie Kirk` is in the quotation."""
    replacement = scrub.Replacement(find="Charlie C.", replace="Rowan F.")
    cite = "(DOA 11-06-2025); Charlie C.]"
    evidence = "the killing of conservative activist Charlie Kirk has intensified fears"
    assert replacement.pattern.sub(replacement.replace, cite) == "(DOA 11-06-2025); Rowan F.]"
    assert replacement.pattern.sub(replacement.replace, evidence) == evidence


def test_a_name_is_still_matched_when_punctuation_or_a_bracket_abuts_it() -> None:
    replacement = scrub.Replacement(find="Willie T", replace="Devon R")
    for text, expected in [
        ("; Willie T]", "; Devon R]"),
        ("(Willie T)", "(Devon R)"),
        ("cut by Willie T.", "cut by Devon R."),
        ("recut-Willie T", "recut-Devon R"),
    ]:
        assert replacement.pattern.sub(replacement.replace, text) == expected


def test_a_name_that_is_a_prefix_of_a_longer_word_is_left_alone() -> None:
    replacement = scrub.Replacement(find="Wood", replace="<X>")
    assert replacement.pattern.sub("<X>", "Woodward argues that") == "Woodward argues that"
    assert replacement.pattern.sub("<X>", "Wood 24 writes") == "<X> 24 writes"


def test_verification_looks_harder_than_replacement_does() -> None:
    """A full name inside a run of binary bytes has survived; `AD` inside `ADVANTAGE` has not."""
    name = scrub.Replacement(find="Jamie Okafor", replace="Rowan Fields")
    assert name.is_unambiguous is True
    assert name.survivor_pattern.search("tEXtAuthorJamie Okafor\x00") is not None
    assert name.pattern.search("tEXtAuthorJamie Okafor\x00") is None, "but it is never rewritten"

    initials = scrub.Replacement(find="AD", replace="<cutter>")
    assert initials.is_unambiguous is False
    assert initials.survivor_pattern.search("THE ADVANTAGE IS UNIQUE") is None
    assert initials.survivor_pattern.search("cut by AD") is not None
