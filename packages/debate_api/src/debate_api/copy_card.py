"""Copy card: a card as the HTML and plain text `app.js` puts on the clipboard (`v1-e39-t06`).

A paste into Google Docs or Word keeps what this HTML says in inline styles, and only that: neither
reads a class or a stylesheet from the clipboard. So the copy is written apart from the card page's
markup (:mod:`debate_core.domain.search_card_html`, which uses classes the page's CSS styles), from
:class:`~debate_core.domain.evidence_search.Card`'s plain values and a fixed table:

* :data:`EMPHASIS_STYLES`, from each emphasis the parser records to the CSS declarations of the
  Verbatim character style it stands for, as the E33 writer's template defines them;
* :data:`HIGHLIGHT_STYLES`, from each OOXML `w:highlight` colour token to its RGB colour, as Word
  draws it; a colour not in the table gets no colour at all;
* :func:`font_size_style`, from half-points to points.

No card text ever reaches a `style` attribute: every declaration is one of the table's own strings,
chosen by an emphasis name, a colour token or an integer. Every character of text is escaped here,
with :func:`html.escape`, quotes included.

## Every span is kept

Each run's text is wrapped in one `span` per emphasis, then one per highlight colour, then one per
size, innermost last, so a size the parser measured wins over an emphasis's own. No two entries of
the table are the same declarations, so reading the spans back gives every emphasis, colour and
size each character carried: the coverage :func:`~debate_core.domain.file_provenance.
formatting_sha256` reads (ac2). A line break is a `<br>` inside the run's spans, so it keeps its
formatting too.

## The tag, the cite and the text, and no provenance line

The tag, in the template's tag style; the cite, its short cite in `Style13ptBold`; then the card's
text. The plain text is the same three parts, one to a line.

**No provenance line** (data-use policy version 1.11, Attribution rules 2 and 5 and the E39 gate's
item 6; Charlie, 2026-10-22; `v1-e39-t11`). Until then the copy carried the line below the cite, in
the Undertag style the E33 writer put it in. A copied card now carries no school, team code,
tournament, round, caselist or camp: the team's own files are disclosed on the caselist, and
republishing other schools' names and team codes in them adds nothing the team needs. The line is
still shown on the card page, below the cite, with the "Disclosed evidence, not platform-verified"
label, and the provenance stays on record in the copy's `card-copied` audit record, which names the
card and is unchanged.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from debate_core.domain.evidence_search import Card, CardRun
from debate_core.domain.style_profile import RunEmphasis

__all__ = [
    "CITE_STYLE",
    "EMPHASIS_STYLES",
    "HIGHLIGHT_STYLES",
    "TAG_STYLE",
    "CopiedCard",
    "copied_card",
    "font_size_style",
]

EMPHASIS_STYLES: Final[Mapping[RunEmphasis, str]] = {
    RunEmphasis.UNDERLINE: "text-decoration:underline",
    RunEmphasis.EMPHASIS: "font-weight:bold;text-decoration:underline",
    RunEmphasis.CITE: "font-weight:bold;font-size:13pt",
    RunEmphasis.UNDERTAG: "color:#385623",
    RunEmphasis.ANALYTIC: "font-weight:bold;color:#1F3864",
    RunEmphasis.BOLD: "font-weight:bold",
    RunEmphasis.SHRUNK: "font-size:smaller",
    RunEmphasis.HEADING: "font-weight:bold;font-size:larger",
}
"""Each emphasis but `HIGHLIGHT` (which is its colour, below) as the declarations of its Verbatim style.

`StyleUnderline` underlines; Verbatim's `Emphasis` is bold and underlined; `Style13ptBold` (a cite) is
13-point bold; `UndertagChar` is the template's green and `AnalyticChar` its bold navy. `SHRUNK` and
`HEADING` say only smaller and larger and bold: the parser measures the real size of such text, and
its size span, written inside, is what a paste shows."""

HIGHLIGHT_STYLES: Final[Mapping[str, str]] = {
    "black": "background-color:#000000",
    "blue": "background-color:#0000FF",
    "cyan": "background-color:#00FFFF",
    "darkBlue": "background-color:#000080",
    "darkCyan": "background-color:#008080",
    "darkGray": "background-color:#808080",
    "darkGreen": "background-color:#008000",
    "darkMagenta": "background-color:#800080",
    "darkRed": "background-color:#800000",
    "darkYellow": "background-color:#808000",
    "green": "background-color:#00FF00",
    "lightGray": "background-color:#C0C0C0",
    "magenta": "background-color:#FF00FF",
    "red": "background-color:#FF0000",
    "white": "background-color:#FFFFFF",
    "yellow": "background-color:#FFFF00",
}
"""OOXML's `ST_HighlightColor` tokens but `none`, as the RGB colours Word draws them. A highlight
changes nothing but the background, as in Word: the text keeps its own colour."""

TAG_STYLE: Final = "font-weight:bold;font-size:13pt"
"""The tag: the template's `Heading4`, 13-point bold."""

CITE_STYLE: Final = EMPHASIS_STYLES[RunEmphasis.CITE]
"""The short cite at the start of the cite: `Style13ptBold`."""

_LARGEST_SIZE: Final = 9999
"""Half-points: Word's largest size is 3276, and the card page's classes stop at four digits too."""


def font_size_style(half_points: int) -> str | None:
    """`font-size:11pt` for 22 half-points, `font-size:10.5pt` for 21; `None` outside 1 to 9999."""
    if not 1 <= half_points <= _LARGEST_SIZE:
        return None
    whole, half = divmod(half_points, 2)
    return f"font-size:{whole}.5pt" if half else f"font-size:{whole}pt"


@dataclass(frozen=True, slots=True)
class CopiedCard:
    """What Copy card puts on the clipboard: `text/html` and `text/plain`."""

    html: str
    text: str


def copied_card(card: Card) -> CopiedCard:
    """The card's tag, cite and formatted text, and no provenance line (policy 1.11)."""
    paragraphs: list[str] = []
    if card.tag:
        paragraphs.append(f'<p style="{TAG_STYLE}">{_escaped(card.tag)}</p>')
    paragraphs.append(f"<p>{_cite(card)}</p>")
    paragraphs.append("<p>" + "".join(_run(run) for run in card.runs) + "</p>")
    text = "\n".join(part for part in (card.tag, card.cite, card.text) if part)
    return CopiedCard(html="".join(paragraphs), text=text)


def _escaped(text: str) -> str:
    """`text` escaped, every character, each line break a `<br>`."""
    return "<br>".join(html.escape(line, quote=True) for line in text.split("\n"))


def _cite(card: Card) -> str:
    short = card.short_cite
    if short and card.cite.startswith(short):
        rest = card.cite[len(short) :]
        return f'<span style="{CITE_STYLE}">{_escaped(short)}</span>{_escaped(rest)}'
    return _escaped(card.cite)


def _run(run: CardRun) -> str:
    styles = [EMPHASIS_STYLES[emphasis] for emphasis in run.emphases if emphasis in EMPHASIS_STYLES]
    styles += [HIGHLIGHT_STYLES[colour] for colour in run.highlight_colors if colour in HIGHLIGHT_STYLES]
    styles += [style for style in map(font_size_style, run.font_sizes) if style is not None]
    body = _escaped(run.text)
    for style in reversed(styles):
        body = f'<span style="{style}">{body}</span>'
    return body
