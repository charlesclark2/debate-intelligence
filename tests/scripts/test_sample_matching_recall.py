"""`scripts/sample_matching_recall.py`, on the invented store of `test_count_matching_recall.py`.

Both counts run on the store first and save their positions; the sample draws from them. In that
store, by hand: one body holding neither end of another; two pairs of trims with the same tag and
cite, Brannock's end to end and Kessler's with 14 words between; and three holders under 300 words
of two bodies sharing no text (Brannock's card, Kessler's and its one-word copy). Six items.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from tests.scripts.test_compare_card_clusters import CASELIST
from tests.scripts.test_count_matching_recall import TELLTALE, write_recall_store

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_card_boundaries  # noqa: E402
import count_matching_recall  # noqa: E402
import sample_matching_recall as script  # noqa: E402

UNDERLINE, REVERSE, BOLD = "\x1b[4m", "\x1b[7m", "\x1b[1m"


@pytest.fixture
def counted(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The store, and the two counts' saved positions."""
    data = tmp_path / "data"
    write_recall_store(data)
    out = tmp_path / "out"
    candidates, holders = out / "candidates.jsonl", out / "holders.jsonl"
    common = ["--data-dir", str(data), "--caselist", CASELIST]
    assert count_matching_recall.main([*common, "--save-candidates", str(candidates)]) == 0
    assert count_card_boundaries.main([*common, "--workers", "1", "--save-candidates", str(holders)]) == 0
    return data, candidates, holders


def _arguments(counted: tuple[Path, Path, Path], sheet: Path, *more: str) -> list[str]:
    data, candidates, holders = counted
    return [
        "--data-dir", str(data), "--caselist", CASELIST, "--candidates", str(candidates),
        "--holders", str(holders), "--tally-sheet", str(sheet), "--seed", "7", *more,
    ]  # fmt: skip


def _run(counted: tuple[Path, Path, Path], sheet: Path) -> str:
    shown: list[str] = []
    assert script.run(script.arguments_parser().parse_args(_arguments(counted, sheet)), shown.append) == 0
    (text,) = shown
    return text


def test_the_items_go_to_the_pager_and_the_sheet_holds_counts_alone(
    counted: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = tmp_path / "sheet.txt"
    shown = _run(counted, sheet)
    assert [int(number) for number in re.findall(r"Item (\d) of 6\.", shown)] == [1, 2, 3, 4, 5, 6]
    assert shown.count("Are A and B the same card? (s same card, d different card, u unsure)") == 1
    assert shown.count("one card cut twice, or two cards? (o one card cut twice, t two cards, u unsure)") == 5
    assert "kchanged" in shown  # the text is shown, to the pager alone
    printed = capsys.readouterr()
    assert not [word for word in TELLTALE if word in printed.out + printed.err]

    lines = sheet.read_text(encoding="utf-8").splitlines()
    assert not [word for word in TELLTALE if word in "\n".join(lines)]
    assert lines[0] == "Matching-recall sample (v1-e31-t29), seed 7: 6 items."
    assert lines[3:8] == [
        "In the corpus, and drawn:",
        "  neither end: nine-tenths inside a body holding neither of its ends: 1 (drew 1 of 20)",
        "  trims with the same tag and cite, end to end in their holder: 1 (drew 1 of 10)",
        "  trims with the same tag and cite, words of the holder between or around them: 1 (drew 1 of 10)",
        "  holders under 300 words of two bodies sharing no text: 3 (drew 3 of 20)",
    ]
    rows = lines[lines.index("Item | Answer | Notes") + 1 :][:6]
    assert rows == [f"{number:>4} |  |" for number in range(1, 7)]
    strata = lines[lines.index("Strata, by item (read after answering):") + 1 :]
    numbers = sorted(int(n) for line in strata for n in line.rsplit(": ", 1)[1].split(", "))
    assert numbers == [1, 2, 3, 4, 5, 6]


def test_the_same_seed_draws_the_same_items_in_the_same_order(
    counted: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    assert _run(counted, tmp_path / "one.txt") == _run(counted, tmp_path / "two.txt")


def test_a_holder_is_shown_whole_with_a_underlined_b_reversed_and_the_words_between_bold(
    counted: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    items = _run(counted, tmp_path / "sheet.txt").split("-" * 72)
    whole = [item for item in items if "The whole body:" in item]
    # Brannock's card in two strata (the trims and the holders), Kessler's in two, its copy in one.
    assert len(whole) == 5

    def styled(item: str, style: str) -> int:
        return len(re.findall(re.escape(style) + r"[bk]\d+", item))

    # Brannock: 13 and 16 words, none between. Kessler: 14 and 18, 14 between; its copy has
    # "kchanged" between, which the count of numbered words leaves out. A is either trim.
    marked = {
        (tuple(sorted((styled(item, UNDERLINE), styled(item, REVERSE)))), styled(item, BOLD))
        for item in whole
    }
    assert marked == {((13, 16), 0), ((14, 18), 14), ((14, 18), 13)}


def test_a_body_holding_neither_end_is_shown_beside_it_with_the_text_both_hold_underlined(
    counted: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    items = _run(counted, tmp_path / "sheet.txt").split("-" * 72)
    (item,) = [item for item in items if "neither A's first" in item]
    assert "B holds neither A's first five words nor its last five" in item
    assert f"{BOLD}wfirst" in item
    assert f"{UNDERLINE}w1{chr(27)}" in item


def test_the_draw_takes_each_strata_planned_number_at_most() -> None:
    population = {
        number: [script.Drawn(number, CASELIST, ((f"s{number}", index),)) for index in range(30)]
        for number in range(len(script.STRATA))
    }
    drawn = script.draw(population, 1)
    assert [sum(item.stratum == number for item in drawn) for number in range(4)] == [20, 10, 10, 20]
    assert len(set(drawn)) == 60


def test_a_sheet_that_exists_or_sits_in_the_repository_is_refused(
    counted: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    sheet = tmp_path / "sheet.txt"
    sheet.write_text("answers\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="written new"):
        script.run(script.arguments_parser().parse_args(_arguments(counted, sheet)), print)
    assert sheet.read_text(encoding="utf-8") == "answers\n"
    inside = Path(script.__file__).resolve().parent / "sheet.txt"
    with pytest.raises(SystemExit, match="outside the repository"):
        script.run(script.arguments_parser().parse_args(_arguments(counted, inside)), print)
    assert not inside.exists()


def test_the_sample_refuses_output_that_is_not_a_terminal(
    counted: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = tmp_path / "sheet.txt"
    assert script.main(_arguments(counted, sheet)) == 2
    assert "only in a terminal" in capsys.readouterr().err
    assert not sheet.exists()
