"""A searched card and its snippet as HTML: text escaped, only allow-listed tags and classes (`v1-e39-t03`).

Disclosed files are untrusted input. A card's text may hold anything a stranger typed into Word,
`<script>`, `onerror=` and `javascript:` included, and none of it may reach a page as markup. So this
module writes markup of its own and nothing else:

* every character of card text goes through the standard library's :func:`html.escape`, quotes
  included, and a line break becomes `<br>`;
* the only tags are :data:`ALLOWED_TAGS`: `span` for a run's formatting, `mark` for a matched word in
  a snippet, and `br`;
* the only attribute is `class`, and its only values are :data:`EMPHASIS_CLASSES`, one class per
  highlight colour in :data:`HIGHLIGHT_COLOURS` (OOXML's `ST_HighlightColor`, every value the parser's
  profile knows among them), and `card-size-<half points>` for a font size. A colour outside the list
  renders as :data:`OTHER_HIGHLIGHT_CLASS`; the colour's own text never reaches the page.

The renderer is lossless for what the parser stores: reading the classes back gives the characters
each emphasis, each highlight colour and each size covers, which is the reading `formatting_sha256`
in :mod:`debate_core.domain.file_provenance` takes. The search page's CSS (`v1-e39-t06`) gives the
classes their look. No template library is used: `debate_core` takes no jinja2 or markupsafe here.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from typing import Final

from debate_core.domain.evidence_search import CardRun, SnippetSegment
from debate_core.domain.style_profile import RunEmphasis

__all__ = [
    "ALLOWED_TAGS",
    "EMPHASIS_CLASSES",
    "FONT_SIZE_CLASS",
    "HIGHLIGHT_COLOURS",
    "OTHER_HIGHLIGHT_CLASS",
    "highlight_class",
    "is_allowed_class",
    "render_card_html",
    "render_snippet_html",
    "render_text_html",
]

ALLOWED_TAGS: Final = frozenset({"span", "mark", "br"})
"""Every tag the renderer writes."""

EMPHASIS_CLASSES: Final = {
    RunEmphasis.UNDERLINE: "card-underline",
    RunEmphasis.EMPHASIS: "card-emphasis",
    RunEmphasis.CITE: "card-cite",
    RunEmphasis.UNDERTAG: "card-undertag",
    RunEmphasis.ANALYTIC: "card-analytic",
    RunEmphasis.HIGHLIGHT: "card-highlight",
    RunEmphasis.BOLD: "card-bold",
    RunEmphasis.SHRUNK: "card-shrunk",
    RunEmphasis.HEADING: "card-heading",
}
"""One class per emphasis the parser records."""

HIGHLIGHT_COLOURS: Final = frozenset(
    {
        "black",
        "blue",
        "cyan",
        "darkBlue",
        "darkCyan",
        "darkGray",
        "darkGreen",
        "darkMagenta",
        "darkRed",
        "darkYellow",
        "green",
        "lightGray",
        "magenta",
        "red",
        "white",
        "yellow",
    }
)
"""OOXML's `ST_HighlightColor` values but `none`: every `w:highlight` a highlight span can name."""

OTHER_HIGHLIGHT_CLASS: Final = "card-highlight-other"
"""The class of a highlight colour outside :data:`HIGHLIGHT_COLOURS`, which the parser never stores."""

FONT_SIZE_CLASS: Final = re.compile(r"^card-size-[1-9][0-9]{0,3}$")
"""`card-size-22`: a font size in half-points, digits only, up to 9999 (Word's largest is 3276)."""

_ALLOWED_CLASSES: Final = frozenset(
    {
        *EMPHASIS_CLASSES.values(),
        OTHER_HIGHLIGHT_CLASS,
        *(f"card-highlight-{one}" for one in HIGHLIGHT_COLOURS),
    }
)


def highlight_class(colour: str) -> str:
    """`card-highlight-cyan` for `cyan`; :data:`OTHER_HIGHLIGHT_CLASS` for a colour not on the list."""
    return f"card-highlight-{colour}" if colour in HIGHLIGHT_COLOURS else OTHER_HIGHLIGHT_CLASS


def is_allowed_class(name: str) -> bool:
    """Whether the renderer may write `name` as a class."""
    return name in _ALLOWED_CLASSES or FONT_SIZE_CLASS.match(name) is not None


def render_text_html(text: str) -> str:
    """`text` escaped, every character, with each line break as `<br>`."""
    return "<br>".join(html.escape(line, quote=True) for line in text.split("\n"))


def _classes(run: CardRun) -> list[str]:
    names = [EMPHASIS_CLASSES[emphasis] for emphasis in run.emphases]
    names += [highlight_class(colour) for colour in run.highlight_colors]
    names += [f"card-size-{size}" for size in run.font_sizes if FONT_SIZE_CLASS.match(f"card-size-{size}")]
    return [name for name in dict.fromkeys(names) if is_allowed_class(name)]


def render_card_html(runs: Iterable[CardRun]) -> str:
    """A card's runs as HTML: each formatted run a `span` with its classes, plain runs as escaped text."""
    parts: list[str] = []
    for run in runs:
        body = render_text_html(run.text)
        names = _classes(run)
        parts.append(f'<span class="{" ".join(names)}">{body}</span>' if names else body)
    return "".join(parts)


def render_snippet_html(segments: Iterable[SnippetSegment]) -> str:
    """A result's snippet as HTML: matched words in `mark`, everything escaped."""
    return "".join(
        f"<mark>{render_text_html(segment.text)}</mark>" if segment.marked else render_text_html(segment.text)
        for segment in segments
    )
