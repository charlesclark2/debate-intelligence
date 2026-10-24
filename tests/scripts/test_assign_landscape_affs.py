"""`scripts/assign_landscape_affs.py` end to end on a planted store (`v1-e32-t09` ac2, ac4).

Seven invented sources in a synthetic caselist: six affirmative files by five invented teams and one
negative file. Three affirmative files hold a plan text naming the sample plan (one also names a
school of the caselist, which must never reach the sheet), two a plan text naming no aff, and one no
plan text at all. The counts each command prints and the sheet's rows were worked out by hand from
those files (working agreement 6).

Every school, team code, tournament and plan text here is invented.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import assign_landscape_affs as script  # noqa: E402

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
  - {{id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}}
"""

PAYROLL = "The United States federal government should establish a sample plan financed by a payroll levy."
PAYROLL_WITH_A_SCHOOL = (
    "The United States federal government should establish a sample plan financed by a School Three "
    "payroll levy."
)
VOUCHER = "The United States federal government should establish a national program using a voucher route."


def path(school: int, side: str, round_number: int) -> str:
    name = ("", "One", "Two", "Three", "Four", "Five", "Six")[school]
    file = f"School {name}-Code{name}-{side}-Sample Invitational-Round {round_number}.docx"
    return f"School {name}/Code{name}/{file}"


def affirmative(plan: str | None) -> bytes:
    body = [paragraph_xml(run_xml("Advantage One"), style="Heading3")]
    if plan is not None:
        body = [
            paragraph_xml(run_xml("Plan"), style="Heading3"),
            paragraph_xml(run_xml(plan), style="Analytic"),
        ]
    return build_docx("".join(body))


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    planted = [
        ("payroll-two", PAYROLL, 2),
        ("payroll-three", PAYROLL_WITH_A_SCHOOL, 3),
        ("payroll-six", PAYROLL + " ", 6),
        ("voucher-four", VOUCHER, 4),
        ("voucher-five", VOUCHER + " ", 5),
        ("no-plan-two", None, 2),
    ]
    for number, (name, plan, school) in enumerate(planted, start=1):
        store.source(
            name,
            [PlantedCard(("1AC", "Advantage One"))],
            disclosures=[("2026-09-15", path(school, "Aff", number))],
            content=affirmative(plan),
        )
    store.source(
        "neg", [PlantedCard(("1NC", "Spending DA"))], disclosures=[("2026-09-15", path(1, "Neg", 1))]
    )
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return data_dir, config_dir


def run(world: tuple[Path, Path], command: str, *extra: str) -> int:
    data_dir, config_dir = world
    return script.main(
        [
            "--config-dir",
            str(config_dir),
            command,
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


VERDICTS = [
    "  NAMES: 3 documents, 3 teams",
    "  CONFLICTING: 0 documents, 0 teams",
    "  UNNAMED: 2 documents, 2 teams",
    "  NONE: 1 documents, 1 teams",
    "  UNREAD: 0 documents, 0 teams",
    "  names sample-plan-aff: 3 documents, 3 teams",
]


def test_plan_texts_are_read_counted_and_cached(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(world, "plan-texts") == 0
    assert printed(capsys) == [
        f"Read {CASELIST} 2026.10.20-docx-6 through {SNAPSHOT}: 7 sources on {TOPIC}, 6 affirmative.",
        "Plan texts: 6 sources, 0 cached, 6 parsed, 0 refused by the parser, 0 unread; cache written.",
        *VERDICTS,
    ]
    assert run(world, "plan-texts") == 0
    assert printed(capsys)[1:] == [
        "Plan texts: 6 sources, 6 cached, 0 parsed, 0 refused by the parser, 0 unread; cache unchanged.",
        *VERDICTS,
    ]


def test_the_sheet_clusters_the_plan_texts_and_names_no_one(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "sheet"
    assert run(world, "sheet", "--out", str(out)) == 0
    lines = printed(capsys)
    assert lines[-2:] == [
        "Sheet: 5 documents with a plan text by 5 teams; 2 clusters shown, 0 withheld (0 documents); "
        "1 plan text naming a school not shown; 0 read differently and 0 unread, left off.",
        f"Wrote {TOPIC}-plan-texts.md and plan-text-answers.csv to {out.resolve()}.",
    ]
    sheet = (out / f"{TOPIC}-plan-texts.md").read_text(encoding="utf-8")
    assert "| C01 | 3 | 3 | sample-plan-aff | financed, levy, payroll, plan, sample | |" in sheet
    assert "| C02 | 2 | 2 | none | national, program, route, using, voucher | |" in sheet
    assert "establish, federal, government, should, states, united" in sheet
    assert f"> {PAYROLL}" in sheet.splitlines()
    assert "Held exactly by 2 of its 3 documents." in sheet
    assert f"> {VOUCHER}" in sheet.splitlines()
    assert "Held exactly by 2 of its 2 documents." in sheet
    with (out / "plan-text-answers.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [(row["cluster"], row["teams"], row["mechanism_name"], row["tag_keywords"]) for row in rows] == [
        ("C01", "3", "", ""),
        ("C02", "2", "", ""),
    ]
    written = (sheet + (out / "plan-text-answers.csv").read_text(encoding="utf-8")).casefold()
    numbers = ("one", "two", "three", "four", "five", "six")
    planted = (
        [f"school {one}" for one in numbers] + [f"code{one}" for one in numbers] + ["sample invitational"]
    )
    assert [name for name in planted if name in written] == []


def test_the_sheet_never_overwrites_answers_the_coach_has_begun(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "sheet"
    out.mkdir()
    begun = (
        "cluster,teams,documents,aff_named,words_in_every_plan_text,mechanism_name,tag_keywords\r\n"
        "C01,3,3,sample-plan-aff,financed levy payroll,Payroll levy,payroll levy\r\n"
    )
    (out / "plan-text-answers.csv").write_text(begun, encoding="utf-8", newline="")
    assert run(world, "sheet", "--out", str(out)) == 2
    assert "already holds answers" in capsys.readouterr().err
    with (out / "plan-text-answers.csv").open(encoding="utf-8", newline="") as stream:
        assert stream.read() == begun
    assert not (out / f"{TOPIC}-plan-texts.md").exists()


def test_the_sheet_replaces_an_unanswered_sheet(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "sheet"
    assert run(world, "sheet", "--out", str(out)) == 0
    assert run(world, "sheet", "--out", str(out)) == 0
    capsys.readouterr()


def test_the_sheet_is_refused_inside_the_repository(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(world, "sheet", "--out", str(script.REPO_ROOT / "tmp-plan-text-sheet")) == 2
    assert "outside the repository" in capsys.readouterr().err
    assert not (script.REPO_ROOT / "tmp-plan-text-sheet").exists()


def test_an_empty_store_fails_rather_than_counting_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    PlantedCaselist(tmp_path / "data", CASELIST).source(
        "neg", [PlantedCard(("1NC",))], disclosures=[("2026-09-15", path(1, "Neg", 1))]
    )
    assert run((tmp_path / "data", config_dir), "plan-texts") == 1
    assert "0 affirmative sources" in capsys.readouterr().err


def test_assign_assigns_each_affirmative_round_and_prints_counts(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(world, "assign") == 0
    assert printed(capsys)[-2:] == [
        "Aff rounds: 6 by 5 teams; assigned 4 (PLAN_TEXT 3, TEAM_CARRY 1), left to placed cards 0, "
        "unidentified 2 (0 with conflicting plan texts).",
        "Carry refused into 0 rounds; teams identified 3 of 5; 0 teams whose rounds disagree.",
    ]
