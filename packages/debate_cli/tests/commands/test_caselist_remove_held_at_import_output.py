"""How `caselist remove` shows an upload an import refused at a held path, once its archive has gone.

The re-run of a `--source` removal reads the held-digest record beside the path entries
(`v1-e30-t23`) and plans each digest it holds for this request: removed whole when no other path
holds the bytes, withdrawn from the held path only when another does. Nothing names such a file but
its digest and the request, so its lines say where it was refused by caselist alone.

Each plan here is built by hand, as `test_caselist_path_hold_output.py`'s are: the renderers are
functions of what they are given.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

from debate_cli.commands.caselist_remove import plan_summary, render_plan
from debate_core.application.caselist.removal_plan import Disposition, Inclusion, PlannedSource, RemovalPlan

from .test_caselist_path_hold_output import new_lines_name_no_one, section
from .test_caselist_remove_plan_output import CASELIST, NAMED, SETTINGS, TEAM_PATH, plan_of, source

REFUSED_WHOLE = "e" * 64
REFUSED_SHARED = "f" * 64
HELD_PATH = hashlib.sha256(f"{CASELIST}/{TEAM_PATH}".encode()).hexdigest()


def refused(sha256: str, disposition: Disposition) -> PlannedSource:
    """An upload the record names at the held path: on this machine nowhere, as the import left it."""
    return dataclasses.replace(
        source(sha256, Inclusion.HELD_AT_IMPORT, disposition),
        byte_size=None,
        source_format=None,
        local_blob=False,
        delete_source_record=False,
        held_at_import=((CASELIST, HELD_PATH),),
    )


def a_re_run_with_two_refused_uploads() -> RemovalPlan:
    return plan_of(
        (
            source(NAMED, Inclusion.NAMED, Disposition.REMOVE),
            refused(REFUSED_WHOLE, Disposition.REMOVE),
            refused(REFUSED_SHARED, Disposition.WITHDRAW),
        )
    )


def test_they_have_a_section_of_their_own_with_what_happens_to_each() -> None:
    shown = section(render_plan(a_re_run_with_two_refused_uploads(), None), "REFUSED AT IMPORT")

    lines = shown.splitlines()
    assert lines[0] == "REFUSED AT IMPORT AT A HELD PATH, ADDED TO THIS PLAN: 2 file(s)"
    assert f"  1. {REFUSED_WHOLE}  (not on this machine)" in lines
    assert f"     refused at a held path in {CASELIST}: suppressed whole: no other path holds it" in lines
    assert (
        f"     refused at a held path in {CASELIST}: withdrawn from this path only: another path still "
        "holds it, so its bytes stay"
    ) in lines
    assert f"     withdraw {CASELIST}  the held path an import refused it at, by its digest" in lines
    assert "no withdrawal record" not in shown
    new_lines_name_no_one(shown)


def test_they_are_not_counted_among_the_files_the_request_names() -> None:
    shown = render_plan(a_re_run_with_two_refused_uploads(), None)

    removed = section(shown, "WILL BE REMOVED")
    assert removed.splitlines()[0] == "WILL BE REMOVED, everywhere, and suppressed: 1 file(s)"
    assert REFUSED_WHOLE not in removed
    assert "SHARED, KEPT" not in shown


def test_the_plan_says_it_covers_them_and_so_does_the_confirmation() -> None:
    shown = render_plan(a_re_run_with_two_refused_uploads(), None)

    assert (
        "This plan covers the 1 file(s) named, and adds 0 later upload(s) at the removed path(s), and 2 "
        "upload(s) an import refused at a held path."
    ) in shown
    assert ("  - Also stopped, as later uploads an import refused at the same path(s): 2 file(s).") in shown[
        shown.index("FOR THE CONFIRMATION TO THE REQUESTER") :
    ]


def test_the_json_names_them_by_inclusion_and_a_withdrawal_by_the_held_paths_digest() -> None:
    data = json.loads(json.dumps(plan_summary(a_re_run_with_two_refused_uploads(), SETTINGS, None)))

    sources = {one["sha256"]: one for one in data["sources"]}
    assert sources[REFUSED_WHOLE]["inclusion"] == "held_at_import"
    assert sources[REFUSED_WHOLE]["withdrawn_disclosures"] == []
    assert sources[REFUSED_SHARED]["withdrawn_disclosures"] == [
        {"caselist": CASELIST, "disclosure": HELD_PATH}
    ]
    new_lines_name_no_one(json.dumps(data))
