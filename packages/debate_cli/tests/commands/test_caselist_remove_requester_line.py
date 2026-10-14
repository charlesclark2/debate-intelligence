"""The line `caselist remove` prints for the confirmation to the requester about suppression (`v1-e30-t17`).

It used to say that next week's cumulative archive could not bring any of the removed files back. A
weekly archive is a window of about a week's editing, not a cumulative copy: a removed file comes back
in a later weekly only if it is edited, carried or uploaded again, and in every complete archive until
the team takes it down on OpenCaselist. The suppression list stops it in all of them. The line now says
that, and says it only of what this removal actually suppressed: a whole file, or this team's copy at
the path a shared file was withdrawn from. Whether a path is held is the line above it (`v1-e30-t13`).

Each plan is built by hand, as in `test_caselist_remove_plan_output.py`; nothing is planned or executed.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from debate_cli.commands.caselist_remove import render_plan
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    RemovalPlan,
    TeamSelector,
)
from debate_core.application.ports.suppression import SuppressionState

from .test_caselist_path_hold_output import THE_PATH_ENTRY
from .test_caselist_remove_plan_output import (
    IDENTIFYING,
    LATER,
    NAMED,
    disclosure,
    later_at_the_team_path,
    plan_of,
    source,
)

SHARED = "f" * 64

REMOVED_ONLY = "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file."
REMOVED_AND_WITHDRAWN = (
    "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or this "
    "team's copy of a shared file at the path it was taken from."
)
HELD = "  - Held: 1 path(s) the file was removed from, so a new upload there is refused when it is imported."
NOT_HELD = "  - Not held: the request was about one version, so a later upload at the same path is imported."


def confirmation(plan: RemovalPlan) -> list[str]:
    """The lines under FOR THE CONFIRMATION TO THE REQUESTER, up to the next section."""
    shown = render_plan(plan, None)
    start = shown.index("FOR THE CONFIRMATION TO THE REQUESTER")
    end = shown.find("\n\n", start)
    return shown[start : end if end != -1 else len(shown)].splitlines()[1:]


def suppression_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if "uppressed" in line]


def says_nothing_cumulative_and_names_no_one(lines: list[str]) -> None:
    assert not [line for line in lines if "cumulative" in line], lines
    assert not [word for word in IDENTIFYING if word in "\n".join(suppression_lines(lines))], lines


def a_source_removal_that_holds_its_path() -> RemovalPlan:
    plan = plan_of(
        (source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),)
    )
    held = SuppressionState.from_entries([], [THE_PATH_ENTRY])
    return dataclasses.replace(plan, path_holds=(THE_PATH_ENTRY,), suppression_after=held)


def test_a_source_removal_says_the_file_is_suppressed_in_every_later_archive_and_its_path_held() -> None:
    lines = confirmation(a_source_removal_that_holds_its_path())

    assert suppression_lines(lines) == [REMOVED_ONLY]
    assert HELD in lines
    says_nothing_cumulative_and_names_no_one(lines)


def test_a_team_removal_says_its_whole_files_and_its_copies_of_shared_files_are_suppressed() -> None:
    """A `--team` removal holds no path, so the confirmation claims none."""
    plan = plan_of(
        (
            source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),
            source(SHARED, Inclusion.NAMED, Disposition.WITHDRAW, disclosures=(disclosure(date(2026, 9, 15)),)),
        ),
        selector=TeamSelector(caselist="testcl26", school="Alder Point", team_code="KR"),
    )

    lines = confirmation(plan)

    assert suppression_lines(lines) == [REMOVED_AND_WITHDRAWN]
    assert not [line for line in lines if "held" in line.lower()], lines
    says_nothing_cumulative_and_names_no_one(lines)


def test_only_named_says_the_named_file_is_suppressed_and_its_path_not_held() -> None:
    plan = plan_of(
        (source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),),
        later_uploads=(later_at_the_team_path(LATER),),
        only_named=True,
    )

    lines = confirmation(plan)

    assert suppression_lines(lines) == [REMOVED_ONLY]
    assert NOT_HELD in lines
    says_nothing_cumulative_and_names_no_one(lines)


def test_a_removal_that_only_withdraws_says_only_the_teams_copy_is_suppressed() -> None:
    plan = plan_of(
        (source(SHARED, Inclusion.NAMED, Disposition.WITHDRAW, disclosures=(disclosure(date(2026, 9, 15)),)),),
        selector=TeamSelector(caselist="testcl26", school="Alder Point", team_code="KR"),
    )

    assert suppression_lines(confirmation(plan)) == [
        "  - Suppressed, so no later archive, weekly or complete, can bring back this team's copy of a "
        "shared file at the path it was taken from."
    ]


def test_a_removal_that_removes_nothing_does_not_say_anything_was_suppressed() -> None:
    """Every file the request names is shared and kept: nothing goes on the list."""
    plan = plan_of((source(NAMED, Inclusion.NAMED, Disposition.SKIP_SHARED),))

    assert suppression_lines(confirmation(plan)) == [
        "  - Nothing suppressed: no file was removed, and no copy withdrawn."
    ]
