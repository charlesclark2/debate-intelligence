"""Copy card's HTML and text: the fixed style table, escaping, and every formatting span kept (`v1-e39-t06`).

The style table is written out by hand below, from the E33 writer's template (`base.docx`'s
`StyleUnderline`, `Emphasis`, `Style13ptBold`, `UndertagChar`, `AnalyticChar`) and OOXML's highlight
colours (working agreement 6). The read-back here parses the copied HTML with the standard library's
parser and inverts that table; `browser/test_search_pages_in_chromium.py` pastes the same HTML into
an editable region in Chromium and reads that back too (ac2).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import pytest

from debate_api.app import PRIVATE_NO_STORE
from debate_api.copy_card import (
    EMPHASIS_STYLES,
    HIGHLIGHT_STYLES,
    PROVENANCE_STYLE,
    TAG_STYLE,
    copied_card,
    font_size_style,
)
from debate_core.domain.file_provenance import formatting_sha256
from debate_core.domain.search_card_html import HIGHLIGHT_COLOURS
from debate_core.domain.style_profile import RunEmphasis

FEATURED_LINE = "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Neg vs. Invented Invitational Round 4]"


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def card_named(world: Any, name: str) -> Any:
    caselist, cluster_id = world.card_path(name).split("/")[2:4]
    with world.services.search_index.lease() as search:
        return search.card(caselist, cluster_id)


def document_named(world: Any, name: str) -> Any:
    return next(one for one in world.corpus if one.doc_id == world.cards[name])


# ------------------------------------------------------------------------------------------------
# The table
# ------------------------------------------------------------------------------------------------


def test_the_emphasis_table_is_the_verbatim_templates_styles() -> None:
    assert dict(EMPHASIS_STYLES) == {
        RunEmphasis.UNDERLINE: "text-decoration:underline",
        RunEmphasis.EMPHASIS: "font-weight:bold;text-decoration:underline",
        RunEmphasis.CITE: "font-weight:bold;font-size:13pt",
        RunEmphasis.UNDERTAG: "color:#385623",
        RunEmphasis.ANALYTIC: "font-weight:bold;color:#1F3864",
        RunEmphasis.BOLD: "font-weight:bold",
        RunEmphasis.SHRUNK: "font-size:smaller",
        RunEmphasis.HEADING: "font-weight:bold;font-size:larger",
    }
    assert set(EMPHASIS_STYLES) | {RunEmphasis.HIGHLIGHT} == set(RunEmphasis)


def test_the_highlight_table_is_words_rgb_colours_and_names_every_colour_the_card_page_knows() -> None:
    assert dict(HIGHLIGHT_STYLES) == {
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
    assert set(HIGHLIGHT_STYLES) == HIGHLIGHT_COLOURS


@pytest.mark.parametrize(
    ("half_points", "expected"),
    [
        (22, "font-size:11pt"),
        (21, "font-size:10.5pt"),
        (1, "font-size:0.5pt"),
        (16, "font-size:8pt"),
        (9999, "font-size:4999.5pt"),
        (0, None),
        (-4, None),
        (10000, None),
    ],
)
def test_a_size_in_half_points_is_written_in_points(half_points: int, expected: str | None) -> None:
    assert font_size_style(half_points) == expected


def test_no_two_entries_of_the_table_are_the_same_declarations_so_each_reads_back_as_itself() -> None:
    declarations = [*EMPHASIS_STYLES.values(), *HIGHLIGHT_STYLES.values()]

    assert len(set(declarations)) == len(declarations)
    assert not any(re.fullmatch(r"font-size:\d+(\.5)?pt", one) for one in declarations)


# ------------------------------------------------------------------------------------------------
# Reading the copy back
# ------------------------------------------------------------------------------------------------


class CopyReader(HTMLParser):
    """Each paragraph of the copy: its own style, its text, and each character's span styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[dict[str, Any]] = []
        self._spans: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        style = dict(attrs).get("style") or ""
        if tag == "p":
            self.paragraphs.append({"style": style, "text": [], "styles": []})
        elif tag == "span":
            self._spans.append(style)
        elif tag == "br":
            self._add("\n")
        else:
            raise AssertionError(f"the copy writes only p, span and br; it wrote <{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._spans.pop()

    def handle_data(self, data: str) -> None:
        for character in data:
            self._add(character)

    def _add(self, character: str) -> None:
        self.paragraphs[-1]["text"].append(character)
        self.paragraphs[-1]["styles"].append(tuple(self._spans))


def paragraphs_of(html: str) -> list[dict[str, Any]]:
    reader = CopyReader()
    reader.feed(html)
    reader.close()
    return reader.paragraphs


def test_the_copy_read_back_carries_every_formatting_span_of_the_stored_card(
    student: Any, read_back: Any
) -> None:
    """ac2 in Python: the copy's spans give the stored spans' `formatting_sha256` coverage exactly."""
    stored = document_named(student, "featured")
    copied = copied_card(card_named(student, "featured"))

    body = paragraphs_of(copied.html)[-1]
    spans, sizes = read_back(body["styles"])

    assert "".join(body["text"]) == stored.text
    assert formatting_sha256(spans, sizes) == formatting_sha256(
        stored.formatting_spans, stored.font_size_spans
    )


def test_the_read_back_tells_apart_two_cards_whose_formatting_differs(student: Any, read_back: Any) -> None:
    """The comparison above can fail: one emphasis dropped from the copy changes the reading."""
    stored = document_named(student, "featured")
    copied = copied_card(card_named(student, "featured"))
    without_bold = copied.html.replace(f'<span style="{EMPHASIS_STYLES[RunEmphasis.BOLD]}">', "<span>")

    spans, sizes = read_back(
        [tuple(s for s in styles if s) for styles in paragraphs_of(without_bold)[-1]["styles"]]
    )

    assert formatting_sha256(spans, sizes) != formatting_sha256(
        stored.formatting_spans, stored.font_size_spans
    )


def test_a_runs_spans_nest_its_emphases_then_its_colours_then_its_sizes_innermost(student: Any) -> None:
    """Written from the featured card's spans: `winds raise` is underlined, cyan and 11 points; the shrunk
    `second paragraph ` is 8 points; the line break is inside the yellow highlight that crosses it."""
    html = copied_card(card_named(student, "featured")).html

    winds = '<span style="text-decoration:underline"><span style="background-color:#00FFFF">'
    assert winds + '<span style="font-size:11pt">winds raise</span></span></span>' in html
    assert (
        '<span style="font-size:smaller"><span style="font-size:8pt">second paragraph </span></span>' in html
    )
    assert '<span style="background-color:#FFFF00"><br></span>' in html


def test_the_copy_is_the_tag_the_cite_the_provenance_line_below_it_then_the_card(student: Any) -> None:
    copied = copied_card(card_named(student, "featured"))

    tag, cite, line, body = paragraphs_of(copied.html)
    assert (tag["style"], "".join(tag["text"])) == (TAG_STYLE, "Zephyr winds raise granite costs")
    assert "".join(cite["text"]) == "Lindqvist 26, Invented Quarterly, 2026"
    assert cite["styles"][0] == (EMPHASIS_STYLES[RunEmphasis.CITE],) and cite["styles"][-1] == ()
    assert (line["style"], "".join(line["text"])) == (PROVENANCE_STYLE, FEATURED_LINE)
    assert body["style"] == ""
    assert copied.html.startswith(f'<p style="{TAG_STYLE}">Zephyr winds raise granite costs</p><p>')


def test_the_plain_text_is_the_same_four_parts_one_to_a_line(student: Any) -> None:
    stored = document_named(student, "featured")

    copied = copied_card(card_named(student, "featured"))

    assert copied.text == "\n".join(
        [
            "Zephyr winds raise granite costs",
            "Lindqvist 26, Invented Quarterly, 2026",
            FEATURED_LINE,
            stored.text,
        ]
    )


def test_a_camp_card_copies_with_its_openev_line(student: Any) -> None:
    copied = copied_card(card_named(student, "camp"))

    assert paragraphs_of(copied.html)[2]["text"] == list(
        "[OpenEv: Cascade Institute 2026 — Policy, Invented Adv CP]"
    )


# ------------------------------------------------------------------------------------------------
# Escaping, and no card text in a style
# ------------------------------------------------------------------------------------------------


def test_hostile_card_text_is_escaped_in_the_copy_and_reads_back_as_written(student: Any) -> None:
    stored = document_named(student, "hostile")
    copied = copied_card(card_named(student, "hostile"))

    for raw in ("<script", "<img", "<style", "<b>", "</p><style"):
        assert raw not in copied.html.replace("</p><p", "").replace("<p", "").replace("</p>", "")
    tag, cite, _line, body = paragraphs_of(copied.html)
    assert "".join(tag["text"]) == stored.tag
    assert "".join(cite["text"]) == stored.cite
    assert "".join(body["text"]) == stored.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in copied.html
    assert "&quot;onerror=alert(1)&quot;" in copied.html


def test_a_colour_outside_the_table_gets_no_colour_and_its_name_is_not_copied(student: Any) -> None:
    copied = copied_card(card_named(student, "hostile"))

    assert "chartreuse" not in copied.html
    assert "background" not in copied.html


def test_every_style_attribute_is_one_of_the_tables_own_strings(student: Any) -> None:
    allowed = {
        *EMPHASIS_STYLES.values(),
        *HIGHLIGHT_STYLES.values(),
        TAG_STYLE,
        PROVENANCE_STYLE,
        *(style for half_points in range(1, 10000) if (style := font_size_style(half_points))),
    }
    for name in ("featured", "long", "hostile", "camp", "public forum"):
        html = copied_card(card_named(student, name)).html
        styles = re.findall(r'style="([^"]*)"', html)
        assert styles and set(styles) <= allowed, name
        assert len(re.findall(r"style=", html)) == len(styles), name


# ------------------------------------------------------------------------------------------------
# The route
# ------------------------------------------------------------------------------------------------


def test_the_copy_route_answers_the_cards_html_and_text_privately(student: Any) -> None:
    response = student.browser.get(student.card_path("featured") + "/copy")

    assert response.status_code == 200
    assert response.headers["cache-control"] == PRIVATE_NO_STORE
    assert response.json() == {
        "html": copied_card(card_named(student, "featured")).html,
        "text": copied_card(card_named(student, "featured")).text,
    }


def test_the_copy_route_for_a_card_not_in_the_index_answers_a_message(student: Any) -> None:
    response = student.browser.get(f"/cards/hsld26/{999:064x}/copy")

    assert response.status_code == 404
    assert response.json() == {"message": "That card is not in the search any more."}


def test_the_copy_route_without_a_session_sends_the_browser_to_sign_in(world: Any) -> None:
    response = world.browser.get(world.card_path("featured") + "/copy")

    assert response.status_code == 302
    assert response.headers["location"].startswith(world.authorize_url)
