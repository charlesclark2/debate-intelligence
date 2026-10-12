"""How the commands show a removed path's hold: `caselist remove`, `import` and `unsuppress`.

Each plan and report here is built by hand, field by field, so the test says exactly what the
command was given and what it must print (`v1-e30-t13`). Nothing is planned, imported or executed:
the renderers are functions of what they are given. The commands run end to end in
`tests/smoke/test_caselist_remove_smoke.py`.

The rule every line this task adds keeps: no school, team code, path or file name. A path is the
digest the path entry stores for it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from debate_cli.commands.caselist import (
    _summary_table as import_table,  # pyright: ignore[reportPrivateUsage]
)
from debate_cli.commands.caselist import import_summary
from debate_cli.commands.caselist_remove import (
    plan_summary,
    render_plan,
    render_unsuppress,
    unsuppress_summary,
)
from debate_core.application.caselist.import_service import Classification, ImportReport
from debate_core.application.caselist.removal_path_versions import (
    PathVersion,
    SamePathEvidence,
    VersionRelation,
)
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    RemovalPlan,
    TeamSelector,
)
from debate_core.application.caselist.removal_service import UnsuppressPlan
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionState,
)
from debate_core.domain.caselist import Event

from .test_caselist_remove_plan_output import (
    CASELIST,
    IDENTIFYING,
    LATER,
    NAMED,
    SETTINGS,
    TEAM_PATH,
    disclosure,
    later_at_the_team_path,
    plan_of,
    source,
)

REMOVED_AT = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
WAITING = "e" * 64

THE_PATH_ENTRY = PathHoldEntry(
    caselist=CASELIST,
    disclosure=hashlib.sha256(f"{CASELIST}/{TEAM_PATH}".encode()).hexdigest(),
    sha256=NAMED,
    after_snapshot=date(2026, 9, 8),
    recorded_at=REMOVED_AT,
    reason=ReasonCode.REQUESTED_BY_TEAM,
    request_id="RM-2026-05",
)

THE_PATH_ENTRY_AS_WRITTEN = (
    '{"after_snapshot":"2026-09-08","caselist":"testcl26",'
    f'"disclosure":"{hashlib.sha256(f"{CASELIST}/{TEAM_PATH}".encode()).hexdigest()}",'
    '"reason":"REQUESTED_BY_TEAM","recorded_at":"2026-09-30T18:00:00Z","request_id":"RM-2026-05",'
    f'"schema_version":1,"sha256":"{NAMED}"' + "}"
)


def a_removal_that_holds_one_path(**changes: object) -> RemovalPlan:
    """One file named by `--source`, removed whole, and the path entry for the path it is taken from."""
    plan = plan_of(
        (source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),)
    )
    held = SuppressionState.from_entries([], [THE_PATH_ENTRY])
    return dataclasses.replace(plan, path_holds=(THE_PATH_ENTRY,), suppression_after=held, **changes)  # pyright: ignore[reportArgumentType]


def section(text: str, heading: str) -> str:
    """The lines of one section of the plan: from its heading to the next blank line."""
    start = text.index(heading)
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def new_lines_name_no_one(lines: str) -> None:
    assert not [word for word in IDENTIFYING if word in lines], lines


# ------------------------------------------------------------------------------------------------
# caselist remove: the path entries
# ------------------------------------------------------------------------------------------------


def test_the_plan_prints_each_path_entry_exactly_as_it_is_appended() -> None:
    shown = section(render_plan(a_removal_that_holds_one_path(), None), "PATH ENTRIES")

    assert shown.splitlines()[0] == "PATH ENTRIES appended beside the list, here and in the bucket: 1"
    assert shown.splitlines()[-1] == f"  {THE_PATH_ENTRY_AS_WRITTEN}"
    assert "an import refuses a" in shown and "new upload at that path" in shown
    assert "`caselist unsuppress` of the removed file releases its paths" in shown
    new_lines_name_no_one(shown)


def test_the_json_carries_the_path_entries_as_written_and_names_no_one() -> None:
    data = plan_summary(a_removal_that_holds_one_path(), SETTINGS, None)

    assert data["path_holds"] == [THE_PATH_ENTRY_AS_WRITTEN]
    new_lines_name_no_one(json.dumps(data))


def test_the_confirmation_to_the_requester_says_the_path_is_held() -> None:
    shown = render_plan(a_removal_that_holds_one_path(), None)

    confirmation = shown[shown.index("FOR THE CONFIRMATION TO THE REQUESTER") :]
    assert (
        "  - Held: 1 path(s) the file was removed from, so a new upload there is refused when it is imported."
    ) in confirmation


def test_only_named_says_no_path_is_held_and_why() -> None:
    plan = dataclasses.replace(
        a_removal_that_holds_one_path(only_named=True), path_holds=(), suppression_after=SuppressionState()
    )

    shown = render_plan(plan, None)

    assert section(shown, "PATH ENTRIES").splitlines() == [
        "PATH ENTRIES appended beside the list, here and in the bucket: 0",
        "  (none: --only-named is a request about one version, so later uploads at the path are not held)",
    ]
    assert (
        "  - Not held: the request was about one version, so a later upload at the same path is imported."
    ) in shown
    assert plan_summary(plan, SETTINGS, None)["path_holds"] == []


def test_a_team_removal_says_it_holds_no_path_and_what_to_do_instead() -> None:
    plan = plan_of(
        (source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),),
        selector=TeamSelector(caselist=CASELIST, school="Alder Point", team_code="KR"),
    )

    shown = section(render_plan(plan, None), "PATH ENTRIES")

    assert shown.splitlines() == [
        "PATH ENTRIES appended beside the list, here and in the bucket: 0",
        "  (none: a --team removal holds no path; run this command again after a pull to cover what the team "
        "uploads later)",
    ]
    new_lines_name_no_one(shown)


def test_a_file_that_is_skipped_or_already_held_says_which() -> None:
    skipped = plan_of((source(NAMED, Inclusion.NAMED, Disposition.SKIP_SHARED),))
    again = dataclasses.replace(
        a_removal_that_holds_one_path(),
        path_holds=(),
        suppression_after=a_removal_that_holds_one_path().suppression_after,
    )

    assert section(render_plan(skipped, None), "PATH ENTRIES").splitlines()[1] == (
        "  (none: no file the request names is removed whole, so no path is held)"
    )
    assert section(render_plan(again, None), "PATH ENTRIES").splitlines()[1] == (
        "  (none: every caselist path of the removed file(s) is already held, or it has none)"
    )
    assert "  - Held: 1 path(s) the file was removed from" in render_plan(again, None)


# ------------------------------------------------------------------------------------------------
# caselist remove: a later upload in the download inbox
# ------------------------------------------------------------------------------------------------


def waiting_in_the_inbox() -> PathVersion:
    return PathVersion(
        sha256=WAITING,
        relation=VersionRelation.LATER,
        of_sha256=NAMED,
        caselist=CASELIST,
        path=TEAM_PATH,
        snapshots=(),
        openev_ids=(),
        evidence=SamePathEvidence.CASELIST_PATH,
        identity=(CASELIST, TEAM_PATH),
        inbox_snapshots=("2026-10-08",),
    )


def a_plan_with_an_upload_waiting_in_the_inbox() -> RemovalPlan:
    waiting = dataclasses.replace(
        source(WAITING, Inclusion.LATER_UPLOAD, Disposition.REMOVE),
        byte_size=None,
        source_format=None,
        delete_source_record=False,
        local_blob=False,
    )
    stored_and_waiting = dataclasses.replace(later_at_the_team_path(), inbox_snapshots=("2026-10-13",))
    return plan_of(
        (
            source(NAMED, Inclusion.NAMED, Disposition.REMOVE, disclosures=(disclosure(date(2026, 9, 8)),)),
            source(
                LATER,
                Inclusion.LATER_UPLOAD,
                Disposition.WITHDRAW,
                disclosures=(disclosure(date(2026, 9, 15)),),
                requester_paths=((CASELIST, TEAM_PATH),),
            ),
            waiting,
        ),
        later_uploads=(stored_and_waiting, waiting_in_the_inbox()),
    )


def test_a_later_upload_only_the_inbox_holds_is_listed_as_in_the_inbox_and_not_in_the_store() -> None:
    shown = section(render_plan(a_plan_with_an_upload_waiting_in_the_inbox(), None), "LATER UPLOADS")

    assert "LATER UPLOADS AT A REMOVED PATH, ADDED TO THIS PLAN: 2 file(s)" in shown
    assert (
        f"     later upload of sha256 {NAMED[:12]} in testcl26, in the download inbox in 2026-10-08, not in "
        "the store: removed everywhere"
    ) in shown
    assert f"  2. {WAITING}  (not on this machine)" in shown
    assert (
        "     not in the store: it is suppressed, and taken out of the inbox archive that holds it" in shown
    )
    assert "held nowhere in this environment" not in shown
    assert "  One marked as in the download inbox is in an archive `caselist pull` downloaded" in shown
    new_lines_name_no_one("\n".join(line for line in shown.splitlines() if "download inbox" in line))


def test_one_the_store_and_the_inbox_both_hold_says_both() -> None:
    shown = section(render_plan(a_plan_with_an_upload_waiting_in_the_inbox(), None), "LATER UPLOADS")

    assert (
        f"     later upload of sha256 {NAMED[:12]} in testcl26, held in 2026-09-15; also in the download "
        "inbox in 2026-10-13: withdrawn from this path only"
    ) in shown


def test_the_json_gives_the_inbox_snapshots_of_each_later_upload() -> None:
    data = plan_summary(a_plan_with_an_upload_waiting_in_the_inbox(), SETTINGS, None)

    assert [
        (one["sha256"], one["snapshots"], one["inbox_snapshots"], one["outcome"])  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue]
        for one in data["later_uploads"]  # pyright: ignore[reportGeneralTypeIssues, reportOptionalIterable]
    ] == [
        (LATER, ["2026-09-15"], ["2026-10-13"], "withdrawn_from_the_path"),
        (WAITING, [], ["2026-10-08"], "removed"),
    ]
    assert data["later_uploads_added"] == 2
    new_lines_name_no_one(json.dumps(data))


def test_a_plan_with_nothing_in_the_inbox_says_nothing_about_it() -> None:
    plan = plan_of(
        (
            source(NAMED, Inclusion.NAMED, Disposition.REMOVE),
            source(LATER, Inclusion.LATER_UPLOAD, Disposition.REMOVE),
        ),
        later_uploads=(later_at_the_team_path(),),
    )

    shown = render_plan(plan, None)

    assert "download inbox is in an archive" not in shown
    assert "in testcl26, held in 2026-09-15: removed everywhere" in shown


# ------------------------------------------------------------------------------------------------
# caselist unsuppress
# ------------------------------------------------------------------------------------------------


def an_unsuppress(path_holds_released: int) -> UnsuppressPlan:
    suppressed = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=NAMED,
        recorded_at=REMOVED_AT,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-05",
    )
    return UnsuppressPlan(
        sha256=NAMED,
        reason=ReasonCode.REMOVED_IN_ERROR,
        request_id="RM-2026-05",
        environment="dev",
        entry=SuppressionEntry(
            action=SuppressionAction.UNSUPPRESS,
            sha256=NAMED,
            recorded_at=REMOVED_AT,
            reason=ReasonCode.REMOVED_IN_ERROR,
            request_id="RM-2026-05",
        ),
        whole_source=True,
        disclosures=0,
        previous=suppressed,
        path_holds_released=path_holds_released,
    )


def test_unsuppress_says_how_many_paths_it_releases() -> None:
    shown = render_unsuppress(an_unsuppress(2), None)

    assert "It also releases the hold on 2 path(s) the file was removed from: a" in shown
    assert "appended beside the list for that; a hold follows the file it came from." in shown
    assert unsuppress_summary(an_unsuppress(2), SETTINGS, None)["path_holds_released"] == 2


def test_unsuppress_of_a_file_with_no_held_path_says_nothing_of_one() -> None:
    assert "releases the hold" not in render_unsuppress(an_unsuppress(0), None)
    assert unsuppress_summary(an_unsuppress(0), SETTINGS, None)["path_holds_released"] == 0


# ------------------------------------------------------------------------------------------------
# caselist import
# ------------------------------------------------------------------------------------------------


def an_import(held_by_request: dict[str, int]) -> ImportReport:
    return ImportReport(
        caselist=CASELIST,
        snapshot=date(2026, 10, 8),
        event=Event.LD,
        archive_sha256="f" * 64,
        applied=True,
        entries=(),
        counts={Classification.SUPPRESSED: 3, Classification.NEW: 1},
        previous_snapshot=date(2026, 10, 6),
        held_by_request=held_by_request,
    )


def test_the_import_summary_counts_held_uploads_by_request() -> None:
    held = an_import({"RM-2026-07": 1, "RM-2026-05": 2})

    data = import_summary(held, Path("/data/objects/manifests/testcl26/2026-10-08.jsonl"))

    assert data["held_at_removed_paths"] == {"RM-2026-05": 2, "RM-2026-07": 1}
    assert data["counts"]["SUPPRESSED"] == 3  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue, reportOptionalSubscript]
    assert import_summary(an_import({}), None)["held_at_removed_paths"] == {}


def test_the_import_table_says_how_many_were_held_under_which_request_and_what_to_do() -> None:
    caption = import_table(an_import({"RM-2026-07": 1, "RM-2026-05": 2}), None).caption or ""

    assert (
        "SUPPRESSED includes 3 new upload(s) at a removed path (2 under RM-2026-05, 1 under RM-2026-07), "
        "refused because that removal holds the path: run the same `caselist remove` again to finish."
    ) in caption
    assert "removed path" not in (import_table(an_import({}), None).caption or "")
