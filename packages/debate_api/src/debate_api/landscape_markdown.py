"""A landscape bundle's two Markdown files as the landscape pages show them (`v1-e39-t17`).

`report.md` is one page, `schools.md` a front page with one page per school and one per position (the
PM's layout ruling of 2026-10-25). Each is rendered once per bundle, by
:class:`~debate_core.application.tub.landscape_pages.LandscapeShelf`'s `prepare`, and served from what
the shelf holds until it reads the bucket again.

## How Markdown becomes HTML

markdown-it-py's CommonMark parser with its table rule, and three options set against the bundle's
text, which the pages treat as untrusted:

* `html` off: raw HTML in a bundle is shown as its text, escaped, never as markup;
* `linkify` off: a bare address in the text stays text;
* markdown-it's own link check stays on, so a `javascript:`, `vbscript:` or `file:` target is never a
  link at all.

Then every link and image is checked by :func:`~debate_core.domain.landscape_pages.landscape_link`
before rendering. A link to a heading on the same page stays a link; in the school view, a team's
openCaselist page that the team-page rule builds itself stays a link and opens like the card page's
"Open on openCaselist" (a new tab, no opener, no referrer). Every other link is its text, and every
image its alt text.

## Pages, contents and anchors

A page is cut from the token stream at top-level headings. Every heading on a page gets an `id`, as
:class:`~debate_core.domain.landscape_pages.Anchors` writes it. The report's contents list is its `#`
parts with their `##` sections, from the headings, and the bundle's own `## Contents` (`v1-e32-t20`)
is left out, so the page has one list (the PM's ruling). The school view's front page lists every
school, addressed by its heading's anchor, and every position under its kind, addressed by its id.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from markdown_it import MarkdownIt
from markdown_it.token import Token

from debate_core.application.tub.landscape_pages import LandscapeBundle
from debate_core.domain.landscape_pages import Anchors, LandscapeLink, is_position_id, landscape_link

__all__ = [
    "ContentsEntry",
    "LandscapePiece",
    "RenderedBundle",
    "RenderedReport",
    "RenderedSchoolView",
    "render_bundle",
    "render_markdown",
]

_MARKDOWN: Final = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable(
    "table"
)
_NEW_TAB: Final = '<span class="new-tab"> (opens in a new tab)</span>'
"""Fixed markup, the same as the card page's link out; never anything a bundle wrote."""
_CONTENTS_HEADING: Final = "Contents"
_BY_SCHOOL: Final = "By school"
_BY_POSITION: Final = "By position"
_UNKINDED: Final = "Positions"
"""The kind a position is listed under when the view names none above it."""


@dataclass(frozen=True, slots=True)
class ContentsEntry:
    text: str
    anchor: str
    sections: tuple[ContentsEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderedReport:
    title: str
    contents: tuple[ContentsEntry, ...]
    body_html: str


@dataclass(frozen=True, slots=True)
class LandscapePiece:
    """One school's or one position's page: its heading, where it is, and its table."""

    heading: str
    path: str
    """The page's last path segment: the school's heading anchor, or the position's id."""
    body_html: str
    kind: str | None = None
    """A position's kind, as the view's heading names it (`Disadvantages`)."""


@dataclass(frozen=True, slots=True)
class PositionKind:
    heading: str
    anchor: str
    lead_html: str
    positions: tuple[LandscapePiece, ...]
    unaddressed: tuple[str, ...] = ()
    """Headings under the kind that are no position id, listed as text with no page."""


@dataclass(frozen=True, slots=True)
class RenderedSchoolView:
    title: str
    header_html: str
    contents: tuple[ContentsEntry, ...]
    by_school_anchor: str
    by_school_lead_html: str
    schools: tuple[LandscapePiece, ...]
    by_position_anchor: str
    by_position_lead_html: str
    kinds: tuple[PositionKind, ...]
    rest_html: str = ""
    """Anything after the two sections, rendered on the front page."""

    def school(self, path: str) -> LandscapePiece | None:
        return next((one for one in self.schools if one.path == path), None)

    def position(self, path: str) -> LandscapePiece | None:
        return next((one for kind in self.kinds for one in kind.positions if one.path == path), None)


@dataclass(frozen=True, slots=True)
class RenderedBundle:
    caselist: str
    snapshot: date
    report: RenderedReport
    school_view: RenderedSchoolView | None


@dataclass(slots=True)
class _Section:
    """A top-level heading and the blocks up to the next one."""

    level: int
    text: str
    heading: list[Token]
    body: list[Token] = field(default_factory=list[Token])

    @property
    def tokens(self) -> list[Token]:
        return [*self.heading, *self.body]


def render_bundle(bundle: LandscapeBundle) -> RenderedBundle:
    """Both files of `bundle` as the pages show them: :class:`LandscapeShelf`'s `prepare`."""
    return RenderedBundle(
        caselist=bundle.caselist,
        snapshot=bundle.snapshot,
        report=_report(bundle.report_markdown, bundle.caselist),
        school_view=(
            None
            if bundle.school_view_markdown is None
            else _school_view(bundle.school_view_markdown, bundle.caselist)
        ),
    )


def render_markdown(markdown: str, *, caselist: str, team_pages: bool = False) -> str:
    """One piece of Markdown as one page's HTML, with its headings anchored and its links checked."""
    return _render(_MARKDOWN.parse(markdown), caselist=caselist, team_pages=team_pages, anchors=Anchors())


# --------------------------------------------------------------------------------------------
# The two files
# --------------------------------------------------------------------------------------------


def _report(markdown: str, caselist: str) -> RenderedReport:
    preamble, sections = _split(_MARKDOWN.parse(markdown))
    title, sections = _title(sections)
    kept = _without_contents(sections)
    anchors = Anchors()
    contents: list[ContentsEntry] = []
    part: ContentsEntry | None = None
    for section in kept:
        if not section.heading:
            continue
        anchor = _anchor(section, anchors)
        if section.level == 1:
            part = ContentsEntry(section.text, anchor)
            contents.append(part)
        elif section.level == 2 and part is not None:
            part = ContentsEntry(
                part.text, part.anchor, (*part.sections, ContentsEntry(section.text, anchor))
            )
            contents[-1] = part
        elif section.level == 2:
            contents.append(ContentsEntry(section.text, anchor))
    tokens = [*preamble, *(token for section in kept for token in section.tokens)]
    body = _render(tokens, caselist=caselist, team_pages=False, anchors=anchors)
    return RenderedReport(title=title, contents=tuple(contents), body_html=body)


def _school_view(markdown: str, caselist: str) -> RenderedSchoolView:
    preamble, sections = _split(_MARKDOWN.parse(markdown))
    title, sections = _title(sections)
    front = Anchors()
    by_school_at = _index_of(sections, 2, _BY_SCHOOL)
    by_position_at = _index_of(sections, 2, _BY_POSITION)
    if by_school_at is None or by_position_at is None or by_position_at < by_school_at:
        # Not the view `v1-e32-t04` writes: shown whole on its front page, with no pages under it.
        header = _render(
            [*preamble, *(token for one in sections for token in one.tokens)],
            caselist=caselist,
            team_pages=True,
            anchors=front,
        )
        return RenderedSchoolView(title, header, (), "", "", (), "", "", ())
    header_tokens = [*preamble, *(token for one in sections[:by_school_at] for token in one.tokens)]
    header = _render(header_tokens, caselist=caselist, team_pages=True, anchors=front)
    by_school, by_position = sections[by_school_at], sections[by_position_at]
    by_school_anchor, by_position_anchor = _anchor(by_school, front), _anchor(by_position, front)
    school_sections = sections[by_school_at + 1 : by_position_at]
    rest = sections[by_position_at + 1 :]
    kinds_end = next((index for index, one in enumerate(rest) if one.level <= 2), len(rest))
    return RenderedSchoolView(
        title=title,
        header_html=header,
        contents=(
            ContentsEntry(by_school.text, by_school_anchor),
            ContentsEntry(by_position.text, by_position_anchor),
        ),
        by_school_anchor=by_school_anchor,
        by_school_lead_html=_render(by_school.body, caselist=caselist, team_pages=True, anchors=front),
        schools=_schools(school_sections, caselist),
        by_position_anchor=by_position_anchor,
        by_position_lead_html=_render(by_position.body, caselist=caselist, team_pages=True, anchors=front),
        kinds=_kinds(rest[:kinds_end], caselist, front),
        rest_html=_render(
            [token for one in rest[kinds_end:] for token in one.tokens],
            caselist=caselist,
            team_pages=True,
            anchors=front,
        ),
    )


def _schools(sections: Sequence[_Section], caselist: str) -> tuple[LandscapePiece, ...]:
    paths = Anchors()
    return tuple(
        LandscapePiece(
            heading=section.text,
            path=paths.add(section.text),
            body_html=_render(section.body, caselist=caselist, team_pages=True, anchors=Anchors()),
        )
        for section in sections
    )


def _kinds(sections: Sequence[_Section], caselist: str, front: Anchors) -> tuple[PositionKind, ...]:
    kinds: list[PositionKind] = []
    seen: set[str] = set()
    for section in sections:
        if section.level == 3:
            lead = _render(section.body, caselist=caselist, team_pages=True, anchors=front)
            kinds.append(PositionKind(section.text, _anchor(section, front), lead, ()))
            continue
        if not kinds:
            kinds.append(PositionKind(_UNKINDED, front.add(_UNKINDED), "", ()))
        kind = kinds[-1]
        if not is_position_id(section.text) or section.text in seen:
            kinds[-1] = PositionKind(
                kind.heading, kind.anchor, kind.lead_html, kind.positions, (*kind.unaddressed, section.text)
            )
            continue
        seen.add(section.text)
        piece = LandscapePiece(
            heading=section.text,
            path=section.text,
            body_html=_render(section.body, caselist=caselist, team_pages=True, anchors=Anchors()),
            kind=kind.heading,
        )
        kinds[-1] = PositionKind(kind.heading, kind.anchor, kind.lead_html, (*kind.positions, piece))
    return tuple(kinds)


# --------------------------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------------------------


def _split(tokens: Sequence[Token]) -> tuple[list[Token], list[_Section]]:
    """The blocks before the first top-level heading, and each top-level heading with its blocks."""
    preamble: list[Token] = []
    sections: list[_Section] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open" and token.level == 0:
            heading = list(tokens[index : index + 3])
            sections.append(_Section(level=int(token.tag[1]), text=_plain(heading[1]), heading=heading))
            index += 3
            continue
        (sections[-1].body if sections else preamble).append(token)
        index += 1
    return preamble, sections


def _title(sections: list[_Section]) -> tuple[str, list[_Section]]:
    """The file's `#` title, which the page's own `<h1>` shows, and the sections after it."""
    if sections and sections[0].level == 1:
        return sections[0].text, [_Section(0, "", [], sections[0].body), *sections[1:]]
    return "", sections


def _without_contents(sections: Sequence[_Section]) -> list[_Section]:
    """`sections` less the bundle's own `## Contents` and anything under it."""
    kept: list[_Section] = []
    skipping = False
    for section in sections:
        if section.level == 2 and section.text == _CONTENTS_HEADING:
            skipping = True
            continue
        if skipping and 0 < section.level <= 2:
            skipping = False
        if not skipping:
            kept.append(section)
    return kept


def _index_of(sections: Sequence[_Section], level: int, text: str) -> int | None:
    return next((index for index, one in enumerate(sections) if (one.level, one.text) == (level, text)), None)


def _anchor(section: _Section, anchors: Anchors) -> str:
    """Give `section`'s heading its anchor on the page `anchors` is for, and return it."""
    anchor = anchors.add(section.text)
    if section.heading:
        section.heading[0].attrSet("id", anchor)
    return anchor


def _plain(inline: Token) -> str:
    """A heading's words as they read: text, code and line breaks, with no markup."""
    words: list[str] = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            words.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            words.append(" ")
        elif child.type == "image":
            words.append(_plain(child))
    return "".join(words).strip()


def _render(tokens: Sequence[Token], *, caselist: str, team_pages: bool, anchors: Anchors) -> str:
    """`tokens` as one page's HTML: each heading not yet anchored gets its anchor, then each link is
    checked against the page's anchors."""
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.attrGet("id") is None:
            token.attrSet("id", anchors.add(_plain(tokens[index + 1])))
    for token in tokens:
        if token.type == "inline" and token.children:
            token.children = _checked(
                token.children, caselist=caselist, team_pages=team_pages, anchors=anchors
            )
    return _MARKDOWN.renderer.render(list(tokens), _MARKDOWN.options, {})


def _checked(children: Sequence[Token], *, caselist: str, team_pages: bool, anchors: Anchors) -> list[Token]:
    """An inline run with each link checked: kept, opened in a new tab, or reduced to its text."""
    kept: list[Token] = []
    open_links: list[LandscapeLink | None] = []
    for child in children:
        if child.type == "link_open":
            allowed = landscape_link(
                str(child.attrGet("href") or ""), caselist=caselist, anchors=anchors, team_pages=team_pages
            )
            open_links.append(allowed)
            if allowed is LandscapeLink.TEAM_PAGE:
                child.attrSet("target", "_blank")
                child.attrSet("rel", "noopener noreferrer")
            if allowed is not None:
                kept.append(child)
        elif child.type == "link_close":
            allowed = open_links.pop() if open_links else None
            if allowed is LandscapeLink.TEAM_PAGE:
                kept.append(Token("html_inline", "", 0, content=_NEW_TAB))
            if allowed is not None:
                kept.append(child)
        elif child.type == "image":
            kept.append(Token("text", "", 0, content=_plain(child)))
        else:
            kept.append(child)
    return kept
