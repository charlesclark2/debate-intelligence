"""A `--source` plan never says "this team's": it names a file, and no team asked (`v1-e30-t16`).

A `--team` removal has a requesting team, and its plan rightly says "this team's copies". A
`--source` removal has none. Its plan still said "N of this team's path(s) to a shared file" over
the suppression entries, "this team's copies of 0 shared file(s)" to the requester, and, once a
later upload was withdrawn, that the list stops "this team's copy of a shared file". Nor did the
plan say a withdrawn later upload's copy stays because "another team there still holds it" when the
holder at the other path may be the same team.

Each plan is built by hand, as in `test_caselist_remove_plan_output.py`, holding every kind of
source a `--source` plan can: the named file removed whole, one skipped as shared, a later upload
removed and one withdrawn from the removed path, and a withdrawal a stopped run left
(:attr:`Inclusion.UNFINISHED`), which is the one that prints the *SHARED, KEPT* section. Every line
of the dry run and of the executed plan is walked, and every string of the JSON. The command run
end to end, on the real planner, is `tests/smoke/test_caselist_remove_smoke.py`.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import UTC, date, datetime
from typing import Any

from debate_cli.commands.caselist_remove import plan_summary, render_plan
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    PlannedSource,
    RemovalPlan,
    RemovalSelector,
    SourceSelector,
    TeamSelector,
)
from debate_core.application.caselist.removal_service import RemovalReport
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)

from .test_caselist_remove_plan_output import (
    CASELIST,
    LATER,
    NAMED,
    SETTINGS,
    TEAM_PATH,
    disclosure,
    later_at_the_team_path,
    plan_of,
    source,
)

SKIPPED = "e" * 64
LATER_REMOVED = "1" * 64
UNFINISHED = "2" * 64
RECORDED_AT = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)


def suppressed(sha256: str, path: str | None = None) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        disclosure=None if path is None else disclosure_digest(CASELIST, path),
        recorded_at=RECORDED_AT,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-05",
    )


def withdrawn(sha256: str, inclusion: Inclusion) -> PlannedSource:
    """Withdrawn from the team's path; the same team's second path keeps it, so no other team is counted."""
    return dataclasses.replace(
        source(sha256, inclusion, Disposition.WITHDRAW, requester_paths=((CASELIST, TEAM_PATH),)),
        other_teams=0,
        suppression=(suppressed(sha256, TEAM_PATH),),
    )


def every_kind_of_source(selector: RemovalSelector | None = None) -> RemovalPlan:
    named = dataclasses.replace(
        source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),
        suppression=(suppressed(NAMED),),
    )
    later_removed = dataclasses.replace(
        source(LATER_REMOVED, Inclusion.LATER_UPLOAD, Disposition.REMOVE),
        suppression=(suppressed(LATER_REMOVED),),
    )
    return plan_of(
        (
            named,
            source(SKIPPED, Inclusion.NAMED, Disposition.SKIP_SHARED),
            withdrawn(UNFINISHED, Inclusion.UNFINISHED),
            later_removed,
            withdrawn(LATER, Inclusion.LATER_UPLOAD),
        ),
        selector=selector,
        later_uploads=(later_at_the_team_path(LATER), later_at_the_team_path(LATER_REMOVED)),
    )


def executed(plan: RemovalPlan) -> RemovalReport:
    return RemovalReport(
        plan=plan,
        log_entry=RemovalLogEntry(
            kind=RemovalLogKind.REMOVAL,
            recorded_at=datetime(2026, 9, 30, 18, 5, tzinfo=UTC),
            request_id="RM-2026-05",
            reason=ReasonCode.REQUESTED_BY_TEAM,
            environment="dev",
            outcome=RemovalOutcome.COMPLETED,
            removed_sha256=(NAMED, LATER_REMOVED),
            withdrawn_sha256=(LATER, UNFINISHED),
        ),
        local_records_deleted=3,
        local_files_deleted=2,
        manifests_rewritten=2,
        manifest_rows_dropped=3,
        s3_versions_deleted=2,
    )


def strings_in(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in (key, *strings_in(item))]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [text for item in value for text in strings_in(item)]  # pyright: ignore[reportUnknownVariableType]
    return []


def test_no_line_of_a_source_plan_or_its_execution_says_this_team() -> None:
    plan = every_kind_of_source()

    printed = [*render_plan(plan, None).splitlines(), *render_plan(plan, executed(plan)).splitlines()]
    data = [plan_summary(plan, SETTINGS, None), plan_summary(plan, SETTINGS, executed(plan))]

    assert len(printed) > 100
    assert [line for line in printed if "this team" in line] == []
    assert [text for text in strings_in(data) if "this team" in text] == []


def test_each_line_that_said_this_team_now_says_what_a_source_removal_did() -> None:
    lines = render_plan(every_kind_of_source(), None).splitlines()

    assert lines[
        lines.index("SHARED, KEPT: 1 file(s) a path this removal does not take them from also holds.") :
    ][:3] == [
        "SHARED, KEPT: 1 file(s) a path this removal does not take them from also holds.",
        "Only the copies at the removed path(s) are withdrawn and suppressed; the file stays at its",
        "other paths.",
    ]
    assert "  2 whole file(s), and 2 path(s) a shared file is withdrawn from. Each" in lines
    assert (
        "  - Removed from this environment: 1 file(s), and the copies at the removed path(s) of 1 shared "
        "file(s)." in lines
    )
    assert (
        "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or the "
        "copy of a shared file at the path it was withdrawn from."
    ) in lines


def test_a_withdrawn_copy_kept_for_another_path_does_not_claim_another_team() -> None:
    """The holder at the other path may be the same team: the plan says a path holds it, not a team."""
    lines = render_plan(every_kind_of_source(), None).splitlines()

    kept = [line for line in lines if line.lstrip().startswith("kept in")]
    assert kept == [f"     kept in  {CASELIST} (another path there still holds it)"] * 2
    assert not [line for line in lines if "another team" in line]


def test_a_source_removal_that_withdraws_nothing_says_only_what_it_removed() -> None:
    plan = plan_of(
        (
            dataclasses.replace(
                source(
                    NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)
                ),
                suppression=(suppressed(NAMED),),
            ),
        )
    )

    lines = render_plan(plan, None).splitlines()

    assert "  1 whole file(s), and 0 path(s) a shared file is withdrawn from. Each" in lines
    assert "  - Removed from this environment: 1 file(s)." in lines


def test_a_team_removal_still_says_this_teams_where_a_team_asked() -> None:
    """The same sources under `--team`: its own wording, as `v1-e30-t11` and `v1-e30-t17` left it."""
    team = TeamSelector(caselist=CASELIST, school="Alder Point", team_code="KR")
    lines = render_plan(every_kind_of_source(team), None).splitlines()

    assert "SHARED, KEPT: 1 file(s) another team or a camp file also holds. Only this" in lines
    assert "  2 whole file(s), and 2 of this team's path(s) to a shared file. Each" in lines
    assert (
        "  - Removed from this environment: 1 file(s), and this team's copies of 1 shared file(s)." in lines
    )
    assert (
        "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or this "
        "team's copy of a shared file at the path it was taken from."
    ) in lines
    assert f"     kept in  {CASELIST} (another team there still holds it)" in lines


def test_the_fixture_withdraws_from_a_path_the_suppression_entries_name() -> None:
    """The entries the hand-built plan carries are the ones a planner would write for those paths."""
    plan = every_kind_of_source()

    assert {entry.disclosure for entry in plan.suppression_entries} == {
        None,
        hashlib.sha256(f"{CASELIST}/{TEAM_PATH}".encode()).hexdigest(),
    }
    assert isinstance(plan.selector, SourceSelector)
