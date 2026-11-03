"""How `caselist status` shows what a removal's hold says is owed (`v1-e30-t21`).

Each report here is built by hand, field by field, so the test says exactly what the command was
given and what it must print. Nothing is compared: the renderers are functions of the report. The
command runs end to end in `tests/smoke/test_caselist_remove_smoke.py`, and the comparison itself in
`packages/debate_core/tests/application/caselist/test_held_path_loose_ends.py`.

What every line this task adds keeps: a held file is named by the first twelve characters of its
sha256 and the request holding its path; never by the path, a school, a team code or a file name;
and neither kind of hold changes whether the command succeeds.
"""

from __future__ import annotations

import json

from debate_cli.commands.caselist import (
    _status_failure,  # pyright: ignore[reportPrivateUsage]
    _status_table,  # pyright: ignore[reportPrivateUsage]
    status_summary,
)
from debate_core.application.caselist.publish_plan import HeldRow
from debate_core.application.caselist.status_service import (
    CaselistStatusReport,
    HeldInboxUpload,
    SnapshotStatus,
)

from .test_caselist_remove_plan_output import CASELIST, IDENTIFYING, SETTINGS

HELD_ROW = "a1b2c3d4e5f6" + "0" * 52
HELD_IN_INBOX = "f6e5d4c3b2a1" + "1" * 52
REQUEST = "RM-2026-05"
OTHER_REQUEST = "RM-2026-06"


def snapshot(name: str, **changes: object) -> SnapshotStatus:
    """A snapshot that agrees with the bucket, unless `changes` say otherwise."""
    fields: dict[str, object] = {
        "caselist": CASELIST,
        "snapshot": name,
        "manifest_key": f"manifests/{CASELIST}/{name}.jsonl",
        "local_manifest": True,
        "manifest_present": True,
        "sources": 3,
        "local_files": 3,
        "published_sources": 3,
    }
    fields.update(changes)
    return SnapshotStatus(**fields)  # type: ignore[arg-type]


def in_sync_with_both_kinds_of_hold() -> CaselistStatusReport:
    return CaselistStatusReport(
        snapshots=(
            snapshot("2026-10-06"),
            snapshot("2026-10-08", held_rows=(HeldRow(sha256=HELD_ROW, request_id=REQUEST),)),
        ),
        held_in_inbox=(
            HeldInboxUpload(CASELIST, "2026-10-10", HELD_IN_INBOX, REQUEST),
            HeldInboxUpload(CASELIST, "full/2026-10-09", HELD_IN_INBOX, OTHER_REQUEST),
        ),
    )


def names_no_one(text: str) -> None:
    assert not [word for word in IDENTIFYING if word in text], text


def test_a_report_with_both_kinds_of_hold_is_still_in_sync() -> None:
    """What decides the exit code: `caselist status` exits 0 when this is true, as before."""
    report = in_sync_with_both_kinds_of_hold()

    assert report.in_sync is True
    assert report.removals_owed == (REQUEST, OTHER_REQUEST)


def test_the_json_counts_each_held_row_by_prefix_and_request() -> None:
    data = status_summary(in_sync_with_both_kinds_of_hold(), SETTINGS)

    entries = {entry["snapshot"]: entry for entry in data["snapshots"]}  # type: ignore[index,union-attr]
    assert (entries["2026-10-08"]["held_rows"], entries["2026-10-08"]["held_row_prefixes"]) == (
        1,
        ["a1b2c3d4e5f6"],
    )
    assert entries["2026-10-08"]["held_row_requests"] == [REQUEST]
    assert (entries["2026-10-06"]["held_rows"], entries["2026-10-06"]["held_row_prefixes"]) == (0, [])
    assert data["in_sync"] is True
    names_no_one(json.dumps(data))


def test_the_json_counts_the_uploads_held_in_the_inbox_per_caselist_and_names_the_removals_owed() -> None:
    data = status_summary(in_sync_with_both_kinds_of_hold(), SETTINGS)

    assert data["held_in_inbox"] == [
        {
            "caselist": CASELIST,
            "uploads": 2,
            "sha256_prefixes": ["f6e5d4c3b2a1", "f6e5d4c3b2a1"],
            "requests": [REQUEST, OTHER_REQUEST],
        }
    ]
    assert data["removals_owed"] == [REQUEST, OTHER_REQUEST]
    assert HELD_ROW not in json.dumps(data) and HELD_IN_INBOX not in json.dumps(data), "a whole digest"


def test_the_table_says_every_snapshot_agrees_then_what_is_held_and_which_removal_to_run_again() -> None:
    caption = _status_table(in_sync_with_both_kinds_of_hold(), SETTINGS).caption or ""

    assert caption.splitlines() == [
        "Every snapshot agrees.",
        "HELD PATH ROWS in testcl26 2026-10-08: 1 row(s) at a path a removal holds "
        "(sha256 a1b2c3d4e5f6, RM-2026-05).",
        "HELD UPLOADS IN THE DOWNLOAD INBOX for testcl26: 2 upload(s) at a path a removal holds "
        "(sha256 f6e5d4c3b2a1, RM-2026-05, sha256 f6e5d4c3b2a1, RM-2026-06).",
        "A held row or a held upload in the inbox means RM-2026-05, RM-2026-06 is owed again: run the "
        "same removal again, dry run first, then --execute (docs/runbooks/caselist-removal.md, step 9).",
    ]
    names_no_one(caption)


def test_a_report_with_no_hold_says_nothing_new() -> None:
    report = CaselistStatusReport(snapshots=(snapshot("2026-10-06"),))

    caption = _status_table(report, SETTINGS).caption or ""

    assert caption.splitlines() == ["Every snapshot agrees."]
    data = status_summary(report, SETTINGS)
    assert (data["held_in_inbox"], data["removals_owed"]) == (
        [{"caselist": CASELIST, "uploads": 0, "sha256_prefixes": [], "requests": []}],
        [],
    )


def test_a_drifted_report_still_fails_as_drift_and_its_hint_names_the_removal_owed() -> None:
    """The exit code and the error code are the drift's; the hold adds one sentence to the hint."""
    report = CaselistStatusReport(
        snapshots=(
            snapshot("2026-10-06", manifest_present=False),
            snapshot("2026-10-08", held_rows=(HeldRow(sha256=HELD_ROW, request_id=REQUEST),)),
        )
    )
    assert report.in_sync is False

    failure = _status_failure(report, status_summary(report, SETTINGS))

    assert failure.code == "CASELIST_DRIFT"
    assert failure.message == "1 snapshot(s) differ between this machine and the bucket: testcl26 2026-10-06"
    assert failure.hint is not None
    assert failure.hint.endswith(
        "A held row or a held upload in the inbox means RM-2026-05 is owed again: run the same removal "
        "again, dry run first, then --execute (docs/runbooks/caselist-removal.md, step 9)."
    )


# ------------------------------------------------------------------------------------------------
# A skipped member's row at a held path, which an earlier build wrote (`v1-e30-t22`)
# ------------------------------------------------------------------------------------------------


def in_sync_with_a_held_skipped_row() -> CaselistStatusReport:
    """A symbolic link at the held path in `2026-10-11`, given a row by an earlier build."""
    return CaselistStatusReport(
        snapshots=(snapshot("2026-10-06"), snapshot("2026-10-11", held_skipped_rows=(REQUEST,))),
    )


def test_a_held_skipped_row_does_not_change_the_verdict_and_says_the_removal_is_owed() -> None:
    report = in_sync_with_a_held_skipped_row()

    assert report.in_sync is True
    assert [one.snapshot for one in report.held_snapshots] == ["2026-10-11"]
    assert report.removals_owed == (REQUEST,)


def test_the_json_counts_each_held_skipped_row_by_request() -> None:
    data = status_summary(in_sync_with_a_held_skipped_row(), SETTINGS)

    entries = {entry["snapshot"]: entry for entry in data["snapshots"]}  # type: ignore[index,union-attr]
    held = entries["2026-10-11"]
    assert (held["held_skipped_rows"], held["held_skipped_row_requests"]) == (1, [REQUEST])
    assert (held["held_rows"], held["held_row_prefixes"]) == (0, [])
    assert (
        entries["2026-10-06"]["held_skipped_rows"],
        entries["2026-10-06"]["held_skipped_row_requests"],
    ) == (
        0,
        [],
    )
    assert data["removals_owed"] == [REQUEST]
    assert data["in_sync"] is True
    names_no_one(json.dumps(data))


def test_the_table_names_a_held_skipped_row_by_its_request_alone() -> None:
    """It has no digest to name, and no line for the snapshot's stored rows, of which none is held."""
    caption = _status_table(in_sync_with_a_held_skipped_row(), SETTINGS).caption or ""

    assert caption.splitlines() == [
        "Every snapshot agrees.",
        "HELD PATH ROWS in testcl26 2026-10-11: 1 skipped member row(s) at a path a removal holds "
        "(RM-2026-05).",
        "A held row or a held upload in the inbox means RM-2026-05 is owed again: run the same removal "
        "again, dry run first, then --execute (docs/runbooks/caselist-removal.md, step 9).",
    ]
    names_no_one(caption)


def test_a_snapshot_with_both_kinds_of_held_row_gets_a_line_for_each() -> None:
    report = CaselistStatusReport(
        snapshots=(
            snapshot(
                "2026-10-11",
                held_rows=(HeldRow(sha256=HELD_ROW, request_id=REQUEST),),
                held_skipped_rows=(OTHER_REQUEST, REQUEST),
            ),
        ),
    )

    lines = (_status_table(report, SETTINGS).caption or "").splitlines()

    assert lines[1:3] == [
        "HELD PATH ROWS in testcl26 2026-10-11: 1 row(s) at a path a removal holds "
        "(sha256 a1b2c3d4e5f6, RM-2026-05).",
        "HELD PATH ROWS in testcl26 2026-10-11: 2 skipped member row(s) at a path a removal holds "
        "(RM-2026-05, RM-2026-06).",
    ]
    assert report.removals_owed == (REQUEST, OTHER_REQUEST)
