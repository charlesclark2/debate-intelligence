"""`scripts/compare_local_classifier.py` end to end on a planted store (`v1-e32-t21` ac1).

Ten invented sources, each disclosed by one of six invented teams of three invented schools. Each
holds three cards under `Spending DA` and three under `States CP`, which aliases place, and two cards
no heading places: eighty cards, sixty labelled and twenty unplaced, worked out by hand (working
agreement 6). The tags carry the teams' schools, codes and tournament, which never reach a file.

The script writes only under `<data dir>/landscape/local-classifier/<caselist>/`, refuses to start
with a `DEBATE_*` variable set or a `caselist pull` running, and refuses a feature table a removal has
reached since it was built.

Every school, team code, tournament, heading and tag here is invented.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.parsed_store import PARSED_PREFIX, source_object_key
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.application.review_queue_order import ReviewQueueOrdering, read_model_file
from debate_core.integrations.landscape.classification_store import LocalQueueOrderModelStore
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.landscape_store import PARSER_VERSION, PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import compare_local_classifier as script  # noqa: E402

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
TEAMS = (
    ("Larkspur Point", "LaPo"),
    ("Larkspur Point", "LaPt"),
    ("Juniper Bay", "JuBa"),
    ("Juniper Bay", "JuBy"),
    ("Hollis Mill", "HoMi"),
    ("Hollis Mill", "HoMl"),
)
TOURNAMENT = "Sample Classic"
NAMES = ("larkspur", "juniper", "hollis", "lapo", "lapt", "juba", "juby", "homi", "homl", "classic")


def _cards(school: str, code: str) -> list[PlantedCard]:
    spending = f"{school} {code} evidence deficit spending crowds out investment"
    states = f"Fifty states solve uniformly {TOURNAMENT}"
    return [
        *(PlantedCard(("1NC", "Spending DA"), tag=spending) for _ in range(3)),
        *(PlantedCard(("1NC", "States CP"), tag=states) for _ in range(3)),
        PlantedCard(("1NC", "Solvency"), tag=f"Deficit spending crowds out {code}"),
        PlantedCard(("Off",), tag="Fifty states solve now"),
    ]


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path, list[str]]:
    """`(data_dir, config_dir, digests)`: ten planted sources and a config with the sample taxonomy."""
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    digests: list[str] = []
    for number in range(10):
        school, code = TEAMS[number % len(TEAMS)]
        path = f"{school}/{code}/{school}-{code}-Neg-{TOURNAMENT}-Round {number + 1}.docx"
        digests.append(
            store.source(f"source-{number}", _cards(school, code), disclosures=[("2026-09-15", path)])
        )
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return data_dir, config_dir, digests


def run(
    world: tuple[Path, Path, list[str]],
    command: str,
    *extra: str,
    environ: Mapping[str, str] | None = None,
    processes: Callable[[], Sequence[tuple[str, str]]] = lambda: [],
) -> int:
    """One command against the planted store, with no `DEBATE_*` variable and no pull unless given."""
    data_dir, config_dir, _ = world
    return script.main(
        [
            "--config-dir",
            str(config_dir),
            command,
            "--caselist",
            CASELIST,
            "--data-dir",
            str(data_dir),
            *extra,
        ],
        environ={} if environ is None else environ,
        processes=processes,
    )


def printed(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if not line.startswith("Runtime")]


def output(world: tuple[Path, Path, list[str]]) -> Path:
    return world[0] / "landscape" / "local-classifier" / CASELIST


def files_under(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def suppress(data_dir: Path, sha256: str, path: str | None = None) -> None:
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        disclosure=disclosure_digest(CASELIST, path) if path is not None else None,
        recorded_at=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
        reason=ReasonCode.POLICY,
        request_id="RM-2026-99",
    )
    asyncio.run(RecordedSuppressionList(local_suppression_list_file(data_dir)).append([entry]))


def test_features_prints_the_hand_counted_placements(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    table = output(world) / f"{TOPIC}-features.jsonl"
    assert run(world, "features") == 0
    assert printed(capsys) == [
        f"Read {CASELIST} {PARSER_VERSION} through 2026-09-15: 10 source entries, 10 parsed, 10 on {TOPIC}.",
        "Taxonomy 1.0.0; review threshold 0.6.",
        "Cards 80; labelled 60 (75.0%).",
        "  cards ALIAS: 60 (75.0%)",
        "  cards UNPLACED: 20 (25.0%)",
        f"Wrote the feature table to {table}.",
    ]
    text = table.read_text(encoding="utf-8").casefold()
    assert len(text.splitlines()) == 1 + 80
    assert not any(name in text for name in NAMES)
    assert "deficit spending crowds out investment" in text


def test_the_five_commands_write_only_under_the_data_directory(
    world: tuple[Path, Path, list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    data_dir = world[0]
    labels = tmp_path / "labelled.csv"
    before = {path: data for path, data in files_under(tmp_path).items() if data_dir not in path.parents}
    assert run(world, "features") == 0
    assert run(world, "compare") == 0
    assert run(world, "sample") == 0
    coach_file = output(world) / f"{TOPIC}-coach-sample.csv"
    with coach_file.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with labels.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**row, "position": "none"} for row in rows)
    before[labels] = labels.read_bytes()
    assert run(world, "score-sample", "--labels", str(labels)) == 0
    assert run(world, "train-queue-order") == 0
    after = {path: data for path, data in files_under(tmp_path).items() if data_dir not in path.parents}
    assert after == before
    written = {path.relative_to(output(world)).as_posix() for path in files_under(output(world))}
    assert written == {
        f"{TOPIC}-features.jsonl",
        f"{TOPIC}-comparison.json",
        f"{TOPIC}-coach-sample.csv",
        f"{TOPIC}-coach-sample.jsonl",
        f"{TOPIC}-coach-sample-score.json",
        f"{TOPIC}-review-order-model.json",
    }
    out = capsys.readouterr().out.casefold()
    assert not any(name in out for name in NAMES)


def test_compare_and_sample_on_the_planted_store(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(world, "features") == 0
    capsys.readouterr()
    assert run(world, "compare") == 0
    lines = printed(capsys)
    assert lines[0] == "Model specified: the tag and every heading; seed 21."
    assert lines[1].startswith("  Split: 10 documents, 1 held out; trained on 54 labelled cards, 2 positions")
    assert lines[2].startswith("  Held out: 6 labelled cards, 6 predicted, 6 correct")
    assert any(
        line == "Model proxy: the tag and the headings that place nothing on their own; seed 21."
        for line in lines
    )
    counts = json.loads((output(world) / f"{TOPIC}-comparison.json").read_text(encoding="utf-8"))
    assert [model["model"] for model in counts["models"]] == ["specified", "proxy"]
    assert [model["would_place"][0]["cards"] for model in counts["models"]] == [20, 20]
    assert run(world, "sample") == 0
    with (output(world) / f"{TOPIC}-coach-sample.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["sample_row", "tag", "headings", "position", "note"]
    assert sorted(int(row[0]) for row in rows[1:]) == list(range(1, 11)), "one unplaced card per document"
    assert all(row[3] == row[4] == "" for row in rows[1:])
    kept = (output(world) / f"{TOPIC}-coach-sample.jsonl").read_text(encoding="utf-8")
    assert len(kept.splitlines()) == 11
    assert "deficit" not in kept and "states solve" not in kept


def test_train_queue_order_writes_the_proxy_with_t21s_threshold_and_a_run_orders_by_it(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, config_dir, digests = world
    assert run(world, "features") == 0
    assert run(world, "compare") == 0
    assert run(world, "sample") == 0
    capsys.readouterr()
    assert run(world, "train-queue-order") == 0
    lines = printed(capsys)
    counts = json.loads((output(world) / f"{TOPIC}-comparison.json").read_text(encoding="utf-8"))
    proxy = next(model for model in counts["models"] if model["model"] == "proxy")
    recorded = proxy["held_out"]["confidence_at_target"]
    text = (output(world) / f"{TOPIC}-review-order-model.json").read_text(encoding="utf-8")
    model_file = read_model_file(text)
    assert model_file.model.suggest_from == recorded
    assert model_file.model.without_placing_headings
    assert model_file.trained_cards == proxy["trained_cards"]
    assert model_file.sources == tuple(sorted(digests))
    assert (model_file.caselist, model_file.topic_id, model_file.taxonomy_version) == (
        CASELIST,
        TOPIC,
        "1.0.0",
    )
    shown = "none reaches it" if recorded is None else f"{recorded:.3f}"
    assert lines[0].startswith(
        f"Trained the proxy model on {proxy['trained_cards']} labelled cards of 9 documents"
    )
    assert lines[1] == f"Its confidence at 90% held-out precision, from which it suggests: {shown}."
    sampled = "none" if recorded is None else f"{recorded:.3f}"
    assert lines[2] == f"The coach sample recorded {sampled} for the proxy model: the same."
    assert lines[3].startswith("Wrote the review queue's order model to ")
    assert not any(name in text.casefold() for name in NAMES)
    taxonomies = YamlTaxonomyRepository.load(config_dir)
    loaded = asyncio.run(
        ReviewQueueOrdering(
            models=LocalQueueOrderModelStore(data_dir),
            parsed_store=LocalParsedStore(data_dir),
            suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        ).load(CASELIST, TOPIC, taxonomies.taxonomy(TOPIC))
    )
    assert loaded.model == model_file.model
    assert loaded.note.startswith("Review queue order: by the local proxy model's confidence, highest first")


def test_score_sample_scores_the_coachs_labels_and_leaves_out_a_removed_source(
    world: tuple[Path, Path, list[str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, _, digests = world
    assert run(world, "features") == 0
    assert run(world, "sample") == 0
    with (output(world) / f"{TOPIC}-coach-sample.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    labels = tmp_path / "labelled.csv"
    with labels.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**row, "position": "none"} for row in rows)
    capsys.readouterr()
    assert run(world, "score-sample", "--labels", str(labels)) == 0
    lines = printed(capsys)
    assert lines[0] == "Labels: 10 of 10 sampled cards (blank and `unsure` rows are not scored)."
    assert (
        "Model specified: 0 of 10 labelled cards right (0.0%); the coach said 10 belong to no position."
        in lines
    )
    suppress(data_dir, digests[3])
    assert run(world, "score-sample", "--labels", str(labels)) == 0
    lines = printed(capsys)
    assert lines[0].startswith(
        "A removal has reached 1 sampled cards' sources since the sample was drawn; row"
    )
    assert lines[1] == "Labels: 9 of 10 sampled cards (blank and `unsure` rows are not scored)."


def test_a_table_a_removal_has_reached_is_refused(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, _, digests = world
    assert run(world, "features") == 0
    (data_dir / PARSED_PREFIX / source_object_key(CASELIST, PARSER_VERSION, digests[0])).unlink()
    assert run(world, "compare") == 2
    assert "a removal has reached 1 of the table's 10 sources" in capsys.readouterr().err
    assert run(world, "features") == 0
    assert run(world, "compare") == 0
    school, code = TEAMS[1]
    suppress(data_dir, digests[1], f"{school}/{code}/{school}-{code}-Neg-{TOURNAMENT}-Round 2.docx")
    assert run(world, "sample") == 2
    assert "a removal has reached 1 of the table's 9 sources" in capsys.readouterr().err
    assert run(world, "train-queue-order") == 2
    assert "a removal has reached 1 of the table's 9 sources" in capsys.readouterr().err


def test_a_table_placed_under_another_taxonomy_version_is_refused(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir, _ = world
    assert run(world, "features") == 0
    taxonomy = config_dir / "taxonomies" / f"{TOPIC}.yaml"
    taxonomy.write_text(taxonomy.read_text(encoding="utf-8").replace("1.0.0", "1.1.0"), encoding="utf-8")
    (config_dir / "topics.yaml").write_text(TOPICS.replace("1.0.0", "1.1.0"), encoding="utf-8")
    assert run(world, "compare") == 2
    assert "placed under taxonomy 1.0.0" in capsys.readouterr().err


def test_a_debate_variable_or_a_running_pull_stops_every_command(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    pull = [("uv", "uv run debate-research caselist pull --caselist hspolicy99")]
    for command in ("features", "compare", "sample", "train-queue-order"):
        assert run(world, command, environ={"DEBATE_STORAGE__DATA_DIR": "/elsewhere"}) == 2
        assert "DEBATE_STORAGE__DATA_DIR is set" in capsys.readouterr().err
        assert run(world, command, processes=lambda: pull) == 2
        assert "a caselist pull is running" in capsys.readouterr().err
    assert not output(world).exists()
    shell = [("zsh", "zsh -c pgrep -f 'caselist pull'")]
    assert run(world, "features", processes=lambda: shell) == 0


def test_a_data_directory_or_labels_inside_the_repository_are_refused(
    world: tuple[Path, Path, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir, _ = world
    inside = Path(script.REPO_ROOT) / "tmp-local-classifier"
    code = script.main(
        ["--config-dir", str(config_dir), "features", "--caselist", CASELIST, "--data-dir", str(inside)],
        environ={},
        processes=lambda: [],
    )
    assert code == 2
    assert "must be outside the repository" in capsys.readouterr().err
    assert not inside.exists()
    assert run(world, "features") == 0
    assert run(world, "sample") == 0
    assert run(world, "score-sample", "--labels", str(Path(script.REPO_ROOT) / "labels.csv")) == 2
    assert "--labels must be outside the repository" in capsys.readouterr().err


def test_running_processes_reads_command_names_and_arguments() -> None:
    found = script.running_processes()
    assert found and all(
        isinstance(command, str) and isinstance(arguments, str) for command, arguments in found
    )
