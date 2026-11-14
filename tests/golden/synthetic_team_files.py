"""Invented Verbatim-style team files for the golden-card tooling's tests.

`scripts/import_golden_card.py` reads the team's season folders, which never enter the repository
and which no test reads. Its tests read these instead: packages built in memory, laid out the way a
team file is (a block heading, then tag, cite and body per card), and carrying an invented roster
name in every place a real Word file hides one:

* the document properties (`docProps/core.xml`'s author and last editor, `docProps/app.xml`'s
  company and template);
* a comment thread (`word/comments.xml`, its markup in the body, and `word/people.xml`);
* a header part, the settings part's template link and a document variable;
* a tracked insertion's author, inside a card's body;
* a tag, and the tail of a cite (a cutter's mark and a team code).

Every name, school and code here is invented. The author in the document properties is
deliberately **not** on the denylist, so a test can tell the metadata scrub from the denylist scrub.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from xml.sax.saxutils import escape, quoteattr

from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, build_styles_xml, paragraph_xml, run_xml

__all__ = [
    "DENYLIST_ENTRIES",
    "METADATA_AUTHOR",
    "ROSTER_NAME",
    "TEAM_CODE",
    "SyntheticCard",
    "body_words",
    "team_file",
    "write_denylist",
]

#: A debater on the invented roster: the denylist lists the name, the surname and the team code.
ROSTER_NAME: Final = "Marisol Quenneville"
ROSTER_SURNAME: Final = "Quenneville"
TEAM_CODE: Final = "QZX"
DENYLIST_ENTRIES: Final = (ROSTER_NAME, ROSTER_SURNAME, TEAM_CODE)

#: The file's author as Word recorded it: a person who is not on the denylist, so only the
#: metadata scrub can remove the name.
METADATA_AUTHOR: Final = "Ottoline Fairweather"
METADATA_COMPANY: Final = "Fairweather Academy"

R_NAMESPACE: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W15_NAMESPACE: Final = "http://schemas.microsoft.com/office/word/2012/wordml"

#: Twenty invented words, so that a body of one paragraph is long enough to be a candidate.
FILLER: Final = (
    "the regional operator measured demand over a decade and found the reserve margin falling "
    "faster than any planner had forecast"
)


def body_words(text: str) -> int:
    return len(text.split())


@dataclass(frozen=True)
class SyntheticCard:
    """One card: its tag, its cite (short cite, then the rest), and its body paragraphs.

    Each body paragraph is written as plain text, an underlined and highlighted stretch, and plain
    text again, so the parser reads it as evidence. `link` goes into the cite as a hyperlink.
    """

    tag: str
    short_cite: str
    cite_rest: str
    body: Sequence[str]
    link: str | None = None
    tracked_insertion: str | None = None
    commented: bool = False
    footnoted: bool = False
    underlined: tuple[str, ...] = field(default=())

    def warrant(self, position: int) -> str:
        return (
            self.underlined[position]
            if position < len(self.underlined)
            else "the warrant the card is read for"
        )


def _hyperlink(relationship_id: str, text: str) -> str:
    return f'<w:hyperlink r:id="{relationship_id}">{run_xml(text)}</w:hyperlink>'


def _card_xml(card: SyntheticCard, link_id: str | None) -> str:
    tag_runs = run_xml(card.tag)
    if card.commented:
        tag_runs = (
            '<w:commentRangeStart w:id="0"/>'
            + tag_runs
            + '<w:commentRangeEnd w:id="0"/>'
            + '<w:r><w:commentReference w:id="0"/></w:r>'
        )
    xml = paragraph_xml(tag_runs, style="Heading4")
    cite = run_xml(card.short_cite, character_style="Style13ptBold")
    if card.link is not None and link_id is not None:
        before, _, after = card.cite_rest.partition("{link}")
        cite += run_xml(before) + _hyperlink(link_id, card.link) + (run_xml(after) if after else "")
    else:
        cite += run_xml(card.cite_rest)
    xml += paragraph_xml(cite)
    for position, text in enumerate(card.body):
        opening, _, closing = text.partition("{warrant}")
        runs = run_xml(opening)
        if position == 0 and card.tracked_insertion is not None:
            runs += (
                f'<w:ins w:id="1" w:author={quoteattr(ROSTER_NAME)} w:date="2026-01-05T10:00:00Z">'
                + run_xml(card.tracked_insertion)
                + "</w:ins>"
            )
        runs += run_xml(card.warrant(position), character_style="StyleUnderline", highlight="cyan")
        runs += run_xml(closing)
        if position == 0 and card.footnoted:
            runs += '<w:r><w:footnoteReference w:id="1"/></w:r>'
        xml += paragraph_xml(runs)
    return xml


_CONTENT_TYPES: Final = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/comments.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
  <Override PartName="/word/people.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.people+xml"/>
  <Override PartName="/word/header1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/docProps/core.xml"
    ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml"
    ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

_PACKAGE_RELS: Final = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    Target="docProps/core.xml"/>
  <Relationship Id="rId3"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
    Target="docProps/app.xml"/>
</Relationships>
"""


def _document_rels(links: Sequence[tuple[str, str]]) -> str:
    hyperlinks = "".join(
        f'<Relationship Id="{relationship_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        f'Target={quoteattr(target)} TargetMode="External"/>'
        for relationship_id, target in links
    )
    base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{base}/styles" Target="styles.xml"/>'
        f'<Relationship Id="rId2" Type="{base}/settings" Target="settings.xml"/>'
        f'<Relationship Id="rId3" Type="{base}/comments" Target="comments.xml"/>'
        f'<Relationship Id="rId4" Type="http://schemas.microsoft.com/office/2011/relationships/people" '
        'Target="people.xml"/>'
        f'<Relationship Id="rId5" Type="{base}/header" Target="header1.xml"/>'
        f"{hyperlinks}</Relationships>"
    )


def _settings() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{W_NAMESPACE}" xmlns:r="{R_NAMESPACE}">'
        '<w:attachedTemplate r:id="rId1"/>'
        f'<w:docVars><w:docVar w:name="Cutter" w:val={quoteattr(ROSTER_NAME)}/></w:docVars>'
        '<w:defaultTabStop w:val="720"/>'
        "</w:settings>"
    )


def _settings_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" '
        f'Target="file:///C:/Users/{ROSTER_SURNAME.lower()}/Templates/Debate.dotm" TargetMode="External"/>'
        "</Relationships>"
    )


def _comments() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:comments xmlns:w="{W_NAMESPACE}">'
        f'<w:comment w:id="0" w:author={quoteattr(ROSTER_NAME)} w:initials="MQ" '
        'w:date="2026-01-05T10:00:00Z">'
        "<w:p><w:r><w:t>recut this before the tournament</w:t></w:r></w:p></w:comment></w:comments>"
    )


def _people() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w15:people xmlns:w15="{W15_NAMESPACE}">'
        f"<w15:person w15:author={quoteattr(ROSTER_NAME)}/></w15:people>"
    )


def _header() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:hdr xmlns:w="{W_NAMESPACE}"><w:p><w:r><w:t>{escape(TEAM_CODE)} Debate</w:t></w:r></w:p></w:hdr>'
    )


def _core() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:creator>{METADATA_AUTHOR}</dc:creator><cp:lastModifiedBy>{METADATA_AUTHOR}</cp:lastModifiedBy>"
        "<dc:title>Grid aff</dc:title>"
        '<dcterms:created xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:created>'
        "</cp:coreProperties>"
    )


def _app() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        f"<Template>Debate.dotm</Template><Company>{METADATA_COMPANY}</Company></Properties>"
    )


def team_file(cards: Sequence[SyntheticCard], *, heading: str = "Synthetic Block") -> bytes:
    """A team file holding `cards` under one block heading, with every identity part filled in."""
    links: list[tuple[str, str]] = []
    body = paragraph_xml(run_xml(heading), style="Heading3")
    for card in cards:
        link_id = None
        if card.link is not None:
            link_id = f"rId{10 + len(links)}"
            links.append((link_id, card.link))
        body += _card_xml(card, link_id)
    body += '<w:sectPr><w:headerReference w:type="default" r:id="rId5"/></w:sectPr>'
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NAMESPACE}" xmlns:r="{R_NAMESPACE}" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        f"<w:body>{body}</w:body></w:document>"
    )
    return build_docx(
        "",
        document_xml=document,
        styles_xml=build_styles_xml(),
        content_types=_CONTENT_TYPES,
        extra_parts={
            "_rels/.rels": _PACKAGE_RELS,
            "word/_rels/document.xml.rels": _document_rels(links),
            "word/settings.xml": _settings(),
            "word/_rels/settings.xml.rels": _settings_rels(),
            "word/comments.xml": _comments(),
            "word/people.xml": _people(),
            "word/header1.xml": _header(),
            "docProps/core.xml": _core(),
            "docProps/app.xml": _app(),
        },
    )


def write_denylist(path: Path, entries: Sequence[str] = DENYLIST_ENTRIES) -> Path:
    """Write a denylist the way the operator does: one entry per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return path


def coach_attests(candidate_id: str) -> bool:
    """The coach's answer in a test not about the attestation: cut by the coach, reviewed for names."""
    del candidate_id
    return True
