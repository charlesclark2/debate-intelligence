"""A searched card renders inert, only allow-listed tags and classes, losing no formatting (`v1-e39-t03`).

ac3: a card whose text holds a script element, an event-handler attribute and a `javascript:` link
renders as text, and the rendered HTML, read back by the standard library's parser, holds only the
allow-listed tags and classes. ac4: reading the classes back gives the characters each emphasis,
highlight colour and font size covers, and `formatting_sha256` (debate_core.domain.file_provenance)
of that reading equals its value over the stored spans.

The fixtures are invented: no card text from any real file (data-use policy, rule 5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.evidence_search import CardRun, SnippetSegment, card_runs
from debate_core.domain.file_provenance import formatting_sha256
from debate_core.domain.search_card_html import (
    ALLOWED_TAGS,
    EMPHASIS_CLASSES,
    HIGHLIGHT_COLOURS,
    OTHER_HIGHLIGHT_CLASS,
    is_allowed_class,
    render_card_html,
    render_snippet_html,
    render_text_html,
)
from debate_core.domain.search_index import IndexedFontSizeSpan, IndexedFormattingSpan
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource

HOSTILE_TEXT = (
    'Invented claim <script>alert("x")</script> and '
    '<img src=x onerror="alert(1)"> then <a href="javascript:alert(2)">read more</a>\n'
    "</span><span class=\"card-underline\" onclick='steal()'>broken out?</span> "
    "<!-- comment --> <style>body{}</style> <svg onload=alert(3)> &amp; &lt; ' \" & end"
)
"""A card body a stranger could type into Word: markup, handlers, a link, a span break-out, entities."""


@dataclass
class ReadBack(HTMLParser):
    """Rendered HTML read back: every tag and attribute seen, and the text with each character's classes."""

    tags: list[str] = field(default_factory=lambda: [])
    attributes: list[tuple[str, str | None]] = field(default_factory=lambda: [])
    text: list[str] = field(default_factory=lambda: [])
    classes: list[frozenset[str]] = field(default_factory=lambda: [])
    stack: list[frozenset[str]] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        super().__init__(convert_charrefs=True)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.extend(attrs)
        if tag == "br":
            self._add("\n")
            return
        names = frozenset(
            name for key, value in attrs if key == "class" and value is not None for name in value.split()
        )
        self.stack.append(names | (self.stack[-1] if self.stack else frozenset[str]()))

    def handle_endtag(self, tag: str) -> None:
        self.tags.append(f"/{tag}")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self._add(data)

    def handle_comment(self, data: str) -> None:
        self.tags.append("<!--")

    def handle_decl(self, decl: str) -> None:
        self.tags.append("<!")

    def handle_pi(self, data: str) -> None:
        self.tags.append("<?")

    def _add(self, data: str) -> None:
        current = self.stack[-1] if self.stack else frozenset[str]()
        self.text.append(data)
        self.classes.extend([current] * len(data))

    @classmethod
    def of(cls, rendered: str) -> ReadBack:
        reader = cls()
        reader.feed(rendered)
        reader.close()
        return reader

    @property
    def plain(self) -> str:
        return "".join(self.text)

    def spans(self) -> tuple[list[FormattingSpan], list[FontSizeSpan]]:
        """The characters each class covers, as parser spans: what `formatting_sha256` reads."""
        by_emphasis = {name: emphasis for emphasis, name in EMPHASIS_CLASSES.items()}
        formatting: list[FormattingSpan] = []
        sizes: list[FontSizeSpan] = []
        for offset, names in enumerate(self.classes):
            for name in names:
                if name in by_emphasis and by_emphasis[name] is not RunEmphasis.HIGHLIGHT:
                    formatting.append(_span(by_emphasis[name], offset))
                elif name.startswith("card-highlight-"):
                    formatting.append(
                        _span(RunEmphasis.HIGHLIGHT, offset, name.removeprefix("card-highlight-"))
                    )
                elif name.startswith("card-size-"):
                    sizes.append(
                        FontSizeSpan(start_offset=offset, end_offset=offset + 1, half_points=int(name[10:]))
                    )
        return formatting, sizes


def _span(emphasis: RunEmphasis, offset: int, colour: str | None = None) -> FormattingSpan:
    return FormattingSpan(
        emphasis=emphasis,
        start_offset=offset,
        end_offset=offset + 1,
        highlight_color=colour,
        rule_id="read-back",
        match_source=StyleMatchSource.VERBATIM,
    )


def _parser_span(span: IndexedFormattingSpan) -> FormattingSpan:
    return FormattingSpan(
        emphasis=span.emphasis,
        start_offset=span.start_offset,
        end_offset=span.end_offset,
        highlight_color=span.highlight_color,
        rule_id="stored",
        match_source=StyleMatchSource.VERBATIM,
    )


#: The allow-list, written by hand rather than read from the module, so a test cannot pass by a change
#: to the list it checks.
TAGS_BY_HAND: Final = {"span", "mark", "br"}
CLASSES_BY_HAND: Final = {
    "card-underline",
    "card-emphasis",
    "card-cite",
    "card-undertag",
    "card-analytic",
    "card-highlight",
    "card-bold",
    "card-shrunk",
    "card-heading",
    "card-highlight-other",
    *(
        f"card-highlight-{colour}"
        for colour in (
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
        )
    ),
}
SIZE_CLASS_BY_HAND: Final = re.compile(r"card-size-[1-9][0-9]{0,3}")


def allowed_by_hand(name: str) -> bool:
    return name in CLASSES_BY_HAND or SIZE_CLASS_BY_HAND.fullmatch(name) is not None


def assert_only_allowed_markup(reader: ReadBack) -> None:
    opened = [tag for tag in reader.tags if not tag.startswith("/")]
    assert set(opened) <= TAGS_BY_HAND
    assert {key for key, _ in reader.attributes} <= {"class"}
    names = {name for _, value in reader.attributes if value for name in value.split()}
    assert all(allowed_by_hand(name) for name in names), names


def test_search_card_html_allow_list_is_the_one_written_by_hand() -> None:
    assert ALLOWED_TAGS == TAGS_BY_HAND
    assert {
        *EMPHASIS_CLASSES.values(),
        OTHER_HIGHLIGHT_CLASS,
        *(f"card-highlight-{c}" for c in HIGHLIGHT_COLOURS),
    } == CLASSES_BY_HAND


@pytest.mark.parametrize(
    "name",
    [
        "card-size-0",
        "card-size-10000",
        "card-size-022",
        "card-size-",
        "onclick",
        "x",
        'card-highlight-cyan" onclick',
        "card-highlight-none",
        "CARD-BOLD",
    ],
)
def test_search_card_html_refuses_a_class_off_the_list(name: str) -> None:
    assert not is_allowed_class(name)
    assert not allowed_by_hand(name)


# ------------------------------------------------------------------------------------------------
# ac3: inert, and only the allow-list
# ------------------------------------------------------------------------------------------------


def test_search_card_html_renders_a_script_a_handler_and_a_javascript_link_as_text() -> None:
    """ac3, on a card's runs."""
    runs = card_runs(
        HOSTILE_TEXT,
        (
            IndexedFormattingSpan(RunEmphasis.UNDERLINE, 0, 40),
            IndexedFormattingSpan(RunEmphasis.HIGHLIGHT, 15, 60, "cyan"),
            IndexedFormattingSpan(RunEmphasis.BOLD, 80, 140),
        ),
        (IndexedFontSizeSpan(0, len(HOSTILE_TEXT), 22),),
    )
    rendered = render_card_html(runs)
    reader = ReadBack.of(rendered)
    assert reader.plain == HOSTILE_TEXT
    assert_only_allowed_markup(reader)
    assert set(reader.tags) == {"span", "/span", "br"}
    lowered = rendered.lower()
    for raw in ("<script", "<img", "<a ", "<svg", "<style", "<!--", 'onerror="', 'href="'):
        assert raw not in lowered, raw


def test_search_card_html_renders_a_hostile_snippet_and_text_inert() -> None:
    """ac3, on a snippet and on plain text such as a tag or a cite."""
    snippet = render_snippet_html(
        (SnippetSegment('<a href="javascript:x">', False), SnippetSegment("<script>", True))
    )
    assert snippet == "&lt;a href=&quot;javascript:x&quot;&gt;<mark>&lt;script&gt;</mark>"
    reader = ReadBack.of(snippet)
    assert reader.tags == ["mark", "/mark"]
    assert render_text_html("a\nb <b onmouseover='x'>") == "a<br>b &lt;b onmouseover=&#x27;x&#x27;&gt;"


def test_search_card_html_never_writes_a_colour_it_does_not_know() -> None:
    """A stored colour is untrusted too: only an allow-listed one becomes a class."""
    rendered = render_card_html(
        (CardRun("x", emphases=(RunEmphasis.HIGHLIGHT,), highlight_colors=('cyan" onclick="steal()',)),)
    )
    assert rendered == f'<span class="card-highlight {OTHER_HIGHLIGHT_CLASS}">x</span>'


def test_search_card_html_writes_the_exact_markup_for_a_small_card() -> None:
    """Written by hand: one plain run, one underlined and highlighted, a line break, a size."""
    runs = (
        CardRun("Invented "),
        CardRun(
            "growth", emphases=(RunEmphasis.UNDERLINE, RunEmphasis.HIGHLIGHT), highlight_colors=("cyan",)
        ),
        CardRun(" <ends>\nbadly", font_sizes=(16,)),
    )
    assert render_card_html(runs) == (
        'Invented <span class="card-underline card-highlight card-highlight-cyan">growth</span>'
        '<span class="card-size-16"> &lt;ends&gt;<br>badly</span>'
    )


@settings(max_examples=300, deadline=None)
@given(st.text(alphabet=st.sampled_from("<>&\"'/=:;\n ascriptjvonerrohf") | st.characters(), max_size=120))
def test_search_card_html_text_of_any_card_reads_back_unchanged_with_no_markup_of_its_own(text: str) -> None:
    reader = ReadBack.of(
        render_card_html(
            card_runs(text, (IndexedFormattingSpan(RunEmphasis.BOLD, 0, 1),) if text else (), ())
        )
    )
    assert reader.plain == text
    assert_only_allowed_markup(reader)


# ------------------------------------------------------------------------------------------------
# ac4: the rendered coverage is the stored spans'
# ------------------------------------------------------------------------------------------------


@st.composite
def stored_card(draw: st.DrawFn) -> tuple[str, list[IndexedFormattingSpan], list[IndexedFontSizeSpan]]:
    text = draw(st.text(alphabet=st.sampled_from("abc <&>\n\"'é"), min_size=1, max_size=60))
    length = len(text)
    offsets = st.tuples(st.integers(0, length - 1), st.integers(1, length)).filter(
        lambda pair: pair[0] < pair[1]
    )
    formatting: list[IndexedFormattingSpan] = []
    for start, end in draw(st.lists(offsets, max_size=12)):
        emphasis = draw(st.sampled_from(list(RunEmphasis)))
        colour = (
            draw(st.sampled_from(sorted(HIGHLIGHT_COLOURS))) if emphasis is RunEmphasis.HIGHLIGHT else None
        )
        formatting.append(IndexedFormattingSpan(emphasis, start, end, colour))
    sizes = [
        IndexedFontSizeSpan(start, end, draw(st.integers(1, 200)))
        for start, end in draw(st.lists(offsets, max_size=4))
    ]
    return text, formatting, sizes


@settings(max_examples=400, deadline=None)
@given(stored_card())
def test_search_card_html_coverage_equals_the_stored_spans_reading(
    card: tuple[str, list[IndexedFormattingSpan], list[IndexedFontSizeSpan]],
) -> None:
    """ac4: `formatting_sha256` of the rendered card equals it over the stored spans."""
    text, formatting, sizes = card
    reader = ReadBack.of(render_card_html(card_runs(text, formatting, sizes)))
    assert reader.plain == text
    rendered_formatting, rendered_sizes = reader.spans()
    stored = formatting_sha256(
        [_parser_span(span) for span in formatting],
        [
            FontSizeSpan(start_offset=s.start_offset, end_offset=s.end_offset, half_points=s.half_points)
            for s in sizes
        ],
    )
    assert formatting_sha256(rendered_formatting, rendered_sizes) == stored


def test_search_card_html_coverage_of_a_fixture_card_written_by_hand() -> None:
    """ac4 on one card, coverage read off by hand: underline 9-22, cyan 9-15, bold 28-33, size 22 from 9."""
    text = "Invented growth always ends badly"
    formatting = [
        IndexedFormattingSpan(RunEmphasis.UNDERLINE, 9, 15),
        IndexedFormattingSpan(RunEmphasis.UNDERLINE, 15, 22),
        IndexedFormattingSpan(RunEmphasis.HIGHLIGHT, 9, 15, "cyan"),
        IndexedFormattingSpan(RunEmphasis.BOLD, 28, 33),
    ]
    sizes = [IndexedFontSizeSpan(9, 33, 22)]
    reader = ReadBack.of(render_card_html(card_runs(text, formatting, sizes)))
    covered: dict[str, list[int]] = {}
    for offset, names in enumerate(reader.classes):
        for name in names:
            covered.setdefault(name, []).append(offset)
    assert {name: (offsets[0], offsets[-1] + 1, len(offsets)) for name, offsets in covered.items()} == {
        "card-underline": (9, 22, 13),
        "card-highlight": (9, 15, 6),
        "card-highlight-cyan": (9, 15, 6),
        "card-bold": (28, 33, 5),
        "card-size-22": (9, 33, 24),
    }
    expected = formatting_sha256(
        [_parser_span(span) for span in formatting],
        [FontSizeSpan(start_offset=9, end_offset=33, half_points=22)],
    )
    assert formatting_sha256(*reader.spans()) == expected


@pytest.mark.parametrize("emphasis", list(RunEmphasis))
def test_search_card_html_has_a_class_for_every_emphasis(emphasis: RunEmphasis) -> None:
    assert is_allowed_class(EMPHASIS_CLASSES[emphasis])
