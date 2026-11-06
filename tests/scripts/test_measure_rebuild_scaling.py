"""`scripts/measure_rebuild_scaling.py`, on synthetic stores built in a temporary directory.

The real run is the operator's, over the dev data directory (`v1-e31-t10`, Goal criterion ac1). What
it is held to here, by the PM's ruling of 2026-11-06:

* **It is read-only.** Over a store holding its aggregates, no file is added, removed or changed,
  by bytes or modification time, and the table it would have written has the store's own SHA-256:
  the rebuild it times is the one the store was built by.
* **It prints counts, seconds and shares only.** No invented word of any card, no tag, cite, path,
  school or team appears in what it prints.
* **Its component counts are the ones worked out by hand** for small dependency graphs, including a
  short body whose both-end holders are bounded as a stock phrase.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import measure_rebuild_scaling as script  # noqa: E402

SEED = 7


def tree(root: Path) -> dict[str, tuple[str, int]]:
    """Every file under `root`: its SHA-256 and modification time; directories with neither."""
    found: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            found[relative] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        else:
            found[relative] = ("directory", 0)
    return found


@pytest.fixture
def built_store(tmp_path: Path) -> Path:
    asyncio.run(script.build_synthetic_store(tmp_path, 24, SEED, aggregates=True))
    return tmp_path


def test_real_mode_reads_the_store_and_writes_nothing(
    built_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = tree(built_store)
    assert any(name.endswith("occurrences.jsonl") for name in before)

    assert script.main(["real", "--data-dir", str(built_store), "--caselist", script.SYNTHETIC_CASELIST]) == 0

    assert tree(built_store) == before
    printed = capsys.readouterr()
    result = json.loads(printed.out)
    assert result["table_equals_the_stores"] is True
    assert result["sources"] == 24
    assert result["version"] == script.SYNTHETIC_PARSER_VERSION
    assert json.loads(printed.err) == {"rebuild_seconds": result["rebuild_seconds"]}


def test_the_phases_add_up_to_the_rebuild(built_store: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script.main(["real", "--data-dir", str(built_store), "--caselist", script.SYNTHETIC_CASELIST])
    result = json.loads(capsys.readouterr().out)
    phases = result["phases_seconds"]
    assert set(phases) == {
        "read_documents",
        "fingerprints",
        "body_words",
        "cut_index",
        "minhash",
        "band_pairs_and_jaccard",
        "joins_of_copies",
        "cut_step",
        "linking",
        "writing",
        "state_read",
        "state_write",
        "plan_ordering_and_rest",
    }
    assert sum(phases.values()) == pytest.approx(result["rebuild_seconds"], abs=0.1)
    assert all(seconds >= 0 for name, seconds in phases.items() if name != "plan_ordering_and_rest")
    assert phases["minhash"] > 0


def test_nothing_printed_is_a_word_of_a_card_a_path_or_a_name(
    built_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script.main(["real", "--data-dir", str(built_store), "--caselist", script.SYNTHETIC_CASELIST])
    script.main(["synthetic", "--sources", "24", "--seed", str(SEED), "--components"])
    printed = capsys.readouterr()
    text = printed.out + printed.err
    vocabulary = set(script.SyntheticCorpus(SEED).words)
    words = {word.lower() for word in re.findall(r"[A-Za-z]+", text)}
    assert not words & vocabulary
    for forbidden in ("Invented", "School", "Team", "round-", ".docx", "claim", "Quarterly", "…"):
        assert forbidden not in text


def test_synthetic_mode_prints_one_line_per_size(capsys: pytest.CaptureFixture[str]) -> None:
    assert script.main(["synthetic", "--sources", "12", "24", "--seed", str(SEED)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["sources"] for line in lines] == [12, 24]
    assert all("components" not in json.loads(line) for line in lines)


# ------------------------------------------------------------------------------------------------
# The component counts, worked out by hand
# ------------------------------------------------------------------------------------------------


def test_a_week_reaches_the_stored_components_its_new_bodies_join() -> None:
    # Stored: {a, b} joined, {c}, {e}. The new body d joins c. So the week re-clusters c and d: 2 of 5.
    edges = script.DependencyEdges(joining=frozenset({("a", "b"), ("c", "d")}), both_ends={})
    counted = script.reached(edges, {"a", "b", "c", "d", "e"}, {"d"}, bound_stock_phrases=False)
    assert counted == {
        "stored_components": 3,
        "largest_stored_components": [2, 1, 1],
        "components_reached": 1,
        "bodies_to_recluster": 2,
        "share_of_bodies_to_recluster": 0.4,
    }


def test_a_new_body_holding_both_ends_of_a_stored_short_body_reaches_it() -> None:
    # s is short; the new body n holds both its ends, and joins nothing. s's component is reached.
    edges = script.DependencyEdges(joining=frozenset({("s", "t")}), both_ends={"s": ("n",)})
    counted = script.reached(edges, {"s", "t", "n", "u"}, {"n"}, bound_stock_phrases=False)
    assert counted["components_reached"] == 1
    assert counted["bodies_to_recluster"] == 3  # n, and s with t


def test_a_stock_phrase_bound_drops_a_saturated_short_bodys_edges() -> None:
    # Ten holders, each its own component, hold both ends of the short body s: with the bound, s's
    # too-common count cannot fall to eight, so its edges go and every holder stays a component of
    # its own. Without it, s joins all ten: one component of eleven.
    holders = tuple(f"h{number:02d}" for number in range(10))
    edges = script.DependencyEdges(joining=frozenset(), both_ends={"s": holders})
    members = {"s", *holders}
    bounded = script.components(edges, members, bound_stock_phrases=True)
    every = script.components(edges, members, bound_stock_phrases=False)
    assert len({bounded.find(member) for member in members}) == 11
    assert len({every.find(member) for member in members}) == 1


def test_nine_holders_are_not_a_stock_phrase() -> None:
    # Nine components can still fall to eight clusters other than s's own, so the edges stay.
    holders = tuple(f"h{number}" for number in range(9))
    edges = script.DependencyEdges(joining=frozenset(), both_ends={"s": holders})
    members = {"s", *holders}
    bounded = script.components(edges, members, bound_stock_phrases=True)
    assert len({bounded.find(member) for member in members}) == 1


def test_the_incremental_steps_place_a_week_from_the_state_and_its_table_is_the_full_rebuilds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`v1-e31-t10`, ac3's measurement: forty sources, the last two a new week."""
    data_dir = tmp_path / "store"
    for step in ("prepare", "week", "full"):
        assert (
            script.main(
                [
                    "incremental",
                    step,
                    "--sources",
                    "40",
                    "--seed",
                    str(SEED),
                    "--new-share",
                    "0.05",
                    "--data-dir",
                    str(data_dir),
                ]
            )
            == 0
        )
    prepare, week, full = (json.loads(line) for line in capsys.readouterr().out.splitlines())

    assert prepare["path"] == ["rebuilt in full (NO_STATE), 38 placed sources read"]
    assert week["parsed_this_run"] == 2
    assert week["path"] == ["placed from the placement state, 2 of 40 placed sources read"]
    assert full["path"] == ["rebuilt in full (TURNED_OFF), 40 placed sources read"]
    assert full["table_equals_the_weeks"] is True
    assert week["distinct_full_bodies_signed"] < full["distinct_full_bodies_signed"]
    assert week["state_bytes"] > 0
