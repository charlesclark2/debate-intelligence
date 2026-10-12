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

    tallies = script.run_sample(pairs, ask=lambda _prompt: next(answers), show=shown.append)

    assert sum(tallies.values()) == 2
    assert sum("Newly in one cluster." in text for text in shown) == 2
    assert {verdict for _, verdict in tallies} == {"same card", "different card"}
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


def _numbered(stem: str, count: int) -> list[str]:
    return [f"{stem}{index}" for index in range(count)]


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
    """Let `sample` run under pytest: both streams say they are a terminal, and input is scripted."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(replies))


def test_sample_by_cluster_shows_pairs_from_the_largest_cluster_and_ends_with_tallies(
    nested_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store rebuilt under the current rules: the largest cluster is the copy's two cards and
    the cut, two texts, one pair of different texts. `--cluster` with its id draws the same pair."""
    _rebuilt_under_todays_rules(nested_dir)
    cluster_id = min(_fingerprint_of(CUT), _fingerprint_of(LONG_COPY))  # the smallest in the cluster
    for chosen in (["--largest", "1"], ["--cluster", cluster_id[:16]]):
        _as_a_terminal(monkeypatch, ["s"])
        arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, "--seed", "3", *chosen]
        assert script.main(arguments) == 0
        shown = capsys.readouterr().out
        before_the_tallies, _, tallies = shown.rpartition(script.CLEAR_TERMINAL)
        assert "word120" in before_the_tallies  # the pair was shown, to what says it is a terminal
        assert "In one cluster now." in before_the_tallies
        assert not [word for word in NUMBERED_TELLTALE if word in tallies]
        assert (
            "Drew 1 of 1 pairs of different texts, at random, from testcl26's cluster of 3 cards and "
            "2 texts (size rank 1), seed 3." in tallies
        )
        assert "full with full: same card: 1" in tallies


def test_sample_by_limit_shows_a_cut_beside_the_smallest_body_that_holds_it(
    nested_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _as_a_terminal(monkeypatch, ["d"])
    arguments = ["--data-dir", str(nested_dir), "sample", "--caselist", CASELIST, "--seed", "3"]
    assert script.main([*arguments, "--kept-apart-by", "long-cut-within-the-share"]) == 0
    shown = capsys.readouterr().out
    before_the_tallies, _, tallies = shown.rpartition(script.CLEAR_TERMINAL)
    assert "Apart now. B is the smallest body that holds A." in before_the_tallies
    assert "--- A: FULL, 90 words" in before_the_tallies
    assert "--- B: FULL, 330 words" in before_the_tallies
    assert not [word for word in NUMBERED_TELLTALE if word in tallies]
    assert "Drew 1 of 1 cuts kept apart by long-cut-within-the-share, seed 3." in tallies
    assert "long-cut-within-the-share: different card: 1" in tallies


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
