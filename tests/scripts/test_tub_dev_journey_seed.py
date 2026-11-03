"""The dev seed `tub_dev_journey.py seed` writes, and why it stays out of every real report (`v1-e39-t10`).

The seed goes into dev's store through the normal path (`caselist import`, `parse`, `tub index build`),
so these hold what it is before anyone imports it: the same bytes every time, three structural
fixtures and nothing else, filed under invented schools in a caselist no weekly run follows, and one
file whose removal takes the journey's card with it. Expected values are written by hand.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tub_dev_journey as journey  # noqa: E402

from debate_cli.caselist_events import event_for_caselist  # noqa: E402
from debate_core.application.caselist_sync import search_index_stores  # noqa: E402

STRUCTURAL: Final = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "structural"

MEMBERS: Final = [
    "testcl26-1027/Brindlecote High/BrHo/Brindlecote High-BrHo-Aff-Lanternfield Invitational-Round 3.docx",
    "testcl26-1027/Ostrander Vale/OvTe/Ostrander Vale-OvTe-Neg-Lanternfield Invitational-Round 2.docx",
    "testcl26-1027/Quillfern Academy/QfAn/Quillfern Academy-QfAn-Aff-Lanternfield Invitational-Round 1.docx",
]

RM_2026_90_SCHOOLS: Final = (
    "Maple Grove",
    "Cedar Hollow",
    "Northgate Prep",
    "Riverbend Academy",
    "Westfield",
    "Bayview",
)
"""The invented schools of `tests/fixtures/caselist/build_synthetic_archives.py`, which dev's `testcl26`
already holds; `Maple Grove/QX` was removed there and its path is held (`RM-2026-90`)."""


def tags_of(fixture: str) -> list[str]:
    expected = json.loads((STRUCTURAL / f"{fixture}.expected.json").read_text(encoding="utf-8"))
    return [card["tag"] for card in expected["cards"] if card["completeness"] != "CITE_ONLY"]


def test_the_archive_is_the_same_bytes_every_time_and_holds_the_three_fixtures() -> None:
    first = journey.seed_archive_bytes()

    assert journey.seed_archive_bytes() == first
    archive = zipfile.ZipFile(io.BytesIO(first))
    assert archive.namelist() == MEMBERS
    by_name = {member.rsplit("/", 1)[1]: archive.read(member) for member in MEMBERS}
    assert by_name == {
        "Brindlecote High-BrHo-Aff-Lanternfield Invitational-Round 3.docx": (
            STRUCTURAL / "cardmirror-caselist-upload.docx"
        ).read_bytes(),
        "Ostrander Vale-OvTe-Neg-Lanternfield Invitational-Round 2.docx": (
            STRUCTURAL / "team-verbatim-file.docx"
        ).read_bytes(),
        "Quillfern Academy-QfAn-Aff-Lanternfield Invitational-Round 1.docx": (
            STRUCTURAL / "cardmirror-camp-file.docx"
        ).read_bytes(),
    }
    assert all(member.compress_type == zipfile.ZIP_STORED for member in archive.infolist())


def test_the_seed_command_writes_the_archive_and_names_the_file_to_remove(tmp_path: Path) -> None:
    said: list[str] = []

    assert journey.main(["seed", "--out", str(tmp_path / "seed")], say=said.append) == 0

    archive = tmp_path / "seed" / "testcl26-2026-10-27.zip"
    removed = hashlib.sha256((STRUCTURAL / "cardmirror-camp-file.docx").read_bytes()).hexdigest()
    assert said[:3] == [
        f"archive {archive}",
        f"archive sha256 {hashlib.sha256(archive.read_bytes()).hexdigest()}",
        "caselist testcl26, snapshot 2026-10-27",
    ]
    assert said[3] == f"remove {removed}  {journey.SEED_FILES[0].path}"
    assert [line.split()[0] for line in said[3:]] == ["remove", "keep", "keep"]


def test_the_journeys_card_is_in_the_removed_file_alone_and_the_other_card_in_every_file() -> None:
    """So after the removal the journey's card is gone, and the shared card stays (one team's line less)."""
    removed = [one for one in journey.SEED_FILES if one.removed]
    kept = [one for one in journey.SEED_FILES if not one.removed]

    assert [one.fixture for one in removed] == ["cardmirror-camp-file"]
    assert tags_of("cardmirror-camp-file") == [
        "Data centre demand collapses the reserve margin",
        "Reserve margins are already below the planning standard",
    ]
    assert journey.SEED_CARD.tag == "Reserve margins are already below the planning standard"
    for one in kept:
        assert tags_of(one.fixture) == ["Data centre demand collapses the reserve margin"], one.fixture


def test_the_seed_is_filed_under_invented_schools_none_of_dev_testcl26s_own() -> None:
    for one in journey.SEED_FILES:
        school, code, name = one.path.split("/")
        assert name.startswith(f"{school}-{code}-"), one.path
        assert "Lanternfield Invitational" in name
        assert not any(taken in one.path for taken in RM_2026_90_SCHOOLS), one.path


def test_the_seed_caselist_is_indexable_and_no_weekly_run_follows_indexes_or_reports_it() -> None:
    """The weekly run imports, indexes and reports `caselist.sync_caselists` (and `openev`) only."""
    assert journey.SEED_CASELIST == "testcl26"
    assert event_for_caselist(journey.SEED_CASELIST) is not None, (
        "tub index build refuses a slug it has no event for"
    )
    dev = tomllib.loads((REPO_ROOT / "config" / "profiles" / "dev.toml").read_text(encoding="utf-8"))
    assert dev["caselist"]["sync_caselists"] == ["hsld26", "hspolicy26", "hspf26"]
    for environment in ("dev", "prod"):
        profile = tomllib.loads(
            (REPO_ROOT / "config" / "profiles" / f"{environment}.toml").read_text(encoding="utf-8")
        )
        # Unset means none: the setting's default is empty, as test_settings_environments pins for prod.
        followed = profile["caselist"].get("sync_caselists", [])
        assert journey.SEED_CASELIST not in followed, environment
        assert journey.SEED_CASELIST not in search_index_stores(followed), environment


def test_the_seed_snapshot_is_after_dev_testcl26s_newest_week() -> None:
    """RM-2026-90's exercise imported testcl26 weeks up to 2026-09-29; an older week would be refused."""
    assert journey.SEED_SNAPSHOT > "2026-09-29"
