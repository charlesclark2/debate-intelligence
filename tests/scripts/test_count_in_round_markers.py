"""`scripts/count_in_round_markers.py`: the counts of `v1-e31-t23`, over an invented store.

The store holds four sources, each built as a `.docx` from invented text, and an occurrence table
whose cluster ids are written by hand. Every expected count is written by hand from what the files
and the table hold (working agreement 6):

* **the marked file**: a tag and a cite (0, 1); body A1 (2); `marked 3:05`, plain, read as nothing
  between two body paragraphs (3); body A2 (4); `Marked 10:42`, plain, read as a cite that opens a
  card with no tag (5); body A3 (6); a second tag and cite (7, 8); body B1 (9); `MARKED` at 8 pt, read
  as body, the end of the card (10). Three cards: A1+A2, A3, B1+MARKED.
* **the plain file**: the same two cards with no marker. A tag and a cite, A1, A2 and A3 as one body;
  a tag and a cite, B1. Two cards: A1+A2+A3, B1.
* **the plain file stored under another digest with no blob on disk.**
* **the plain file stored under another digest whose blob has a line at its head**, so its cards
  differ from the stored ones: the line is read as nothing, elsewhere.

The occurrence table: the marked file's A1+A2 and the plain file's A1+A2+A3 in one cluster (the
near-duplicate rules joined the half to the whole), A3 alone in another; B1+MARKED and B1 in two.
So leaving every marker form out of matching joins A1+A2 and A3 into the plain file's body, which
spans two clusters, and makes B1+MARKED the plain file's B1, which spans two more.
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
from tests.evals.parser.cite_shapes import prose

from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.fingerprints import fingerprint_text
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_in_round_markers as script  # noqa: E402

CASELIST = "testcl26"
SNAPSHOT = "2026-11-02"
FINGERPRINT_VERSION = "card-fingerprint-v4"


def plain(text: str, *, half_points: int = 22) -> str:
    return paragraph_xml(run_xml(text, half_points=half_points))


def body(text: str) -> str:
    return paragraph_xml(run_xml(text, underline="single", half_points=22))


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


A1, A2, A3 = prose(300, "Alpha reserve margins"), prose(300, "Alpha imports"), prose(300, "Alpha exports")
B1 = prose(300, "Bravo storage")

MARKED_FILE = build_docx(
    tag("Grid tag one")
    + plain("Okonkwo 26, invented report on grid reserves")
    + body(A1)
    + plain("marked 3:05")
    + body(A2)
    + plain("Marked 10:42")
    + body(A3)
    + tag("Grid tag two")
    + plain("Ferreira 25, invented report on grid storage")
    + body(B1)
    + plain("MARKED", half_points=16)
)


def plain_file(*, head: str = "") -> bytes:
    return build_docx(
        head
        + tag("Grid tag one")
        + plain("Okonkwo 26, invented report on grid reserves")
        + body(A1)
        + body(A2)
        + body(A3)
        + tag("Grid tag two")
        + plain("Ferreira 25, invented report on grid storage")
        + body(B1)
    )


PLAIN_FILE = plain_file()
PLAIN_FILE_SHIFTED = plain_file(head=plain("A banner line"))


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


MARKED, PLAIN = digest(MARKED_FILE), digest(PLAIN_FILE)
NO_BLOB, SHIFTED = "b" * 64, "c" * 64

A12, A3_ALONE, B1_MARKED = (
    fingerprint_text(f"{A1}\n{A2}"),
    fingerprint_text(A3),
    fingerprint_text(f"{B1}\nMARKED"),
)
A123, B1_ALONE = fingerprint_text(f"{A1}\n{A2}\n{A3}"), fingerprint_text(B1)
CLUSTER_A, CLUSTER_A3, CLUSTER_B_MARKED, CLUSTER_B = "1" * 64, "2" * 64, "3" * 64, "4" * 64

#: Each stored card's range, fingerprint and cluster, written by hand.
OCCURRENCES = (
    (MARKED, 0, 4, A12, CLUSTER_A),
    (MARKED, 5, 6, A3_ALONE, CLUSTER_A3),
    (MARKED, 7, 10, B1_MARKED, CLUSTER_B_MARKED),
    (PLAIN, 0, 4, A123, CLUSTER_A),
    (PLAIN, 5, 7, B1_ALONE, CLUSTER_B),
)

#: Words and digests the output must not contain: the store's text, and the sources' and cards' names.
TELLTALES = (
    "Grid tag",
    "Okonkwo",
    "Alpha",
    "Bravo",
    "banner",
    "invented",
    "10:42",
    "3:05",
    MARKED,
    PLAIN,
    NO_BLOB,
    A12,
    A123,
    B1_MARKED,
    CLUSTER_A,
)


def parsed(content: bytes, sha256: str) -> ParsedDocument:
    source = SourceDocument(
        sha256=sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=date(2026, 11, 2),
        last_seen_snapshot=date(2026, 11, 2),
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
    common = {
        "caselist": CASELIST,
        "snapshot": SNAPSHOT,
        "parser_version": DOCX_PARSER_VERSION,
        "profile_version": DebateDocxParser().profile_version,
        "fingerprint_version": FINGERPRINT_VERSION,
    }
    entries: list[SourceEntry] = []
    for sha256, content in {
        MARKED: MARKED_FILE,
        PLAIN: PLAIN_FILE,
        NO_BLOB: PLAIN_FILE,
        SHIFTED: PLAIN_FILE,
    }.items():
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
            document, caselist=CASELIST, snapshot=SNAPSHOT, fingerprint_version=FINGERPRINT_VERSION, camp=None
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
    occurrences = [
        OccurrenceRecord.model_validate(
            {
                **common,
                "source_sha256": sha256,
                "last_snapshot": SNAPSHOT,
                "disclosure": "e" * 64,
                "first_element_index": first,
                "last_element_index": last,
                "exact_fingerprint": exact,
                "cluster_id": cluster,
                "membership": "NEAR_DUPLICATE",
                "completeness": "FULL",
            }
        )
        for sha256, first, last, exact, cluster in OCCURRENCES
    ]
    asyncio.run(
        store.write_aggregates(
            CASELIST, DOCX_PARSER_VERSION, index=[*entries, unsupported], failures=[], occurrences=occurrences
        )
    )
    write_blob(tmp_path, MARKED, MARKED_FILE)
    write_blob(tmp_path, PLAIN, PLAIN_FILE)
    write_blob(tmp_path, SHIFTED, PLAIN_FILE_SHIFTED)
    return tmp_path


def run(data_dir: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[dict[str, Any], str]:
    code = script.main(["--data-dir", str(data_dir), "--caselist", CASELIST, "--workers", "1", *options])
    assert code == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.out + captured.err


def test_the_files_read_as_the_counts_below_assume() -> None:
    marked = parsed(MARKED_FILE, MARKED)
    assert [card.tag for card in marked.cards] == ["Grid tag one", None, "Grid tag two"]
    assert [card.evidence_text for card in marked.cards] == [f"{A1}\n{A2}", A3, f"{B1}\nMARKED"]
    plain_ = parsed(PLAIN_FILE, PLAIN)
    assert [card.evidence_text for card in plain_.cards] == [f"{A1}\n{A2}\n{A3}", B1]
    stored = [
        (sha256, card.provenance.first_element_index, card.provenance.last_element_index)
        for sha256, document in ((MARKED, marked), (PLAIN, plain_))
        for card in document.cards
    ]
    assert stored == [(sha256, first, last) for sha256, first, last, _, _ in OCCURRENCES]


BODY, NOTHING, CITE = "read as body", "read as nothing", "read as a cite"
NO_FORM, WORD_AND_TIME, WORD_ALONE = "no-marker-form", "marker-word-and-clock-time", "marker-word-alone"
FIRST, INSIDE, LAST, ONLY = (
    "the body's first line",
    "inside the body",
    "the end of the body",
    "the body's only line",
)
BETWEEN, ELSEWHERE = "between two body paragraphs of one card", "elsewhere"
OPENING_A_CARD = "below a body, opening a card with no tag and a body"
SHORT = "40 characters or fewer"


def test_each_count_is_the_one_the_invented_store_holds(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output, _ = run(data_dir, capsys)
    counts = output["caselists"][CASELIST]
    assert (counts["store_version"], counts["parser_version"]) == (DOCX_PARSER_VERSION, DOCX_PARSER_VERSION)
    assert (counts["sources"], counts["sources_parsed_again"], counts["without_a_blob"]) == (4, 3, 1)
    assert (counts["not_parsed"], counts["sources_whose_cards_differ_from_the_store"]) == (0, 1)
    assert counts["cards"] == 7
    assert counts["lines"] == {
        BODY: {NO_FORM: {FIRST: 4, INSIDE: 2, LAST: 3, ONLY: 3}, WORD_ALONE: {LAST: 1}},
        NOTHING: {NO_FORM: {ELSEWHERE: 1}, WORD_AND_TIME: {BETWEEN: 1}},
        CITE: {NO_FORM: {ELSEWHERE: 6}, WORD_AND_TIME: {OPENING_A_CARD: 1}},
    }
    assert counts["marker_shaped_lines_by_rule"] == {
        BODY: {WORD_ALONE: {"heuristic-shrunk-body-text": 1}},
        NOTHING: {WORD_AND_TIME: {"heuristic-unclassified-paragraph": 1}},
        CITE: {WORD_AND_TIME: {"heuristic-cite-line-author-year": 1}},
    }
    assert counts["cards_holding"][BODY][WORD_ALONE] == {LAST: 1}
    assert counts["cards_holding"][NOTHING][WORD_AND_TIME] == {BETWEEN: 1}
    assert counts["cards_holding"][CITE][WORD_AND_TIME] == {OPENING_A_CARD: 1}
    assert counts["cards_holding"][BODY][NO_FORM] == {FIRST: 4, INSIDE: 2, LAST: 3, ONLY: 3}
    assert counts["cards_with_a_line_read_as_nothing_between_body_paragraphs"] == 1
    assert counts["files_holding_a_marker_shaped_line"] == {
        BODY: {WORD_ALONE: 1},
        NOTHING: {WORD_AND_TIME: 1},
        CITE: {WORD_AND_TIME: 1},
    }
    one_short_line = {"lines": 1, "no_sentence_end": 1, "ends_a_sentence": 0, "in_capitals": 0}
    assert counts["read_as_nothing_by_length"] == {
        BETWEEN: {SHORT: one_short_line},
        ELSEWHERE: {SHORT: one_short_line},
    }
    assert (counts["occurrence_rows"], counts["occurrence_fingerprint_versions"]) == (
        5,
        [FINGERPRINT_VERSION],
    )


def clusters(
    changed: int, joined: int, held: int, split: int, *, fingerprints: int | None = None
) -> dict[str, int]:
    return {
        "bodies_changed": changed,
        "bodies_joined_across_a_marker_read_as_a_cite": joined,
        "marker_free_fingerprints": changed if fingerprints is None else fingerprints,
        "marker_free_fingerprints_another_card_has_today": held,
        "marker_free_fingerprints_held_by_two_copies_or_more": held,
        "marker_free_fingerprints_spanning_two_clusters_or_more": split,
        "clusters_that_would_join_one_another": split,
        "exact_fingerprints_the_occurrence_table_does_not_hold": 0,
    }


def test_the_clusters_each_set_of_forms_splits(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output, _ = run(data_dir, capsys)
    assert output["caselists"][CASELIST]["clusters"] == {
        # `Marked 10:42`, read as a cite, divides A1+A2+A3; the two halves sit in two clusters.
        WORD_AND_TIME: clusters(1, 1, 1, 1),
        "clock-time-alone": clusters(0, 0, 0, 0),
        # `MARKED` ends B1's body; B1+MARKED and B1 sit in two clusters.
        WORD_ALONE: clusters(1, 0, 1, 1),
        "marker-word-opens-a-short-line": clusters(0, 0, 0, 0),
        "marker-word-and-clock-time+clock-time-alone+marker-word-alone": clusters(2, 1, 2, 2),
        "every-marker-form": clusters(2, 1, 2, 2),
    }
    assert output["form_sets"]["every-marker-form"] == [
        WORD_AND_TIME,
        "clock-time-alone",
        WORD_ALONE,
        "marker-word-opens-a-short-line",
    ]


def test_a_fingerprint_the_table_does_not_hold_is_counted_and_joins_nothing(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = next((data_dir / "parsed" / CASELIST).iterdir()) / "occurrences.jsonl"
    rows = [json.loads(line) for line in table.read_text(encoding="utf-8").splitlines()]
    table.write_text(
        "".join(json.dumps(row) + "\n" for row in rows if row["exact_fingerprint"] != B1_MARKED),
        encoding="utf-8",
    )
    output, _ = run(data_dir, capsys)
    word_alone = output["caselists"][CASELIST]["clusters"][WORD_ALONE]
    assert word_alone["exact_fingerprints_the_occurrence_table_does_not_hold"] == 1
    assert word_alone["marker_free_fingerprints_spanning_two_clusters_or_more"] == 0


def test_the_total_adds_the_caselists_up(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output, _ = run(data_dir, capsys)
    counts, total = output["caselists"][CASELIST], output["total"]
    assert total["lines"] == counts["lines"]
    assert total["clusters"] == counts["clusters"]
    assert total["cards"] == counts["cards"]
    assert "store_version" not in total
    assert "occurrence_fingerprint_versions" not in total


def test_nothing_but_counts_form_ids_and_rule_names_is_printed(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, printed = run(data_dir, capsys)
    for telltale in TELLTALES:
        assert telltale not in printed


def test_a_store_of_another_parser_version_is_refused_by_name(data_dir: Path) -> None:
    with pytest.raises(
        SystemExit, match=f"newest version directory is {DOCX_PARSER_VERSION}, not 2099.01.01-docx-9"
    ):
        script.main(
            ["--data-dir", str(data_dir), "--caselist", CASELIST, "--expect-version", "2099.01.01-docx-9"]
        )


def test_a_store_another_parser_wrote_is_counted_on_this_checkouts_parse(
    data_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "DOCX_PARSER_VERSION", "2099.01.01-docx-9")
    output, _ = run(data_dir, capsys)
    counts = output["caselists"][CASELIST]
    assert (counts["store_version"], counts["parser_version"]) == (DOCX_PARSER_VERSION, "2099.01.01-docx-9")
    assert counts["cards"] == 7


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
