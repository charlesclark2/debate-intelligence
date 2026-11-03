"""`scripts/sample_card_boundaries.py`: the sample of `v1-e31-t22`'s counts, on invented files.

The end-to-end test builds a store of two invented sources, runs the count to save the positions,
and answers the sample by the keys each question offers. Every expectation is written by hand from
the files (working agreement 6).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose

from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry, SourceOutcome
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.card_boundaries import LongBodyKind, ending_of, paragraphs_inside
from debate_core.evidence.near_duplicates import shingles
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_card_boundaries as counting  # noqa: E402
import sample_card_boundaries as script  # noqa: E402

CASELIST = "testcl26"
SNAPSHOT = date(2026, 10, 19)
PROFILE = DebateDocxParser().profile


def para(text: str, *, style: str | None = None, **formatting: Any) -> str:
    return paragraph_xml(run_xml(text, **formatting), style=style)


def cite(name: str) -> str:
    return paragraph_xml(
        run_xml(name, bold=True, half_points=CITE_SIZE)
        + run_xml(f", Adaeze Okonkwo, invented for this test, {SOURCE}", half_points=READING_SIZE)
    )


def underlined(text: str) -> str:
    return para(text, underline="single", half_points=SMALL_PRINT)


def numbered(stem: str, count: int) -> str:
    return " ".join(f"{stem}{number}" for number in range(count))


LONG_PARAGRAPH = prose(11_500)


def long_file(last_paragraph: str = LONG_PARAGRAPH) -> bytes:
    return build_docx(
        para("First tag", style="Heading4")
        + cite("Okonkwo 26")
        + underlined(LONG_PARAGRAPH)
        + para("Reserve margins fall in every region", half_points=READING_SIZE)
        + para(f"Lindqvist 2019, invented review of grid planning, {SOURCE}", highlight="yellow")
        + underlined(last_paragraph)
        + para("Second tag", style="Heading4")
        + cite("Ferreira 25")
        + underlined(numbered("third", 70))
    )


LONG_FILE = long_file()
#: The holder: A's words, a line read as nothing, B's words; then B's card and A's, each under a cite.
#: Then a body of 100 words and two cuts of it sharing 20, too few to overlap: counted, never drawn.
HOLDING_FILE = build_docx(
    para("Holding tag", style="Heading4")
    + cite("Okonkwo 26")
    + underlined(numbered("first", 80))
    + para("A tag typed in body style", half_points=READING_SIZE)
    + underlined(numbered("second", 80))
    + cite("Lindqvist 2019")
    + underlined(numbered("second", 80))
    + cite("Ferreira 25")
    + underlined(numbered("first", 80))
    + cite("Achebe 24")
    + underlined(numbered("run", 100))
    + cite("Mensah 23")
    + underlined(" ".join(numbered("run", 100).split()[:60]))
    + cite("Tanaka 22")
    + underlined(" ".join(numbered("run", 100).split()[40:]))
)
LONG, HOLDING = hashlib.sha256(LONG_FILE).hexdigest(), hashlib.sha256(HOLDING_FILE).hexdigest()


def parsed(content: bytes, sha256: str) -> ParsedDocument:
    source = SourceDocument(
        sha256=sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    document = DebateDocxParser().parse(content, source, source_path="invented.docx")
    assert isinstance(document, ParsedDocument)
    return document


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    store = LocalParsedStore(tmp_path)
    entries: list[SourceEntry] = []
    for sha256, content in ((LONG, LONG_FILE), (HOLDING, HOLDING_FILE)):
        document = parsed(content, sha256)
        entry = SourceEntry.model_validate(
            {
                "caselist": CASELIST,
                "snapshot": "2026-10-19",
                "source_sha256": sha256,
                "parser_version": DOCX_PARSER_VERSION,
                "profile_version": document.profile_version,
                "fingerprint_version": "card-fingerprint-v4",
                "source_format": SourceFormat.DOCX,
                "byte_size": len(content),
                "outcome": SourceOutcome.PARSED,
                "cards": len(document.cards),
            }
        )
        record = DocumentRecord.from_parsed_document(
            document,
            caselist=CASELIST,
            snapshot="2026-10-19",
            fingerprint_version="card-fingerprint-v4",
            camp=None,
        )
        asyncio.run(store.write_source(CASELIST, DOCX_PARSER_VERSION, entry, record))
        entries.append(entry)
        blob = tmp_path / "blobs" / "sha256" / sha256[:2] / sha256[2:4] / sha256
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(content)
    asyncio.run(
        store.write_aggregates(CASELIST, DOCX_PARSER_VERSION, index=entries, failures=[], occurrences=[])
    )
    return tmp_path


@pytest.fixture
def operator_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("operator")


def counted(data_dir: Path, operator_dir: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    candidates = operator_dir / "candidates.jsonl"
    counting.main(
        [
            "--data-dir",
            str(data_dir),
            "--caselist",
            CASELIST,
            "--workers",
            "1",
            "--save-candidates",
            str(candidates),
        ]
    )
    capsys.readouterr()
    return candidates


# ------------------------------------------------------------------------------------------------
# The plan and the draw
# ------------------------------------------------------------------------------------------------


def test_the_plan_is_ten_of_each_long_body_kind_and_ten_of_each_holder_band() -> None:
    assert [(stratum.count, stratum.group, stratum.planned) for stratum in script.STRATA] == [
        ("long-body", "a short line above a cite-shaped paragraph inside", 10),
        ("long-body", "a cite-shaped paragraph inside, with no short line above it", 10),
        ("long-body", "no cite inside, marked up", 10),
        ("long-body", "no cite inside, plain prose", 10),
        ("two-cards-in-one", "body under 1,000 words", 10),
        ("two-cards-in-one", "body of 1,000 words or more", 10),
    ]


def candidate(number: int, fingerprint: str | None = None) -> Any:
    return script._Candidate(CASELIST, (f"{number:064d}", 0), fingerprint or f"text{number}", None)  # pyright: ignore[reportPrivateUsage]


def test_each_stratum_draws_its_plan_one_draw_a_text_and_the_seed_draws_the_same_again() -> None:
    strata = (script.Stratum("long-body", "one", 2), script.Stratum("long-body", "two", 3))
    population = {
        0: [candidate(1), candidate(2), candidate(3), candidate(4)],
        # The same text twice and once more: two texts, both drawn, short of the plan.
        1: [candidate(5, "same"), candidate(6, "same"), candidate(7)],
    }
    drawn = script.draw(population, 11, strata)
    assert Counter(item.stratum for item in drawn) == {0: 2, 1: 2}
    second = {item.card[0][-1] for item in drawn if item.stratum == 1}
    assert "7" in second
    assert len(second & {"5", "6"}) == 1
    assert script.draw(population, 11, strata) == drawn


def test_the_order_does_not_follow_the_strata() -> None:
    strata = (script.Stratum("long-body", "one", 10), script.Stratum("long-body", "two", 10))
    population = {0: [candidate(n) for n in range(10)], 1: [candidate(n) for n in range(10, 20)]}
    orders = {tuple(item.stratum for item in script.draw(population, seed, strata)) for seed in range(5)}
    assert (0,) * 10 + (1,) * 10 not in orders


def test_a_text_drawn_in_one_stratum_is_not_drawn_in_another() -> None:
    strata = (script.Stratum("long-body", "one", 1), script.Stratum("long-body", "two", 1))
    drawn = script.draw({0: [candidate(1, "shared")], 1: [candidate(2, "shared")]}, 3, strata)
    assert [item.stratum for item in drawn] == [0]


# ------------------------------------------------------------------------------------------------
# What an item shows
# ------------------------------------------------------------------------------------------------

_STYLE = re.compile(r"\x1b\[[0-9;]*m")


def item_of(content: bytes, sha256: str, *, pieces: tuple[str, str] | None = None) -> Any:
    document = parsed(content, sha256)
    card = document.cards[0]
    ending, closer = ending_of(document, card)
    stratum = 4 if pieces else 0
    piece_sets = (shingles(pieces[0]), shingles(pieces[1])) if pieces else None
    inside = tuple(paragraphs_inside(document, card, PROFILE))
    return script.Item(
        drawn=script.Drawn(stratum, CASELIST, (sha256, 0)),
        card=card,
        inside=inside,
        glimpses=() if pieces else script._glimpses_of(inside, PROFILE),  # pyright: ignore[reportPrivateUsage]
        ending=ending,
        closer=closer.text if closer else None,
        pieces=piece_sets,
        piece_words=(80, 80) if pieces else (0, 0),
    )


def test_a_long_body_shows_each_paragraph_its_reading_and_marks_and_what_ended_it() -> None:
    shown = _STYLE.sub("", script.render_item(item_of(LONG_FILE, LONG), 160))
    rows = [line for line in shown.splitlines() if re.match(r"\s+\d+ ", line)]
    assert [row.split()[1] for row in rows] == ["tag", "cite", "body", "NOTHING", "body", "body"]
    assert "▸ Reserve margins fall in every region" in rows[3]
    assert "◆ Lindqvist 2019, invented review of grid planning" in rows[4]
    # A paragraph of 1,900 words is shown by its opening and its end.
    assert " … " in rows[2]
    assert "Ended by a tag in a debate style: Second tag" in shown
    assert shown.rstrip().endswith("What is this body?")


def test_a_body_holding_two_cards_shows_how_much_of_each_paragraph_is_in_each() -> None:
    item = item_of(HOLDING_FILE, HOLDING, pieces=(numbered("first", 80), numbered("second", 80)))
    shown = _STYLE.sub("", script.render_item(item, 160))
    rows = [line for line in shown.splitlines() if re.match(r"\s+\d+ ", line)]
    assert [re.findall(r"[AB]\s*(\d+)%", row) for row in rows] == [
        ["0", "0"],
        ["0", "0"],
        ["100", "0"],
        ["0", "0"],
        ["0", "100"],
    ]
    assert "A tag typed in body style" in rows[3]
    assert "Ended by a cite, starting a card with no tag" in shown
    assert "Are they two cards, or one card cut twice?" in shown


def test_a_short_body_paragraph_in_a_long_run_is_shown_with_the_paragraphs_beside_it() -> None:
    paragraphs = [underlined(prose(400)) for _ in range(12)]
    paragraphs[5] = underlined("A short paragraph of the body, twelve words or so, in the middle.")
    document_file = build_docx(para("A tag", style="Heading4") + cite("Okonkwo 26") + "".join(paragraphs))
    shown = _STYLE.sub("", script.render_item(item_of(document_file, "e" * 64), 160))
    rows = [line for line in shown.splitlines() if re.match(r"\s+\d+ ", line)]
    assert [int(row.split()[0]) for row in rows] == [1, 2, 3, 4, 7, 8, 9, 12, 13, 14]


def test_where_one_part_gives_way_to_the_other_is_shown_however_long_the_body() -> None:
    first, second = numbered("first", 240).split(), numbered("second", 240).split()
    paragraphs = [
        underlined(" ".join(words[start : start + 40]))
        for words in (first, second)
        for start in range(0, 240, 40)
    ]
    holder = build_docx(para("A tag", style="Heading4") + cite("Okonkwo 26") + "".join(paragraphs))
    item = item_of(holder, "e" * 64, pieces=(" ".join(first), " ".join(second)))
    shown = _STYLE.sub("", script.render_item(item, 160))
    rows = [line for line in shown.splitlines() if re.match(r"\s+\d+ ", line)]
    # The last of A's six paragraphs is the eighth row, the first of B's the ninth.
    assert [int(row.split()[0]) for row in rows] == [1, 2, 3, 4, 8, 9, 10, 12, 13, 14]


FIRST, SECOND = numbered("first", 80), numbered("second", 80)
MISSED = "a missed tag and Mensah 2024 cite"


def one_paragraph_holder(between: str) -> Any:
    holder = build_docx(
        para("A tag", style="Heading4") + cite("Okonkwo 26") + underlined(f"{FIRST} {between} {SECOND}")
    )
    return item_of(holder, "e" * 64, pieces=(FIRST, SECOND))


def test_where_a_ends_and_b_begins_is_shown_word_by_word_inside_one_paragraph() -> None:
    shown = script.render_item(one_paragraph_holder(MISSED), 160)
    plain = _STYLE.sub("", shown)
    assert "A is words 1 to 80 of 167; B is words 88 to 167; 7 words between them." in plain
    assert "[… 65 words before not shown …]" in plain
    assert "[… 65 words after not shown …]" in plain
    words = set(plain.split())
    assert "first65" in words and "first64" not in words
    assert "second14" in words and "second15" not in words
    # A's words underlined, the words between in bold, B's reversed.
    assert "\x1b[4mfirst79\x1b[0m \x1b[1ma\x1b[0m" in shown
    assert "\x1b[1mcite\x1b[0m \x1b[7msecond0\x1b[0m" in shown


def test_a_long_gap_between_a_and_b_keeps_its_two_ends() -> None:
    plain = _STYLE.sub("", script.render_item(one_paragraph_holder(numbered("gap", 200)), 160))
    assert "200 words between them." in plain
    assert "[… 100 words between not shown …]" in plain
    words = set(plain.split())
    assert {"gap49", "gap150"} <= words
    assert "gap50" not in words and "gap149" not in words


def test_parts_that_meet_are_said_to_meet_and_a_paragraph_start_is_marked() -> None:
    holder = build_docx(
        para("A tag", style="Heading4") + cite("Okonkwo 26") + underlined(FIRST) + underlined(SECOND)
    )
    plain = _STYLE.sub("", script.render_item(item_of(holder, "e" * 64, pieces=(FIRST, SECOND)), 1_000))
    assert "no word between them: they meet." in plain
    assert "first79 ¶ second0" in plain


def test_a_is_the_part_that_comes_first_inside_one_paragraph() -> None:
    text = f"{FIRST} {MISSED} {SECOND}"
    first_shared = script._first_shared  # pyright: ignore[reportPrivateUsage]
    assert first_shared(text, shingles(FIRST)) == 0
    assert first_shared(text, shingles(SECOND)) == 87


def test_a_long_paragraph_shows_each_name_with_a_year_inside_it() -> None:
    long_paragraph = prose(1_200) + " As Mensah 2024 argued in an invented study, " + prose(600)
    plain = _STYLE.sub(
        "",
        script.render_item(
            item_of(build_docx(cite("Okonkwo 26") + underlined(long_paragraph)), "e" * 64), 200
        ),
    )
    assert "Each name with a year inside the paragraphs over 150 words" in plain
    [glimpse] = [
        line for line in plain.splitlines() if "Mensah 2024" in line and line.lstrip().startswith("2:")
    ]
    assert "As Mensah 2024 argued in an invented study" in glimpse
    none = _STYLE.sub(
        "",
        script.render_item(item_of(build_docx(cite("Okonkwo 26") + underlined(prose(1_500))), "e" * 64), 200),
    )
    assert "Each name with a year" in none
    assert "  none." in none


def test_long_runs_of_body_paragraphs_are_shown_as_a_count() -> None:
    body = "".join(underlined(prose(400)) for _ in range(12))
    document_file = build_docx(para("A tag", style="Heading4") + cite("Okonkwo 26") + body)
    shown = _STYLE.sub("", script.render_item(item_of(document_file, "e" * 64), 160))
    rows = [line for line in shown.splitlines() if re.match(r"\s+\d+ ", line)]
    # Tag, cite and two body paragraphs first, three last; the seven between are counted.
    assert [int(row.split()[0]) for row in rows] == [1, 2, 3, 4, 12, 13, 14]
    assert re.search(r"… 7 body paragraphs, [\d,]+ words, not shown …", shown)


LINE_ABOVE = "  long-body | a short line above a cite-shaped paragraph inside"
CITE_INSIDE = "  long-body | a cite-shaped paragraph inside, with no short line above it"

# ------------------------------------------------------------------------------------------------
# Asking
# ------------------------------------------------------------------------------------------------


def test_each_item_is_answered_by_its_own_keys_and_q_stops_keeping_the_answers_so_far() -> None:
    items = [
        item_of(LONG_FILE, LONG),
        item_of(HOLDING_FILE, HOLDING, pieces=("first0", "second0")),
        item_of(LONG_FILE, LONG),
        item_of(LONG_FILE, LONG),
    ]
    # The fourth item is never asked: `q` on the third stops, and the `s` after it is not read.
    keys = iter(["t", "s", "x", "o", "q", "s"])
    shown: list[str] = []
    answered, stopped, _ = script.ask_about(
        items, ask=lambda _: next(keys), show=shown.append, columns=160, clock=lambda: 0.0
    )
    # `t` is no answer to a long body; `x` is no answer at all.
    assert answered == {(0, "several cards stored as one"): 1, (4, "one card cut twice"): 1}
    assert stopped is True
    assert shown[-1] == script.CLEAR_TERMINAL


def test_the_tallies_name_strata_and_answers_and_nothing_else() -> None:
    tallies = script.Tallies(
        seed=5,
        population={0: 256, 4: 900},
        drawn=Counter({0: 2, 4: 1}),
        answered=Counter({(0, "one card"): 1, (0, "unsure"): 1, (4, "one card cut twice"): 1}),
        asked=3,
        skipped=1,
        stopped=False,
        seconds_answering=61.4,
    )
    assert tallies.lines() == [
        "Card-boundary sample, seed 5: drew 3 of 60 planned, asked 3, answered 3 in 61 seconds.",
        "  not reproduced by this checkout's parser, and skipped: 1",
        LINE_ABOVE + ": distinct texts 256, planned 10, drawn 2",
        "    one card: 1",
        "    unsure: 1",
        CITE_INSIDE + ": distinct texts 0, planned 10, drawn 0",
        "  long-body | no cite inside, marked up: distinct texts 0, planned 10, drawn 0",
        "  long-body | no cite inside, plain prose: distinct texts 0, planned 10, drawn 0",
        "  two-cards-in-one | body under 1,000 words: distinct texts 900, planned 10, drawn 1",
        "    one card cut twice: 1",
        "  two-cards-in-one | body of 1,000 words or more: distinct texts 0, planned 10, drawn 0",
    ]


# ------------------------------------------------------------------------------------------------
# The command
# ------------------------------------------------------------------------------------------------


def test_the_sample_runs_on_the_counted_positions_and_appends_its_tallies(
    data_dir: Path, operator_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates = counted(data_dir, operator_dir, capsys)
    tallies = operator_dir / "tallies.txt"
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(script, "read_key", lambda prompt: "s" if "s several" in prompt else "t")
    code = script.main(
        [
            "--data-dir",
            str(data_dir),
            "--candidates",
            str(candidates),
            "--seed",
            "7",
            "--save-tallies",
            str(tallies),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    lines = tallies.read_text().splitlines()
    assert re.fullmatch(
        r"Card-boundary sample, seed 7: drew 2 of 60 planned, asked 2, answered 2 in \d+ seconds\.", lines[0]
    )
    assert lines[1:] == [
        LINE_ABOVE + ": distinct texts 1, planned 10, drawn 1",
        "    several cards stored as one: 1",
        CITE_INSIDE + ": distinct texts 0, planned 10, drawn 0",
        "  long-body | no cite inside, marked up: distinct texts 0, planned 10, drawn 0",
        "  long-body | no cite inside, plain prose: distinct texts 0, planned 10, drawn 0",
        "  two-cards-in-one | body under 1,000 words: distinct texts 1, planned 10, drawn 1",
        "    two cards: a boundary the parser missed: 1",
        "  two-cards-in-one | body of 1,000 words or more: distinct texts 0, planned 10, drawn 0",
    ]
    tally_text = tallies.read_text()
    for telltale in ("first0", "Reserve margins", "Okonkwo", "Holding tag", LONG, HOLDING):
        assert telltale not in tally_text
    # The text went to the terminal only.
    assert "A tag typed in body style" in printed


def test_a_holding_band_is_set_at_1000_words() -> None:
    assert script.holder_band(999) == "body under 1,000 words"
    assert script.holder_band(1_000) == "body of 1,000 words or more"


def write_source(data_dir: Path, sha256: str, stored: bytes, blob: bytes) -> None:
    """A source the store holds as `stored`'s parse, whose blob on disk is `blob`."""
    document = parsed(stored, sha256)
    entry = SourceEntry.model_validate(
        {
            "caselist": CASELIST,
            "snapshot": "2026-10-19",
            "source_sha256": sha256,
            "parser_version": DOCX_PARSER_VERSION,
            "profile_version": document.profile_version,
            "fingerprint_version": "card-fingerprint-v4",
            "source_format": SourceFormat.DOCX,
            "byte_size": len(stored),
            "outcome": SourceOutcome.PARSED,
            "cards": len(document.cards),
        }
    )
    record = DocumentRecord.from_parsed_document(
        document,
        caselist=CASELIST,
        snapshot="2026-10-19",
        fingerprint_version="card-fingerprint-v4",
        camp=None,
    )
    asyncio.run(LocalParsedStore(data_dir).write_source(CASELIST, DOCX_PARSER_VERSION, entry, record))
    path = data_dir / "blobs" / "sha256" / sha256[:2] / sha256[2:4] / sha256
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def test_an_item_the_parse_does_not_give_back_is_skipped_and_counted(data_dir: Path) -> None:
    changed = long_file(LONG_PARAGRAPH.replace("operators", "planners", 1))
    write_source(data_dir, "f" * 64, LONG_FILE, changed)
    versions = {CASELIST: DOCX_PARSER_VERSION}
    assert script.prepare([script.Drawn(0, CASELIST, ("f" * 64, 0))], data_dir, versions, PROFILE) == ([], 1)
    items, skipped = script.prepare([script.Drawn(0, CASELIST, (LONG, 0))], data_dir, versions, PROFILE)
    assert (len(items), skipped) == (1, 0)


def test_a_is_the_part_the_body_holds_first_in_whichever_order_the_count_named_them(data_dir: Path) -> None:
    holding = parsed(HOLDING_FILE, HOLDING)
    holder, b_card, a_card = (card.provenance.first_element_index for card in holding.cards[:3])
    versions = {CASELIST: DOCX_PARSER_VERSION}
    for pieces in (((HOLDING, a_card), (HOLDING, b_card)), ((HOLDING, b_card), (HOLDING, a_card))):
        [item], _ = script.prepare(
            [script.Drawn(4, CASELIST, (HOLDING, holder), pieces)], data_dir, versions, PROFILE
        )
        assert item.pieces == (shingles(numbered("first", 80)), shingles(numbered("second", 80)))


def test_the_sample_refuses_anything_but_a_terminal(data_dir: Path, operator_dir: Path) -> None:
    code = script.main(["--data-dir", str(data_dir), "--save-tallies", str(operator_dir / "tallies.txt")])
    assert code == 2
    assert not (operator_dir / "tallies.txt").exists()


def test_the_tallies_go_outside_the_repository_and_the_data_directory(data_dir: Path) -> None:
    with pytest.raises(SystemExit, match="outside the data directory"):
        script.main(["--data-dir", str(data_dir), "--save-tallies", str(data_dir / "tallies.txt")])
    with pytest.raises(SystemExit, match="outside the repository"):
        script.main(["--data-dir", str(data_dir), "--save-tallies", str(script.REPO_ROOT / "tallies.txt")])


def test_the_candidates_are_read_from_the_operators_home_by_default() -> None:
    assert counting.CANDIDATES == script.CANDIDATES


def test_the_kinds_drawn_are_the_kinds_the_count_names() -> None:
    assert {stratum.group for stratum in script.STRATA[:4]} == {kind.value for kind in LongBodyKind}
