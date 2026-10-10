"""`scripts/compare_card_clusters.py`, on an invented parsed store built in a temporary directory.

The real run is the operator's, on the dev data directory (`v1-e31-t08-short-card-recall`, Goal
criterion ac5). This checks the counting against figures worked out by hand from five invented
cards, that `counts` prints no word of any card, and that `sample` shows text only to a terminal
and ends with tallies alone.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import compare_card_clusters as script  # noqa: E402

CASELIST = "testcl26"
BEFORE_T08 = "card-fingerprint-v1"

SENSORS = (
    "Coastal councils that installed tidal sensors in 2024 reported flood warnings arriving forty "
    "minutes earlier on average, and the earlier warnings let crews close storm gates before the "
    "surge reached the harbour road."
)
#: (short cite, completeness, body). What `card-fingerprint-v2` does with them, by hand:
#: the one-typo copy joins the sensors card; the two orchard cuts, which no full card matches,
#: are grouped; the ferry card is alone. Five cards, five clusters before, three after.
CARDS = (
    ("Ilmar 26", CardCompleteness.FULL, SENSORS),
    ("Ilmar 26", CardCompleteness.FULL, SENSORS.replace("forty", "fourty")),
    ("Tamsin 26", CardCompleteness.ABBREVIATED, "Shaded orchards on the … two degrees on August nights."),
    ("Tamsin 26", CardCompleteness.ABBREVIATED, "Shaded orchards on … by two degrees on August nights."),
    (
        "Brannock 25",
        CardCompleteness.FULL,
        "Raising ferry fares by a third cut weekday ridership by only six percent, the transit board "
        "found, which suggests commuters on the island routes have nowhere else to turn.",
    ),
)
#: Words that would give a card away in output that is meant to hold counts only.
TELLTALE = ("Coastal", "orchards", "ferry", "Ilmar", "Tamsin", "Brannock", "fourty")


def _one_card_file(marker: str) -> bytes:
    return build_docx(
        paragraph_xml(run_xml(f"Invented tag {marker}"), style="Heading4")
        + paragraph_xml(
            run_xml("Invented 26", character_style="Style13ptBold") + run_xml(", Fictional Review")
        )
        + paragraph_xml(
            run_xml(f"Invented body {marker}.", character_style="StyleUnderline", underline="single")
        )
    )


def _document(marker: str, cards: tuple[tuple[str, CardCompleteness, str], ...]) -> ParsedDocument:
    """A real parsed document whose one card is replaced by `cards`, at element indices 10, 20, ..."""
    content = _one_card_file(marker)
    source = SourceDocument(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=date(2026, 9, 1),
        last_seen_snapshot=date(2026, 9, 1),
    )
    parsed = DebateDocxParser().parse(content, source, source_path="Maple Grove/QX/invented.docx")
    assert isinstance(parsed, ParsedDocument)
    (template,) = parsed.cards
    replaced = tuple(
        template.model_copy(
            update={
                "short_cite": short_cite,
                "completeness": completeness,
                "evidence_text": body,
                "formatting_spans": (),
                "font_size_spans": (),
                "provenance": template.provenance.model_copy(
                    update={"first_element_index": 10 * position, "last_element_index": 10 * position + 1}
                ),
            }
        )
        for position, (short_cite, completeness, body) in enumerate(cards, start=1)
    )
    return parsed.model_copy(update={"cards": replaced})


def _as_v1_placed(card: ParsedCard) -> tuple[str, ClusterMembership]:
    """`card-fingerprint-v1` on these five cards, written out: every card its own cluster."""
    full = card.completeness is CardCompleteness.FULL
    return (
        card_fingerprint(card).exact_fingerprint,
        ClusterMembership.NEAR_DUPLICATE if full else ClusterMembership.UNLINKED,
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A store of two sources and five cards, with the occurrence table as v1 left it."""
    store = LocalParsedStore(tmp_path)
    documents = [_document("one", CARDS[:3]), _document("two", CARDS[3:])]
    entries: list[SourceEntry] = []
    rows: list[OccurrenceRecord] = []
    for document in documents:
        common = {
            "caselist": CASELIST,
            "snapshot": "2026-09-01",
            "source_sha256": document.source_sha256,
            "parser_version": document.parser_version,
            "profile_version": document.profile_version,
            "fingerprint_version": BEFORE_T08,
        }
        entry = SourceEntry.model_validate(
            {
                **common,
                "source_format": SourceFormat.DOCX,
                "byte_size": 100,
                "outcome": SourceOutcome.PARSED,
                "cards": len(document.cards),
            }
        )
        record = DocumentRecord.from_parsed_document(
            document, caselist=CASELIST, snapshot="2026-09-01", fingerprint_version=BEFORE_T08, camp=None
        )
        asyncio.run(store.write_source(CASELIST, document.parser_version, entry, record))
        entries.append(entry)
        for card in document.cards:
            cluster, membership = _as_v1_placed(card)
            rows.append(
                OccurrenceRecord.model_validate(
                    {
                        **common,
                        "last_snapshot": "2026-09-01",
                        "disclosure": "d" * 64,
                        "first_element_index": card.provenance.first_element_index,
                        "last_element_index": card.provenance.last_element_index,
                        "exact_fingerprint": cluster,
                        "cluster_id": cluster,
                        "membership": membership,
                        "completeness": card.completeness,
                    }
                )
            )
    asyncio.run(
        store.write_aggregates(
            CASELIST, documents[0].parser_version, index=entries, failures=[], occurrences=rows
        )
    )
    return tmp_path


#: Worked out by hand from `CARDS`: two of the five earlier clusters each joined another.
EXPECTED_COUNTS = {
    "cards": 5,
    "before_version": BEFORE_T08,
    "after_version": FINGERPRINT_VERSION,
    "clusters_before": 5,
    "clusters_after": 3,
    "clusters_merged_into_another": 2,
    "clusters_made_of_several": 2,
    "absorbed": {"2": 2, "3 to 5": 0, "6 to 20": 0, "21 to 100": 0, "101 or more": 0},
    "most_absorbed": 2,
    "clusters_divided": 0,
    "newly_linked_to_a_full_card": 0,
    "newly_grouped_with_abbreviated_cards": 2,
    "no_longer_linked": 0,
    "largest_before": 1,
    "largest_after": 2,
    "largest_before_distinct_texts": 1,
    "largest_after_distinct_texts": 2,
    "exact_fingerprints_changed": 0,
}


def test_counts_previews_the_next_rebuild_and_prints_counts_only(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main(["--data-dir", str(data_dir), "counts", "--caselist", CASELIST]) == 0
    output = capsys.readouterr().out
    counts = json.loads(output)[CASELIST]
    assert counts.pop("seconds") >= 0
    assert counts == EXPECTED_COUNTS
    assert not [word for word in TELLTALE if word in output]


def _rebuilt_under_todays_rules(data_dir: Path) -> Path:
    """Save the v1 table aside, then rewrite the store's with today's placement. Returns the copy."""
    store = LocalParsedStore(data_dir)
    version = script.current_version(store, CASELIST)
    table = store.root / CASELIST / version / "occurrences.jsonl"
    saved = data_dir / "saved" / f"{CASELIST}.jsonl"
    saved.parent.mkdir()
    saved.write_bytes(table.read_bytes())
    held = script.read_placements(table)
    now = script.placements_now(script.read_cards(store, CASELIST, version, held), FINGERPRINT_VERSION)
    rewritten: list[str] = []
    for line in table.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        placement = now[(row["source_sha256"], row["first_element_index"])]
        row.update(
            cluster_id=placement.cluster_id,
            membership=placement.membership,
            fingerprint_version=placement.fingerprint_version,
        )
        rewritten.append(json.dumps(row, sort_keys=True))
    table.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return saved


def test_counts_compares_a_saved_table_with_the_one_the_store_holds_now(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """After the rebuild, nothing is placed again: the two files are compared as they are."""
    saved = _rebuilt_under_todays_rules(data_dir)
    for before in (saved, saved.parent):
        assert (
            script.main(
                ["--data-dir", str(data_dir), "counts", "--caselist", CASELIST, "--before", str(before)]
            )
            == 0
        )
        counts = json.loads(capsys.readouterr().out)[CASELIST]
        del counts["seconds"]
        assert counts == EXPECTED_COUNTS


def test_a_table_that_covers_other_cards_is_refused(data_dir: Path) -> None:
    saved = _rebuilt_under_todays_rules(data_dir)
    lines = saved.read_text(encoding="utf-8").splitlines()
    saved.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="cover different cards"):
        script.main(["--data-dir", str(data_dir), "counts", "--caselist", CASELIST, "--before", str(saved)])


def test_one_pair_is_offered_for_each_cluster_that_joined_another(data_dir: Path) -> None:
    store = LocalParsedStore(data_dir)
    version = script.current_version(store, CASELIST)
    before = script.read_placements(store.root / CASELIST / version / "occurrences.jsonl")
    after = script.placements_now(script.read_cards(store, CASELIST, version, before), FINGERPRINT_VERSION)
    pairs = script.joined_pairs(before, after)
    assert sorted(pair.kind for pair in pairs) == ["abbreviated with abbreviated", "full with full"]
    for pair in pairs:
        assert before[pair.joiner].cluster_id != before[pair.host].cluster_id
        assert after[pair.joiner].cluster_id == after[pair.host].cluster_id


def test_sample_refuses_to_show_card_text_to_anything_but_a_terminal(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Under pytest neither stream is a terminal, which is the case this refuses."""
    assert script.main(["--data-dir", str(data_dir), "sample", "--caselist", CASELIST]) == 2
    captured = capsys.readouterr()
    assert "terminal" in captured.err
    assert not [word for word in TELLTALE if word in captured.out + captured.err]


def test_the_sample_shows_each_pair_then_clears_it_and_returns_tallies_alone(data_dir: Path) -> None:
    store = LocalParsedStore(data_dir)
    version = script.current_version(store, CASELIST)
    before = script.read_placements(store.root / CASELIST / version / "occurrences.jsonl")
    after = script.placements_now(script.read_cards(store, CASELIST, version, before), FINGERPRINT_VERSION)
    pairs = []
    for pair in script.joined_pairs(before, after):
        cards = script.read_cards(store, CASELIST, version, [pair.joiner, pair.host])
        pairs.append((CASELIST, pair, cards[pair.joiner], cards[pair.host]))
    shown: list[str] = []
    answers = iter(["x", "S", "d"])  # an answer that is not a verdict is asked again

    tallies = script.run_sample(pairs, ask=lambda _prompt: next(answers), show=shown.append)

    assert sum(tallies.values()) == 2
    assert {verdict for _, verdict in tallies} == {"same card", "different card"}
    assert any("Coastal" in text for text in shown)
    assert shown[-1] == script.CLEAR_TERMINAL
    assert shown.count(script.CLEAR_TERMINAL) == len(pairs) + 1
    assert not [word for word in TELLTALE if word in repr(tallies)]
