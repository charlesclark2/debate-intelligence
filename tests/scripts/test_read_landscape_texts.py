"""`scripts/read_landscape_texts.py` end to end on a planted store (`v1-e32-t11` ac2).

Four invented sources in a synthetic caselist: two negative files by two invented teams, one holding a
States CP with its text, a theory block the actor guard refuses, a Capitalism K with its alternative, an
overview and a role of the ballot, and an `OFF` block whose alternative nothing places; one negative file
with only that `OFF` block; one affirmative file with an overview under an advantage; and one negative file
whose bytes are not on this machine. A fifth, negative, holds `v1-e32-t16`'s planks: an advantage CP whose
CP text ends in a colon and lists three planks, one after a label that is only an advantage's alias and one
naming a school of the caselist, and a
labelled States CP text with no actor whose one list plank the guard refuses. The counts the script prints
were worked out by hand from those files (working agreement 6).

Every school, team code, tournament and text here is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import read_landscape_texts as script  # noqa: E402

CASELIST = "hspolicy99"
TOPIC = "policy-sample-topic"
SNAPSHOT = "2026-09-29"

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
  - {{id: sample-plan-aff, label: Sample plan, kind: aff, side: aff, aliases: [sample plan]}}
  - {{id: costs-advantage, label: Costs advantage, kind: advantage, side: aff,
      aliases: [costs advantage, costs]}}
  - {{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}}
  - {{id: advantage-cp, label: Advantage CP, kind: cp, side: neg, aliases: [advantage cp]}}
  - {{id: cap-k, label: Capitalism K, kind: k, side: neg, aliases: [cap k]}}
"""

ACTORS = f"""\
schema_version: 1
topic_id: {TOPIC}
cp_text_actors: [fifty states, congress]
"""


def path(school: str, side: str, round_number: int) -> str:
    file = f"School {school}-Code{school}-{side}-Sample Invitational-Round {round_number}.docx"
    return f"School {school}/Code{school}/{file}"


def _card(tag: str) -> str:
    return (
        paragraph_xml(run_xml(tag), style="Heading4")
        + paragraph_xml(run_xml("Sample 26", character_style="Style13ptBold") + run_xml(" invented cite"))
        + paragraph_xml(run_xml("An invented body of evidence that goes on.", underline="single"))
    )


def negative() -> bytes:
    return build_docx(
        "".join(
            [
                paragraph_xml(run_xml("States CP"), style="Heading2"),
                paragraph_xml(
                    run_xml("The fifty states should establish a sample program."), style="Analytic"
                ),
                paragraph_xml(run_xml("Theory"), style="Heading3"),
                paragraph_xml(
                    run_xml("Our counter interpretation is that we should get one."), style="Analytic"
                ),
                paragraph_xml(run_xml("Cap K"), style="Heading2"),
                _card("The alternative is to reject sample markets."),
                paragraph_xml(run_xml("O/V"), style="Heading3"),
                paragraph_xml(run_xml("ROB"), style="Heading3"),
                paragraph_xml(run_xml("Vote for the best sample method."), style="Analytic"),
                paragraph_xml(run_xml("OFF"), style="Heading2"),
                _card("The alt is sample refusal."),
            ]
        )
    )


def with_planks() -> bytes:
    return build_docx(
        "".join(
            [
                paragraph_xml(run_xml("Advantage CP"), style="Heading2"),
                paragraph_xml(run_xml("Congress should:"), style="Analytic"),
                paragraph_xml(run_xml("Costs"), style="Analytic"),
                paragraph_xml(run_xml("Expand sample clinics."), style="Analytic"),
                paragraph_xml(run_xml("Cut sample costs and fees."), style="Analytic"),
                paragraph_xml(run_xml("School One should fund sample clinics."), style="Analytic"),
                _card("Sample clinics work"),
                paragraph_xml(run_xml("States CP"), style="Heading2"),
                paragraph_xml(run_xml("Text: The sample panel should:"), style="Analytic"),
                paragraph_xml(run_xml("Ban sample surprise bills."), style="Analytic"),
            ]
        )
    )


def off_only() -> bytes:
    return build_docx(paragraph_xml(run_xml("OFF"), style="Heading2") + _card("The alt is sample refusal."))


def affirmative() -> bytes:
    return build_docx(
        paragraph_xml(run_xml("Costs Advantage"), style="Heading2")
        + paragraph_xml(run_xml("Overview"), style="Heading3")
        + paragraph_xml(run_xml("Costs rise without the sample plan."), style="Analytic")
    )


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    store.source(
        "neg-one",
        [PlantedCard(("States CP",))],
        disclosures=[("2026-09-15", path("One", "Neg", 1))],
        content=negative(),
    )
    store.source(
        "neg-two",
        [PlantedCard(("OFF",))],
        disclosures=[("2026-09-15", path("Two", "Neg", 2))],
        content=off_only(),
    )
    store.source(
        "aff-three",
        [PlantedCard(("Costs Advantage",))],
        disclosures=[("2026-09-15", path("Three", "Aff", 3))],
        content=affirmative(),
    )
    store.source(
        "neg-five",
        [PlantedCard(("Advantage CP",))],
        disclosures=[("2026-09-15", path("Five", "Neg", 5))],
        content=with_planks(),
    )
    store.source("neg-gone", [PlantedCard(("Cap K",))], disclosures=[("2026-09-15", path("Four", "Neg", 4))])
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    (config_dir / "analytic_texts").mkdir()
    (config_dir / "analytic_texts" / f"{TOPIC}.yaml").write_text(ACTORS, encoding="utf-8")
    return data_dir, config_dir


def run(world: tuple[Path, Path], *extra: str) -> int:
    data_dir, config_dir = world
    return script.main(
        [
            "--config-dir",
            str(config_dir),
            "--caselist",
            CASELIST,
            "--data-dir",
            str(data_dir),
            "--snapshot",
            SNAPSHOT,
            "--workers",
            "0",
            *extra,
        ]
    )


def printed(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if not line.startswith("Runtime")]


KINDS = [
    "  CP_TEXT: 3 found, 3 placed",
    "  K_ALTERNATIVE: 3 found, 1 placed",
    "  ROLE_OF_THE_BALLOT: 1 found, 1 placed",
    "  OVERVIEW: 2 found, 2 placed",
    "  CP_PLANK: 3 found, 3 placed",
    "CP texts by place in negative files: 2 kept by the actor guard, 1 refused.",
    "CP planks: 1 alias-only labels, 1 list planks refused with their CP text, 0 cards under a plank saying "
    "solves with other words.",
]


def test_the_texts_are_read_counted_and_cached(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(world) == 0
    assert printed(capsys) == [
        f"Read {CASELIST} 2026.10.20-docx-6 through {SNAPSHOT}: 5 sources on {TOPIC}, "
        "4 negative, 1 affirmative.",
        "Analytic texts: 5 sources, 0 cached, 4 parsed, 0 refused by the parser, 1 unread; cache written.",
        *KINDS,
    ]
    data_dir, _ = world
    cache = data_dir / "landscape" / "analytic_texts" / f"{CASELIST}.jsonl"
    assert len(cache.read_text(encoding="utf-8").splitlines()) == 4
    assert run(world) == 0
    assert printed(capsys)[1:] == [
        "Analytic texts: 5 sources, 4 cached, 0 parsed, 0 refused by the parser, 1 unread; cache unchanged.",
        *KINDS,
    ]


def test_quote_reads_the_texts_again_and_prints_counts_only(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(world, "--quote") == 0
    lines = printed(capsys)
    # Two CP texts and three planks more in neg-five. The three are distinct; the one naming School One is
    # withheld, and the other two both solve Costs (by the label, and by their own words): 1 group.
    # Only "Cut sample costs and fees." names an alias itself.
    assert lines[-4:] == [
        "Quoted: 2 sources read again for 8 texts; 8 read as they were read, 0 not, 0 unread.",
        "Planks under a CP in negative files: 3 under 1 CPs, in 1 groups by what they solve, 1 withheld for "
        "naming a school.",
        "  advantage-cp: 3 planks, 1 groups, 1 withheld",
        "Planks naming an advantage alias in their own words: costs 1.",
    ]
    for words in ("sample program", "sample markets", "sample method", "counter interpretation", "clinics"):
        assert not any(words in line for line in lines)


def test_the_data_directory_must_be_outside_the_repository(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, config_dir = world
    inside = Path(__file__).resolve().parents[2] / "landscape-texts-data"
    assert (
        script.main(["--config-dir", str(config_dir), "--caselist", CASELIST, "--data-dir", str(inside)]) == 2
    )
    assert "outside the repository" in capsys.readouterr().err
    assert not inside.exists()


def test_an_empty_store_fails_rather_than_counting_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    PlantedCaselist(tmp_path / "data", CASELIST).source(
        "elsewhere", [PlantedCard(("1NC",))], disclosures=[("2026-08-15", path("One", "Neg", 1))]
    )
    assert run((tmp_path / "data", config_dir)) == 1
    assert "0 sources" in capsys.readouterr().err
