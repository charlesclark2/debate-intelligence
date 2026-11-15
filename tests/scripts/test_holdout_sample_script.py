"""`scripts/compare_local_classifier.py holdout-sample` end to end on a planted store (`v1-e32-t50`).

Twenty invented sources by six invented teams: ten disclosed on 2026-09-15, which the first sample is drawn
from, and ten on 2026-09-22. Each holds six cards aliases place and two no heading places. The occurrence
table gives every card a body and cluster of its own, except that the first unplaced card of each later source
is in the cluster of the same card of its earlier twin: a copy of that evidence in another team's file. The
holdout is drawn at 2026-09-22 and must share no document and no cluster with the first sample. It writes its
own files and refuses to write over any; the first sample's commands still read their one feature table.

Every school, team code, tournament, heading and tag here is invented.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.coach_sample_labels_file import digest_path, labels_digest
from debate_core.application.ports.parsed_store import (
    OCCURRENCES_NAME,
    PARSED_PREFIX,
    OccurrenceRecord,
    parse_version_directory,
)
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.domain.landscape_classification import card_item_id
from debate_core.testing.landscape_store import PARSER_VERSION, PROFILE_VERSION, PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import compare_local_classifier as script  # noqa: E402

CASELIST = "hspolicy98"
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
TEAMS = (
    ("Larkspur Point", "LaPo"),
    ("Larkspur Point", "LaPt"),
    ("Juniper Bay", "JuBa"),
    ("Juniper Bay", "JuBy"),
    ("Hollis Mill", "HoMi"),
    ("Hollis Mill", "HoMl"),
)
SNAPSHOTS = ("2026-09-15", "2026-09-22")
PARAGRAPHS_PER_CARD = 3


def _cards(number: int) -> list[PlantedCard]:
    return [
        *(
            PlantedCard(("1NC", "Spending DA"), tag="Deficit spending crowds out investment")
            for _ in range(3)
        ),
        *(PlantedCard(("1NC", "States CP"), tag="Fifty states solve uniformly") for _ in range(3)),
        PlantedCard(("1NC", "Solvency"), tag=f"Deficit spending crowds out investment now {number}"),
        PlantedCard(("Off",), tag=f"Fifty states solve uniformly now {number}"),
    ]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path, Path]:
    """`(data_dir, config_dir, labels_out)`."""
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    occurrences: list[OccurrenceRecord] = []
    for number in range(20):
        school, code = TEAMS[number % len(TEAMS)]
        snapshot = SNAPSHOTS[number // 10]
        path = f"{school}/{code}/{school}-{code}-Neg-Sample Classic-Round {number + 1}.docx"
        cards = _cards(number)
        sha = store.source(f"source-{number}", cards, disclosures=[(snapshot, path)])
        for index in range(len(cards)):
            twin = number % 10 if index == 6 else number
            first = index * PARAGRAPHS_PER_CARD
            occurrences.append(
                OccurrenceRecord.model_validate(
                    {
                        "caselist": CASELIST,
                        "snapshot": snapshot,
                        "last_snapshot": snapshot,
                        "source_sha256": sha,
                        "parser_version": PARSER_VERSION,
                        "profile_version": PROFILE_VERSION,
                        "fingerprint_version": "card-fingerprint-v4",
                        "disclosure": disclosure_digest(CASELIST, path),
                        "first_element_index": first,
                        "last_element_index": first + 2,
                        "exact_fingerprint": _digest(f"body {number} {index}"),
                        "cluster_id": _digest(f"cluster {twin} {index}"),
                        "membership": "NEAR_DUPLICATE",
                        "completeness": "FULL",
                    }
                )
            )
    table = data_dir / PARSED_PREFIX / CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    table.write_text("".join(one.model_dump_json() + "\n" for one in occurrences), encoding="utf-8")
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return data_dir, config_dir, tmp_path / "review" / "holdout-sample-labelled.csv"


def run(world: tuple[Path, Path, Path], command: str, *extra: str) -> int:
    data_dir, config_dir, _ = world
    arguments = [
        "--config-dir",
        str(config_dir),
        command,
        "--caselist",
        CASELIST,
        "--data-dir",
        str(data_dir),
    ]
    return script.main([*arguments, *extra], environ={}, processes=lambda: [])


def holdout(world: tuple[Path, Path, Path], *extra: str) -> int:
    return run(world, "holdout-sample", "--snapshot", SNAPSHOTS[1], "--labels-out", str(world[2]), *extra)


def output(world: tuple[Path, Path, Path]) -> Path:
    return world[0] / "landscape" / "local-classifier" / CASELIST


def files_under(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def rows_of(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[0], lines[1:]


def clusters(world: tuple[Path, Path, Path]) -> dict[str, str]:
    table = world[0] / PARSED_PREFIX / CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    found: dict[str, str] = {}
    for line in table.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        found[card_item_id(row["source_sha256"], row["first_element_index"])] = row["cluster_id"]
    return found


@pytest.fixture
def first_sample(world: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]) -> dict[Path, bytes]:
    """The first sample, drawn at 2026-09-15 as `v1-e32-t21` drew it; its files, as written."""
    assert run(world, "features", "--snapshot", SNAPSHOTS[0]) == 0
    assert run(world, "sample") == 0
    capsys.readouterr()
    return files_under(output(world))


HOLDOUT_FILES = (f"{TOPIC}-holdout-2026-09-22-features.jsonl", f"{TOPIC}-holdout-2026-09-22-sample.jsonl")


def test_the_holdout_shares_no_document_or_cluster_with_the_first_sample(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    assert holdout(world) == 0

    printed = capsys.readouterr().out
    _, first = rows_of(output(world) / f"{TOPIC}-coach-sample.jsonl")
    header, held_out = rows_of(output(world) / HOLDOUT_FILES[1])
    cluster_of = clusters(world)
    assert len(first) == 10 and len(held_out) == 10
    assert not {one["source_sha256"] for one in first} & {one["source_sha256"] for one in held_out}
    assert not {cluster_of[one["item_id"]] for one in first} & {
        cluster_of[one["item_id"]] for one in held_out
    }
    copies = sum(one["item_id"].endswith(f":card:{6 * PARAGRAPHS_PER_CARD}") for one in first)
    assert f"  in a first-sample card's cluster: {10 + copies}\n" in printed
    assert "  from a first-sample document: 20\n" in printed
    assert "  with no occurrence row: 0\n" in printed
    assert header["holdout"] is True and header["seed"] == 20261114
    assert header["exclusions"]["candidates"] == 40
    assert header["exclusions"]["excluded"] == 20 + copies
    assert header["drawn_from"]["snapshot"] == "2026-09-22"
    assert (header["drawn_from"]["version"], header["drawn_from"]["parser_version"]) == (
        PARSER_VERSION,
        parse_version_directory(PARSER_VERSION)[0],
    )


def test_it_writes_its_own_files_and_the_coachs_csv_with_its_sidecar_and_leaves_the_first_samples(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes]
) -> None:
    assert holdout(world) == 0

    after = files_under(output(world))
    assert {path: data for path, data in after.items() if path in first_sample} == first_sample
    assert sorted(path.name for path in set(after) - set(first_sample)) == sorted(HOLDOUT_FILES)
    labels = world[2]
    with labels.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["sample_row", "tag", "headings", "position", "note", "also"]
    assert sorted(int(row[0]) for row in rows[1:]) == list(range(1, 11))
    assert all(row[3] == row[4] == row[5] == "" for row in rows[1:])
    assert digest_path(labels).read_text(encoding="ascii").split()[0] == labels_digest(labels.read_bytes())
    assert "deficit" not in (output(world) / HOLDOUT_FILES[1]).read_text(encoding="utf-8").casefold()


def test_a_second_draw_writes_over_nothing(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    assert holdout(world) == 0
    before = {**files_under(output(world)), **files_under(world[2].parent)}

    assert holdout(world) == 2

    assert "is there already; the draw writes over no file" in capsys.readouterr().err
    assert {**files_under(output(world)), **files_under(world[2].parent)} == before


def test_the_draw_never_writes_the_first_samples_csv(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    first_csv = output(world) / f"{TOPIC}-coach-sample.csv"

    code = run(
        world, "holdout-sample", "--snapshot", SNAPSHOTS[1], "--labels-out", str(first_csv), "--dry-run"
    )

    assert code == 2
    assert "is the first sample's; the draw never writes it" in capsys.readouterr().err
    assert files_under(output(world)) == first_sample


def test_a_dry_run_draws_and_counts_and_writes_nothing(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    assert holdout(world, "--dry-run") == 0

    assert "Dry run: nothing was written." in capsys.readouterr().out
    assert files_under(output(world)) == first_sample
    assert not world[2].exists()


def test_a_first_sample_card_with_no_occurrence_row_stops_the_draw_by_count(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    _, first = rows_of(output(world) / f"{TOPIC}-coach-sample.jsonl")
    table = world[0] / PARSED_PREFIX / CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    dropped = first[0]["item_id"]
    kept = [
        line
        for line in table.read_text(encoding="utf-8").splitlines(keepends=True)
        if card_item_id(json.loads(line)["source_sha256"], json.loads(line)["first_element_index"]) != dropped
    ]
    table.write_text("".join(kept), encoding="utf-8")

    assert holdout(world) == 1

    err = capsys.readouterr().err
    assert "STOPPED: 1 of the first sample's 10 cards have no row in the occurrence table" in err
    assert dropped not in err
    assert files_under(output(world)) == first_sample and not world[2].exists()


def test_the_first_samples_commands_still_read_their_one_feature_table(
    world: tuple[Path, Path, Path], first_sample: dict[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    assert holdout(world) == 0
    capsys.readouterr()

    assert run(world, "compare") == 0

    counts = json.loads((output(world) / f"{TOPIC}-comparison.json").read_text(encoding="utf-8"))
    assert counts["through"] == SNAPSHOTS[0]
