"""Loose ends in what a removal plan prints (`v1-e30-t20`).

* **The JSON's withdrawals.** The text has printed the withdrawal record's lines under
  *WITHDRAWALS* since `v1-e30-t16`; the JSON carried none of them. It now has `withdrawals` beside
  `path_holds`: one entry per withdrawal, by the file's digest, the path's digest and the caselist's
  slug, and an empty list when the plan withdraws nothing. A withdrawal from a held path an import
  refused the file at (`v1-e30-t23`) is one of them, known by the held path's digest.
* **Another holder's path is not "this team's".** A `--team --include-shared` plan removes a shared
  file whole, so it takes the file from the other holders' paths too, and a later upload at one of
  them is withdrawn from that holder's path. The suppression count called that path "this team's",
  and the line on what the list stops called the copy "this team's copy".
* **A re-run that removes nothing says so.** Its confirmation to the requester said "Removed from
  this environment: 1 file(s)" under *Nothing is left to remove*: it counted what the re-run
  planned again, not what it removed.
* **The JSON's sweep count.** The plan has said since `v1-e30-t19` how many noncurrent manifest
  versions the execution's sweep deletes, by manifest. The JSON now carries the same count, as
  `manifest_versions_swept`, and says *not counted* where the plan line does, never 0.

Each plan is built by hand, as in `test_caselist_remove_plan_output.py`: the renderers are
functions of what they are given. The command end to end, on the real planner, is
`tests/smoke/test_caselist_remove_smoke.py`.
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from datetime import UTC, datetime

from debate_cli.commands.caselist_remove import plan_summary, render_plan
from debate_core.application.caselist.removal_path_versions import (
    PathVersion,
    SamePathEvidence,
    VersionRelation,
)
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    PlannedSource,
    RemovalPlan,
    TeamSelector,
)
from debate_core.application.caselist.removal_service import RemovalReport
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)

from .test_caselist_path_hold_output import new_lines_name_no_one, section
from .test_caselist_remove_plan_output import (
    CASELIST,
    LATER,
    NAMED,
    SETTINGS,
    TEAM_PATH,
    plan_of,
    source,
)

SHARED = "5" * 64
REFUSED = "6" * 64
RECORDED_AT = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)

TEAM = TeamSelector(caselist=CASELIST, school="Alder Point", team_code="KR")
SECOND_TEAM_PATH = "Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2 (1).docx"
ANOTHER_HOLDERS_PATH = "Tamarack/TS/Tamarack-TS-Aff-Lakeshore Open-Round 4.docx"
"""Another team's path of the named shared file, where a later upload of it is withdrawn from."""
HELD_PATH = disclosure_digest(CASELIST, TEAM_PATH)

PLAN_KEYS_BEFORE_THIS_TASK = frozenset(
    {
        "environment",
        "bucket",
        "applied",
        "request_id",
        "reason",
        "selector",
        "include_shared",
        "only_named",
        "versions_counted",
        "sources",
        "later_uploads",
        "later_uploads_added",
        "earlier_versions",
        "manifests",
        "objects",
        "suppression_entries",
        "path_holds",
        "inbox_directory",
        "inbox_exists",
        "inbox",
        "inbox_team_files_left",
        "counts",
    }
)
"""The plan's top-level keys at the start of this task, read from `plan_summary` there by hand."""

EXECUTION_KEYS = frozenset({"outcome", "log_entry", "preflight_probes_left"})


def suppressed(sha256: str, path: str | None = None) -> SuppressionEntry:
    """A suppression entry: of the whole file, or of its copy at one `CASELIST` path."""
    return suppressed_by_digest(sha256, None if path is None else disclosure_digest(CASELIST, path))


def suppressed_by_digest(sha256: str, disclosure: str | None) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        disclosure=disclosure,
        recorded_at=RECORDED_AT,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-05",
    )


def removed_whole(sha256: str = NAMED) -> PlannedSource:
    return dataclasses.replace(
        source(sha256, Inclusion.NAMED, Disposition.REMOVE), suppression=(suppressed(sha256),)
    )


def withdrawn_from(sha256: str, inclusion: Inclusion, *paths: str) -> PlannedSource:
    """Withdrawn from each of `paths` in `CASELIST`, with the entry the plan appends for each."""
    return dataclasses.replace(
        source(
            sha256,
            inclusion,
            Disposition.WITHDRAW,
            requester_paths=tuple((CASELIST, path) for path in paths),
        ),
        suppression=tuple(suppressed(sha256, path) for path in paths),
    )


def refused_at_the_held_path() -> PlannedSource:
    """An upload an import refused at the held path, withdrawn from it by its digest (`v1-e30-t23`)."""
    return dataclasses.replace(
        source(REFUSED, Inclusion.HELD_AT_IMPORT, Disposition.WITHDRAW),
        byte_size=None,
        source_format=None,
        held_at_import=((CASELIST, HELD_PATH),),
        suppression=(suppressed_by_digest(REFUSED, HELD_PATH),),
    )


def later_at(path: str) -> PathVersion:
    return PathVersion(
        sha256=LATER,
        relation=VersionRelation.LATER,
        of_sha256=NAMED,
        caselist=CASELIST,
        path=path,
        snapshots=("2026-09-15",),
        openev_ids=(),
        evidence=SamePathEvidence.CASELIST_PATH,
        identity=(CASELIST, path),
    )


def executed(plan: RemovalPlan) -> RemovalReport:
    """A run of `plan` that completed; the counts are what it says it did, which these tests leave alone."""
    return RemovalReport(
        plan=plan,
        log_entry=RemovalLogEntry(
            kind=RemovalLogKind.REMOVAL,
            recorded_at=datetime(2026, 9, 30, 18, 5, tzinfo=UTC),
            request_id="RM-2026-05",
            reason=ReasonCode.REQUESTED_BY_TEAM,
            environment="dev",
            outcome=RemovalOutcome.COMPLETED,
        ),
        local_records_deleted=0,
        local_files_deleted=0,
        manifests_rewritten=0,
        manifest_rows_dropped=0,
        s3_versions_deleted=0,
    )


def confirmation(text: str) -> list[str]:
    return section(text, "FOR THE CONFIRMATION TO THE REQUESTER").splitlines()


# ------------------------------------------------------------------------------------------------
# (1) The JSON's withdrawals
# ------------------------------------------------------------------------------------------------


def a_team_removal_that_withdraws() -> RemovalPlan:
    """A file removed whole, a shared one withdrawn from the team's two paths, and a refused upload."""
    return plan_of(
        (
            removed_whole(),
            withdrawn_from(SHARED, Inclusion.NAMED, TEAM_PATH, SECOND_TEAM_PATH),
            refused_at_the_held_path(),
        ),
        selector=TEAM,
    )


def test_the_json_has_one_withdrawal_for_each_the_plan_makes_by_digest_and_caselist() -> None:
    data = json.loads(json.dumps(plan_summary(a_team_removal_that_withdraws(), SETTINGS, None)))

    assert data.get("withdrawals") == [
        {"sha256": SHARED, "disclosure": disclosure_digest(CASELIST, TEAM_PATH), "caselist": CASELIST},
        {"sha256": SHARED, "disclosure": disclosure_digest(CASELIST, SECOND_TEAM_PATH), "caselist": CASELIST},
        {"sha256": REFUSED, "disclosure": HELD_PATH, "caselist": CASELIST},
    ]
    new_lines_name_no_one(json.dumps(data["withdrawals"]))


def test_the_jsons_withdrawals_are_the_lines_the_plan_prints_under_withdrawals() -> None:
    plan = a_team_removal_that_withdraws()

    printed = section(render_plan(plan, None), "WITHDRAWALS").splitlines()[4:]
    data = plan_summary(plan, SETTINGS, None)

    as_printed = [json.loads(line) for line in printed]
    assert [
        {key: line[key] for key in ("sha256", "disclosure", "caselist")} for line in as_printed
    ] == data.get("withdrawals")


def test_a_plan_that_withdraws_nothing_has_an_empty_list() -> None:
    data = plan_summary(plan_of((removed_whole(),)), SETTINGS, None)

    assert data.get("withdrawals") == []


def test_the_plans_keys_are_t11s_and_the_two_this_task_adds() -> None:
    plan = a_team_removal_that_withdraws()

    assert set(plan_summary(plan, SETTINGS, None)) == PLAN_KEYS_BEFORE_THIS_TASK | {
        "withdrawals",
        "manifest_versions_swept",
    }
    assert set(plan_summary(plan, SETTINGS, executed(plan))) == (
        PLAN_KEYS_BEFORE_THIS_TASK | EXECUTION_KEYS | {"withdrawals", "manifest_versions_swept"}
    )


# ------------------------------------------------------------------------------------------------
# (2) A later upload at another holder's path, under --team --include-shared
# ------------------------------------------------------------------------------------------------


def a_team_removal_including_shared_files(*, also_at_the_teams_path: bool = False) -> RemovalPlan:
    """The shared file removed whole, and its later upload withdrawn from another team's path.

    With `also_at_the_teams_path`, a second shared file of the team's is withdrawn from the team's
    own path as well, so the plan withdraws from both kinds of path.
    """
    sources = [
        removed_whole(),
        dataclasses.replace(
            withdrawn_from(LATER, Inclusion.LATER_UPLOAD, ANOTHER_HOLDERS_PATH), other_teams=1
        ),
    ]
    if also_at_the_teams_path:
        sources.append(withdrawn_from(SHARED, Inclusion.NAMED, TEAM_PATH))
    return dataclasses.replace(
        plan_of(tuple(sources), selector=TEAM, later_uploads=(later_at(ANOTHER_HOLDERS_PATH),)),
        include_shared=True,
    )


def test_the_count_does_not_call_another_holders_path_this_teams() -> None:
    lines = render_plan(a_team_removal_including_shared_files(), None).splitlines()

    assert (
        "  1 whole file(s), and 1 path(s) of another holder a later upload is withdrawn from. Each" in lines
    )
    assert not [line for line in lines if "this team's path" in line]


def test_the_list_line_does_not_call_another_holders_copy_this_teams() -> None:
    lines = render_plan(a_team_removal_including_shared_files(), None).splitlines()

    assert (
        "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or "
        "another holder's copy of a later upload at the path it was withdrawn from."
    ) in lines
    assert not [line for line in lines if "this team's copy" in line]


def test_a_plan_withdrawing_from_both_kinds_of_path_names_each() -> None:
    text = render_plan(a_team_removal_including_shared_files(also_at_the_teams_path=True), None)
    lines = text.splitlines()

    assert (
        "  1 whole file(s), 1 of this team's path(s) to a shared file, and 1 path(s) of another holder a "
        "later upload is withdrawn from. Each"
    ) in lines
    assert (
        "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or this "
        "team's copy of a shared file at the path it was taken from, or another holder's copy of a later "
        "upload at the path it was withdrawn from."
    ) in lines
    plan = a_team_removal_including_shared_files(also_at_the_teams_path=True)
    assert render_plan(plan, executed(plan)).count("another holder's copy of a later upload") == 1


def test_a_team_removal_withdrawing_only_from_its_own_paths_reads_as_before() -> None:
    lines = render_plan(a_team_removal_that_withdraws(), None).splitlines()

    assert "  1 whole file(s), and 3 of this team's path(s) to a shared file. Each" in lines
    assert (
        "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or this "
        "team's copy of a shared file at the path it was taken from."
    ) in lines


def test_a_withdrawal_an_earlier_run_left_no_path_of_is_still_called_this_teams() -> None:
    """A `--team` re-run plans a file an earlier run withdrew again, with no path left to show:
    the team's own, as the line has always said, and nothing of another holder's."""
    earlier = dataclasses.replace(
        source(SHARED, Inclusion.UNFINISHED, Disposition.WITHDRAW), withdrawn_earlier_from=(CASELIST,)
    )

    lines = render_plan(plan_of((earlier,), selector=TEAM), None).splitlines()

    assert (
        "  - Suppressed, so no later archive, weekly or complete, can bring back this team's copy of a "
        "shared file at the path it was taken from."
    ) in lines


# ------------------------------------------------------------------------------------------------
# (3) A re-run that removes nothing
# ------------------------------------------------------------------------------------------------


def a_rerun_with_nothing_left() -> RemovalPlan:
    """The named file and its later upload planned again, both already gone and suppressed."""
    gone = {"local_blob": False, "delete_source_record": False, "already_suppressed": True}
    return plan_of(
        (
            dataclasses.replace(source(NAMED, Inclusion.NAMED, Disposition.REMOVE), **gone),
            dataclasses.replace(source(LATER, Inclusion.LATER_UPLOAD, Disposition.REMOVE), **gone),
        ),
        later_uploads=(later_at(TEAM_PATH),),
    )


def test_the_dry_run_of_a_rerun_that_removes_nothing_says_so_and_counts_nothing_removed() -> None:
    plan = a_rerun_with_nothing_left()
    assert plan.nothing_to_do

    told = confirmation(render_plan(plan, None))

    assert "  - Removed from this environment: nothing; this run found nothing left to remove." in told
    assert not [line for line in told if "file(s)" in line and "removed" in line.casefold()], told


def test_the_execution_of_a_rerun_that_removes_nothing_says_so_too() -> None:
    plan = a_rerun_with_nothing_left()

    told = confirmation(render_plan(plan, executed(plan)))

    assert "  - Removed from this environment: nothing; this run found nothing left to remove." in told
    assert not [line for line in told if "file(s)" in line and "removed" in line.casefold()], told


def test_a_run_that_removes_something_still_counts_what_it_removes() -> None:
    plan = plan_of((removed_whole(),))

    told = confirmation(render_plan(plan, None))

    assert "  - Removed from this environment: 1 file(s)." in told


# ------------------------------------------------------------------------------------------------
# (6) The JSON's sweep count
# ------------------------------------------------------------------------------------------------

MANIFEST = f"manifests/{CASELIST}/2026-09-15.jsonl"
OTHER_MANIFEST = f"manifests/{CASELIST}/2026-09-01.jsonl"


def noncurrent(key: str, version_id: str) -> ObjectVersion:
    return ObjectVersion(key=key, version_id=version_id, is_latest=False)


def sweeping(versions: tuple[ObjectVersion, ...] | None) -> RemovalPlan:
    return dataclasses.replace(plan_of((removed_whole(),)), superseded_versions=versions)


def test_the_json_counts_the_sweep_in_all_and_by_manifest_as_the_plan_line_does() -> None:
    plan = sweeping(
        (noncurrent(MANIFEST, "v1"), noncurrent(MANIFEST, "v2"), noncurrent(OTHER_MANIFEST, "v3"))
    )

    data = json.loads(json.dumps(plan_summary(plan, SETTINGS, None)))
    shown = section(render_plan(plan, None), "MANIFEST VERSIONS SWEPT").splitlines()

    assert data.get("manifest_versions_swept") == {
        "total": 3,
        "by_manifest": {MANIFEST: 2, OTHER_MANIFEST: 1},
    }
    assert shown[0] == (
        "MANIFEST VERSIONS SWEPT from the bucket by --execute: 3 noncurrent version(s) of 2 manifest(s)."
    )
    printed = Counter(
        {
            line.split()[1]: int(line.split("(")[1].split()[0])
            for line in shown
            if line.startswith("  bucket ")
        }
    )
    assert printed == Counter(data["manifest_versions_swept"]["by_manifest"])
    assert sum(printed.values()) == data["manifest_versions_swept"]["total"]


def test_a_plan_with_nothing_to_sweep_counts_none() -> None:
    data = plan_summary(sweeping(()), SETTINGS, None)

    assert data.get("manifest_versions_swept") == {"total": 0, "by_manifest": {}}


def test_a_plan_that_could_not_list_says_not_counted_and_never_zero() -> None:
    plan = sweeping(None)

    data = plan_summary(plan, SETTINGS, None)

    assert data.get("manifest_versions_swept") == "not counted"
    assert "MANIFEST VERSIONS SWEPT from the bucket by --execute: not counted." in render_plan(plan, None)


def test_the_sweep_count_names_no_one() -> None:
    """A manifest key names a caselist and a date, and nothing of a team or a file."""
    plan = sweeping((noncurrent(MANIFEST, "v1"),))

    new_lines_name_no_one(json.dumps(plan_summary(plan, SETTINGS, None).get("manifest_versions_swept")))
