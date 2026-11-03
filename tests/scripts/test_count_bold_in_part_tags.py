"""`scripts/count_bold_in_part_tags.py`: the lines t24's rule leaves, bold in part, by shape (`v1-e31-t32`).

Two invented files in (7)'s formatting, whose defaults make every run bold at 13 pt and whose bodies
and cites switch bold off at 11 pt, in two caselists. Every line above a cite is written to be one
case; the second file holds one of the first file's lines again. Expectations are written by hand
from what the files were built to hold (working agreement 6).

The first file (`testcl26`, its store directory written by `docx-7`):

====  =============================================================  ===============================
 at    paragraph                                                      counted as
====  =============================================================  ===============================
  0    a tag in `Heading4`, then its cite and body (1, 2)             -
  3    bold, a full stop unbolded                                     alone: tail, punctuation only
  6    bold, two words at the tail unbolded                           alone: tail, letters, no digits
  9    bold, a tail holding a number unbolded                         alone: tail, with digits
 12    unbolded at both ends, bold between                            alone: head and tail only
 15    unbolded at the head                                           alone: head only
 18    bold, one word in the middle unbolded                          alone: in the middle
 21    bold, over 300 characters, its last word unbolded              and something else: tail, words
 24    bold switched off throughout                                   not bold
 27    nothing set: bold throughout as Word shows it                  - (t24's rule reads it as a tag)
 30    bold, an exclamation mark unbolded                             alone: tail, punctuation only
 33    a tag in `Heading4`                                            -
 34    bold switched off, under the tag, above its cite (35, 36)      - (its cite's card has a tag)
====  =============================================================  ===============================

Each line from 3 to 30 is followed by a bracketed cite opening a card with no tag, and a body.

The second file (`testcl25`, its store directory written by `docx-6`): a tag, its cite and body, then
line 6 of the first file again, above a cite and a body.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from tests.evals.parser.cite_shapes import READING_SIZE, SOURCE, prose, qualifications

from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_bold_in_part_tags as script  # noqa: E402

STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W_NAMESPACE}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:b w:val="1"/><w:sz w:val="26"/></w:rPr></w:rPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
    '<w:basedOn w:val="Normal"/></w:style>'
    "</w:styles>"
)


def _off(text: str) -> str:
    return run_xml(text, bold=False, half_points=READING_SIZE)


def _card(name: str, stem: str) -> str:
    cite = paragraph_xml(_off(f"{name} [{qualifications(450)}, {SOURCE}] KR"))
    body = paragraph_xml(
        run_xml(prose(400, f"{stem} "), bold=False, half_points=READING_SIZE, underline="single")
    )
    return cite + body


LONG_LINE = "Grid operators warn that " + "reserve margins thin every winter and " * 8 + "fall"
TAIL_WORDS = paragraph_xml(run_xml("Reserve margins thin ") + _off("every winter"))

FIRST = build_docx(
    paragraph_xml(run_xml("First tag"), style="Heading4")
    + _card("Okonkwo 26", "Alpha")
    + paragraph_xml(run_xml("Reserve margins thin") + _off("."))
    + _card("Ferreira 25", "Bravo")
    + TAIL_WORDS
    + _card("Achebe 23", "Charlie")
    + paragraph_xml(run_xml("Imports fall ") + _off("within 30 days"))
    + _card("Mensah 21", "Delta")
    + paragraph_xml(_off("AT: ") + run_xml("Storage fills") + _off(" the gap"))
    + _card("Tanaka 22", "Echo")
    + paragraph_xml(_off("AT: ") + run_xml("Storage fills the gap"))
    + _card("Lindqvist 24", "Foxtrot")
    + paragraph_xml(run_xml("Storage ") + _off("never") + run_xml(" fills"))
    + _card("Ibsen 19", "Golf")
    + paragraph_xml(run_xml(LONG_LINE) + _off(" again"))
    + _card("Nakamura 20", "Hotel")
    + paragraph_xml(_off("A note left plain"))
    + _card("Achebe 18", "India")
    + paragraph_xml(run_xml("Imports cannot close the gap"))
    + _card("Mensah 17", "Juliet")
    + paragraph_xml(run_xml("Margins hold") + _off("!"))
    + _card("Tanaka 16", "Mike")
    + paragraph_xml(run_xml("Last tag"), style="Heading4")
    + paragraph_xml(_off("A note under the tag"))
    + _card("Ibsen 15", "November"),
    styles_xml=STYLES,
)
SECOND = build_docx(
    paragraph_xml(run_xml("Second tag"), style="Heading4")
    + _card("Okonkwo 26", "Kilo")
    + TAIL_WORDS
    + _card("Ferreira 25", "Lima"),
    styles_xml=STYLES,
)

SHAPES = [shape.value for shape in script.BoldInPartShape]
OTHER_CONDITIONS = [
    condition.value
    for condition in script.FailingCondition
    if condition is not script.FailingCondition.BOLD_IN_PART
]


def _store(root: Path, caselist: str, version: str, files: list[bytes]) -> None:
    directory = root / "parsed" / caselist / version
    directory.mkdir(parents=True)
    records = []
    for content in files:
        digest = hashlib.sha256(content).hexdigest()
        blob = root / "blobs" / "sha256" / digest[:2] / digest[2:4] / digest
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(content)
        records.append({"source_sha256": digest, "outcome": "PARSED"})
    records.append({"source_sha256": "0" * 64, "outcome": "UNSUPPORTED"})
    (directory / "index.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _store(tmp_path, "testcl26", "2026.10.27-docx-7", [FIRST])
    _store(tmp_path, "testcl25", "2026.10.20-docx-6", [SECOND])
    return tmp_path


def _shapes(**found: tuple[int, int, int]) -> dict[str, dict[str, int]]:
    """Every shape, zero unless named: (lines, distinct lines, files)."""
    named = {script.BoldInPartShape[name].value: counts for name, counts in found.items()}
    return {
        shape: dict(zip(("lines", "distinct_lines", "files"), named.get(shape, (0, 0, 0)), strict=True))
        for shape in SHAPES
    }


def _first_failing(**found: int) -> dict[str, int]:
    named = {script.FailingCondition[name].value: n for name, n in found.items()}
    return {
        **{condition.value: named.get(condition.value, 0) for condition in script.FailingCondition},
        script.FAILS_NOTHING: 0,
    }


def test_every_caselist_counted_by_first_failing_condition_and_shape(data_dir: Path) -> None:
    counts = script.count(data_dir, None, workers=1)

    assert counts["parser_version"] == DOCX_PARSER_VERSION
    assert sorted(counts["caselists"]) == ["testcl25", "testcl26"]
    every = counts["every_caselist"]
    assert (every["sources"], every["parsed"], every["lines_left"]) == (2, 2, 10)
    assert every["by_first_failing_condition"] == _first_failing(BOLD_IN_PART=9, NOT_BOLD=1)
    assert every["bold_in_part_and_nothing_else"] == {
        "lines": 8,
        "distinct_lines": 6,  # line 6 twice, and lines 12 and 15 one text bolded two ways
        "files": 2,
        "by_shape": _shapes(
            TAIL_PUNCTUATION_ONLY=(2, 2, 1),
            TAIL_WITHOUT_DIGITS=(2, 1, 2),
            TAIL_WITH_DIGITS=(1, 1, 1),
            HEAD_ONLY=(1, 1, 1),
            BOTH_ENDS_ONLY=(1, 1, 1),
            IN_THE_MIDDLE=(1, 1, 1),
        ),
    }
    assert every["bold_in_part_and_something_else"] == {
        "lines": 1,
        "by_shape": _shapes(TAIL_WITHOUT_DIGITS=(1, 1, 1)),
        "by_other_condition": {
            condition: int(condition == script.FailingCondition.LONGER_THAN_A_HEADING.value)
            for condition in OTHER_CONDITIONS
        },
    }


def test_each_caselist_alone_whatever_version_wrote_its_directory(data_dir: Path) -> None:
    counts = script.count(data_dir, None, workers=1)["caselists"]

    second = counts["testcl25"]
    assert (second["store_version"], second["sources"], second["parsed"], second["without_a_blob"]) == (
        "2026.10.20-docx-6",
        1,
        1,
        0,
    )
    assert second["lines_left"] == 1
    assert second["bold_in_part_and_nothing_else"]["by_shape"] == _shapes(TAIL_WITHOUT_DIGITS=(1, 1, 1))
    first = counts["testcl26"]
    assert first["store_version"] == "2026.10.27-docx-7"
    assert first["lines_left"] == 9
    assert first["bold_in_part_and_nothing_else"]["lines"] == 7


def test_a_missing_blob_is_counted_and_nothing_else_is(data_dir: Path) -> None:
    digest = hashlib.sha256(SECOND).hexdigest()
    (data_dir / "blobs" / "sha256" / digest[:2] / digest[2:4] / digest).unlink()

    second = script.count(data_dir, ["testcl25"], workers=1)["caselists"]["testcl25"]
    assert (second["sources"], second["parsed"], second["without_a_blob"], second["lines_left"]) == (
        1,
        0,
        1,
        0,
    )


def test_the_output_is_counts_and_names_only(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert script.main(["--data-dir", str(data_dir), "--workers", "1"]) == 0
    captured = capsys.readouterr()
    printed = captured.out
    json.loads(printed)
    for word in ("Reserve", "winter", "Storage", "Okonkwo", "First tag", "Alpha", str(data_dir)):
        assert word not in printed, word
    assert not re.search(r"[0-9a-f]{12}", printed)
    assert "testcl26: reading 1 sources of 2026.10.27-docx-7" in captured.err
