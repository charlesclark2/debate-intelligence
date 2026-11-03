"""What `caselist remove` and `caselist status` print of the landscape school views (`v1-e32-t13`).

Each plan and report is built by hand, field by field, as in `test_caselist_remove_plan_output.py`:
the renderers are functions of what they are given. The behaviour behind them is
`packages/debate_core/tests/application/caselist/test_removal_reaches_landscape_school_views.py`.

The plan's text and JSON list keys, which hold a caselist, a snapshot and a file's name and nothing
else, and name the bundle to republish, which the command never does itself. The status lines give
counts and the removal they are older than.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, date, datetime

from debate_cli.commands.caselist import (
    _status_table,  # pyright: ignore[reportPrivateUsage]
    status_summary,
)
from debate_cli.commands.caselist_remove import plan_summary, render_plan
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    RemovalPlan,
    SchoolViewRemoval,
    Side,
)
from debate_core.application.caselist.removal_residue import CaselistResidue, OlderVersions, RemovalCompletion
from debate_core.application.caselist.removal_school_views import SchoolViewReach
from debate_core.application.caselist.removal_service import RemovalReport
from debate_core.application.caselist.status_service import CaselistStatusReport
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
)

from .test_caselist_remove_plan_output import CASELIST, IDENTIFYING, NAMED, SETTINGS, plan_of, source
from .test_caselist_status_held_paths import snapshot

OLDER = "reports/landscape/testcl26/2026-09-15/schools.csv"
NEWER = "reports/landscape/testcl26/2026-09-29/schools.md"
EARLIER_RUN = RemovalCompletion("RM-2026-03", datetime(2026, 9, 20, 9, 30, tzinfo=UTC))


def version(key: str) -> ObjectVersion:
    return ObjectVersion(key=key, version_id="v1")


def with_school_views(*, counted: bool = True, earlier: bool = False) -> RemovalPlan:
    """A file removed from `testcl26`, two of its bundles' school views on each side, and with
    `earlier` a second caselist an earlier run of the request touched, with nothing of it left."""
    reach = (SchoolViewReach(CASELIST),)
    if earlier:
        reach += (SchoolViewReach("othercl26", older_than=EARLIER_RUN),)
    return dataclasses.replace(
        plan_of((source(NAMED, Inclusion.NAMED, Disposition.REMOVE),)),
        school_view_reach=reach,
        school_views=(
            SchoolViewRemoval(key=OLDER, side=Side.LOCAL, versions=(version(OLDER),)),
            SchoolViewRemoval(key=NEWER, side=Side.LOCAL, versions=(version(NEWER),)),
            SchoolViewRemoval(
                key=OLDER, side=Side.BUCKET, versions=(version(OLDER), version(OLDER)) if counted else None
            ),
            SchoolViewRemoval(key=NEWER, side=Side.BUCKET, versions=(version(NEWER),) if counted else None),
        ),
        school_view_versions_counted=counted,
    )


def told(text: str) -> str:
    return " ".join(text.split())


class TestThePlansText:
    def test_it_lists_each_file_by_side_and_key_and_says_what_stays(self) -> None:
        shown = render_plan(with_school_views(), None).splitlines()

        start = shown.index(
            f"LANDSCAPE SCHOOL VIEWS deleted, here and in the bucket: 4 file(s) of {CASELIST}"
        )
        assert shown[start + 1 : start + 7] == [
            "  Each names schools and team codes as disclosed. The circuit-wide files beside them",
            "  (report.md and its CSVs) and every other caselist's bundles are left as they are.",
            f"  local  {OLDER}",
            f"  local  {NEWER}",
            f"  bucket {OLDER}  2 version(s)",
            f"  bucket {NEWER}  1 version(s)",
        ]

    def test_it_names_the_newest_bundle_to_republish_and_that_it_never_republishes(self) -> None:
        shown = render_plan(with_school_views(), None)

        assert (
            "REPUBLISH, once this removal is done: the newest bundle it took a school view from, without "
            "the removed rounds. This command never republishes; tell the PM, who coordinates it."
        ) in told(shown)
        assert (
            "  testcl26 2026-09-29: debate-research landscape report --caselist testcl26 --snapshot "
            "2026-09-29 --publish"
        ) in shown.splitlines()

    def test_where_versions_were_not_listed_it_says_so_and_what_execute_does(self) -> None:
        shown = render_plan(with_school_views(counted=False), None)

        assert f"  bucket {OLDER}  versions not counted" in shown.splitlines()
        assert (
            "Bucket versions not counted: the everyday profile lists no versions under reports/. --execute "
            "lists every version of every bundle with the removal profile and deletes each this rule "
            "reaches, a noncurrent one the listing above could not show included."
        ) in told(shown)

    def test_a_caselist_an_earlier_run_touched_says_which_views_it_takes(self) -> None:
        shown = render_plan(with_school_views(earlier=True), None)

        assert (
            "  othercl26: only those written before RM-2026-03's run completed 2026-09-20 09:30 UTC; "
            "this run finishes it."
        ) in shown.splitlines()

    def test_a_reach_with_nothing_found_says_none_and_a_plan_with_no_reach_says_nothing(self) -> None:
        empty = dataclasses.replace(with_school_views(), school_views=())

        assert (
            "  (none: no school view they reach is on this machine or in the bucket)"
            in render_plan(empty, None).splitlines()
        )
        assert "REPUBLISH" not in render_plan(empty, None)
        assert "LANDSCAPE SCHOOL VIEWS" not in render_plan(plan_of(()), None)

    def test_the_confirmation_counts_the_bundles_and_names_no_key(self) -> None:
        shown = render_plan(with_school_views(), None).splitlines()
        confirmation = shown[shown.index("FOR THE CONFIRMATION TO THE REQUESTER") :]

        assert (
            "  - Deleted: the per-school view of 2 argument landscape report(s); the newest is to be "
            "republished without the removed rounds."
        ) in confirmation
        assert not [line for line in confirmation if "reports/" in line]

    def test_the_done_line_says_how_many_of_the_deletions_were_school_views(self) -> None:
        plan = with_school_views()
        report = RemovalReport(
            plan=plan,
            log_entry=RemovalLogEntry(
                kind=RemovalLogKind.REMOVAL,
                recorded_at=datetime(2026, 9, 30, 18, 5, tzinfo=UTC),
                request_id="RM-2026-05",
                reason=ReasonCode.REQUESTED_BY_TEAM,
                environment="dev",
                outcome=RemovalOutcome.COMPLETED,
            ),
            local_records_deleted=1,
            local_files_deleted=3,
            manifests_rewritten=0,
            manifest_rows_dropped=0,
            s3_versions_deleted=4,
            school_view_files_deleted=2,
            school_view_versions_deleted=3,
        )

        done = render_plan(plan, report).splitlines()

        assert done[1] == "Of those, 2 local file(s) and 3 bucket version(s) were landscape school views."
        assert "Bucket versions not counted" not in render_plan(
            dataclasses.replace(plan, school_view_versions_counted=False), report
        )


class TestThePlansJson:
    def test_it_gives_the_reach_the_files_by_key_and_the_bundle_to_republish(self) -> None:
        data = plan_summary(with_school_views(earlier=True), SETTINGS, None)

        assert data["school_views"] == {
            "reach": [
                {"caselist": CASELIST, "older_than": None},
                {
                    "caselist": "othercl26",
                    "older_than": {"request_id": "RM-2026-03", "completed_at": "2026-09-20T09:30:00Z"},
                },
            ],
            "files": [
                {"key": OLDER, "side": "local", "versions": 1},
                {"key": NEWER, "side": "local", "versions": 1},
                {"key": OLDER, "side": "bucket", "versions": 2},
                {"key": NEWER, "side": "bucket", "versions": 1},
            ],
            "versions_counted": True,
            "republish": [{"caselist": CASELIST, "snapshot": date(2026, 9, 29).isoformat()}],
        }
        assert not [word for word in IDENTIFYING if word in json.dumps(data["school_views"])]

    def test_uncounted_versions_are_null_never_zero(self) -> None:
        data = plan_summary(with_school_views(counted=False), SETTINGS, None)

        files = data["school_views"]["files"]  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue, reportOptionalSubscript]
        assert [one["versions"] for one in files if one["side"] == "bucket"] == [None, None]  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue, reportOptionalSubscript, reportOptionalIterable, reportGeneralTypeIssues]


def with_school_views_left() -> CaselistStatusReport:
    return CaselistStatusReport(
        snapshots=(snapshot("2026-09-15"),),
        residue=(
            CaselistResidue(
                caselist=CASELIST,
                checked=True,
                school_views=(
                    OlderVersions(role="school view", versions=4),
                    OlderVersions(role="local school view", versions=2),
                ),
                school_views_older_than=EARLIER_RUN,
            ),
        ),
    )


class TestStatus:
    def test_views_left_fail_the_command_as_residue(self) -> None:
        report = with_school_views_left()

        assert report.residue_found
        assert report.in_sync is False

    def test_the_table_counts_them_by_side_against_the_run_they_are_older_than(self) -> None:
        caption = _status_table(with_school_views_left(), SETTINGS).caption or ""

        assert (
            f"REMOVAL RESIDUE in {CASELIST}: 4 school view file(s) and 2 local school view file(s) "
            "older than RM-2026-03, completed 2026-09-20 09:30 UTC."
        ) in told(caption)
        assert "reports/" not in caption

    def test_the_json_gives_them_beside_the_other_older_versions(self) -> None:
        data = status_summary(with_school_views_left(), SETTINGS)
        (entry,) = data["removal_residue"]  # pyright: ignore[reportGeneralTypeIssues, reportArgumentType]

        assert entry["school_views"] == [  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue, reportOptionalSubscript]
            {"role": "school view", "files": 4},
            {"role": "local school view", "files": 2},
        ]
        assert entry["school_views_older_than"] == {  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue, reportOptionalSubscript]
            "request_id": "RM-2026-03",
            "completed_at": "2026-09-20T09:30:00Z",
        }
