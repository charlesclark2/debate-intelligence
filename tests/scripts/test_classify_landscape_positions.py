"""`scripts/classify_landscape_positions.py` end to end on a planted store (`v1-e32-t02` ac4, ac5).

Two invented sources in a synthetic caselist, disclosed a week apart by two invented teams. The
counts each run prints were worked out by hand from those cards (working agreement 6): four cards,
two placed by alias and two under `Fed Key`, which no alias names; seven distinct cache keys. The
second run is all hits; after the coach's decision on `fed key`, two keys miss and the rest hit.

Every school, team code, tournament and heading here is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import classify_landscape_positions as script  # noqa: E402

CASELIST = "hspolicy99"
TOPIC = "policy-sample-topic"

TOPICS = f"""\
schema_version: 1
topics:
  - id: {TOPIC}
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {{caselist: {CASELIST}, from: 2026-09-01, to: 2026-12-31}}
"""

TAXONOMY = f"""\
schema_version: 1
topic_id: {TOPIC}
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {{id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}}
  - {{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}}
"""

NEG = "School One/CodeOne/School One-CodeOne-Neg-Sample Invitational-Round 1.docx"
AFF = "School Two/CodeTwo/School Two-CodeTwo-Aff-Sample Invitational-Round 2.docx"


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    """`(data_dir, config_dir)`: the planted store and a config directory with the sample taxonomy."""
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    store.source(
        "one",
        [PlantedCard(("1NC", "Spending DA")), PlantedCard(("1NC", "Fed Key"))],
        disclosures=[("2026-09-08", NEG)],
    )
    store.source(
        "two",
        [PlantedCard(("Fed Key",)), PlantedCard(("AT: Spending DA",))],
        disclosures=[("2026-09-15", AFF)],
    )
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return data_dir, config_dir


def classify(world: tuple[Path, Path], *extra: str) -> int:
    data_dir, config_dir = world
    return script.main(
        [
            "--config-dir",
            str(config_dir),
            "classify",
            "--caselist",
            CASELIST,
            "--data-dir",
            str(data_dir),
            *extra,
        ]
    )


def printed(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if not line.startswith("Runtime")]


def test_classify_prints_counts_and_a_second_run_is_all_cache_hits(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, _ = world
    queue = data_dir / "landscape" / "review" / CASELIST / f"{TOPIC}-review-queue.csv"
    assert classify(world) == 0
    assert printed(capsys) == [
        f"Read {CASELIST} 2026.10.20-docx-6 through 2026-09-15: 2 source entries, 2 parsed, 2 on {TOPIC}.",
        f"Classified {CASELIST} on {TOPIC} 1.0.0 (prompt version none).",
        "Sources 2; sections 5; cards 4.",
        "  cards ALIAS: 2 (50.0%)",
        "  cards OVERRIDE: 0 (0.0%)",
        "  cards INHERITED: 0 (0.0%)",
        "  cards TAG_KEYWORD: 0 (0.0%)",
        "  cards OVERRIDE_NO_POSITION: 0 (0.0%)",
        "  cards UNPLACED: 2 (50.0%)",
        "Cards counted (placed at or above the review threshold): 2 (50.0%); below the threshold: 0.",
        "Review queue: 5 items (2 cards, 1 under no heading) under 1 headings; 1 rows written, "
        "0 headings left out as used by too few teams.",
        f"Wrote the review queue to {queue}.",
        "Cache: 7 distinct keys, 0 hits (0.0%), 7 placed (0 cached results refused); written.",
    ]
    assert queue.read_text(encoding="utf-8").splitlines()[1] == "fed key,false,2,2,1,1,2,,"
    assert classify(world, "--show-unplaced", "5") == 0
    second = printed(capsys)
    assert (
        "Cache: 7 distinct keys, 7 hits (100.0%), 0 placed (0 cached results refused); unchanged." in second
    )
    assert second[-1] == "  unplaced: fed key: 2 teams, 2 documents, 2 cards; candidates none"


def test_classify_reads_the_store_as_it_stood_at_a_snapshot(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert classify(world, "--snapshot", "2026-09-08") == 0
    lines = printed(capsys)
    assert (
        lines[0]
        == f"Read {CASELIST} 2026.10.20-docx-6 through 2026-09-08: 2 source entries, 2 parsed, 1 on {TOPIC}."
    )
    assert "Sources 1; sections 3; cards 2." in lines


def test_classify_fails_when_it_reads_no_source(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert classify(world, "--snapshot", "2026-09-01") == 1
    assert "FAILED: 0 sources read" in capsys.readouterr().err


def test_classify_refuses_a_snapshot_on_no_topic(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert classify(world, "--snapshot", "2026-08-01") == 2
    assert "on no topic with a taxonomy" in capsys.readouterr().err


def test_classify_refuses_a_data_directory_inside_the_repository(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir = world
    inside = script.REPO_ROOT / "build" / "landscape-data"
    code = script.main(
        ["--config-dir", str(config_dir), "classify", "--caselist", CASELIST, "--data-dir", str(inside)]
    )
    assert code == 2
    assert "outside the repository" in capsys.readouterr().err
    assert not inside.exists()


def test_apply_decisions_writes_overrides_that_place_the_heading_next_run(
    world: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, config_dir = world
    assert classify(world) == 0
    capsys.readouterr()
    queue = data_dir / "landscape" / "review" / CASELIST / f"{TOPIC}-review-queue.csv"
    decisions = tmp_path / "decisions.csv"
    decisions.write_text(
        queue.read_text(encoding="utf-8").replace(
            "fed key,false,2,2,1,1,2,,", "fed key,false,2,2,1,1,2,,states-cp"
        ),
        encoding="utf-8",
    )
    code = script.main(
        [
            "--config-dir",
            str(config_dir),
            "apply-decisions",
            "--topic",
            TOPIC,
            "--decisions",
            str(decisions),
            "--today",
            "2026-10-24",
        ]
    )
    assert code == 0
    target = config_dir / "overrides" / f"{TOPIC}.yaml"
    assert capsys.readouterr().out.splitlines()[0] == (
        f"Applied 1 decisions to {TOPIC}: 1 added, 0 changed, 0 unchanged; 1 overrides in {target}."
    )
    assert "heading: fed key\n    position_id: states-cp\n    decided: '2026-10-24'" in target.read_text(
        encoding="utf-8"
    )
    assert classify(world) == 0
    lines = printed(capsys)
    assert "  cards OVERRIDE: 2 (50.0%)" in lines
    assert "  cards UNPLACED: 0 (0.0%)" in lines
    assert "Cache: 7 distinct keys, 5 hits (71.4%), 2 placed (0 cached results refused); written." in lines


def test_apply_decisions_refuses_a_decision_naming_no_position(
    world: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir = world
    decisions = tmp_path / "decisions.csv"
    decisions.write_text("normalized_heading,decision\nfed key,medicaid-da\n", encoding="utf-8")
    code = script.main(
        ["--config-dir", str(config_dir), "apply-decisions", "--topic", TOPIC, "--decisions", str(decisions)]
    )
    assert code == 2
    assert "not a position" in capsys.readouterr().err
    assert not (config_dir / "overrides").exists()


def test_apply_decisions_refuses_a_decisions_file_inside_the_repository(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir = world
    inside = script.REPO_ROOT / "decisions.csv"
    code = script.main(
        ["--config-dir", str(config_dir), "apply-decisions", "--topic", TOPIC, "--decisions", str(inside)]
    )
    assert code == 2
    assert "outside the repository" in capsys.readouterr().err
