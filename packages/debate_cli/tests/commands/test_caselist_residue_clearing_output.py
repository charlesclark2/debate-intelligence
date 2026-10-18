"""What the remove plan and `caselist status` print of the residue clearing gaps (`v1-e30-t19`).

Each plan and report is built by hand, field by field, as in `test_caselist_remove_plan_output.py`
and `test_caselist_status_held_paths.py`: the renderers are functions of what they are given. The
behaviour behind them is `packages/debate_core/tests/application/caselist/test_residue_clearing_gaps.py`,
and the commands end to end are `tests/smoke/test_caselist_remove_smoke.py` and
`tests/smoke/test_caselist_publish_smoke.py`.

* **The dry run's line.** A plan whose execution would sweep a manifest version says so, with the
  count, and is never "Nothing is left to remove"; one whose sweep could not be counted says that.
* **A re-planned withdrawal** says where the withdrawal record puts the copy, or that none does.
* **A withdrawn copy's residue** is named by the caselist it was withdrawn from and the request,
  and a withdrawal an earlier build made is *not attributed*. Neither changes the exit code, and
  neither names a path, school, team code or file name.
"""

from __future__ import annotations

import dataclasses
import json

from debate_cli.commands.caselist import (
    _status_table,  # pyright: ignore[reportPrivateUsage]
    status_summary,
)
from debate_cli.commands.caselist_remove import render_plan
from debate_core.application.caselist.removal_plan import Disposition, Inclusion, RemovalPlan, TeamSelector
from debate_core.application.caselist.removal_residue import CaselistResidue, WithdrawnCopy
from debate_core.application.caselist.status_service import CaselistStatusReport
from debate_core.application.ports.evidence_versions import ObjectVersion

from .test_caselist_remove_plan_output import CASELIST, IDENTIFYING, NAMED, SETTINGS, plan_of, source
from .test_caselist_status_held_paths import snapshot

MANIFEST = f"manifests/{CASELIST}/2026-09-15.jsonl"
OTHER_MANIFEST = f"manifests/{CASELIST}/2026-09-01.jsonl"
NOTHING_LEFT = "Nothing is left to remove"
WITHDRAWN = "c0ffee000000" + "2" * 52
REQUEST = "RM-2026-07"


def noncurrent(key: str, version_id: str) -> ObjectVersion:
    return ObjectVersion(key=key, version_id=version_id, is_latest=False)


def finished_plan() -> RemovalPlan:
    """A re-run that finds the named file already gone and suppressed: nothing else to do."""
    return plan_of(
        (
            dataclasses.replace(
                source(NAMED, Inclusion.NAMED, Disposition.REMOVE),
                local_blob=False,
                delete_source_record=False,
            ),
        )
    )


class TestTheDryRunsSweepLine:
    def test_a_plan_whose_execution_would_sweep_versions_counts_them_by_manifest(self) -> None:
        plan = dataclasses.replace(
            finished_plan(),
            superseded_versions=(
                noncurrent(MANIFEST, "v1"),
                noncurrent(MANIFEST, "v2"),
                noncurrent(OTHER_MANIFEST, "v3"),
            ),
        )

        lines = render_plan(plan, None).splitlines()

        assert NOTHING_LEFT not in "\n".join(lines)
        assert (
            "MANIFEST VERSIONS SWEPT from the bucket by --execute: 3 noncurrent version(s) of 2 manifest(s)."
        ) in lines
        assert f"  bucket {OTHER_MANIFEST}  (1 version(s))" in lines
        assert f"  bucket {MANIFEST}  (2 version(s))" in lines
        assert "TO CARRY IT OUT" in lines

    def test_a_sweep_that_could_not_be_counted_says_so_and_is_never_nothing_left(self) -> None:
        plan = dataclasses.replace(finished_plan(), superseded_versions=None)

        shown = render_plan(plan, None)

        assert NOTHING_LEFT not in shown
        assert "MANIFEST VERSIONS SWEPT from the bucket by --execute: not counted." in shown.splitlines()
        assert "TO CARRY IT OUT" in shown

    def test_a_plan_with_nothing_to_sweep_says_nothing_of_a_sweep_and_is_nothing_left(self) -> None:
        shown = render_plan(finished_plan(), None)

        assert NOTHING_LEFT in shown
        assert "MANIFEST VERSIONS SWEPT" not in shown
        assert "TO CARRY IT OUT" not in shown


class TestARePlannedWithdrawal:
    TEAM = TeamSelector(caselist=CASELIST, school="Maple Grove", team_code="QX")

    def test_it_names_the_caselist_the_withdrawal_record_gives(self) -> None:
        withdrawn = dataclasses.replace(
            source(WITHDRAWN, Inclusion.UNFINISHED, Disposition.WITHDRAW), withdrawn_earlier_from=(CASELIST,)
        )

        shown = render_plan(plan_of((withdrawn,), selector=self.TEAM), None)

        assert (
            f"     withdrawn earlier from {CASELIST}, as the withdrawal record says: its paths there are gone"
        ) in shown.splitlines()

    def test_one_no_record_names_says_its_aggregates_cannot_be_planned_again(self) -> None:
        withdrawn = source(WITHDRAWN, Inclusion.UNFINISHED, Disposition.WITHDRAW)

        shown = " ".join(render_plan(plan_of((withdrawn,), selector=self.TEAM), None).split())

        assert "no withdrawal record names the caselist it was withdrawn from" in shown


def with_a_withdrawn_copy_left(*, not_attributed: tuple[str, ...] = ()) -> CaselistStatusReport:
    return CaselistStatusReport(
        snapshots=(snapshot("2026-09-15"),),
        residue=(
            CaselistResidue(
                caselist=CASELIST,
                checked=True,
                withdrawn_copies=(
                    WithdrawnCopy(
                        sha256=WITHDRAWN, request_id=REQUEST, current_objects=1, noncurrent_versions=2
                    ),
                ),
            ),
        ),
        withdrawals_not_attributed=not_attributed,
    )


class TestAWithdrawnCopyLeft:
    def test_it_does_not_change_whether_the_command_succeeds(self) -> None:
        report = with_a_withdrawn_copy_left(not_attributed=("RM-2026-90",))

        assert report.in_sync is True
        assert not report.residue_found

    def test_the_table_names_its_caselist_its_request_and_twelve_characters(self) -> None:
        caption = _status_table(with_a_withdrawn_copy_left(), SETTINGS).caption or ""
        told = " ".join(caption.split())

        assert (
            f"WITHDRAWN COPIES LEFT in {CASELIST}: 1 current object(s), 2 noncurrent version(s) and 0 delete "
            f"marker(s) of 1 file(s) withdrawn from {CASELIST} (sha256 {WITHDRAWN[:12]}, {REQUEST})."
        ) in told
        assert "No version of a removed file is left" not in told
        assert WITHDRAWN not in caption
        assert not [word for word in IDENTIFYING if word in caption]

    def test_a_withdrawal_an_earlier_build_made_is_not_attributed(self) -> None:
        caption = (
            _status_table(with_a_withdrawn_copy_left(not_attributed=("RM-2026-90",)), SETTINGS).caption or ""
        )

        assert "Withdrawals NOT ATTRIBUTED to a caselist: RM-2026-90." in " ".join(caption.split())

    def test_the_json_gives_each_copy_by_caselist_prefix_and_request(self) -> None:
        data = status_summary(with_a_withdrawn_copy_left(not_attributed=("RM-2026-90",)), SETTINGS)

        assert data["withdrawn_copies_left"] == [
            {
                "caselist": CASELIST,
                "sha256_prefix": WITHDRAWN[:12],
                "request_id": REQUEST,
                "current_objects": 1,
                "noncurrent_versions": 2,
                "delete_markers": 0,
            }
        ]
        assert data["withdrawals_not_attributed"] == ["RM-2026-90"]
        assert WITHDRAWN not in json.dumps(data)
