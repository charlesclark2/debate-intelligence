"""`scripts/diff_cite_lines_by_their_place.py`: the store's cards against `v1-e31-t31`'s reading, in counts.

An invented file holds one card of each effect, written to be it: a line under a tag, a later line of a
cite, a cite in the tag style, a body with a white run, and a card the rules leave alone. The "store"
side is the checkout's parser with the cite-by-place pass left out and white read as highlight, which
is how `2026.10.20-docx-6` read it. Every expected count is written by hand from the file.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence import style_classifier
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))

import diff_cite_lines_by_their_place as diff  # noqa: E402

BODY = "Reserve margins fall below safe levels within two summers, the invented desk finds."


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite(name: str) -> str:
    return paragraph_xml(
        run_xml(name, character_style="Style13ptBold") + run_xml(", Analyst, Invented Review")
    )


def plain(text: str, style: str | None = None) -> str:
    return paragraph_xml(run_xml(text), style=style)


def body(*, white: bool = False) -> str:
    runs = run_xml(BODY, underline="single")
    if white:
        runs += run_xml(" and nobody plans for it", highlight="white")
    return paragraph_xml(runs)


FILE = build_docx(
    plain("Invented Negative", "Heading1")
    # 1-3: a line under a tag
    + tag("Moratoria raise prices")
    + plain("reported by an invented desk, 2026, https://example.org/a")
    + body()
    # 4-7: a later line of a cite
    + tag("Older plants fail first")
    + cite("Okonkwo 26")
    + plain("accessed through https://example.org/b")
    + body()
    # 8-10: a cite in the tag style
    + tag("Reserve margins recover")
    + plain("Lindqvist 25, Professor, Invented University", "Heading4")
    + body()
    # 11-13: white highlight
    + tag("Fleets age out")
    + cite("Adebayo 24")
    + body(white=True)
    # 14-16: nothing for the rules
    + tag("Prices settle")
    + cite("Mensah 23")
    + body()
)


class ReadAsDocx6(DebateDocxParser):
    def _cite_lines_by_their_place(self, assembled: Any) -> dict[int, str]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return {}


def parse(parser: DebateDocxParser) -> ParsedDocument:
    source = SourceDocument(
        sha256="0" * 64,
        byte_size=len(FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hsld26",
        first_seen_snapshot=date(2026, 10, 27),
        last_seen_snapshot=date(2026, 10, 27),
    )
    document = parser.parse(FILE, source, source_path="invented.docx")
    assert isinstance(document, ParsedDocument)
    return document


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> ParsedDocument:
    with monkeypatch.context() as patched:
        patched.setattr(style_classifier, "COLOURS_NOT_READ_AS_HIGHLIGHT", frozenset())
        return parse(ReadAsDocx6())


def test_each_card_is_counted_by_its_effect(stored: ParsedDocument) -> None:
    after = parse(DebateDocxParser())

    compared = diff.compare(stored.cards, after)

    assert dict(compared.cards_gaining_a_cite) == {"line under a tag": 1, "cite in the tag style": 1}
    assert dict(compared.cards_whose_cite_gains_a_line) == {"later line of a cite": 1}
    assert (compared.cards_losing_only_white_highlight, compared.white_highlight_spans_removed) == (1, 1)
    assert compared.cards_unchanged == 1
    assert dict(compared.other_cards_changed) == {}
    assert (compared.cards_the_store_holds_that_vanish, compared.new_cards) == (0, 0)
    assert compared.cards_changed_only_in_their_heading_path == 0
    assert compared.gained_by_last_paragraph == {
        3: "line under a tag",
        7: "later line of a cite",
        10: "cite in the tag style",
    }


def test_a_card_changed_any_other_way_is_named_by_its_fields(stored: ParsedDocument) -> None:
    after = parse(DebateDocxParser())
    last = after.cards[-1]
    changed = after.model_copy(
        update={"cards": (*after.cards[:-1], last.model_copy(update={"evidence_text": "Something else."}))}
    )

    compared = diff.compare(stored.cards, changed)

    assert dict(compared.other_cards_changed) == {"evidence_text": 1}
    assert compared.cards_unchanged == 0


def test_the_sample_is_one_line_a_file_and_the_same_for_a_seed() -> None:
    candidates = [
        (
            f"hsld26/{file:064x}",
            {"line": f"l{file}-{n}", "tag_above": "", "body_below": "", "element_index": str(n)},
        )
        for file in range(30)
        for n in range(3)
    ]

    drawn = diff.draw_sample(candidates, seed=7, size=20)

    assert len(drawn) == 20
    assert len({file for file, _ in drawn}) == 20
    assert drawn == diff.draw_sample(list(reversed(candidates)), seed=7, size=20)
    assert drawn != diff.draw_sample(candidates, seed=8, size=20)


def test_the_candidates_are_the_lines_under_a_tag() -> None:
    after = parse(DebateDocxParser())

    (candidate,) = diff._candidates(after)  # pyright: ignore[reportPrivateUsage]

    assert candidate == {
        "line": "reported by an invented desk, 2026, https://example.org/a",
        "tag_above": "Moratoria raise prices",
        "body_below": BODY,
        "element_index": "2",
    }


def test_the_sample_is_refused_inside_the_repository_or_outside_the_data_directory(tmp_path: Path) -> None:
    inside = REPOSITORY / "build" / "sample.csv"
    assert diff.main(["--data-dir", str(tmp_path), "--sample-out", str(inside), "--caselist", "x"]) == 2
    elsewhere = tmp_path.parent / "elsewhere.csv"
    assert (
        diff.main(["--data-dir", str(tmp_path / "data"), "--sample-out", str(elsewhere), "--caselist", "x"])
        == 2
    )
    assert not inside.exists() and not elsewhere.exists()


def test_the_index_gives_each_no_cite_document_by_its_representatives_file(tmp_path: Path) -> None:
    index = tmp_path / "search-index.sqlite"
    connection = sqlite3.connect(index)
    connection.executescript(
        "CREATE TABLE documents (doc_id INTEGER, caselist TEXT, cite TEXT);"
        "CREATE TABLE occurrences"
        " (doc_id INTEGER, ordinal INTEGER, source_sha256 TEXT, last_element_index INTEGER);"
        "INSERT INTO documents VALUES (1, 'hsld26', ''), (2, 'hsld26', '  '), (3, 'hsld26', 'Okonkwo 26');"
        "INSERT INTO occurrences VALUES (1, 0, 'a', 7), (1, 1, 'b', 9), (2, 0, 'a', 12), (3, 0, 'a', 15);"
    )
    connection.commit()
    connection.close()

    assert diff.no_cite_documents(index) == {("hsld26", "a"): (7, 12)}


def test_the_sample_files_say_nothing_of_where_a_row_came_from_but_the_key(tmp_path: Path) -> None:
    drawn = [("hsld26/" + "a" * 64, {"line": "l", "tag_above": "t", "body_below": "b", "element_index": "4"})]
    out = tmp_path / "sample.csv"

    diff.write_sample(drawn, out)

    assert out.read_text(encoding="utf-8").splitlines() == [
        "sample_row,line,tag_above,body_below_first_200,verdict",
        "1,l,t,b,",
    ]
    key = [
        json.loads(line) for line in out.with_suffix(".key.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert key == [{"sample_row": 1, "source": "hsld26/" + "a" * 64, "element_index": 4}]
