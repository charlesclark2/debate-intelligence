"""`scripts/count_late_disclosures.py` over a synthetic hsld26 store and this checkout's topics.yaml (t51).

The planted store mimics the weeks around the de-extinction topic's start: a space colonization
tournament first disclosed on 2026-10-27 and again, late, on 2026-11-10; Florida Blue Key (`fbk`, the
topic's entry spelling) on 2026-11-03 and 2026-11-10; a November tournament on 2026-11-10. Every school,
team code, tournament, tag and heading is invented; the expected counts are written by hand from them.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_late_disclosures as script  # noqa: E402

SPACE = (PlantedCard(("1AC", "Colonization good"), tag="Space colonization solves"),)
EXTINCT = (PlantedCard(("1NC", "De-extinction bad"), tag="De-extinction is hubris"),)
WORD_ARGUMENTS = [
    "--topic-word",
    "de-extinct",
    "--other-topic-word",
    "space col",
    "--other-topic-word",
    "coloniz",
]


def path(school: str, code: str, side: str, tournament: str, round_number: int) -> str:
    return f"{school}/{code}/{school}-{code}-{side}-{tournament}-Round {round_number}.docx"


def plant(data_dir: Path) -> None:
    planted = PlantedCaselist(data_dir, "hsld26")
    planted.source("a", SPACE, disclosures=[("2026-10-27", path("Alder", "AbCd", "Aff", "Lakeside Open", 1))])
    planted.source("b", SPACE, disclosures=[("2026-10-27", path("Brook", "EfGh", "Neg", "Lakeside Open", 1))])
    planted.source("c", SPACE, disclosures=[("2026-11-10", path("Alder", "AbCd", "Neg", "Lakeside Open", 2))])
    planted.source("d", EXTINCT, disclosures=[("2026-11-03", path("Cedar", "IjKl", "Aff", "FBK", 1))])
    planted.source("e", EXTINCT, disclosures=[("2026-11-10", path("Cedar", "IjKl", "Neg", "FBK", 4))])
    planted.source(
        "f", EXTINCT, disclosures=[("2026-11-10", path("Brook", "EfGh", "Aff", "Pinecrest Open", 1))]
    )
    planted.source(
        "g", EXTINCT, disclosures=[("2026-11-10", path("Dune", "MnOp", "Neg", "Pinecrest Open", 1))]
    )


def every_file(data_dir: Path) -> dict[str, str]:
    return {
        str(one.relative_to(data_dir)): hashlib.sha256(one.read_bytes()).hexdigest()
        for one in sorted(data_dir.rglob("*"))
        if one.is_file()
    }


def test_the_count_is_printed_as_json_and_the_data_directory_is_left_as_it_was(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plant(tmp_path)
    before = every_file(tmp_path)

    code = script.main(
        ["--data-dir", str(tmp_path), "--caselist", "hsld26", "--snapshot", "2026-11-10", *WORD_ARGUMENTS]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert every_file(tmp_path) == before
    assert printed["topic"] == "ld-2026-nov-dec-de-extinction"
    assert (printed["range_from"], printed["first_seen_through"]) == ("2026-11-06", "2026-11-03")
    assert printed["tournament_entry_spellings"] == ["bluekey", "fbk"]
    assert (printed["disclosures"], printed["tournament_entry_spelling_disclosures"]) == (4, 1)
    assert printed["late"] == {
        "disclosures": 1,
        "sources": 1,
        "schools": 1,
        "spellings": 1,
        "share": 0.25,
        "by_first_seen": {"2026-10-27": 1},
    }
    assert printed["topic_word_check"]["late"]["sources"]["other topic words only"] == 1
    assert printed["topic_word_check"]["other"]["sources"]["topic words only"] == 2
    assert (printed["earlier_topic"], printed["moved_to"]) == (
        "ld-2026-sep-oct-space-colonization",
        "ld-2026-sep-oct-space-colonization",
    )
    out = json.dumps(printed).casefold()
    for tournament in ("lakeside", "pinecrest"):
        assert tournament not in out
    assert not {"late_spellings_named", "late_spellings_not_named"} & set(printed)
    assert isinstance(printed["runtime_seconds"], float)


def test_a_snapshot_the_store_lacks_is_refused_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plant(tmp_path)

    code = script.main(
        ["--data-dir", str(tmp_path), "--caselist", "hsld26", "--snapshot", "2026-11-17", *WORD_ARGUMENTS]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "holds no manifest of hsld26's snapshot of 2026-11-17" in captured.err


def test_a_missing_data_directory_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = script.main(
        [
            "--data-dir",
            str(tmp_path / "absent"),
            "--caselist",
            "hsld26",
            "--snapshot",
            "2026-11-10",
            *WORD_ARGUMENTS,
        ]
    )

    assert code == 2
    assert "no data directory" in capsys.readouterr().err
    assert not (tmp_path / "absent").exists()


def test_without_word_options_the_check_reads_topics_yaml_check_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plant(tmp_path)

    code = script.main(["--data-dir", str(tmp_path), "--caselist", "hsld26", "--snapshot", "2026-11-10"])

    assert code == 0
    check = json.loads(capsys.readouterr().out)["topic_word_check"]
    assert check["late"]["sources"]["other topic words only"] == 1
    assert check["other"]["sources"]["topic words only"] == 2


def test_one_word_option_without_the_other_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as refused:
        script.main(
            [
                "--data-dir",
                str(tmp_path),
                "--caselist",
                "hsld26",
                "--snapshot",
                "2026-11-10",
                "--topic-word",
                "x",
            ]
        )

    assert refused.value.code == 2
    assert "together, or neither" in capsys.readouterr().err
