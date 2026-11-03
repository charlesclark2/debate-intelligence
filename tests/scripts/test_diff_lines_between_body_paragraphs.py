"""`scripts/diff_lines_between_body_paragraphs.py`: N1's before and after, over an invented store.

Three sources, each built as a `.docx` from invented text, and every expected count written by hand
from what the files hold (working agreement 6):

* **the read file**: one card, whose body holds a sentence of 41 to 200 characters and a line over
  200 between its paragraphs, both made body by N1, and an omission note N1 leaves;
* **the guarded file**: two cards. The first holds, between its paragraphs, a sentence carrying a link
  (the ruled guard) and a sentence naming its source at its head (the session's guard); the second
  holds nothing between its paragraphs;
* **a source stored with no blob on disk.**
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import prose

from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import diff_lines_between_body_paragraphs as script  # noqa: E402

CASELIST = "testcl26"
VERSION = "2026.11.03-docx-9"
SENTENCE_RULE = "assembly-sentence-between-body-paragraphs"
LONG_LINE_RULE = "assembly-long-line-between-body-paragraphs"


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def plain(text: str) -> str:
    return paragraph_xml(run_xml(text, half_points=22))


def body(text: str) -> str:
    return paragraph_xml(run_xml(text, underline="single", half_points=22))


CITE = "Okonkwo 26, invented professor of grid planning, invented report on reserve margins"
SECOND_CITE = "Ferreira 25, invented analyst, invented report on grid storage"
SENTENCE = "The review found that reserve margins narrowed in every season of the year."
LONG_LINE = prose(230, "Planners in four regional markets") + " and the operators who answer for"
LINKED = "The review is at https://example.invalid/grid-review and found that margins narrowed."
NAMED = "Professor Adaeze Okonkwo 26 reviewed the reserve margins of four regional markets."

READ_FILE = build_docx(
    tag("Grid tag one")
    + plain(CITE)
    + body(prose(300, "Alpha"))
    + plain(SENTENCE)
    + body(prose(300, "Bravo"))
    + plain(LONG_LINE)
    + body(prose(300, "Charlie"))
    + plain("[Table omitted]")
    + body(prose(300, "Delta"))
)
GUARDED_FILE = build_docx(
    tag("Grid tag two")
    + plain(CITE)
    + body(prose(300, "Echo"))
    + plain(LINKED)
    + body(prose(300, "Foxtrot"))
    + plain(NAMED)
    + body(prose(300, "Golf"))
    + tag("Grid tag three")
    + plain(SECOND_CITE)
    + body(prose(300, "Hotel"))
    + body(prose(300, "India"))
)
READ, GUARDED = hashlib.sha256(READ_FILE).hexdigest(), hashlib.sha256(GUARDED_FILE).hexdigest()
NO_BLOB = "b" * 64

TELLTALES = (
    "Grid tag",
    "Okonkwo",
    "Alpha",
    "review",
    "example.invalid",
    "Table omitted",
    READ,
    GUARDED,
    NO_BLOB,
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    for digest, content in ((READ, READ_FILE), (GUARDED, GUARDED_FILE)):
        blob = tmp_path / "blobs" / "sha256" / digest[:2] / digest[2:4] / digest
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(content)
    version = tmp_path / "parsed" / CASELIST / VERSION
    version.mkdir(parents=True)
    entries = [{"source_sha256": digest, "outcome": "PARSED"} for digest in (READ, GUARDED, NO_BLOB)]
    entries.append({"source_sha256": "d" * 64, "outcome": "UNSUPPORTED"})
    (version / "index.jsonl").write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return tmp_path


def run(data_dir: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[dict[str, Any], str]:
    assert script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, *options]) == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.out + captured.err


def test_each_count_is_the_one_the_invented_store_holds(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output, _ = run(data_dir, capsys, "--workers", "1")
    counts = output["caselists"][CASELIST]
    assert (counts["sources"], counts["sources_read"], counts["without_a_blob"], counts["not_parsed"]) == (
        3,
        2,
        1,
        0,
    )
    assert counts["cards"] == 3
    assert counts["lines_made_body"] == {SENTENCE_RULE: 1, LONG_LINE_RULE: 1}
    assert counts["lines_held_back_by_the_cite_guard"] == {
        SENTENCE_RULE: {"a link, a web address, a DOI or accessed": 1, "names its source at its head": 1}
    }
    assert counts["cards_whose_evidence_text_changed"] == 1
    assert counts["files_with_a_card_whose_evidence_text_changed"] == 1
    assert counts["other_cards_changed"] == 0
    assert output["total"]["lines_made_body"] == counts["lines_made_body"]
    assert "store_version" not in output["total"]


def test_worker_processes_give_the_counts_one_process_gives(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one, _ = run(data_dir, capsys, "--workers", "1")
    two, _ = run(data_dir, capsys, "--workers", "2")
    for output in (one, two):
        output.pop("seconds")
        output["caselists"][CASELIST].pop("seconds")
    assert one == two


def test_nothing_but_counts_and_rule_names_is_printed(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, printed = run(data_dir, capsys, "--workers", "1")
    for telltale in TELLTALES:
        assert telltale not in printed
