"""The backfile rules (`v1-e34-t34`): the marker setting, the no-import window and the free-space estimate.

Every expected value here was worked out by hand from the PM's rulings of 2026-10-25:

* the window is Tuesday 06:00 to Thursday 00:00, America/Chicago, which is UTC-5 until
  1 November 2026 and UTC-6 after it;
* the precheck needs the archive in the inbox, its blobs (the archive's size again) and its parsed
  store (four times), plus 25%.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from debate_core.application.caselist.backfile_import import (
    in_no_import_window,
    no_import_window_ends,
    space_needed,
)
from debate_core.application.caselist.backfiles import (
    BackfileHasNoLandscape,
    BackfileIsNotPulled,
    refuse_a_landscape,
    refuse_backfiles,
)
from debate_core.application.settings import CaselistSettings


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("moment", "inside"),
    [
        ("2026-10-27T10:59:59", False),  # Tuesday 05:59:59 CDT
        ("2026-10-27T11:00:00", True),  # Tuesday 06:00 CDT: the window opens
        ("2026-10-28T08:00:00", True),  # Wednesday 03:00 CDT: the login
        ("2026-10-28T11:00:00", True),  # Wednesday 06:00 CDT: the weekly run
        ("2026-10-29T04:59:59", True),  # Wednesday 23:59:59 CDT
        ("2026-10-29T05:00:00", False),  # Thursday 00:00 CDT: it closes
        ("2026-11-03T11:59:59", False),  # Tuesday 05:59:59 CST, after the clocks went back
        ("2026-11-03T12:00:00", True),  # Tuesday 06:00 CST
        ("2026-11-04T05:30:00", True),  # Tuesday 23:30 CST, already Wednesday in UTC
        ("2026-11-05T05:59:59", True),  # Wednesday 23:59:59 CST
        ("2026-11-05T06:00:00", False),  # Thursday 00:00 CST
        ("2026-11-01T18:00:00", False),  # a Sunday
        ("2026-11-02T18:00:00", False),  # a Monday
    ],
)
def test_the_no_import_window_is_tuesday_06_00_to_thursday_00_00_chicago(moment: str, inside: bool) -> None:
    assert in_no_import_window(utc(moment)) is inside


def test_the_window_ends_at_the_thursday_midnight_after_it() -> None:
    assert no_import_window_ends(utc("2026-11-03T13:00:00")) == utc("2026-11-05T06:00:00")
    assert no_import_window_ends(utc("2026-10-28T11:00:00")) == utc("2026-10-29T05:00:00")


def test_the_precheck_needs_the_inbox_the_blobs_and_four_times_for_the_parsed_store_plus_a_quarter() -> None:
    space = space_needed(1_000, free_bytes=7_500)

    assert (space.archive_bytes, space.estimate_bytes, space.required_bytes) == (1_000, 6_000, 7_500)
    assert space.enough
    assert not space_needed(1_000, free_bytes=7_499).enough


def test_an_archive_already_in_the_inbox_needs_no_room_for_itself() -> None:
    space = space_needed(1_000, free_bytes=0, in_inbox=True)

    assert (space.estimate_bytes, space.required_bytes) == (5_000, 6_250)


def test_hspolicy25s_measured_size_needs_about_30_gb() -> None:
    """The survey's figure for 2025-26 Policy: what the dry run on the Mac compares with 12 GiB."""
    space = space_needed(3_958_272_657, free_bytes=12 * 1024**3)

    assert space.required_bytes == 29_687_044_928
    assert not space.enough


def test_a_pull_of_a_backfile_is_refused_by_name_and_another_is_not() -> None:
    refuse_backfiles(["testcl26", None], ["testcl25"])
    with pytest.raises(BackfileIsNotPulled) as refused:
        refuse_backfiles(["testcl26", "testcl25"], ["testcl25"])
    assert refused.value.caselists == ("testcl25",)
    with pytest.raises(BackfileIsNotPulled):
        refuse_backfiles(["testcl26", None, "testcl24"], ["testcl24", "testcl25"])


def test_a_landscape_of_a_backfile_is_refused() -> None:
    refuse_a_landscape("testcl26", ["testcl25"])
    with pytest.raises(BackfileHasNoLandscape):
        refuse_a_landscape("testcl25", ["testcl25"])


# ------------------------------------------------------------------------------------------------
# The marker: caselist.backfile_caselists
# ------------------------------------------------------------------------------------------------


def test_a_backfile_in_sync_caselists_too_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="both name hspolicy25"):
        CaselistSettings(sync_caselists=("hspolicy26", "hspolicy25"), backfile_caselists=("hspolicy25",))


def test_a_backfile_of_a_season_before_2021_22_is_refused() -> None:
    with pytest.raises(ValidationError, match="before 2021-22"):
        CaselistSettings(backfile_caselists=("hspolicy20",))
    assert CaselistSettings(backfile_caselists=("hspolicy21",)).backfile_caselists == ("hspolicy21",)


def test_a_backfile_must_be_a_slug() -> None:
    with pytest.raises(ValidationError, match="not a caselist slug"):
        CaselistSettings(backfile_caselists=("hs-policy-25",))


def test_the_annual_purge_keeps_what_the_setting_names() -> None:
    """`v1-e30-t28`'s purge has no code yet (its spec is a runbook, Pending): this pins the accessor it
    reads, `CaselistSettings.is_backfile`, so that the purge and the import ask one question."""
    settings = CaselistSettings(backfile_caselists=("hspolicy25", "hsld25"), sync_caselists=("hspolicy26",))

    assert settings.is_backfile("hspolicy25")
    assert settings.is_backfile("hsld25")
    assert not settings.is_backfile("hspolicy26")
    assert not settings.is_backfile("hspolicy20")
