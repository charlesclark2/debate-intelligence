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
import re
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
#: (short cite, completeness, body). What the rules since `card-fingerprint-v2` do with them, by hand:
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


def _document(marker: str, cards: tuple[tuple[str | None, CardCompleteness, str], ...]) -> ParsedDocument:
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


#: The two sources' digests by name, filled in as the store is built.
_SOURCES: dict[str, str] = {}


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A store of two sources and five cards, with the occurrence table as v1 left it."""
    store = LocalParsedStore(tmp_path)
    documents = [_document("one", CARDS[:3]), _document("two", CARDS[3:])]
    _SOURCES.update(one=documents[0].source_sha256, two=documents[1].source_sha256)
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
    "cards_only_before": 0,
    "cards_only_after": 0,
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


def test_cards_in_only_one_table_are_counted_and_left_out_of_the_comparison(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pull between the saved table and the rebuild adds sources. The second source's two cards
    are missing from the saved table here: the ferry card, and the orchard cut that had joined the
    first source's. Three cards remain, and one earlier cluster joined another among them."""
    saved = _rebuilt_under_todays_rules(data_dir)
    kept = [
        line
        for line in saved.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["source_sha256"] == _SOURCES["one"]
    ]
    assert len(kept) == 3
    saved.write_text("\n".join(kept) + "\n", encoding="utf-8")

    assert (
        script.main(["--data-dir", str(data_dir), "counts", "--caselist", CASELIST, "--before", str(saved)])
        == 0
    )
    counts = json.loads(capsys.readouterr().out)[CASELIST]
    assert (counts["cards"], counts["cards_only_before"], counts["cards_only_after"]) == (3, 0, 2)
    assert (counts["clusters_before"], counts["clusters_after"]) == (3, 2)
    assert counts["clusters_merged_into_another"] == 1


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
    # `sample --divided` asks the same question with the two placements exchanged: pairs in one
    # cluster before and two after. Nothing was divided here.
    assert script.joined_pairs(after, before) == []
    assert script.joined_pairs(after, after) == []


def test_cards_are_placed_by_the_rules_handed_over_not_the_installed_ones(data_dir: Path) -> None:
    """`--before-rules` puts four modules from a git ref ahead of the installed package.

    Here the four are today's, with the version string changed in one of them. The child process
    stamps its placements with that string, which only the copy it was handed contains, and places
    the cards exactly as this process does.
    """

    def todays_rules_renamed(module: str) -> bytes:
        source = (script.PACKAGE_SOURCE / "debate_core" / module).read_bytes()
        return source.replace(FINGERPRINT_VERSION.encode(), b"card-fingerprint-handed-over")

    store = LocalParsedStore(data_dir)
    version = script.current_version(store, CASELIST)
    held = script.read_placements(store.root / CASELIST / version / "occurrences.jsonl")
    here = script.placements_now(script.read_cards(store, CASELIST, version, held), FINGERPRINT_VERSION)

    handed_over = script.placements_under_rules(todays_rules_renamed, data_dir, CASELIST)

    assert {placement.fingerprint_version for placement in handed_over.values()} == {
        "card-fingerprint-handed-over"
    }
    assert {key: placement.cluster_id for key, placement in handed_over.items()} == {
        key: placement.cluster_id for key, placement in here.items()
    }


def test_counts_reads_the_earlier_rules_from_a_git_ref(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With `--before-rules HEAD`, before is the committed rules and after is the store's table.

    The store's table here is the one v1 left, so the comparison reads backwards: three clusters
    under the committed rules, five in the table, and the two that had joined are divided again.
    """
    arguments = ["--data-dir", str(data_dir), "counts", "--caselist", CASELIST, "--before-rules", "HEAD"]
    assert script.main(arguments) == 0
    output = capsys.readouterr().out
    counts = json.loads(output)[CASELIST]
    assert (counts["clusters_before"], counts["clusters_after"]) == (3, 5)
    assert (counts["clusters_divided"], counts["clusters_merged_into_another"]) == (2, 0)
    assert (counts["before_version"], counts["after_version"]) == (FINGERPRINT_VERSION, BEFORE_T08)
    assert not [word for word in TELLTALE if word in output]


def test_placements_under_earlier_rules_are_saved_once_and_read_back(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--save-before` keeps what `--before-rules` took minutes to compute, for `--before`."""
    saved = data_dir / "saved-before"
    arguments = ["--data-dir", str(data_dir), "counts", "--caselist", CASELIST]
    assert script.main([*arguments, "--before-rules", "HEAD", "--save-before", str(saved)]) == 0
    computed = json.loads(capsys.readouterr().out)[CASELIST]

    written = (saved / f"{CASELIST}.jsonl").read_text(encoding="utf-8")
    assert len(written.splitlines()) == 5
    assert not [word for word in TELLTALE if word in written]

    assert script.main([*arguments, "--before", str(saved)]) == 0
    read_back = json.loads(capsys.readouterr().out)[CASELIST]
    del computed["seconds"], read_back["seconds"]
    assert read_back == computed


def test_a_ref_git_does_not_have_is_refused_by_name(data_dir: Path) -> None:
    arguments = ["--data-dir", str(data_dir), "counts", "--caselist", CASELIST]
    with pytest.raises(SystemExit, match="git has no no-such-ref:packages/debate_core"):
        script.main([*arguments, "--before-rules", "no-such-ref"])


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

    tallies = script.run_sample(pairs, ask=lambda _prompt: next(answers), show=shown.append, columns=120)

    # Neither pair is the rule's: the one-typo copy shares 24 of its 29 shingles, overlapping, and
    # the orchard cuts are abbreviated.
    assert (tallies.drawn, tallies.asked, sum(tallies.decided.values())) == (2, 2, 0)
    assert sum(tallies.answered.values()) == 2
    assert sum("Newly in one cluster." in text for text in shown) == 2
    assert {verdict for _, _, verdict in tallies.answered} == {"same card", "different card"}
    assert any("Coastal" in text for text in shown)
    assert shown[-1] == script.CLEAR_TERMINAL
    assert shown.count(script.CLEAR_TERMINAL) == len(pairs) + 1
    assert not [word for word in TELLTALE if word in repr(tallies)]


# ------------------------------------------------------------------------------------------------
# Inside one placement: `diagnose`, and `sample` by cluster or by limit (`v1-e31-t11`)
# ------------------------------------------------------------------------------------------------
#
# A second invented store, of numbered made-up words, so every count below is arithmetic: a body
# of n words has n - 4 shingles. A 330-word card, a 90-word copy from inside it disclosed twice, a
# 30-word cut from inside the copy, and an unrelated 80-word card.


def _numbered(stem: str, count: int, *, start: int = 0) -> list[str]:
    return [f"{stem}{index}" for index in range(start, start + count)]


WHOLE = _numbered("word", 330)
LONG_COPY = WHOLE[100:190]
CUT = LONG_COPY[10:40]
ELSEWHERE = _numbered("elsewhere", 80)
#: Words of those bodies, which output that is meant to hold counts must not contain.
NUMBERED_TELLTALE = ("word0", "word120", "word150", "elsewhere7")

NESTED_CARDS = {
    "one": (
        ("Invented 26", CardCompleteness.FULL, " ".join(WHOLE)),
        ("Invented 26", CardCompleteness.FULL, " ".join(LONG_COPY)),
        ("Invented 26", CardCompleteness.FULL, " ".join(CUT)),
    ),
    "two": (
        ("Invented 26", CardCompleteness.FULL, " ".join(LONG_COPY)),
        ("Other 25", CardCompleteness.FULL, " ".join(ELSEWHERE)),
    ),
}


def _fingerprint_of(words: list[str]) -> str:
    """The exact fingerprint of a body of numbered words: they are already normalized."""
    return hashlib.sha256(" ".join(words).encode("utf-8")).hexdigest()


def _write_store(root: Path, documents: list[ParsedDocument], cluster_of: dict[str, str]) -> None:
    """A store of `documents` whose occurrence table places each exact fingerprint as `cluster_of` says."""
    store = LocalParsedStore(root)
    entries: list[SourceEntry] = []
    rows: list[OccurrenceRecord] = []
    for document in documents:
        common = {
            "caselist": CASELIST,
            "snapshot": "2026-09-01",
            "source_sha256": document.source_sha256,
            "parser_version": document.parser_version,
            "profile_version": document.profile_version,
            "fingerprint_version": "card-fingerprint-v2",
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
            document,
            caselist=CASELIST,
            snapshot="2026-09-01",
            fingerprint_version="card-fingerprint-v2",
            camp=None,
        )
        asyncio.run(store.write_source(CASELIST, document.parser_version, entry, record))
        entries.append(entry)
        for card in document.cards:
            fingerprint = card_fingerprint(card).exact_fingerprint
            rows.append(
                OccurrenceRecord.model_validate(
                    {
                        **common,
                        "last_snapshot": "2026-09-01",
                        "disclosure": "d" * 64,
                        "first_element_index": card.provenance.first_element_index,
                        "last_element_index": card.provenance.last_element_index,
                        "exact_fingerprint": fingerprint,
                        "cluster_id": cluster_of[fingerprint],
                        "membership": ClusterMembership.NEAR_DUPLICATE,
                        "completeness": card.completeness,
                    }
                )
            )
    asyncio.run(
        store.write_aggregates(
            CASELIST, documents[0].parser_version, index=entries, failures=[], occurrences=rows
        )
    )


@pytest.fixture
def nested_dir(tmp_path: Path) -> Path:
    """The nested store as `card-fingerprint-v2` placed it: every text a cluster of its own.

    Written out, not computed: the banding never pairs the copy with the card (`near_duplicates`'
    own tests check that), the cut is inside both and so joined neither under `v2`, and the fourth
    body shares no word with any of them.
    """
    documents = [_document(name, cards) for name, cards in NESTED_CARDS.items()]
    alone = {_fingerprint_of(body): _fingerprint_of(body) for body in (WHOLE, LONG_COPY, CUT, ELSEWHERE)}
    _write_store(tmp_path, documents, alone)
    return tmp_path


def _diagnosed(data_dir: Path, capsys: pytest.CaptureFixture[str], *options: str) -> dict[str, object]:
    assert script.main(["--data-dir", str(data_dir), "diagnose", "--caselist", CASELIST, *options]) == 0
    output = capsys.readouterr().out
    assert not [word for word in (*TELLTALE, *NUMBERED_TELLTALE) if word in output]
    return json.loads(output)[CASELIST]


WITHIN_THE_RULE = "short: one cluster is its witness, within the share, and it is still apart"
LONG_NEVER_PAIRED = "long: its containers are one cluster the banding never paired it with"
NESTED_DETAIL = "its containers are nested copies in several clusters"
SPLIT_BY_THE_BANDING = "pass the thresholds, never paired by the banding"


def test_diagnose_says_which_limit_kept_each_cut_out_and_prints_counts_only(
    nested_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """By hand: five cards, four texts, one of them short. Two bodies have a container outside
    their cluster. The cut (26 shingles) is inside the copy (86) and the card (326), which are two
    clusters, and the card holds the copy: nested, three-tenths of the copy, still apart. The copy
    is 86 of the card's 326 shingles, a long cut the banding never paired with its one container,
    whose cluster is that one text."""
    result = _diagnosed(nested_dir, capsys, "--largest-clusters", "1")
    assert result["placement"] == "the store's table"
    assert result["fingerprint_version"] == "card-fingerprint-v2"
    assert (result["cards"], result["clusters"]) == (5, 4)
    assert (result["full_texts"], result["short_full_texts"]) == (4, 1)
    assert "divided_pairs" not in result

    cuts = result["cuts"]
    assert isinstance(cuts, dict)
    assert cuts["bodies_with_a_container_outside_their_cluster"] == 2
    assert {name: count for name, count in cuts["by_outcome"].items() if count} == {
        WITHIN_THE_RULE: 1,
        LONG_NEVER_PAIRED: 1,
    }
    assert cuts["short_with_containers_in_several_clusters"] == {
        "cuts": 1,
        "of which the containers are nested": 1,
        "as one card, split": 1,
        "as different cards": 0,
        "one card split, by what kept the copies apart": {SPLIT_BY_THE_BANDING: 1},
    }
    assert cuts["short_within_the_rule_and_apart"] == {
        "cuts": 1,
        NESTED_DETAIL: 1,
        "the container first by fingerprint is over the share": 0,
        "neither: another short body of its cluster points elsewhere": 0,
    }
    assert cuts["long_never_paired_by_share"] == {
        "under a tenth": 0,
        "a tenth to a quarter": 0,
        "a quarter to a half": 1,
        "half or more": 0,
    }
    assert cuts["long_with_one_witness_within_the_share"] == {
        "cuts": 1,
        "sharing text with every text of the witness's cluster": 1,
        "of which that cluster is one text": 1,
        "sharing nothing with at least one text of it": 0,
    }

    # The largest cluster is the copy's: one text, disclosed twice.
    (largest,) = result["largest_clusters"]
    assert "cluster_id" not in largest
    assert (largest["rank"], largest["cards"], largest["distinct_texts"], largest["pairs"]) == (1, 2, 1, 0)
    assert (largest["words_smallest"], largest["words_largest"], largest["cards_not_full"]) == (90, 90, 0)


def test_diagnose_can_describe_the_largest_clusters_alone_and_name_them(
    nested_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _diagnosed(
        nested_dir, capsys, "--only-largest-clusters", "--largest-clusters", "1", "--show-cluster-ids"
    )
    assert "cuts" not in result
    assert (result["cards"], result["clusters"]) == (5, 4)
    (largest,) = result["largest_clusters"]
    assert largest["cluster_id"] == _fingerprint_of(LONG_COPY)


def test_diagnose_explains_each_divided_pair_from_a_saved_table(
    nested_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before: the card, the copy and the cut in one cluster, as the rules before the short-body
    step left them when the banding paired the cut with both. Now three clusters. The copy's part
    has the most cards, so it is the host and two parts left it. The cut's part left because the
    cut was left out; the card's part had been joined to the rest only through the cut."""
    store = LocalParsedStore(nested_dir)
    version = script.current_version(store, CASELIST)
    table = store.root / CASELIST / version / "occurrences.jsonl"
    together = {_fingerprint_of(body) for body in (WHOLE, LONG_COPY, CUT)}
    saved = nested_dir / "saved" / f"{CASELIST}.jsonl"
    saved.parent.mkdir()
    rows = [json.loads(line) for line in table.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["exact_fingerprint"] in together:
            row["cluster_id"] = min(together)
        row["fingerprint_version"] = BEFORE_T08
    saved.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    divided = _diagnosed(nested_dir, capsys, "--before", str(saved), "--largest-clusters", "0")[
        "divided_pairs"
    ]
    assert isinstance(divided, dict)
    assert divided["pairs"] == 2
    common = {
        "pairs": 1,
        "outcome": WITHIN_THE_RULE,
        "detail": NESTED_DETAIL,
        "containers_read": "as one card, split",
        "copies_kept_apart_by": [SPLIT_BY_THE_BANDING],
    }
    assert divided["by_reason"] == [
        {**common, "kind": "a short cut in this part was left out"},
        {**common, "kind": "this part was joined only through a short cut elsewhere"},
    ]


def test_diagnose_previews_the_placement_the_checked_out_rules_would_make(
    nested_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Under the current rules the cut joins the copy: three clusters, nothing divided, and the one
    body still outside a cluster that holds it is the long copy. The largest cluster is the copy's
    two cards and the cut: two texts, one pair, the cut wholly inside the copy."""
    result = _diagnosed(nested_dir, capsys, "--preview", "--largest-clusters", "1")
    assert result["placement"] == "the checked-out rules, in memory"
    assert result["fingerprint_version"] == FINGERPRINT_VERSION
    assert (result["cards"], result["clusters"]) == (5, 3)
    cuts = result["cuts"]
    assert isinstance(cuts, dict)
    assert {name: count for name, count in cuts["by_outcome"].items() if count} == {LONG_NEVER_PAIRED: 1}
    assert result["divided_pairs"] == {"pairs": 0, "by_reason": []}
    (largest,) = result["largest_clusters"]
    assert (largest["cards"], largest["distinct_texts"], largest["short_texts"]) == (3, 2, 1)
    assert (largest["pairs"], largest["pairs_sharing_half_or_more"], largest["pairs_matching"]) == (1, 1, 1)


def _placed_and_cards(
    data_dir: Path,
) -> tuple[dict[script.CardKey, script.Placement], dict[script.CardKey, ParsedCard]]:
    store = LocalParsedStore(data_dir)
    version = script.current_version(store, CASELIST)
    placed = script.read_placements(store.root / CASELIST / version / "occurrences.jsonl")
    return placed, script.read_cards(store, CASELIST, version, placed)


def test_bodies_read_as_json_are_the_bodies_the_card_models_hold(nested_dir: Path) -> None:
    store = LocalParsedStore(nested_dir)
    version = script.current_version(store, CASELIST)
    placed, cards = _placed_and_cards(nested_dir)
    texts = script.read_bodies(store, CASELIST, version, placed)
    assert texts == {key: card.evidence_text for key, card in cards.items()}
    assert len(texts) == 5

    (sha256, _element) = next(iter(placed))
    with pytest.raises(SystemExit, match="1 card positions of the table are in no stored document"):
        script.read_bodies(store, CASELIST, version, [(sha256, 999)])


def test_the_largest_cluster_is_found_by_rank_or_by_the_start_of_its_id(nested_dir: Path) -> None:
    placed, _ = _placed_and_cards(nested_dir)
    copy = _fingerprint_of(LONG_COPY)
    assert script._resolve_cluster(placed, None, 1) == copy
    assert script._resolve_cluster(placed, copy[:12].upper(), None) == copy
    assert script._resolve_cluster(placed, copy, None) == copy
    with pytest.raises(SystemExit, match="4 cluster ids start with what was given"):
        script._resolve_cluster(placed, "", None)
    with pytest.raises(SystemExit, match="0 cluster ids start with what was given"):
        script._resolve_cluster(placed, "not-a-digest", None)
    for rank in (0, 5):
        with pytest.raises(SystemExit, match="the placement has 4 clusters"):
            script._resolve_cluster(placed, None, rank)


def test_pairs_inside_a_cluster_are_of_different_texts_one_card_each(nested_dir: Path) -> None:
    """All five cards as one cluster: four texts, so six pairs of different texts, and the copy's
    two cards never paired with each other. The three pairs that share nothing are the unrelated
    card's, and they come first when the least alike are asked for."""
    placed, cards = _placed_and_cards(nested_dir)
    keys = sorted(placed)
    elsewhere = next(key for key in keys if placed[key].exact_fingerprint == _fingerprint_of(ELSEWHERE))

    at_random, available = script.cluster_pairs(cards, placed, keys, count=20, seed=7, least_alike=False)
    assert (len(at_random), available) == (6, 6)
    assert {pair.kind for pair in at_random} == {"full with full"}
    for pair in at_random:
        assert placed[pair.joiner].exact_fingerprint != placed[pair.host].exact_fingerprint
    again, _ = script.cluster_pairs(cards, placed, keys, count=20, seed=7, least_alike=False)
    assert again == at_random

    least_alike, available = script.cluster_pairs(cards, placed, keys, count=3, seed=7, least_alike=True)
    assert (len(least_alike), available) == (3, 6)
    assert all(elsewhere in (pair.joiner, pair.host) for pair in least_alike)


def test_cuts_are_drawn_by_the_limit_that_keeps_them_apart(nested_dir: Path) -> None:
    """The store holds one long cut within the share, the copy, whose smallest container is the
    card. The short cut is within the rule and apart, which is no limit's doing, so no limit draws
    it."""
    from debate_core.evidence.cluster_diagnosis import diagnose_cuts

    store = LocalParsedStore(nested_dir)
    version = script.current_version(store, CASELIST)
    placed, _ = _placed_and_cards(nested_dir)
    bodies, clusters = script.full_bodies(script.read_bodies(store, CASELIST, version, placed), placed)
    findings = diagnose_cuts(bodies, clusters).findings
    drawn = {limit: script.kept_apart(findings, limit) for limit in script.KEPT_APART_BY}
    assert drawn.pop("long-cut-within-the-share") == [(_fingerprint_of(LONG_COPY), _fingerprint_of(WHOLE))]
    assert all(pairs == [] for pairs in drawn.values())


def _as_a_terminal(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    """Let `sample` run under pytest: both streams say they are a terminal, and the keys pressed
    are scripted."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    replies = iter(answers)
    monkeypatch.setattr(script, "read_key", lambda _prompt: next(replies))


def test_sample_by_cluster_draws_from_the_largest_cluster_and_lets_the_rule_decide_a_cut(
    nested_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store rebuilt under the current rules: the largest cluster is the copy's two cards and
    the cut, two texts, one pair of different texts. `--cluster` with its id draws the same pair.
    The cut's 26 shingles are all inside the copy's 86, under a third of them: the rule says it
    is the same card, and nothing is shown (`v1-e31-t21`)."""
    _rebuilt_under_todays_rules(nested_dir)
    cluster_id = min(_fingerprint_of(CUT), _fingerprint_of(LONG_COPY))  # the smallest in the cluster
    for chosen in (["--largest", "1"], ["--cluster", cluster_id[:16]]):
        _as_a_terminal(monkeypatch, [])
        arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, "--seed", "3", *chosen]
        assert script.main(arguments) == 0
        shown = capsys.readouterr().out
        assert not [word for word in NUMBERED_TELLTALE if word in shown]
        assert "to judge" not in shown
        assert shown.endswith(
            "Drew 1 of 1 pairs of different texts, at random, from testcl26's cluster of 3 cards and "
            "2 texts (size rank 1), seed 3.\n"
            "  Decided by rule 1 of 1; asked 0; answered 0 in 0 seconds.\n"
            "  by rule: full with full: contained, under a third of the larger: same card: 1\n"
        )


def test_sample_by_limit_draws_a_cut_beside_the_smallest_body_that_holds_it(
    nested_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The copy's 86 shingles are all inside the card's 326, under a third of it: a cut held by a
    body is contained, the same card by rule, and is counted without being shown."""
    _as_a_terminal(monkeypatch, [])
    arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, "--seed", "3"]
    assert script.main([*arguments, "--kept-apart-by", "long-cut-within-the-share"]) == 0
    shown = capsys.readouterr().out
    assert not [word for word in NUMBERED_TELLTALE if word in shown]
    assert shown.endswith(
        "Drew 1 of 1 cuts kept apart by long-cut-within-the-share, seed 3.\n"
        "  Decided by rule 1 of 1; asked 0; answered 0 in 0 seconds.\n"
        "  by rule: long-cut-within-the-share: contained, under a third of the larger: same card: 1\n"
    )


def test_the_closing_lines_of_each_sample_are_appended_to_a_file_of_counts(
    nested_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each pair clears the terminal and its scrollback, the previous sample's tallies with it.
    The file keeps them, and holds no word of a card."""
    saved = nested_dir / "kept" / "tallies.txt"
    arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, "--seed", "3"]
    for chosen in (["--largest", "1"], ["--kept-apart-by", "long-cut-within-the-share"]):
        _as_a_terminal(monkeypatch, [])
        assert script.main([*arguments, *chosen, "--save-tallies", str(saved)]) == 0
    capsys.readouterr()
    kept = saved.read_text(encoding="utf-8").splitlines()
    assert kept == [
        "Drew 0 of 0 pairs of different texts, at random, from testcl26's cluster of 2 cards and 1 texts "
        "(size rank 1), seed 3.",
        "  Decided by rule 0 of 0; asked 0; answered 0 in 0 seconds.",
        "Drew 1 of 1 cuts kept apart by long-cut-within-the-share, seed 3.",
        "  Decided by rule 1 of 1; asked 0; answered 0 in 0 seconds.",
        "  by rule: long-cut-within-the-share: contained, under a third of the larger: same card: 1",
    ]
    assert not [word for word in NUMBERED_TELLTALE if word in "\n".join(kept)]


@pytest.mark.parametrize(
    ("options", "refusal"),
    [
        (["--largest", "1", "--divided"], "read one placement"),
        (["--kept-apart-by", "lacking-an-end", "--before-rules", "HEAD"], "read one placement"),
        (["--least-alike"], "give --cluster or --largest"),
        (["--largest", "1", "--caselist", "another"], "give --caselist once"),
    ],
)
def test_sample_refuses_options_that_do_not_go_together(
    nested_dir: Path, monkeypatch: pytest.MonkeyPatch, options: list[str], refusal: str
) -> None:
    _as_a_terminal(monkeypatch, [])
    arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, *options]
    with pytest.raises(SystemExit, match=refusal):
        script.main(arguments)


@pytest.mark.parametrize("options", [["--largest", "1"], ["--kept-apart-by", "lacking-an-end"]])
def test_sample_inside_a_placement_also_refuses_anything_but_a_terminal(
    nested_dir: Path, capsys: pytest.CaptureFixture[str], options: list[str]
) -> None:
    arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, *options]
    assert script.main(arguments) == 2
    captured = capsys.readouterr()
    assert "terminal" in captured.err
    assert not [word for word in NUMBERED_TELLTALE if word in captured.out + captured.err]


def test_earlier_rules_place_the_cards_although_the_diagnosis_could_not_import_from_them(
    data_dir: Path,
) -> None:
    """`--before-rules` runs this script against the matching modules of an earlier commit. The
    diagnosis imports names those modules may not have, so the script must not import it until it
    diagnoses. Here the handed-over rules are today's with one such name taken away, as a commit
    before `v1-e31-t11` lacks it: the child still places all five cards."""

    def without_what_the_diagnosis_imports(module: str) -> bytes:
        source = (script.PACKAGE_SOURCE / "debate_core" / module).read_bytes()
        return source.replace(b"confirms_a_cut", b"confirms_a_cut_under_another_name")

    assert (
        b"confirms_a_cut"
        in (script.PACKAGE_SOURCE / "debate_core" / "evidence" / "near_duplicates.py").read_bytes()
    )
    handed_over = script.placements_under_rules(without_what_the_diagnosis_imports, data_dir, CASELIST)
    assert len(handed_over) == 5


def test_diagnose_reads_the_earlier_rules_from_a_git_ref(
    nested_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With `--before-rules HEAD`, before is the committed rules and after is the store's table,
    which here is the one `v2` left. So the comparison reads backwards, as it does for `counts`:
    the committed rules put the cut with the copy, the table has it alone, and that one pair is
    divided, the cut being a short cut that was left out."""
    divided = _diagnosed(nested_dir, capsys, "--before-rules", "HEAD", "--largest-clusters", "0")[
        "divided_pairs"
    ]
    assert isinstance(divided, dict)
    assert divided["pairs"] == 1
    (reason,) = divided["by_reason"]
    assert (reason["kind"], reason["outcome"], reason["detail"]) == (
        "a short cut in this part was left out",
        WITHIN_THE_RULE,
        NESTED_DETAIL,
    )


# ------------------------------------------------------------------------------------------------
# Cluster shapes, and a sample that asks only what a rule cannot decide (`v1-e31-t21`)
# ------------------------------------------------------------------------------------------------
#
# A third invented store: one cluster holding a pair of every shape the rule speaks to, and a
# card alone. By hand, with n words making n - 4 shingles:
#
# * PASSAGE, 200 words (196 shingles), disclosed twice.
# * PASSAGE_CUT, its words 50 to 109 (56 shingles): contained in it, under a third of it.
# * OVERLAPPING, its last 50 words and 50 of its own (96 shingles): 46 shared, 0.48 of the smaller.
# * UNRELATED, 70 words of its own: shares nothing with any of them.
# * PASSAGE_ABBREVIATED, its words 60 to 79, abbreviated (16 shingles): inside PASSAGE and
#   PASSAGE_CUT, sharing nothing with OVERLAPPING or UNRELATED. Never the rule's to decide.
# * LONE, 40 words, a cluster of its own.

PASSAGE = _numbered("passage", 200)
PASSAGE_CUT = PASSAGE[50:110]
OVERLAPPING = [*PASSAGE[150:], *_numbered("further", 50)]
UNRELATED = _numbered("apart", 70)
PASSAGE_ABBREVIATED = PASSAGE[60:80]
LONE = _numbered("lone", 40)
SHAPED_CARDS: dict[str, tuple[tuple[str | None, CardCompleteness, str], ...]] = {
    "one": (
        ("Invented 26", CardCompleteness.FULL, " ".join(PASSAGE)),
        ("Invented 26", CardCompleteness.FULL, " ".join(PASSAGE_CUT)),
        ("Other 25", CardCompleteness.FULL, " ".join(OVERLAPPING)),
        (None, CardCompleteness.FULL, " ".join(UNRELATED)),
        ("Invented 26", CardCompleteness.ABBREVIATED, " ".join(PASSAGE_ABBREVIATED)),
    ),
    "two": (
        ("invented  26", CardCompleteness.FULL, " ".join(PASSAGE)),
        ("Lone 24", CardCompleteness.FULL, " ".join(LONE)),
    ),
}
SHAPED_TELLTALE = ("passage0", "passage120", "further3", "apart7", "lone5", "Invented", "Other 25", "Lone 24")
#: What a file of counts may not hold besides card words: a digest, or a path.
DIGEST_OR_PATH = re.compile(r"[0-9a-f]{12}|/|\\")


@pytest.fixture
def shaped_dir(tmp_path: Path) -> Path:
    documents = [_document(name, cards) for name, cards in SHAPED_CARDS.items()]
    together = [
        _fingerprint_of(body) for body in (PASSAGE, PASSAGE_CUT, OVERLAPPING, UNRELATED, PASSAGE_ABBREVIATED)
    ]
    cluster_of = {fingerprint: min(together) for fingerprint in together}
    cluster_of[_fingerprint_of(LONE)] = _fingerprint_of(LONE)
    _write_store(tmp_path, documents, cluster_of)
    return tmp_path


def _shapes(data_dir: Path, capsys: pytest.CaptureFixture[str], *options: str) -> dict[str, object]:
    assert script.main(["--data-dir", str(data_dir), "shapes", "--caselist", CASELIST, *options]) == 0
    output = capsys.readouterr().out
    assert not [word for word in (*SHAPED_TELLTALE, *NUMBERED_TELLTALE) if word in output]
    return json.loads(output)[CASELIST]


NO_PAIRS = {
    "identical": 0,
    "contained, under a third of the larger": 0,
    "contained, a third or more of the larger": 0,
    "overlapping": 0,
    "sharing a little": 0,
    "sharing nothing": 0,
}


def test_shapes_counts_the_pairs_of_each_largest_cluster_by_shape_and_names_no_text(
    shaped_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The cluster's four full texts make six pairs: the cut inside the passage, the passage and
    the overlapping text, and four sharing nothing. The abbreviated card is counted, not paired."""
    result = _shapes(shaped_dir, capsys, "--largest-clusters", "2")
    assert (result["cards"], result["clusters"]) == (7, 2)
    assert result["fingerprint_version"] == "card-fingerprint-v2"
    first, second = result["described_clusters"]  # type: ignore[misc]
    assert first == {
        "rank": 1,
        "cards": 5,
        "cards_not_full": 1,
        "distinct_texts": 4,
        "texts_with_no_words": 0,
        "pairs": 6,
        "pairs_by_shape": {
            **NO_PAIRS,
            "contained, under a third of the larger": 1,
            "overlapping": 1,
            "sharing nothing": 4,
        },
        "share_of_pairs_by_shape": {
            **dict.fromkeys(NO_PAIRS, 0.0),
            "contained, under a third of the larger": 0.1667,
            "overlapping": 0.1667,
            "sharing nothing": 0.6667,
        },
        "distinct_short_cites": 2,  # the passage's two spellings are one
        "texts_with_no_short_cite": 1,
        "words_smallest": 60,
        "words_median": 85,
        "words_largest": 200,
    }
    assert second == {
        "rank": 2,
        "cards": 1,
        "cards_not_full": 0,
        "distinct_texts": 1,
        "texts_with_no_words": 0,
        "pairs": 0,
        "pairs_by_shape": NO_PAIRS,
        "share_of_pairs_by_shape": dict.fromkeys(NO_PAIRS, 0.0),
        "distinct_short_cites": 1,
        "texts_with_no_short_cite": 0,
        "words_smallest": 40,
        "words_median": 40,
        "words_largest": 40,
    }
    assert "cluster_id" not in first


def test_shapes_describes_one_cluster_by_id_and_names_it_when_asked(
    shaped_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lone = _fingerprint_of(LONE)
    result = _shapes(shaped_dir, capsys, "--cluster", lone[:12], "--show-cluster-ids")
    (described,) = result["described_clusters"]  # type: ignore[misc]
    assert (described["rank"], described["cluster_id"], described["pairs"]) == (2, lone, 0)
    with pytest.raises(SystemExit, match="give --caselist once"):
        script.main(
            [
                "--data-dir",
                str(shaped_dir),
                "shapes",
                "--caselist",
                CASELIST,
                "--caselist",
                "x",
                "--cluster",
                lone,
            ]
        )


@pytest.mark.parametrize("store", ["shaped_dir", "nested_dir"])
def test_shapes_shares_the_texts_and_the_count_sharing_nothing_with_diagnose(
    request: pytest.FixtureRequest, capsys: pytest.CaptureFixture[str], store: str
) -> None:
    """The PM's figures of 2026-10-16 are `diagnose`'s `pairs_sharing_nothing`; `shapes` must give
    the same count of the same pairs, on both invented stores."""
    for data_dir in (request.getfixturevalue(store),):
        shapes = _shapes(data_dir, capsys, "--largest-clusters", "3")["described_clusters"]
        described = _diagnosed(data_dir, capsys, "--only-largest-clusters", "--largest-clusters", "3")
        assert [
            (
                entry["rank"],
                entry["cards"],
                entry["distinct_texts"],
                entry["pairs"],
                entry["pairs_by_shape"]["sharing nothing"],
            )  # type: ignore[index]
            for entry in shapes  # type: ignore[union-attr]
        ] == [
            (
                entry["rank"],
                entry["cards"],
                entry["distinct_texts"],
                entry["pairs"],
                entry["pairs_sharing_nothing"],
            )
            for entry in described["largest_clusters"]  # type: ignore[union-attr]
        ]


def _cards(*bodies: tuple[CardCompleteness, list[str]]) -> list[ParsedCard]:
    return list(
        _document("unit", tuple(("Invented 26", kind, " ".join(words)) for kind, words in bodies)).cards
    )


def _pair(
    kind: str, left: ParsedCard, right: ParsedCard
) -> tuple[str, script.Joined, ParsedCard, ParsedCard]:
    return (CASELIST, script.Joined(kind=kind, joiner=("a" * 64, 1), host=("b" * 64, 2)), left, right)


FULL, ABBREVIATED = CardCompleteness.FULL, CardCompleteness.ABBREVIATED
#: Each drawn pair below, by hand: a cut inside a card (its 46 shingles in the card's 196),
#: two cards sharing nothing, two that overlap (46 of the smaller's 96), and an abbreviated cut
#: inside its card. Each pair's words are its own, so what was shown says which pairs were.
CONTAINED_PAIR = _cards((FULL, _numbered("xray", 200)), (FULL, _numbered("xray", 50, start=10)))
DISJOINT_PAIR = _cards((FULL, _numbered("yank", 80)), (FULL, _numbered("zulu", 80)))
OVERLAP_PAIR = _cards(
    (FULL, _numbered("mid", 100)), (FULL, [*_numbered("mid", 50, start=50), *_numbered("new", 150)])
)
ABBREVIATED_PAIR = _cards((ABBREVIATED, _numbered("alpha", 20)), (FULL, _numbered("alpha", 100)))
DRAWN = [
    _pair("full with full", *CONTAINED_PAIR),
    _pair("full with full", *DISJOINT_PAIR),
    _pair("full with full", *OVERLAP_PAIR),
    _pair("abbreviated with full", *ABBREVIATED_PAIR),
]


def test_a_pair_is_decided_by_rule_only_between_two_full_cards() -> None:
    assert script.classify_pair(*CONTAINED_PAIR) == ("contained, under a third of the larger", "same card")
    assert script.classify_pair(*DISJOINT_PAIR) == ("sharing nothing", "different card")
    assert script.classify_pair(*OVERLAP_PAIR) == ("overlapping", None)
    assert script.classify_pair(*ABBREVIATED_PAIR) == ("contained, under a third of the larger", None)
    (identical,) = _cards((FULL, _numbered("same", 30)))
    assert script.classify_pair(identical, identical) == ("identical", "same card")
    (empty,) = _cards((FULL, ["--"]))
    assert script.classify_pair(empty, identical) == (script.NO_WORDS, None)


def test_the_sample_shows_only_the_pairs_no_rule_decides_and_tallies_the_two_apart() -> None:
    shown: list[str] = []
    asked: list[str] = []
    answers = iter(["s", "u"])

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return next(answers)

    tallies = script.run_sample(
        DRAWN, ask=ask, show=shown.append, columns=120, clock=iter([10.0, 75.4]).__next__
    )

    screens = "".join(shown).split(script.CLEAR_TERMINAL)[1:-1]
    assert len(screens) == len(asked) == 2
    assert "mid60" in screens[0] and "alpha5" in screens[1]
    assert not [word for word in ("xray", "yank", "zulu") if word in "".join(shown)]
    assert screens[0].startswith("Pair 1 of 2 to judge; the rule decided 2 of the 4 drawn.")
    assert tallies.decided == {
        ("full with full", "contained, under a third of the larger", "same card"): 1,
        ("full with full", "sharing nothing", "different card"): 1,
    }
    assert tallies.answered == {
        ("full with full", "overlapping", "same card"): 1,
        ("abbreviated with full", "contained, under a third of the larger", "unsure"): 1,
    }
    assert tallies.lines() == [
        "  Decided by rule 2 of 4; asked 2; answered 2 in 65 seconds.",
        "  by rule: full with full: contained, under a third of the larger: same card: 1",
        "  by rule: full with full: sharing nothing: different card: 1",
        "  asked: abbreviated with full: contained, under a third of the larger: unsure: 1",
        "  asked: full with full: overlapping: same card: 1",
    ]


def test_the_stop_key_ends_the_sample_and_keeps_what_was_answered() -> None:
    answers = iter(["d", script.STOP_KEY])
    shown: list[str] = []
    tallies = script.run_sample(
        DRAWN,
        ask=lambda _prompt: next(answers),
        show=shown.append,
        columns=120,
        clock=iter([0.0, 30.0]).__next__,
    )
    assert "alpha5" in "".join(shown)  # the second pair was shown, and the stop key answered it
    assert tallies.answered == {("full with full", "overlapping", "different card"): 1}
    assert (
        tallies.lines()[0]
        == "  Decided by rule 2 of 4; asked 2; answered 1 in 30 seconds, stopped with 1 not answered."
    )
    assert shown[-1] == script.CLEAR_TERMINAL


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _styled(style: str, word: str) -> str:
    return f"{style}{word}{script.RESET_STYLE}"


def test_a_shown_pair_has_its_counts_and_shares_at_the_top_and_its_shared_text_marked() -> None:
    """The overlapping pair: 46 shingles shared, 48% of the first's 96 and 23% of the second's
    196. The first is shown whole: its first 50 words its own, its last 50 shared."""
    left, right = OVERLAP_PAIR
    shown = script.render_pair(left, right, "overlapping", 80)
    header, _, sides = shown.partition("\n--- A\n")
    first, _, second = sides.partition("\n--- B\n")
    assert header.splitlines()[:3] == [
        "Shape: overlapping.",
        "A: FULL, 100 words, cite Invented 26; 48% of its five-word runs are in the other.",
        "B: FULL, 200 words, cite Invented 26; 23% of its five-word runs are in the other. "
        "Showing 45 of them.",
    ]
    assert _styled(script.OWN_STYLE, "mid49") in first
    assert _styled(script.SHARED_STYLE, "mid50") in first
    assert _styled(script.SHARED_STYLE, "mid99") in first
    assert _styled(script.SHARED_STYLE, "mid10") not in first
    assert _styled(script.OWN_STYLE, "new0") in second
    assert _styled(script.SHARED_STYLE, "mid50") in second


def test_a_long_side_is_trimmed_to_its_shared_region_and_says_how_much_was_left_out() -> None:
    """The second text, 200 words: its first 50 shared, the rest its own. Shown: ten words at each
    end of the shared run, 25 of its own after it; 30 and 125 words are left out, and said to be."""
    left, right = OVERLAP_PAIR
    second = ANSI.sub("", script.render_pair(left, right, "overlapping", 80).partition("\n--- B\n")[2])
    words = second.split()
    assert "mid59" in words and "mid90" in words and "mid60" not in words and "mid89" not in words
    assert "new24" in words and "new25" not in words
    assert "[… 30 words shared not shown …]" in second
    assert "[… 125 words after not shown …]" in second


def test_a_long_side_keeps_some_of_its_own_text_on_each_side_of_the_region_it_shares() -> None:
    """100 words of its own, 20 shared, 100 more of its own: 25 kept each side of the shared 20."""
    marked = [(f"before{index}", False) for index in range(100)]
    marked += [(f"s{index}", True) for index in range(20)]
    marked += [(f"after{index}", False) for index in range(100)]
    runs, shown = script._trimmed(marked)
    assert runs[0].words == ("[… 75 words before not shown …]",)
    assert runs[1].words[0] == "before75"
    assert runs[-2].words[-1] == "after24"
    assert runs[-1].words == ("[… 75 words after not shown …]",)
    assert shown == 25 + 20 + 25


def test_runs_of_a_side_s_own_text_inside_its_shared_region_keep_their_ends() -> None:
    marked = [(f"s{index}", True) for index in range(20)]
    marked += [(f"own{index}", False) for index in range(200)]
    marked += [(f"t{index}", True) for index in range(20)]
    runs, shown = script._trimmed(marked)
    notes = [run.words[0] for run in runs if run.note]
    assert notes == ["[… 120 words of its own not shown …]"]
    assert shown == 20 + 80 + 20


def test_a_long_side_sharing_nothing_shows_its_opening_and_says_how_much_is_left() -> None:
    runs, shown = script._trimmed([(f"w{index}", False) for index in range(200)])
    assert shown == script.SHOWN_IN_FULL_WORDS
    assert runs[-1].words == ("[… 50 more words not shown …]",)


@pytest.mark.parametrize(("columns", "side_by_side"), [(80, False), (102, False), (103, True), (160, True)])
def test_two_texts_are_side_by_side_when_the_terminal_is_wide_enough_and_never_wider_than_it(
    columns: int, side_by_side: bool
) -> None:
    shown = script.render_pair(*OVERLAP_PAIR, "overlapping", columns)
    assert ("--- A" in shown) is not side_by_side
    lines = [ANSI.sub("", line) for line in shown.partition("\n\n")[2].splitlines()]
    if side_by_side:
        assert lines[0].split() == ["A", "│", "B"]
        assert all(" │" in line for line in lines)
    else:
        assert not [line for line in lines if "│" in line]
    assert max(len(line) for line in lines) <= columns


def test_written_words_are_marked_by_the_matching_words_they_hold() -> None:
    """`commis- sion` is one matching word in two written ones; a dash goes with the word before."""
    text = "One two three four five commis- sion six — seven eight nine ten"
    marked = script._marked_words(text, shingles_of("six seven eight nine ten"))
    assert marked == [
        ("One", False),
        ("two", False),
        ("three", False),
        ("four", False),
        ("five", False),
        ("commis- sion", False),
        ("six", True),
        ("—", True),
        ("seven", True),
        ("eight", True),
        ("nine", True),
        ("ten", True),
    ]
    assert all(flag for _, flag in script._marked_words(text, shingles_of(text)))


def shingles_of(text: str) -> frozenset[str]:
    from debate_core.evidence.near_duplicates import shingles

    return shingles(text)


@pytest.mark.skipif(sys.platform == "win32", reason="reads a key through termios")
def test_one_key_answers_and_a_key_pressed_before_the_question_is_discarded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A key pressed twice must not answer the next pair before anyone has seen it.

    A pseudo-terminal stands in for the operator's. Something has to read what it echoes, as a
    terminal emulator does, or switching it to one key at a time waits for that output forever.
    """
    import os
    import pty
    import threading

    controller, terminal = pty.openpty()

    def emulator() -> None:
        try:
            while os.read(controller, 1024):
                pass
        except OSError:
            pass

    keys = [
        threading.Timer(0.3, os.write, (controller, b"d")),
        threading.Timer(3.0, os.write, (controller, b"u")),
    ]
    threading.Thread(target=emulator, daemon=True).start()
    try:
        with open(terminal, encoding="utf-8", closefd=False) as stream:  # noqa: PTH123 - a descriptor, not a path
            monkeypatch.setattr(sys, "stdin", stream)
            os.write(controller, b"s")  # pressed while the pair was being drawn
            for key in keys:
                key.start()
            answer = script.read_key("> ")
    finally:
        for key in keys:
            key.cancel()
        os.close(terminal)
        os.close(controller)
    assert answer == "d"
    assert capsys.readouterr().out == "> d\n"


def _sample_shaped(data_dir: Path, monkeypatch: pytest.MonkeyPatch, answers: list[str], *options: str) -> int:
    _as_a_terminal(monkeypatch, answers)
    arguments = ["--data-dir", str(data_dir), "sample", "--caselist", CASELIST, "--seed", "3", *options]
    return script.main(arguments)


def test_a_cluster_sample_asks_about_five_of_its_ten_pairs_and_saves_counts_alone(
    shaped_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five texts, ten pairs. The rule decides five: the cut inside the passage is the same card,
    and the four pairs of full texts sharing nothing are different cards. The person is asked the
    overlapping pair and the abbreviated card's four, whatever they share."""
    saved = shaped_dir / "kept" / "tallies.txt"
    options = ("--largest", "1", "--count", "10", "--save-tallies", str(saved))
    assert _sample_shaped(shaped_dir, monkeypatch, ["s"] * 5, *options) == 0
    shown = capsys.readouterr().out
    assert shown.count("to judge; the rule decided 5 of the 10 drawn.") == 5
    kept = saved.read_text(encoding="utf-8")
    assert re.sub(r"in \d+ seconds", "in N seconds", kept).splitlines() == [
        "Drew 10 of 10 pairs of different texts, at random, from testcl26's cluster of 6 cards and 5 texts "
        "(size rank 1), seed 3.",
        "  Decided by rule 5 of 10; asked 5; answered 5 in N seconds.",
        "  by rule: full with full: contained, under a third of the larger: same card: 1",
        "  by rule: full with full: sharing nothing: different card: 4",
        "  asked: abbreviated with full: contained, under a third of the larger: same card: 2",
        "  asked: abbreviated with full: sharing nothing: same card: 2",
        "  asked: full with full: overlapping: same card: 1",
    ]
    assert shown.endswith(kept)


@pytest.mark.parametrize(
    ("store", "answers", "options"),
    [
        ("shaped_dir", ["d", "s", "u", "d", "s"], ["--largest", "1", "--count", "10"]),
        ("shaped_dir", ["s", "q"], ["--largest", "1", "--least-alike"]),
        ("nested_dir", [], ["--kept-apart-by", "long-cut-within-the-share"]),
        ("data_dir", ["s", "d"], []),
        ("data_dir", [], ["--divided"]),
    ],
)
def test_nothing_a_sample_saves_holds_text_a_tag_a_cite_a_path_or_a_digest(
    request: pytest.FixtureRequest,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    store: str,
    answers: list[str],
    options: list[str],
) -> None:
    data_dir: Path = request.getfixturevalue(store)
    saved = data_dir / "kept" / "tallies.txt"
    assert _sample_shaped(data_dir, monkeypatch, answers, *options, "--save-tallies", str(saved)) == 0
    capsys.readouterr()
    kept = saved.read_text(encoding="utf-8")
    assert kept.startswith("Drew ")
    assert "  Decided by rule " in kept
    forbidden = (
        *TELLTALE,
        *NUMBERED_TELLTALE,
        *SHAPED_TELLTALE,
        "Invented tag",
        "Fictional Review",
        "Maple Grove",
    )
    assert not [word for word in forbidden if word in kept]
    assert not DIGEST_OR_PATH.findall(kept)
    assert str(data_dir) not in kept
