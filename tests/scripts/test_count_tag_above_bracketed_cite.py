"""`scripts/count_tag_above_bracketed_cite.py`: the counts of `v1-e31-t24`, over an invented store.

The store holds five sources, each built as a `.docx` from invented text and parsed by the parser
this checkout carries, and every expected count is written by hand from what the files hold
(working agreement 6):

* **the bold file**, in (7)'s formatting: document defaults bold at 13 pt, bodies and cites that
  switch bold off. A tag and a bracketed cite under it (0, 1); a body (2); (7)'s line, nothing set,
  read as body (3) above a bracketed cite opening a card with no tag (4); a body (5); a plain line,
  bold off, read as nothing (6) above a bracketed cite (7); a body (8); a line with nothing set,
  read as body (9) above a short name-and-year cite (10); a body (11); a line with nothing set read
  as nothing inside that body (12); a body (13).
* **the plain file**: defaults that set only a size. A tag and a bracketed cite (0, 1); a body (2);
  a line in bold of its own, no size, read as nothing (3) above a bracketed cite (4); a body (5).
* **the short-cite file**: a tag, a short name-and-year cite and a body. Nothing bracketed and no
  bold defaults, so it is parsed again only with `--every-source`.
* **the plain file stored under another digest with no blob on disk.**
* **the plain file stored under another digest whose blob has a paragraph more at its head**, so
  its parse gives back other ranges.
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

import count_tag_above_bracketed_cite as script  # noqa: E402

CASELIST = "testcl26"
SNAPSHOT = date(2026, 10, 20)


def styles(run_defaults: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NAMESPACE}">'
        f"<w:docDefaults><w:rPrDefault><w:rPr>{run_defaults}</w:rPr></w:rPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
        '<w:basedOn w:val="Normal"/></w:style>'
        "</w:styles>"
    )


CREDENTIALS = "Adaeze Okonkwo is an invented professor of grid planning at an invented university; " * 5


def plain(text: str, **formatting: Any) -> str:
    return run_xml(text, bold=False, half_points=22, **formatting)


def bracketed_cite(name: str) -> str:
    return paragraph_xml(plain(f"{name} [{CREDENTIALS}{SOURCE}] KR"))


def body(stem: str) -> str:
    return paragraph_xml(plain(prose(400, f"{stem} "), underline="single"))


def nothing_set(text: str, *, underlined_tail: str = "") -> str:
    tail = run_xml(underlined_tail, underline="single") if underlined_tail else ""
    return paragraph_xml(run_xml(text) + tail)


BOLD_FILE = build_docx(
    paragraph_xml(run_xml("First tag"), style="Heading4")
    + bracketed_cite("Okonkwo 26")
    + body("Alpha")
    + nothing_set("Demand outruns ", underlined_tail="new generation")
    + bracketed_cite("Ferreira 25")
    + body("Bravo")
    + paragraph_xml(plain("A note left plain"))
    + bracketed_cite("Achebe 23")
    + body("Charlie")
    + nothing_set("Imports cannot ", underlined_tail="close the gap")
    + paragraph_xml(plain("Nakamura 20, invented report on grid imports"))
    + body("Delta")
    + nothing_set("A line in the middle of a body")
    + body("Echo"),
    styles_xml=styles('<w:b w:val="1"/><w:sz w:val="26"/>'),
)


def plain_file(*, head: str = "") -> bytes:
    return build_docx(
        head
        + paragraph_xml(run_xml("Second tag"), style="Heading4")
        + bracketed_cite("Lindqvist 24")
        + body("Foxtrot")
        + paragraph_xml(run_xml("Reserve margins fall", bold=True))
        + bracketed_cite("Tanaka 22")
        + body("Golf"),
        styles_xml=styles('<w:sz w:val="24"/>'),
    )


PLAIN_FILE = plain_file()
#: The plain file with a paragraph more at its head: the same cards at other ranges.
PLAIN_FILE_SHIFTED = plain_file(head=paragraph_xml(plain("A banner line")))

SHORT_CITE_FILE = build_docx(
    paragraph_xml(run_xml("Third tag"), style="Heading4")
    + paragraph_xml(plain("Mensah 21, invented report on grid imports"))
    + body("Hotel")
)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


BOLD, PLAIN, SHORT = digest(BOLD_FILE), digest(PLAIN_FILE), digest(SHORT_CITE_FILE)
NO_BLOB, SHIFTED = "b" * 64, "c" * 64

#: Words and digests the output must not contain: the store's text, and the sources' names.
TELLTALES = (
    "First tag",
    "Second tag",
    "Okonkwo",
    "Demand outruns",
    "Reserve margins",
    "Alpha",
    "invented",
    BOLD,
    PLAIN,
    SHORT,
    NO_BLOB,
)


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


def write_blob(data_dir: Path, sha256: str, content: bytes) -> None:
    blob = data_dir / "blobs" / "sha256" / sha256[:2] / sha256[2:4] / sha256
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(content)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    store = LocalParsedStore(tmp_path)
    stored = {
        BOLD: BOLD_FILE,
        PLAIN: PLAIN_FILE,
        SHORT: SHORT_CITE_FILE,
        NO_BLOB: PLAIN_FILE,
        SHIFTED: PLAIN_FILE,
    }
    common = {
        "caselist": CASELIST,
        "snapshot": "2026-10-20",
        "parser_version": DOCX_PARSER_VERSION,
        "profile_version": DebateDocxParser().profile_version,
        "fingerprint_version": "card-fingerprint-v4",
    }
    entries: list[SourceEntry] = []
    for sha256, content in stored.items():
        document = parsed(content, sha256)
        entry = SourceEntry.model_validate(
            {
                **common,
                "source_sha256": sha256,
                "source_format": SourceFormat.DOCX,
                "byte_size": len(content),
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
        entries.append(entry)
    unsupported = SourceEntry.model_validate(
        {
            **common,
            "source_sha256": "d" * 64,
            "source_format": SourceFormat.PDF,
            "byte_size": 10,
            "outcome": SourceOutcome.UNSUPPORTED,
            "reason": "UNSUPPORTED_FORMAT",
            "detail": "PDF is stored unparsed in V1",
            "cards": 0,
        }
    )
    asyncio.run(
        store.write_aggregates(
            CASELIST, DOCX_PARSER_VERSION, index=[*entries, unsupported], failures=[], occurrences=[]
        )
    )
    write_blob(tmp_path, BOLD, BOLD_FILE)
    write_blob(tmp_path, PLAIN, PLAIN_FILE)
    write_blob(tmp_path, SHORT, SHORT_CITE_FILE)
    write_blob(tmp_path, SHIFTED, PLAIN_FILE_SHIFTED)
    return tmp_path


def run(data_dir: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[dict[str, Any], str]:
    code = script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--workers", "1", *options])
    assert code == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.out + captured.err


def test_the_files_read_as_the_counts_below_assume() -> None:
    bold = parsed(BOLD_FILE, BOLD)
    assert [card.tag for card in bold.cards] == ["First tag", None, None, None]
    assert [
        (card.provenance.first_element_index, card.provenance.last_element_index) for card in bold.cards
    ] == [(0, 3), (4, 5), (7, 9), (10, 13)]
    assert [section.match.rule_id.split(":")[0] for section in bold.sections][:11] == [
        "verbatim-style-id",
        "heuristic-cite-line-bracketed",
        "heuristic-marked-up-body-text",
        "heuristic-marked-up-body-text",
        "heuristic-cite-line-bracketed",
        "heuristic-marked-up-body-text",
        "heuristic-unclassified-paragraph",
        "heuristic-cite-line-bracketed",
        "heuristic-marked-up-body-text",
        "heuristic-marked-up-body-text",
        "heuristic-cite-line-author-year",
    ]
    plain_ = parsed(PLAIN_FILE, PLAIN)
    assert [card.tag for card in plain_.cards] == ["Second tag", None]
    assert plain_.sections[3].match.rule_id == "heuristic-unclassified-paragraph"


def test_each_count_is_the_one_the_invented_store_holds(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output, _ = run(data_dir, capsys)
    counts = output["caselists"][CASELIST]
    assert counts["version"] == DOCX_PARSER_VERSION
    assert (counts["sources"], counts["sources_parsed_again"]) == (5, 3)
    assert (counts["not_reproduced"], counts["without_a_blob"]) == (1, 1)
    assert "in_every_file" not in counts

    bracketed = counts["above_a_bracketed_cite"]
    assert bracketed["files_holding_the_shape"] == 2
    assert bracketed["files_holding_the_shape_above_a_cite_opening_a_card_with_no_tag"] == 2
    every_rule = bracketed["every_bracketed_rule"]
    assert every_rule["cites"] == 5
    assert every_rule["cites_opening_a_card_with_no_tag"] == 3
    assert every_rule["line_above_read_as"] == {"EVIDENCE": 1, "OTHER": 2, "TAG": 2}
    assert every_rule["line_above_read_as_body_or_nothing"] == 3
    assert every_rule["the_proposed_rule_takes"] == 2
    assert every_rule["the_proposed_rule_takes_lines_bold_only_by_inheritance"] == 1
    assert every_rule["the_shape"]["lines"] == 2
    assert every_rule["the_shape"]["bold_as_the_reader_sees_it"] == {"bold throughout": 1, "not bold": 1}
    assert every_rule["read_as_body_or_nothing_and_not_the_shape_by_bold_as_word_shows_it"] == {"not bold": 1}
    assert list(bracketed["by_cite_rule"]) == ["heuristic-cite-line-bracketed"]

    bold = counts["in_files_whose_defaults_make_text_bold"]
    assert bold["files"] == 1
    assert bold["above_every_cite"]["cites"] == 4
    assert bold["above_every_cite"]["cites_opening_a_card_with_no_tag"] == 3
    assert bold["above_every_cite"]["the_proposed_rule_takes"] == 2
    assert list(bold["above_every_cite_by_cite_rule"]) == [
        "heuristic-cite-line-author-year",
        "heuristic-cite-line-bracketed",
    ]
    assert bold["bold_lines_read_as_body_or_nothing"] == {
        "lines": 3,
        "directly_above_a_cite": 2,
        "directly_above_a_cite_opening_a_card_with_no_tag": 2,
        "bold_as_the_reader_sees_it": 0,
        "behind_a_style_that_maps_to_no_unit": 0,
    }
    assert bold["files_with_a_bold_line_read_as_body_or_nothing"] == 1


def test_every_source_parses_the_rest_and_counts_every_file(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output, _ = run(data_dir, capsys, "--every-source")
    counts = output["caselists"][CASELIST]
    assert (counts["sources_parsed_again"], counts["not_reproduced"], counts["without_a_blob"]) == (4, 1, 1)
    everywhere = counts["in_every_file"]
    assert everywhere["above_every_cite"]["cites"] == 7
    assert everywhere["above_every_cite"]["the_proposed_rule_takes"] == 3
    assert everywhere["files_the_proposed_rule_reaches"] == 2
    assert everywhere["above_every_cite_by_cite_rule"]["heuristic-cite-line-author-year"]["cites"] == 2
    assert counts["above_a_bracketed_cite"]["every_bracketed_rule"]["cites"] == 5


def test_nothing_but_counts_and_rule_names_is_printed(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for options in ((), ("--every-source",)):
        _, printed = run(data_dir, capsys, *options)
        for telltale in TELLTALES:
            assert telltale not in printed


def test_a_store_of_another_parser_version_is_refused_by_name(data_dir: Path) -> None:
    with pytest.raises(
        SystemExit, match=f"newest version directory is {DOCX_PARSER_VERSION}, not 2099.01.01-docx-9"
    ):
        script.main(
            ["--data-dir", str(data_dir), "--caselist", CASELIST, "--expect-version", "2099.01.01-docx-9"]
        )


def test_a_store_another_parser_wrote_is_refused(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "DOCX_PARSER_VERSION", "2099.01.01-docx-9")
    with pytest.raises(SystemExit, match="this checkout's parser is 2099.01.01-docx-9"):
        script.main(["--data-dir", str(data_dir), "--caselist", CASELIST])


def test_worker_processes_give_the_counts_one_process_gives(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one, _ = run(data_dir, capsys)
    assert script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--workers", "2"]) == 0
    two = json.loads(capsys.readouterr().out)
    for output in (one, two):
        output.pop("seconds")
        output["caselists"][CASELIST].pop("seconds")
    assert one == two


def test_a_file_whose_styles_hold_no_bold_default_is_not_opened_for_it(tmp_path: Path) -> None:
    for content, expected in ((BOLD_FILE, True), (PLAIN_FILE, False), (SHORT_CITE_FILE, False)):
        blob = tmp_path / digest(content)
        blob.write_bytes(content)
        assert script._may_have_bold_defaults(blob) is expected  # pyright: ignore[reportPrivateUsage]
