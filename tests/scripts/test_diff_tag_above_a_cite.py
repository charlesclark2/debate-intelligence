"""`scripts/diff_tag_above_a_cite.py`: the PM's before-and-after check of `v1-e31-t24`'s rule.

One invented file in (7)'s formatting (defaults bold at 13 pt; bodies and cites switch bold off),
stored as `docx-5` read it, with one card of each kind the check sorts. Expectations are written by
hand from the file (working agreement 6):

====  ===============================================  ==============================================
 at    paragraph                                        with the rule
====  ===============================================  ==============================================
  0    tag "First tag"                                  its card loses its last paragraph, line 3
  1    cite, 2 body
  3    a line with nothing set                          taken: the tag of the card at 4
  4    cite, 5 a long body                              the card gains a tag
  6    cite (after a body: a card with no tag), 7 body  its heading path names line 3 instead
  8    tag "Lonely tag"                                 nothing left under it: an analytic, no card
  9    a line with nothing set, the tag's only body     taken: the tag of the card at 10
 10    cite, 11 body                                    the card gains a tag and ends at 12 as before
 12    a line with nothing set, its tail highlighted    left by the highlight guard
 13    cite, 14 body                                    its heading path names line 9 instead
====  ===============================================  ==============================================
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import SOURCE, prose

from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry, SourceOutcome
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import diff_tag_above_a_cite as script  # noqa: E402

CASELIST = "testcl26"
SNAPSHOT = date(2026, 10, 20)

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


def plain(text: str, **formatting: Any) -> str:
    return run_xml(text, bold=False, half_points=22, **formatting)


def cite(name: str) -> str:
    return paragraph_xml(plain(f"{name}, Adaeze Okonkwo, invented for this test, {SOURCE}"))


def body(stem: str, characters: int = 400) -> str:
    return paragraph_xml(plain(prose(characters, f"{stem} "), underline="single"))


def line(text: str, tail: str, **tail_formatting: Any) -> str:
    return paragraph_xml(run_xml(text) + run_xml(tail, **tail_formatting))


FILE = build_docx(
    paragraph_xml(run_xml("First tag"), style="Heading4")
    + cite("Ferreira 25")
    + body("Alpha")
    + line("Demand outruns ", "new generation", underline="single")
    + cite("Okonkwo 26")
    + body("Bravo")
    + cite("Achebe 23")
    + body("Charlie")
    + paragraph_xml(run_xml("Lonely tag"), style="Heading4")
    + line("Imports cannot ", "close the gap", underline="single")
    + cite("Tanaka 22")
    + body("Delta")
    + line("Prices rise ", "every winter", highlight="yellow")
    + cite("Mensah 21")
    + body("Echo"),
    styles_xml=STYLES,
)
DIGEST = hashlib.sha256(FILE).hexdigest()


def as_docx_5_read_it(content: bytes, sha256: str) -> ParsedDocument:
    source = SourceDocument(
        sha256=sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    document = script._Reading(with_the_rule=False).parse(content, source, source_path="invented.docx")  # pyright: ignore[reportPrivateUsage]
    assert isinstance(document, ParsedDocument)
    return document


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    store = LocalParsedStore(tmp_path)
    document = as_docx_5_read_it(FILE, DIGEST)
    entry = SourceEntry.model_validate(
        {
            "caselist": CASELIST,
            "snapshot": "2026-10-20",
            "parser_version": DOCX_PARSER_VERSION,
            "profile_version": DebateDocxParser().profile_version,
            "fingerprint_version": "card-fingerprint-v4",
            "source_sha256": DIGEST,
            "source_format": SourceFormat.DOCX,
            "byte_size": len(FILE),
            "outcome": SourceOutcome.PARSED,
            "cards": len(document.cards),
        }
    )
    record = DocumentRecord.from_parsed_document(
        document,
        caselist=CASELIST,
        snapshot="2026-10-20",
        fingerprint_version="card-fingerprint-v4",
        camp=None,
    )
    asyncio.run(store.write_source(CASELIST, DOCX_PARSER_VERSION, entry, record))
    asyncio.run(
        store.write_aggregates(CASELIST, DOCX_PARSER_VERSION, index=[entry], failures=[], occurrences=[])
    )
    blob = tmp_path / "blobs" / "sha256" / DIGEST[:2] / DIGEST[2:4] / DIGEST
    blob.parent.mkdir(parents=True)
    blob.write_bytes(FILE)
    return tmp_path


def test_the_file_reads_as_the_table_says() -> None:
    before = as_docx_5_read_it(FILE, DIGEST)
    assert [
        (c.provenance.first_element_index, c.provenance.last_element_index, c.tag) for c in before.cards
    ] == [
        (0, 3, "First tag"),
        (4, 5, None),
        (6, 7, None),
        (8, 9, "Lonely tag"),
        (10, 12, None),
        (13, 14, None),
    ]


def test_each_card_is_sorted_by_what_changed_it(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--workers", "1"]) == 0
    printed = capsys.readouterr()
    counts = json.loads(printed.out)[CASELIST]
    counts.pop("seconds")
    assert counts == {
        "version": DOCX_PARSER_VERSION,
        "sources": 1,
        "sources_read": 1,
        "without_a_blob": 0,
        "not_parsed": 0,
        "first_reading_differs_from_the_store": 0,
        "files_with_a_line_taken": 1,
        "files_the_sampled_rule_reaches": 1,
        "sampled_rule_takes": 3,
        "taken": 2,
        "taken_beyond_the_sampled_rule": 0,
        "left_highlighted": 1,
        "left_underline_or_emphasis_style": 0,
        "left_otherwise": 0,
        "cards_gaining_a_tag": 2,
        "cards_above_losing_their_last_body_paragraph": 1,
        "cards_above_that_vanish": 1,
        "cards_whose_heading_path_now_names_a_taken_line": 2,
        "cards_changed_only_in_their_heading_path": 2,
        "other_cards_changed": 0,
        "cards_unchanged": 0,
    }
    for telltale in ("First tag", "Lonely tag", "Demand", "Okonkwo", DIGEST):
        assert telltale not in printed.out + printed.err


def test_a_card_changed_in_any_other_way_is_counted_as_such() -> None:
    """A body the rule did not cut, changed all the same, is no effect of the rule."""
    before = as_docx_5_read_it(FILE, DIGEST)
    reading = script._Reading(with_the_rule=False)  # pyright: ignore[reportPrivateUsage]
    after_reading = script._Reading(with_the_rule=True)  # pyright: ignore[reportPrivateUsage]
    source = SourceDocument(
        sha256=DIGEST,
        byte_size=len(FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    after = after_reading.parse(FILE, source, source_path="invented.docx")
    reading.parse(FILE, source, source_path="invented.docx")  # keeps the paragraphs `compare` reads
    assert isinstance(after, ParsedDocument)
    tampered = after.model_copy(
        update={
            "cards": tuple(
                card.model_copy(update={"evidence_text": card.evidence_text + " more"})
                if card.provenance.first_element_index == 13
                else card
                for card in after.cards
            )
        }
    )
    compared = script.compare(before, tampered, reading)
    assert (compared.other_cards_changed, compared.cards_changed_only_in_their_heading_path) == (1, 1)
