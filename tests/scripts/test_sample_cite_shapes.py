"""`scripts/sample_cite_shapes.py`: the coach's sample of v1-e31-t19's cite rules (`v1-e31-t19`).

Every test reads an invented store: one file whose cards hold one paragraph of each stratum the
PM's plan names, written as the corpus writes them. Expectations are written by hand from the
file (working agreement 6).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose, qualifications

from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry, SourceOutcome
from debate_core.domain.caselist import SourceFormat
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sample_cite_shapes as script  # noqa: E402

CASELIST = "testcl26"
VERSION = "2026.10.18-docx-4"

Runs = list[tuple[str, dict[str, Any]]]


def paragraph(runs: Runs, style: str | None = None) -> str:
    return paragraph_xml("".join(run_xml(text, **formatting) for text, formatting in runs), style=style)


def tag(text: str) -> str:
    return paragraph([(text, {})], style="Heading4")


def cite(style: str | None = None) -> str:
    return paragraph(
        [
            ("Okonkwo 26", {"bold": True, "half_points": CITE_SIZE}),
            (f", Adaeze Okonkwo, invented for this test, {SOURCE}.", {"half_points": READING_SIZE}),
        ],
        style=style,
    )


BODY_TEXT = prose(240)


def body(style: str | None = None) -> str:
    return paragraph(
        [
            (BODY_TEXT[:60], {"half_points": SMALL_PRINT}),
            (BODY_TEXT[60:140], {"underline": "single", "highlight": "cyan", "half_points": SMALL_PRINT}),
            (BODY_TEXT[140:], {"half_points": SMALL_PRINT}),
        ],
        style=style,
    )


TAIL = f", professor of energy policy, Invented Institute of Grid Studies, {SOURCE}"
SENTENCE_TAIL = TAIL + ", a review of reserve margins in four regional markets."

#: Small print past 2,000 characters holding an ellipsis and a name with a year, 900 in.
LONG_GUESS = (
    prose(899)[:899]
    + " Lindqvist 2019 reached the same conclusion [...] and so did the audit. "
    + prose(1_400)
)[:2_300]
LONGER_GUESS = "Okonkwo 26, " + (LONG_GUESS + " " + prose(2_100))[:4_300]

#: Each card of the invented file, with the stratum of its one paragraph under test, by hand.
CARDS: list[tuple[str, int | None, str]] = [
    # A cite behind a first name, read as nothing before: bold name, under 200 characters.
    (
        tag("First tag") + paragraph([("Adaeze ", {}), ("Okonkwo 26", {"bold": True}), (TAIL, {})]) + body(),
        0,
        "taken, nothing",
    ),
    # The same, prose before: 200 characters and a full stop.
    (
        tag("Second tag")
        + paragraph([("Adaeze ", {}), ("Okonkwo 26", {"bold": True}), (SENTENCE_TAIL, {})])
        + body(),
        1,
        "taken, body",
    ),
    # Left: no bold, no bracket. Read as nothing.
    (tag("Third tag") + paragraph([("Adaeze Okonkwo 26" + TAIL, {})]) + body(), 2, "left, nothing"),
    # Left: no bold, no bracket, read as prose.
    (tag("Fourth tag") + paragraph([("Adaeze Okonkwo 26" + SENTENCE_TAIL, {})]) + body(), 3, "left, body"),
    # A style that maps to no unit: its cite, its body, and a short line it leaves.
    (
        tag("Fifth tag")
        + cite("NormalWeb")
        + body("NormalWeb")
        + paragraph([("Continued below", {})], "NormalWeb"),
        None,
        "unmapped",
    ),
    # A highlighted cite with a body below it.
    (
        tag("Sixth tag")
        + paragraph([("Okonkwo 26", {"bold": True, "highlight": "yellow"}), (", " + qualifications(588), {})])
        + body(),
        7,
        "highlighted, taken",
    ),
    # A highlighted cite with a tag below it: a card written as one paragraph.
    (
        tag("Seventh tag")
        + paragraph(
            [("Ferreira 25", {"bold": True, "highlight": "yellow"}), (", " + qualifications(587), {})]
        ),
        8,
        "highlighted, left",
    ),
    # A long guess with the cite style on a name inside it, after the card's cite.
    (
        tag("Eighth tag")
        + cite()
        + paragraph(
            [
                (LONG_GUESS[:900], {"half_points": 10}),
                ("Lindqvist 2019", {"character_style": "Style13ptBold", "half_points": 10}),
                (LONG_GUESS[914:], {"half_points": 10}),
            ]
        ),
        9,
        "hold, re-read",
    ),
    # A longer guess with the cite style on the name and year at its head: still held.
    (
        tag("Ninth tag")
        + cite()
        + paragraph(
            [
                ("Okonkwo 26", {"character_style": "Style13ptBold", "half_points": 10}),
                (LONGER_GUESS[10:], {"half_points": 10}),
            ]
        ),
        10,
        "hold, held",
    ),
]

FILE = build_docx("".join(card for card, _, _ in CARDS))
DIGEST = hashlib.sha256(FILE).hexdigest()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    blob = tmp_path / "blobs" / "sha256" / DIGEST[:2] / DIGEST[2:4] / DIGEST
    blob.parent.mkdir(parents=True)
    blob.write_bytes(FILE)
    version = tmp_path / "parsed" / CASELIST / VERSION
    version.mkdir(parents=True)
    records = [
        {"source_sha256": DIGEST, "outcome": "PARSED"},
        {"source_sha256": "0" * 64, "outcome": "UNSUPPORTED"},
    ]
    (version / "index.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))
    return tmp_path


def parsed_with_reads() -> tuple[list[Any], ParsedDocument]:
    source = script._Source(CASELIST, DIGEST, Path("unused"), Path("unused"), VERSION)  # pyright: ignore[reportPrivateUsage]
    parser = script._ReadingParser()  # pyright: ignore[reportPrivateUsage]
    document = parser.parse(FILE, script_source(source), source_path="sample.docx")
    assert isinstance(document, ParsedDocument)
    return parser.reads, document


def script_source(source: Any) -> Any:
    from datetime import date

    from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin

    return SourceDocument(
        sha256=source.sha256,
        byte_size=len(FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=date(2026, 10, 18),
        last_seen_snapshot=date(2026, 10, 18),
    )


def test_each_paragraph_under_test_is_in_its_stratum_and_nothing_else_is() -> None:
    reads, document = parsed_with_reads()
    found = script.strata_of(reads, document.sections, script._ReadingParser().profile)  # pyright: ignore[reportPrivateUsage]
    texts = [(stratum, document.sections[position].text[:20]) for stratum, position in found]

    assert texts == [
        (0, "Adaeze Okonkwo 26, p"),
        (1, "Adaeze Okonkwo 26, p"),
        (2, "Adaeze Okonkwo 26, p"),
        (3, "Adaeze Okonkwo 26, p"),
        (4, "Okonkwo 26, Adaeze O"),
        (5, BODY_TEXT[:20]),
        (6, "Continued below"),
        (7, "Okonkwo 26, Adaeze O"),
        (8, "Ferreira 25, Adaeze "),
        (9, LONG_GUESS[:20]),
        (10, "Okonkwo 26, Grid ope"),
    ]


def test_the_plan_is_the_one_the_pm_approved() -> None:
    planned = Counter[str]()
    for stratum in script.STRATA:
        if stratum.plan == script.FIRST_PLAN:
            planned[stratum.rule] += stratum.planned

    assert planned == {
        "a cite behind a first name or a title": 20,
        "a paragraph style that maps to no unit": 20,
        "a highlighted cite": 20,
        "the cite-style hold": 10,
    }
    assert [
        (s.side, s.planned) for s in script.STRATA if s.rule == "a paragraph style that maps to no unit"
    ] == [
        ("taken as a cite", 6),
        ("taken as body", 8),
        ("left as nothing", 6),
    ]


def _keys(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> list[str]:
    asked: list[str] = []
    replies = iter(answers)

    def reply(prompt: str) -> str:
        asked.append(prompt)
        return next(replies)

    monkeypatch.setattr(script, "read_key", reply)
    return asked


def test_a_sample_asks_about_every_stratum_and_saves_counts_alone(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "tallies.txt"
    asked = _keys(monkeypatch, ["x", "y", "n", "u", "y", "n", "u", "y", "n", "u", "y", "n"])

    assert (
        script.main(
            [
                "--data-dir",
                str(data_dir),
                "--caselist",
                CASELIST,
                "--seed",
                "7",
                "--save-tallies",
                str(saved),
                "--workers",
                "1",
            ]
        )
        == 0
    )

    lines = saved.read_text().splitlines()
    assert lines[0] == "Cite-shape sample (v1-e31-t19), seed 7: drew 11 items from 1 parsed sources."
    assert re.fullmatch(r"  Asked 11; answered 11 in \d+ seconds\.", lines[1])
    assert len(asked) == 12, "the key that is not an answer is asked again"
    per_stratum = lines[2:]
    assert [line.split(":")[0].strip() for line in per_stratum] == [
        s.label for s in script.STRATA if s.plan == script.FIRST_PLAN
    ]
    for line in per_stratum:
        counts = re.fullmatch(r"  .+: in the corpus 1; drew 1 of \d+; yes (\d), no (\d), unsure (\d)", line)
        assert counts is not None, line
        assert sum(int(count) for count in counts.groups()) == 1
    totals = Counter[str]()
    for line in per_stratum:
        for word in ("yes", "no", "unsure"):
            totals[word] += int(re.search(rf"{word} (\d)", line).group(1))  # type: ignore[union-attr]
    assert totals == {"yes": 4, "no": 4, "unsure": 3}
    assert "\n".join(lines) in capsys.readouterr().out


def test_stopping_keeps_the_tallies_so_far(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = tmp_path / "tallies.txt"
    _keys(monkeypatch, ["y", "y", "q"])

    script.main(
        [
            "--data-dir",
            str(data_dir),
            "--caselist",
            CASELIST,
            "--seed",
            "7",
            "--save-tallies",
            str(saved),
            "--workers",
            "1",
        ]
    )

    lines = saved.read_text().splitlines()
    assert re.fullmatch(r"  Asked 11; answered 2 in \d+ seconds, stopped with 9 not answered\.", lines[1])


def test_the_same_seed_draws_the_same_items_in_the_same_order(data_dir: Path) -> None:
    found, _ = script.scan(script.sources_in(data_dir, [CASELIST]), workers=1)

    first, second = script.draw(found, 11), script.draw(found, 11)
    assert [(stratum, position) for stratum, _, position in first] == [
        (stratum, position) for stratum, _, position in second
    ]
    assert sorted(stratum for stratum, _, _ in first) == list(range(11))
    assert [stratum for stratum, _, _ in first] != list(range(11)), "shuffled: the order says nothing"


def test_each_stratum_draws_its_planned_number_and_no_more() -> None:
    source = script._Source(CASELIST, DIGEST, Path("unused"), Path("unused"), VERSION)  # pyright: ignore[reportPrivateUsage]
    found = {number: [(source, position) for position in range(30)] for number in range(len(script.STRATA))}

    first = Counter(stratum for stratum, _, _ in script.draw(found, 5))
    left_quote = Counter(stratum for stratum, _, _ in script.draw(found, 5, script.LEFT_QUOTE_PLAN))

    assert first == {n: s.planned for n, s in enumerate(script.STRATA) if s.plan == script.FIRST_PLAN}
    assert sum(first.values()) == 70
    assert left_quote == {11: 18, 12: 10}


def test_nothing_saved_holds_text_a_tag_a_path_or_a_digest(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = tmp_path / "tallies.txt"
    _keys(monkeypatch, ["y"] * 11)

    script.main(
        [
            "--data-dir",
            str(data_dir),
            "--caselist",
            CASELIST,
            "--seed",
            "3",
            "--save-tallies",
            str(saved),
            "--workers",
            "1",
        ]
    )

    written = saved.read_text()
    for word in (
        "Okonkwo",
        "Adaeze",
        "Ferreira",
        "Lindqvist",
        "Grid",
        "reserve",
        "tag",
        "Continued",
        CASELIST,
    ):
        assert word not in written, word
    assert "/" not in written and "\\" not in written
    assert not re.search(r"[0-9a-f]{12}", written)


def test_the_tallies_file_may_not_be_inside_the_repository(data_dir: Path) -> None:
    inside = Path(__file__).resolve().parents[2] / "build" / "tallies.txt"

    with pytest.raises(SystemExit, match="outside the repository"):
        script.main(["--data-dir", str(data_dir), "--save-tallies", str(inside), "--workers", "1"])
    assert not inside.exists()


def test_each_item_is_answered_under_its_own_stratum() -> None:
    items = [script._Item(9, "first"), script._Item(4, "second"), script._Item(9, "third")]  # pyright: ignore[reportPrivateUsage]
    replies = iter(["n", "y", "u"])
    shown: list[str] = []

    answered, stopped, seconds = script.ask_about(
        items, ask=lambda _prompt: next(replies), show=shown.append, clock=iter([10.0, 25.0]).__next__
    )

    assert answered == Counter({(9, "no"): 1, (4, "yes"): 1, (9, "unsure"): 1})
    assert (stopped, seconds) == (False, 15.0)
    assert script.STRATA[9].question + "\n" in shown and script.STRATA[4].question + "\n" in shown


def test_an_item_shows_the_tag_the_marked_paragraph_and_the_one_below() -> None:
    reads, document = parsed_with_reads()
    position = next(
        k for k, s in enumerate(document.sections) if s.text.startswith("Okonkwo 26, Adaeze Okonkwo is")
    )

    shown = script.render_item(reads, document.sections, position)

    assert shown.splitlines()[0] == "Tag above:  Sixth tag"
    assert "\x1b[1m\x1b[7mOkonkwo 26\x1b[0m" in shown, "bold and highlighted as in the file"
    assert shown.splitlines()[-1] == f"Paragraph below:  {BODY_TEXT[:240]} …"


def test_a_long_paragraph_is_shown_by_its_opening_and_its_end() -> None:
    reads, document = parsed_with_reads()
    position = next(k for k, s in enumerate(document.sections) if s.text.startswith(LONGER_GUESS[:30]))

    shown = script.render_item(reads, document.sections, position)

    assert f"[… {len(LONGER_GUESS) - 1_300:,} characters not shown …]" in shown
    plain = shown.replace("\x1b[0m", "")
    assert LONGER_GUESS[:900] in plain and LONGER_GUESS[-400:] in plain
    assert LONGER_GUESS[:901] not in plain


# ------------------------------------------------------------------------------------------------
# The left-quote plan, after the PM's review of 2026-10-18
# ------------------------------------------------------------------------------------------------

STORED_VERSION = "2026.10.12-docx-3"
LEFT_QUOTE = "\u2018"
LEFT_QUOTED_LINE = f"Okonkwo {LEFT_QUOTE}26, invented for this test, {SOURCE}."
PLAIN_CITE_LINE = f"Okonkwo 26, invented for this test, {SOURCE}."
BRACKETED = f"[Adaeze Okonkwo 2026, {qualifications(300)}, {SOURCE}] KR"

#: Four cards: a line opening `Okonkwo ‘26` that was the body and is now the only cite; a short
#: cite `Okonkwo ‘26` alone above a bracketed cite; a cite line that leaves its card no body with
#: no left quote in it; and a card that does not change.
LEFT_QUOTE_FILE = build_docx(
    tag("Tenth tag")
    + paragraph([("Okonkwo \u201826", {}), (LEFT_QUOTED_LINE[11:], {"underline": "single"})])
    + tag("Eleventh tag")
    + paragraph([(f"Okonkwo {LEFT_QUOTE}26", {"character_style": "Style13ptBold"})])
    + paragraph([(BRACKETED, {})])
    + body()
    + tag("Twelfth tag")
    + paragraph([("Okonkwo 26", {"bold": True}), (PLAIN_CITE_LINE[10:], {})])
    + tag("Thirteenth tag")
    + cite()
    + body()
)
LEFT_QUOTE_DIGEST = hashlib.sha256(LEFT_QUOTE_FILE).hexdigest()


def _left_quote_document() -> tuple[list[Any], ParsedDocument]:
    source = script._Source(CASELIST, LEFT_QUOTE_DIGEST, Path("unused"), Path("unused"), STORED_VERSION)  # pyright: ignore[reportPrivateUsage]
    parser = script._ReadingParser()  # pyright: ignore[reportPrivateUsage]
    document = parser.parse(LEFT_QUOTE_FILE, script_source(source), source_path="sample.docx")
    assert isinstance(document, ParsedDocument)
    return parser.reads, document


def _as_stored_before(document: ParsedDocument) -> ParsedDocument:
    """The same file as the parser before the left quote: the two lone cite lines were each a card's
    whole body, and the short cite above the bracket was none."""

    def before(card: ParsedCard) -> ParsedCard:
        if card.full_cite in (LEFT_QUOTED_LINE, PLAIN_CITE_LINE):
            return card.model_copy(
                update={
                    "completeness": CardCompleteness.FULL,
                    "full_cite": "",
                    "short_cite": None,
                    "evidence_text": card.full_cite,
                }
            )
        if card.short_cite is not None and LEFT_QUOTE in card.short_cite:
            return card.model_copy(update={"short_cite": None})
        return card

    return document.model_copy(
        update={"cards": tuple(before(card) for card in document.cards), "parser_version": STORED_VERSION}
    )


@pytest.fixture
def left_quote_dir(tmp_path: Path) -> Path:
    blob = tmp_path / "blobs" / "sha256" / LEFT_QUOTE_DIGEST[:2] / LEFT_QUOTE_DIGEST[2:4] / LEFT_QUOTE_DIGEST
    blob.parent.mkdir(parents=True)
    blob.write_bytes(LEFT_QUOTE_FILE)
    _, document = _left_quote_document()
    stored = _as_stored_before(document)
    entry = SourceEntry.model_validate(
        {
            "caselist": CASELIST,
            "snapshot": "2026-10-18",
            "source_sha256": LEFT_QUOTE_DIGEST,
            "parser_version": STORED_VERSION,
            "profile_version": stored.profile_version,
            "fingerprint_version": FINGERPRINT_VERSION,
            "source_format": SourceFormat.DOCX,
            "byte_size": len(LEFT_QUOTE_FILE),
            "outcome": SourceOutcome.PARSED,
            "cards": len(stored.cards),
        }
    )
    record = DocumentRecord.from_parsed_document(
        stored, caselist=CASELIST, snapshot="2026-10-18", fingerprint_version=FINGERPRINT_VERSION, camp=None
    )
    store = LocalParsedStore(tmp_path)
    asyncio.run(store.write_source(CASELIST, STORED_VERSION, entry, record))
    asyncio.run(store.write_aggregates(CASELIST, STORED_VERSION, index=[entry], failures=[], occurrences=[]))
    return tmp_path


def test_the_left_quote_cards_are_found_against_the_stored_ones(left_quote_dir: Path) -> None:
    reads, document = _left_quote_document()
    (source,) = script.sources_in(left_quote_dir, [CASELIST])
    stored = script._stored_cards(source)  # pyright: ignore[reportPrivateUsage]

    found, without = script.card_strata(reads, document, stored, script._ReadingParser().profile)  # pyright: ignore[reportPrivateUsage]

    assert [(stratum, document.sections[position].text) for stratum, position in found] == [
        (11, LEFT_QUOTED_LINE),
        (12, f"Okonkwo {LEFT_QUOTE}26"),
        (11, PLAIN_CITE_LINE),
    ]
    assert without == 1, "the plain cite line holds no left quote"


def test_with_nothing_stored_only_the_short_cites_are_found() -> None:
    reads, document = _left_quote_document()

    found, without = script.card_strata(reads, document, [], script._ReadingParser().profile)  # pyright: ignore[reportPrivateUsage]

    assert [stratum for stratum, _ in found] == [12, 12]
    assert without == 0


def test_the_left_quote_plan_asks_its_28_and_shows_the_short_cite(
    left_quote_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "tallies.txt"
    _keys(monkeypatch, ["y", "n", "u"])

    script.main(
        [
            "--data-dir",
            str(left_quote_dir),
            "--caselist",
            CASELIST,
            "--plan",
            "left-quote",
            "--seed",
            "4",
            "--save-tallies",
            str(saved),
            "--workers",
            "1",
        ]
    )

    lines = saved.read_text().splitlines()
    assert (
        lines[0]
        == "Cite-shape sample (v1-e31-t19), left-quote plan, seed 4: drew 3 items from 1 parsed sources."
    )
    assert re.fullmatch(r"  Asked 3; answered 3 in \d+ seconds\.", lines[1])
    assert re.fullmatch(
        r"  a short cite with a left quote \| a cite line that leaves its card no body: "
        r"in the corpus 2; drew 2 of 18; yes \d, no \d, unsure \d",
        lines[2],
    )
    assert re.fullmatch(
        r"  a short cite with a left quote \| a card gaining such a short cite: "
        r"in the corpus 1; drew 1 of 10; yes \d, no \d, unsure \d",
        lines[3],
    )
    assert lines[4] == (
        "  Of the cards whose cite line leaves them no body, 1 hold no line read only through the left quote."
    )
    assert len(lines) == 5
    assert f"Short cite read:  Okonkwo {LEFT_QUOTE}26" in capsys.readouterr().out
    written = saved.read_text()
    for word in ("Okonkwo", "Adaeze", "Tenth", "Grid", CASELIST):
        assert word not in written, word
    assert not re.search(r"[0-9a-f]{12}", written)
