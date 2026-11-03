"""`scripts/seed_landscape_taxonomy.py` end to end on a planted store (`v1-e32-t01-position-taxonomy` ac4).

Six invented sources in a synthetic caselist's parsed store, disclosed by four invented teams, and a
topic map whose one topic covers September to December. The candidates CSV and the counts the run
prints are written out by hand below from those sources (working agreement 6), not from a run.

Every school, team code, tournament and heading here is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import seed_landscape_taxonomy as script  # noqa: E402

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
  - id: spending-da
    label: Spending DA
    kind: da
    side: neg
    aliases: [spending da, spending disad]
"""


def path(number: str, side: str, round_number: int) -> str:
    school, code = f"School {number}", f"Code{number}"
    return f"{school}/{code}/{school}-{code}-{side}-Sample Invitational-Round {round_number}.docx"


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    """`(data_dir, config_dir)`: the planted store and a topic map with the sample topic's taxonomy."""
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    store.source(
        "one",
        [
            PlantedCard(("1NC", "Off", "Spending DA Shell")),
            PlantedCard(("School One CodeOne Neg", "Courts CP")),
        ],
        disclosures=[("2026-09-08", path("One", "Neg", 1))],
    )
    store.source(
        "two",
        [PlantedCard(("1NC", "Spending Disad")), PlantedCard(("2NC", "Courts CP", "Link"))],
        disclosures=[("2026-09-15", path("Two", "Neg", 2))],
    )
    store.source(
        "three",
        [PlantedCard(("2AC", "AT: Spending DA")), PlantedCard(("Single Payer Aff",))],
        disclosures=[("2026-09-15", path("Three", "Aff", 2))],
    )
    store.source(
        "four-before", [PlantedCard(("Spending DA",))], disclosures=[("2026-08-25", path("One", "Neg", 3))]
    )
    store.source(
        "five",
        [PlantedCard(("1NC", "Spending DA", "Uniqueness"))],
        disclosures=[("2026-10-06", path("Four", "Neg", 4))],
    )
    store.source(
        "six",
        [PlantedCard(("2AC", "A2 Spending DA")), PlantedCard(("Single Payer Aff",))],
        disclosures=[("2026-10-13", path("Two", "Aff", 5))],
    )
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return data_dir, config_dir


# By hand. On the topic: one, two, three, five, six; four-before is disclosed only in August.
#   spending da (read): one (block), five (hat): 2 documents, teams One and Four, both neg; the tie
#     between block and hat goes to the outer level, hat.
#   spending da (answer): three, six: teams Three and Two, both aff; paths too short for a level.
#   courts cp: one (shortened path), two (hat): teams One and Two, neg; hat.
#   single payer aff: three, six: teams Three and Two, aff; a one-heading path, unknown.
#   Left out, one team each: spending disad (Two), link (Two), uniqueness (Four).
#   The spending-da cluster's teams: One, Four, Two (spending disad, the answer), Three: 4.
#   School One CodeOne Neg is team One's own names and a side: no heading.
EXPECTED_CSV = (
    "suggested_position_id,suggested_kind,cluster_teams,normalized_heading,answer,level,"
    "documents,teams,aff_teams,neg_teams\r\n"
    "spending-da,da,4,spending da,false,hat,2,2,0,2\r\n"
    "spending-da,da,4,spending da,true,unknown,2,2,2,0\r\n"
    "courts-cp,cp,2,courts cp,false,hat,2,2,0,2\r\n"
    "single-payer-aff,aff,2,single payer aff,false,unknown,2,2,2,0\r\n"
)
EXPECTED_SUMMARY = [
    f"Read {CASELIST} 2026.10.20-docx-6: 6 source entries, 6 parsed.",
    f"On {TOPIC}: 5 sources, 9 cards "
    "(1 parsed sources had no live disclosure in its ranges; 0 had no readable team).",
    "Headings: 11 counted, 7 distinct; 3 used by fewer than 2 teams left out.",
]


def run(config_dir: Path, *arguments: str) -> int:
    return script.main(["--config-dir", str(config_dir), *arguments])


def test_candidates_writes_the_csv_and_says_what_it_read(
    world: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, config_dir = world
    out = tmp_path / "seed" / "candidates.csv"
    assert (
        run(config_dir, "candidates", "--topic", TOPIC, "--data-dir", str(data_dir), "--out", str(out)) == 0
    )
    assert out.read_bytes().decode("utf-8") == EXPECTED_CSV
    printed = capsys.readouterr().out.splitlines()
    assert printed[:3] == EXPECTED_SUMMARY
    assert printed[-1] == f"{CASELIST} sources read: 5; candidate rows: 4"
    text = out.read_text(encoding="utf-8") + "\n".join(printed)
    for withheld in ("School", "Code", "Sample Invitational", ".docx"):
        assert withheld not in text


def test_no_source_on_the_topic_fails_loudly_and_writes_nothing(
    world: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, config_dir = world
    (config_dir / "topics.yaml").write_text(
        TOPICS.replace("2026-09-01, to: 2026-12-31", "2027-01-01, to: 2027-01-31")
    )
    out = tmp_path / "seed" / "candidates.csv"
    assert (
        run(config_dir, "candidates", "--topic", TOPIC, "--data-dir", str(data_dir), "--out", str(out)) == 1
    )
    assert "FAILED: 0 sources read" in capsys.readouterr().err
    assert not out.exists()


def test_an_empty_store_fails_loudly(
    tmp_path: Path, world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir = world
    out = tmp_path / "seed" / "candidates.csv"
    empty = tmp_path / "empty"
    assert run(config_dir, "candidates", "--topic", TOPIC, "--data-dir", str(empty), "--out", str(out)) == 2
    assert "no version" in capsys.readouterr().err
    assert not out.exists()


def test_output_inside_the_repository_is_refused(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, config_dir = world
    inside = script.REPO_ROOT / "candidates-that-must-not-exist.csv"
    assert (
        run(config_dir, "candidates", "--topic", TOPIC, "--data-dir", str(data_dir), "--out", str(inside))
        == 2
    )
    assert "outside the repository" in capsys.readouterr().err
    assert not inside.exists()


def test_an_unknown_topic_is_refused(
    world: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, config_dir = world
    out = tmp_path / "candidates.csv"
    assert (
        run(
            config_dir,
            "candidates",
            "--topic",
            "no-such-topic",
            "--data-dir",
            str(data_dir),
            "--out",
            str(out),
        )
        == 2
    )
    assert "no-such-topic" in capsys.readouterr().err


def test_review_sets_the_taxonomy_beside_the_candidates(world: tuple[Path, Path], tmp_path: Path) -> None:
    _, config_dir = world
    candidates = tmp_path / "candidates.csv"
    candidates.write_text(EXPECTED_CSV, encoding="utf-8")
    sheet = tmp_path / "review.md"
    assert (
        run(config_dir, "review", "--topic", TOPIC, "--candidates", str(candidates), "--out", str(sheet)) == 0
    )
    text = sheet.read_text(encoding="utf-8")
    assert "### Spending DA" in text
    assert "- `spending disad`: not in the candidates file" in text
    assert "| `courts cp` | 2 | 2 | hat | courts-cp |" in text
    assert "| `single payer aff` | 2 | 2 | unknown | single-payer-aff |" in text
