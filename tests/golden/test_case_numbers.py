"""A golden case's number is never given to another card (the PM's ruling of 2026-11-20, 3).

The importer numbers each event's cases from the highest number ever assigned in it, never the
first free one, and INDEX.md keeps every retired ID on one line, so an ID in an earlier report
always names the card it named then. A case leaves the corpus by `record` (its source is dropped)
or by `retire` (it does not label); both put its ID on that line. Every case here is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import golden_snapshots as snaps  # noqa: E402
import import_golden_card as golden  # noqa: E402
from tests.golden.snapshot_world import (  # noqa: E402
    IMPORTED_ON,
    LINKS,
    TEST_KEY,
    World,
    build_world,
    card,
    envelope,
    tree,
)
from tests.golden.synthetic_team_files import coach_attests, team_file  # noqa: E402

LATE_LINK = "https://www.brookings.edu/articles/late-grid"


@pytest.fixture
def numbered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> World:
    """Two Policy cases and one LD case, imported; the Policy cards' pages reported, one paywalled."""
    monkeypatch.setattr(snaps, "_checkouts", lambda repository: [REPO_ROOT.resolve()])
    layout = (
        ("2025-2026", "Policy", [card(name, LINKS[name]) for name in ("accessible", "paywalled")]),
        ("2024-2025", "LD", [card("errored", LINKS["errored"])]),
    )
    world = build_world(tmp_path, layout, dict(LINKS))
    snapshot = world.store_page(LINKS["accessible"])
    world.report("accessible", envelope(LINKS["accessible"], "ACCESSIBLE", snapshot_id=snapshot.snapshot_id))
    world.report("paywalled", envelope(LINKS["paywalled"], "PAYWALLED"))
    capsys.readouterr()
    return world


def _import_late_card(world: World, event: str = "Policy") -> str:
    """Import one more invented card into `event`, as a later pick round would; its case ID."""
    folder = world.root / "later" / "2026-2027" / event
    folder.mkdir(parents=True)
    (folder / "late file.docx").write_bytes(team_file([card("late", LATE_LINK)]))
    listing = golden.list_candidates([world.root / "later" / "2026-2027"], (), TEST_KEY)
    imported, refused = golden.import_candidates(
        listing.candidates,
        [c.candidate_id for c in listing.candidates],
        golden.NO_DENYLIST,
        world.fixtures,
        today=IMPORTED_ON,
        attest=coach_attests,
    )
    assert refused == []
    (case,) = imported
    return case.case_id


def _index(world: World) -> str:
    return (world.fixtures / golden.INDEX_NAME).read_text(encoding="utf-8")


def test_a_dropped_cases_number_is_retired_and_never_given_again(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    kept, dropped = numbered.case_for("accessible"), numbered.case_for("paywalled")
    assert {kept, dropped} == {"policy-001", "policy-002"}

    numbered.record("--execute")
    capsys.readouterr()

    # The next number after the highest ever given, whether the dropped case held it or not.
    assert _import_late_card(numbered) == "policy-003"
    assert f"\nRetired: {dropped}.\n" in _index(numbered)


def test_the_highest_number_is_not_given_again_once_its_case_has_left(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    highest = max(numbered.case_for("accessible"), numbered.case_for("paywalled"))
    assert golden.main(["retire", highest, "--execute", "--fixtures", str(numbered.fixtures)]) == 0
    capsys.readouterr()

    assert _import_late_card(numbered) == "policy-003"


def test_retired_ids_survive_every_rewrite_of_the_index(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    dropped = numbered.case_for("paywalled")
    numbered.record("--execute")

    assert golden.main(["index", "--fixtures", str(numbered.fixtures)]) == 0
    _import_late_card(numbered, "LD")
    capsys.readouterr()

    assert f"\nRetired: {dropped}.\n" in _index(numbered)


def test_an_index_with_nothing_retired_says_so() -> None:
    assert golden.render_index(Path("/nonexistent-golden-corpus")).endswith("\nRetired: none.\n")


def test_retire_is_a_dry_run_until_execute_and_then_removes_the_case(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    case_id = numbered.case_for("errored")
    before = tree(numbered.fixtures)

    assert golden.main(["retire", case_id, "--fixtures", str(numbered.fixtures)]) == 0
    assert capsys.readouterr().out == (
        f"would retire: 1\n  {case_id}\ndry run: nothing written; run again with --execute to retire\n"
    )
    assert tree(numbered.fixtures) == before

    assert golden.main(["retire", case_id, "--execute", "--fixtures", str(numbered.fixtures)]) == 0
    assert capsys.readouterr().out == f"retired: 1\n  {case_id}\n"
    assert not (numbered.fixtures / case_id).exists()
    assert f"\nRetired: {case_id}.\n" in _index(numbered)


def test_retire_refuses_an_id_that_is_not_a_case_and_changes_nothing(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    before = tree(numbered.fixtures)

    assert golden.main(["retire", "policy-009", "--execute", "--fixtures", str(numbered.fixtures)]) == 2
    assert "policy-009 is not a case in the corpus" in capsys.readouterr().err
    assert tree(numbered.fixtures) == before


def test_retired_ids_are_listed_in_order_and_never_include_a_present_case(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    golden.write_index(numbered.fixtures, retired=["pf-004", "ld-002", "policy-010"])
    golden.write_index(numbered.fixtures)

    assert "\nRetired: ld-002, pf-004, policy-010.\n" in _index(numbered)
    with pytest.raises(ValueError, match="policy-001 is a case in the corpus"):
        golden.write_index(numbered.fixtures, retired=["policy-001"])


def test_existing_case_ids_are_kept_as_they_are(numbered: World, capsys: pytest.CaptureFixture[str]) -> None:
    dropped = numbered.case_for("paywalled")
    before = {path.name for path in numbered.fixtures.iterdir() if path.is_dir()}

    numbered.record("--execute")
    late = _import_late_card(numbered)

    after = {path.name for path in numbered.fixtures.iterdir() if path.is_dir()}
    assert after == (before - {dropped}) | {late}


def test_a_number_below_the_highest_is_not_given_again_even_with_no_retired_line(
    numbered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    # A folder removed by hand leaves no retired ID; the next number still follows the highest,
    # never the first free one (the ruling's own words).
    lowest = min(numbered.case_for("accessible"), numbered.case_for("paywalled"))
    golden.shutil.rmtree(numbered.fixtures / lowest)

    assert _import_late_card(numbered) == "policy-003"
