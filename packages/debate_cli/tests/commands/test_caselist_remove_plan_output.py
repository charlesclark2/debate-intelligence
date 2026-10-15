"""How `caselist remove` shows a plan with later uploads: as text for a person, as JSON for a program.

Each plan here is built by hand, field by field, so the test says exactly what the command was given
and what it must print (`v1-e30-t11`). Nothing is planned or executed: `render_plan` and
`plan_summary` are functions of the plan. The command run end to end is
`tests/smoke/test_caselist_remove_smoke.py`.

The one rule this module is for: the JSON carries no school, team code, path, camp, title or file
name. The text may, as it always has, but the lines this task adds do not.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

from debate_cli.commands.caselist_remove import plan_summary, render_plan
from debate_core.application.caselist.inbox_purge import (
    InboxAction,
    InboxFileKind,
    InboxFilePlan,
    InboxReason,
)
from debate_core.application.caselist.removal_path_versions import (
    PathVersion,
    SamePathEvidence,
    VersionRelation,
)
from debate_core.application.caselist.removal_plan import (
    CampFileRef,
    DisclosureRef,
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
)
from debate_core.application.settings import Environment
from debate_core.domain.caselist import Event

NAMED = "a" * 64
LATER = "b" * 64
LATER_CAMP = "c" * 64
EARLIER = "d" * 64

CASELIST = "testcl26"
TEAM_PATH = "Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2.docx"
CAMP_ROW = "openev-640-TSF-Estuary_Solvency_Advocate.docx"
INBOX_NAME = "openev-512-TSF-Estuary_Solvency_Advocate.docx"

#: Every word of the paths, the school, the team code, the tournament, the camp and the title above.
IDENTIFYING = (
    "Alder Point",
    "KR",
    "Lakeshore",
    "Round 2",
    ".docx",
    "Tamarack",
    "TSF",
    "Estuary",
    "Solvency",
    "Advocate",
)

SETTINGS: Any = SimpleNamespace(
    environment=Environment.DEV, storage=SimpleNamespace(s3=SimpleNamespace(bucket="debate-test-evidence"))
)


def source(
    sha256: str,
    inclusion: Inclusion,
    disposition: Disposition,
    *,
    disclosures: tuple[DisclosureRef, ...] = (),
    camp_files: tuple[CampFileRef, ...] = (),
    requester_paths: tuple[tuple[str, str], ...] = (),
) -> PlannedSource:
    return PlannedSource(
        sha256=sha256,
        disposition=disposition,
        byte_size=900,
        source_format="DOCX",
        disclosures=disclosures,
        camp_files=camp_files,
        requester_paths=requester_paths,
        other_teams=1 if disposition is not Disposition.REMOVE else 0,
        camp_file_holders=0,
        kept_in=(CASELIST,) if disposition is Disposition.WITHDRAW else (),
        delete_source_record=disposition is Disposition.REMOVE,
        local_blob=disposition is Disposition.REMOVE,
        suppression=(),
        inclusion=inclusion,
    )


def disclosure(snapshot: date) -> DisclosureRef:
    return DisclosureRef(
        caselist=CASELIST,
        snapshot=snapshot,
        source_path=TEAM_PATH,
        school="Alder Point",
        team_code="KR",
        tournament="Lakeshore Open",
        round_label="Round 2",
    )


def later_at_the_team_path(sha256: str = LATER, snapshots: tuple[str, ...] = ("2026-09-15",)) -> PathVersion:
    return PathVersion(
        sha256=sha256,
        relation=VersionRelation.LATER,
        of_sha256=NAMED,
        caselist=CASELIST,
        path=TEAM_PATH,
        snapshots=snapshots,
        openev_ids=(),
        evidence=SamePathEvidence.CASELIST_PATH,
        identity=(CASELIST, TEAM_PATH),
    )


def later_at_the_camp_path(evidence: SamePathEvidence) -> PathVersion:
    return PathVersion(
        sha256=LATER_CAMP,
        relation=VersionRelation.LATER,
        of_sha256=NAMED,
        caselist="openev",
        path=CAMP_ROW,
        snapshots=("2026-policy",),
        openev_ids=(640,),
        evidence=evidence,
        identity=("openev", "2026-policy", "tsf_estuary_solvency_advocate_docx"),
    )


def plan_of(
    sources: tuple[PlannedSource, ...],
    *,
    selector: RemovalSelector | None = None,
    later_uploads: tuple[PathVersion, ...] = (),
    earlier_versions: tuple[PathVersion, ...] = (),
    only_named: bool = False,
    inbox: tuple[InboxFilePlan, ...] = (),
) -> RemovalPlan:
    return RemovalPlan(
        selector=selector or SourceSelector(NAMED),
        request_id="RM-2026-05",
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=False,
        environment="dev",
        bucket="debate-test-evidence",
        recorded_at=datetime(2026, 9, 30, 18, 0, tzinfo=UTC),
        sources=sources,
        manifests=(),
        objects=(),
        versions_counted=True,
        inbox=inbox,
        inbox_directory="/data/inbox",
        inbox_exists=True,
        only_named=only_named,
        later_uploads=later_uploads,
        earlier_versions=earlier_versions,
    )


def the_full_plan(selector: RemovalSelector | None = None) -> RemovalPlan:
    """A named file with a disclosure and a camp-file record, three later uploads and an earlier version.

    One later upload is removed, one is withdrawn from the team's path, and the camp one is kept
    because another holder has it. The inbox holds the named camp file's download.
    """
    return plan_of(
        (
            source(
                NAMED,
                Inclusion.NAMED,
                Disposition.REMOVE,
                disclosures=(disclosure(date(2026, 9, 8)),),
                camp_files=(
                    CampFileRef(
                        year=2026, event=Event.POLICY, camp="Tamarack", file_title="Estuary Solvency Advocate"
                    ),
                ),
            ),
            source(
                LATER,
                Inclusion.LATER_UPLOAD,
                Disposition.WITHDRAW,
                disclosures=(disclosure(date(2026, 9, 15)),),
                requester_paths=((CASELIST, TEAM_PATH),),
            ),
            source(LATER_CAMP, Inclusion.LATER_UPLOAD, Disposition.SKIP_SHARED),
        ),
        selector=selector,
        later_uploads=(later_at_the_team_path(), later_at_the_camp_path(SamePathEvidence.ROW_NAME)),
        earlier_versions=(
            PathVersion(
                sha256=EARLIER,
                relation=VersionRelation.EARLIER,
                of_sha256=NAMED,
                caselist=CASELIST,
                path=TEAM_PATH,
                snapshots=("2026-09-01", "full/2026-09-05"),
                openev_ids=(),
                evidence=SamePathEvidence.CASELIST_PATH,
                identity=(CASELIST, TEAM_PATH),
            ),
        ),
        inbox=(
            InboxFilePlan(
                name=INBOX_NAME,
                kind=InboxFileKind.OPENEV,
                sha256=NAMED,
                action=InboxAction.DELETE,
                reason=InboxReason.THE_FILE_IS_REMOVED,
                removed_sha256=(NAMED,),
                openev_id=512,
            ),
        ),
    )


# ------------------------------------------------------------------------------------------------
# JSON
# ------------------------------------------------------------------------------------------------


def test_the_json_names_no_school_team_code_path_camp_title_or_file() -> None:
    for selector in (None, TeamSelector(caselist=CASELIST, school="Alder Point", team_code="KR")):
        emitted = json.dumps(plan_summary(the_full_plan(selector), SETTINGS, None))

        assert not [word for word in IDENTIFYING if word in emitted], selector


def test_the_json_lists_later_uploads_by_digest_caselist_and_snapshot_with_what_happens() -> None:
    data = plan_summary(the_full_plan(), SETTINGS, None)

    assert data["later_uploads"] == [
        {
            "sha256": LATER,
            "sha256_prefix": "bbbbbbbbbbbb",
            "relation": "later",
            "of_sha256": NAMED,
            "caselist": CASELIST,
            "snapshots": ["2026-09-15"],
            "inbox_snapshots": [],
            "openev_ids": [],
            "same_path_by": "caselist_path",
            "outcome": "withdrawn_from_the_path",
        },
        {
            "sha256": LATER_CAMP,
            "sha256_prefix": "cccccccccccc",
            "relation": "later",
            "of_sha256": NAMED,
            "caselist": "openev",
            "snapshots": ["2026-policy"],
            "inbox_snapshots": [],
            "openev_ids": [640],
            "same_path_by": "row_name",
            "outcome": "kept_shared",
        },
    ]
    assert data["earlier_versions"] == [
        {
            "sha256": EARLIER,
            "sha256_prefix": "dddddddddddd",
            "relation": "earlier",
            "of_sha256": NAMED,
            "caselist": CASELIST,
            "snapshots": ["2026-09-01", "full/2026-09-05"],
            "inbox_snapshots": [],
            "openev_ids": [],
            "same_path_by": "caselist_path",
        }
    ]
    assert (data["only_named"], data["later_uploads_added"]) == (False, 1)


def test_the_json_gives_a_disclosure_as_the_digest_the_suppression_list_uses() -> None:
    data: Any = plan_summary(
        the_full_plan(TeamSelector(caselist=CASELIST, school="Alder Point", team_code="KR")), SETTINGS, None
    )
    digest_of_the_disclosure = hashlib.sha256(f"{CASELIST}/{TEAM_PATH}".encode()).hexdigest()

    named, later, _ = data["sources"]
    assert named["inclusion"] == "named" and later["inclusion"] == "later_upload"
    assert named["disclosures"] == [
        {"caselist": CASELIST, "snapshot": "2026-09-08", "disclosure": digest_of_the_disclosure}
    ]
    assert named["camp_files"] == [{"year": 2026, "event": "POLICY"}]
    assert later["withdrawn_disclosures"] == [{"caselist": CASELIST, "disclosure": digest_of_the_disclosure}]
    assert data["selector"] == {"kind": "TEAM", "caselist": CASELIST}
    assert [one["name"] for one in data["inbox"]] == ["openev-512"]
    assert plan_summary(the_full_plan(), SETTINGS, None)["selector"] == {"kind": "SOURCE", "sha256": NAMED}


# ------------------------------------------------------------------------------------------------
# Text
# ------------------------------------------------------------------------------------------------


def test_the_text_gives_each_later_upload_its_caselist_snapshots_and_outcome() -> None:
    shown = render_plan(the_full_plan(), None)

    assert "LATER UPLOADS AT A REMOVED PATH, ADDED TO THIS PLAN: 2 file(s)" in shown
    assert (
        "     later upload of sha256 aaaaaaaaaaaa in testcl26, held in 2026-09-15: withdrawn from this path "
        "only: another path still holds it, so its bytes stay"
    ) in shown
    assert (
        "     later upload of sha256 aaaaaaaaaaaa in openev 2026-policy as openev-640 (matched by file name "
        "alone: no row and no delivery record here knows both ids' upstream path, so check it): KEPT: "
        "another holder has it too, and this plan takes it from none of its paths"
    ) in shown
    assert "EARLIER VERSIONS AT A REMOVED PATH, NOT REMOVED: 1 file(s)" in shown
    assert (
        "     at the path of sha256 aaaaaaaaaaaa in testcl26, held in 2026-09-01, full/2026-09-05: earlier"
    ) in shown


def test_the_lines_about_later_uploads_and_earlier_versions_show_no_path() -> None:
    """The record lines under a file show its path, as they do for a named file. These lines do not."""
    shown = render_plan(the_full_plan(), None).splitlines()

    added = [line for line in shown if "later upload of" in line or "at the path of" in line]
    assert len(added) == 3
    assert not [word for line in added for word in IDENTIFYING if word in line]


def test_a_camp_match_by_upstream_path_says_so() -> None:
    """The rows or the delivery record put both ids at one upstream path (`v1-e30-t14`)."""
    plan = plan_of(
        (
            source(NAMED, Inclusion.NAMED, Disposition.REMOVE),
            source(LATER_CAMP, Inclusion.LATER_UPLOAD, Disposition.REMOVE),
        ),
        later_uploads=(later_at_the_camp_path(SamePathEvidence.UPSTREAM_PATH_DIGEST),),
    )

    assert (
        "     later upload of sha256 aaaaaaaaaaaa in openev 2026-policy as openev-640 (matched by upstream "
        "path: both ids were uploaded at one upstream path): removed everywhere"
    ) in render_plan(plan, None)


def test_the_confirmation_says_how_many_later_uploads_the_plan_adds() -> None:
    """Above the command the operator runs: two found, one added, one shared and kept."""
    shown = render_plan(the_full_plan(), None)
    confirm = shown[shown.index("TO CARRY IT OUT") :].splitlines()

    assert confirm[1] == (
        "  This plan covers the 1 file(s) named, and adds 1 later upload(s) at the removed path(s) "
        "(1 more is shared and kept)."
    )
    assert "--only-named" in confirm[2]
    assert confirm[3].endswith("--request RM-2026-05 --reason REQUESTED_BY_TEAM --execute")


def test_with_only_named_the_confirmation_and_the_command_say_so() -> None:
    plan = plan_of(
        (source(NAMED, Inclusion.NAMED, Disposition.REMOVE),),
        later_uploads=(later_at_the_team_path(), later_at_the_team_path("e" * 64, ("2026-09-22",))),
        only_named=True,
    )
    shown = render_plan(plan, None)
    confirm = shown[shown.index("TO CARRY IT OUT") :].splitlines()

    assert "LATER UPLOADS AT A REMOVED PATH, LEFT IN PLACE (--only-named): 2 file(s)" in shown
    assert shown.count(": left in place (--only-named)") == 2
    assert confirm[1] == (
        "  This plan covers the 1 file(s) named only; 2 later upload(s) at the removed path(s) are left in "
        "place (--only-named)."
    )
    assert confirm[3].endswith("--reason REQUESTED_BY_TEAM --only-named --execute")
    data = plan_summary(plan, SETTINGS, None)
    assert (data["only_named"], data["later_uploads_added"]) == (True, 0)


def test_a_plan_with_no_later_upload_says_it_adds_none() -> None:
    shown = render_plan(plan_of((source(NAMED, Inclusion.NAMED, Disposition.REMOVE),)), None)

    assert "LATER UPLOADS AT A REMOVED PATH" not in shown and "EARLIER VERSIONS" not in shown
    assert (
        "  This plan covers the 1 file(s) named, and adds 0 later upload(s) at the removed path(s)." in shown
    )
    assert "--only-named" not in shown


def test_the_done_line_says_what_the_run_covered() -> None:
    plan = the_full_plan()
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
        local_records_deleted=3,
        local_files_deleted=1,
        manifests_rewritten=2,
        manifest_rows_dropped=2,
        s3_versions_deleted=1,
    )

    done = render_plan(plan, report).splitlines()

    assert done[0].startswith("DONE in dev (debate-test-evidence): 3 record(s), 1 local file(s)")
    assert done[1] == (
        "It covered the 1 file(s) named and 1 later upload(s) at the removed path(s) "
        "(1 more is shared and kept)."
    )
    assert "TO CARRY IT OUT" not in done
