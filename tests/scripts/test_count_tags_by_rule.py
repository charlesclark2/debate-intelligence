"""`scripts/count_tags_by_rule.py`: a parsed store's cards by tag and by the rule that read it (`v1-e31-t32`).

One invented file in (7)'s formatting, parsed by this checkout's parser and stored as a caselist
store does, beside an older version directory holding no document. Expectations are written by hand
from the file (working agreement 6):

====  ===========================================================  =================================
 at    paragraph                                                    its card
====  ===========================================================  =================================
  0    a tag in `Heading4`, 1 cite, 2 body                          tagged by its heading style
  3    nothing set: bold throughout as Word shows it                tags the card at 4: t24's rule
  4    cite, 5 body
  6    bold but for its tail                                        tags the card at 7: t32's rule
  7    cite, 8 body
  9    bold switched off throughout                                 none: the card at 10 has no tag
 10    cite, 11 body
====  ===========================================================  =================================
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import READING_SIZE, SOURCE, prose

from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry, SourceOutcome
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_tags_by_rule as script  # noqa: E402

CASELIST = "testcl26"
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


def _off(text: str, **formatting: Any) -> str:
    return run_xml(text, bold=False, half_points=READING_SIZE, **formatting)


def _card(name: str, stem: str) -> str:
    return paragraph_xml(_off(f"{name}, Adaeze Okonkwo, invented for this test, {SOURCE}")) + paragraph_xml(
        _off(prose(400, f"{stem} "), underline="single")
    )


FILE = build_docx(
    paragraph_xml(run_xml("First tag"), style="Heading4")
    + _card("Ferreira 25", "Alpha")
    + paragraph_xml(run_xml("Imports cannot close the gap"))
    + _card("Okonkwo 26", "Bravo")
    + paragraph_xml(run_xml("Demand outruns ") + _off("new generation", underline="single"))
    + _card("Achebe 23", "Charlie")
    + paragraph_xml(_off("A note left plain"))
    + _card("Tanaka 22", "Delta"),
    styles_xml=STYLES,
)
DIGEST = hashlib.sha256(FILE).hexdigest()


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    snapshot = date(2026, 11, 3)
    source = SourceDocument(
        sha256=DIGEST,
        byte_size=len(FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    document = DebateDocxParser().parse(FILE, source, source_path="invented.docx")
    assert isinstance(document, ParsedDocument)
    entry = SourceEntry.model_validate(
        {
            "caselist": CASELIST,
            "snapshot": "2026-11-03",
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
        snapshot="2026-11-03",
        fingerprint_version="card-fingerprint-v4",
        camp=None,
    )
    store = LocalParsedStore(tmp_path)
    asyncio.run(store.write_source(CASELIST, DOCX_PARSER_VERSION, entry, record))
    asyncio.run(
        store.write_aggregates(CASELIST, DOCX_PARSER_VERSION, index=[entry], failures=[], occurrences=[])
    )
    older = tmp_path / "parsed" / CASELIST / "2026.10.27-docx-7"
    older.mkdir()
    (older / "index.jsonl").write_text("")
    return tmp_path


def test_each_version_directory_counted_by_the_rule_that_read_each_tag(
    copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main(["--data-dir", str(copy)]) == 0
    printed = capsys.readouterr().out
    output = json.loads(printed)

    assert output["caselists"] == {
        CASELIST: {
            "2026.10.27-docx-7": {
                "sources": 0,
                "cards": 0,
                "no_tag": 0,
                "tagged_by_bold_tag": 0,
                "tagged_by_unbolded_tail": 0,
            },
            DOCX_PARSER_VERSION: {
                "sources": 1,
                "cards": 4,
                "no_tag": 1,
                "tagged_by_bold_tag": 1,
                "tagged_by_unbolded_tail": 1,
            },
        }
    }
    for word in ("First tag", "Imports", "Demand", "Okonkwo", "Alpha"):
        assert word not in printed, word
    assert not re.search(r"[0-9a-f]{12}", printed)


def test_a_copy_with_no_parsed_store_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no parsed store"):
        script.main(["--data-dir", str(tmp_path)])
