"""`scripts/count_card_boundaries.py`: the counts of `v1-e31-t22`, over an invented store.

The store holds four sources, each built as a `.docx` from invented text and parsed by the parser
this checkout carries, and every expected count is written by hand from what the files hold
(working agreement 6):

* **the long file**: a card of over 3,000 words with a tag typed in body style above a cite its
  body kept, then a second card under a tag. Its blob is on disk.
* **the holding file**: one card whose body is two others' bodies run together, and those two.
* **the same long file stored under another digest, with no blob on disk.**
* **the same long file stored under another digest whose blob is the holding file's bytes**, so
  parsing it again does not give the stored card back.
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
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose

from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry, SourceOutcome
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_card_boundaries as script  # noqa: E402

CASELIST = "testcl26"
SNAPSHOT = date(2026, 10, 19)


def para(text: str, *, style: str | None = None, **formatting: Any) -> str:
    return paragraph_xml(run_xml(text, **formatting), style=style)


def cite(name: str) -> str:
    return paragraph_xml(
        run_xml(name, bold=True, half_points=CITE_SIZE)
        + run_xml(f", Adaeze Okonkwo, invented for this test, {SOURCE}", half_points=READING_SIZE)
    )


def numbered(stem: str, count: int) -> str:
    return " ".join(f"{stem}{number}" for number in range(count))


def underlined(text: str) -> str:
    return para(text, underline="single", half_points=SMALL_PRINT)


#: Two paragraphs of about 1,900 words each.
LONG_PARAGRAPH = prose(11_500)

LONG_FILE = build_docx(
    para("First tag", style="Heading4")
    + cite("Okonkwo 26")
    + underlined(LONG_PARAGRAPH)
    + para("Reserve margins fall in every region", half_points=READING_SIZE)
    + para(f"Lindqvist 2019, invented review of grid planning, {SOURCE}", highlight="yellow")
    + underlined(LONG_PARAGRAPH)
    + para("Second tag", style="Heading4")
    + cite("Ferreira 25")
    + underlined(numbered("third", 70))
)

HOLDING_FILE = build_docx(
    cite("Okonkwo 26")
    + underlined(numbered("first", 80) + " " + numbered("second", 80))
    + cite("Ferreira 25")
    + underlined(numbered("first", 80))
    + cite("Lindqvist 2019")
    + underlined(numbered("second", 80))
)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


LONG, HOLDING = digest(LONG_FILE), digest(HOLDING_FILE)
NO_BLOB, OTHER_BLOB = "b" * 64, "c" * 64

#: Words and digests the output must not contain: the store's text, and the sources' names.
TELLTALES = ("first0", "second7", "third3", "Grid operators", "Reserve margins", "Okonkwo", LONG, HOLDING)


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
    stored = {LONG: LONG_FILE, HOLDING: HOLDING_FILE, NO_BLOB: LONG_FILE, OTHER_BLOB: LONG_FILE}
    entries: list[SourceEntry] = []
    common = {
        "caselist": CASELIST,
        "snapshot": "2026-10-19",
        "parser_version": DOCX_PARSER_VERSION,
        "profile_version": DebateDocxParser().profile_version,
        "fingerprint_version": "card-fingerprint-v4",
    }
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
            snapshot="2026-10-19",
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
    write_blob(tmp_path, LONG, LONG_FILE)
    write_blob(tmp_path, HOLDING, HOLDING_FILE)
    write_blob(tmp_path, OTHER_BLOB, HOLDING_FILE)
    return tmp_path


def run(data_dir: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[dict[str, Any], str]:
    code = script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--workers", "1", *options])
    assert code == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.out + captured.err


def test_the_long_file_is_as_the_counts_below_assume() -> None:
    document = parsed(LONG_FILE, LONG)
    words = [len(card.evidence_text.split()) for card in document.cards]
    assert len(words) == 2
    assert words[0] > 3_000
    assert words[0] < 5_000
    assert words[1] == 70


def test_each_count_is_the_one_the_invented_store_holds(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output, _ = run(data_dir, capsys)
    counts = output["caselists"][CASELIST]
    assert output["long_body_words"] == 3_000
    assert counts["version"] == DOCX_PARSER_VERSION
    assert counts["sources"] == 4
    assert counts["cards"] == 9
    assert counts["full_cards"] == 9
    assert counts["long_bodies"] == {
        "texts": 1,
        "not_reproduced": 1,
        "in_a_source_with_no_blob": 1,
        "cards": 1,
        "by_cards_in_file": {"2 to 5": 1},
        "by_ending": {"a tag in a debate style": 1},
        "by_ending_and_file_writing_tags": {"a tag in a debate style | file writes tags: yes": 1},
        "by_file_using_debate_styles": {"yes": 1},
        "by_file_writing_tags": {"file writes tags: yes": 1},
        "by_kind": {"a short line above a cite-shaped paragraph inside": 1},
        "by_kind_and_file_styles": {
            "a short line above a cite-shaped paragraph inside | debate styles: yes": 1
        },
        "by_marked_up_share": {"5% or more": 1},
        "by_tag_and_cite": {"tag: yes | cite: yes": 1},
        "by_words": {"3,001 to 5,000": 1},
        "cite_shaped_paragraphs_by_rule": {"assembly-cite-guess-inside-card-body": 1},
    }
    assert counts["two_cards_in_one"] == {
        "full_texts": 5,
        "holding_two_sharing_nothing_texts": 1,
        "holding_two_sharing_nothing_cards": 1,
        "holding_two_not_overlapping_texts": 1,
        "by_bodies_sharing_nothing": {"2": 1},
        "by_holder_over_the_long_body_line": {"no": 1},
        "by_holder_words": {"0 to 299": 1},
        "by_smaller_of_the_two": {"long (64 words or more)": 1},
    }
    assert set(counts["seconds"]) == {"reading", "long_bodies", "two_cards_in_one"}


def test_nothing_but_counts_and_rule_names_is_printed(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, printed = run(data_dir, capsys)
    for telltale in TELLTALES:
        assert telltale not in printed


def test_the_candidates_are_store_positions_and_hold_no_text(
    data_dir: Path, capsys: pytest.CaptureFixture[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    saved = tmp_path_factory.mktemp("operator") / "candidates.jsonl"
    run(data_dir, capsys, "--save-candidates", str(saved))
    rows = [json.loads(line) for line in saved.read_text().splitlines()]
    holding = parsed(HOLDING_FILE, HOLDING)
    first_of = [card.provenance.first_element_index for card in holding.cards]
    assert rows == [
        {
            "caselist": CASELIST,
            "count": "long-body",
            "group": "a short line above a cite-shaped paragraph inside",
            "card": [LONG, 0],
        },
        {
            "caselist": CASELIST,
            "count": "two-cards-in-one",
            "group": "sharing nothing",
            "card": [HOLDING, first_of[0]],
            "pieces": [[HOLDING, first_of[1]], [HOLDING, first_of[2]]],
        },
    ]
    for telltale in TELLTALES[:6]:
        assert telltale not in saved.read_text()


def test_the_candidates_file_must_be_outside_the_repository(data_dir: Path) -> None:
    inside = Path(__file__).resolve().parents[2] / "scripts" / "candidates.jsonl"
    with pytest.raises(SystemExit, match="outside the repository"):
        script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--save-candidates", str(inside)])
    assert not inside.exists()


def test_a_store_of_another_parser_version_is_refused_by_name(data_dir: Path) -> None:
    with pytest.raises(
        SystemExit, match=f"newest version directory is {DOCX_PARSER_VERSION}, not 2099.01.01-docx-9"
    ):
        script.main(
            ["--data-dir", str(data_dir), "--caselist", CASELIST, "--expect-version", "2099.01.01-docx-9"]
        )


def test_the_version_expected_is_read(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output, _ = run(data_dir, capsys, "--expect-version", DOCX_PARSER_VERSION)
    assert output["caselists"][CASELIST]["cards"] == 9


def test_the_newest_version_directory_with_an_index_is_the_one_read(data_dir: Path) -> None:
    parsed_root = data_dir / "parsed"
    (parsed_root / CASELIST / "2026.10.12-docx-3").mkdir()
    (parsed_root / CASELIST / "2026.10.12-docx-3" / "index.jsonl").write_text("")
    (parsed_root / CASELIST / "2099.01.01-docx-9").mkdir()
    assert script.version_directory(parsed_root, CASELIST, None).name == DOCX_PARSER_VERSION


def test_worker_processes_give_the_counts_one_process_gives(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one, _ = run(data_dir, capsys)
    code = script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--workers", "2"])
    assert code == 0
    two = json.loads(capsys.readouterr().out)
    for output in (one, two):
        output["seconds"] = 0
        output["caselists"][CASELIST]["seconds"] = {}
    assert one == two
