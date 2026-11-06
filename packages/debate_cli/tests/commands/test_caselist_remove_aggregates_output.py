"""The plan shows the aggregates it rewrites apart from the file's own objects (`v1-e30-t33`, ruling (b)).

*AGGREGATES REWRITTEN WITHOUT THE REMOVED ROWS* lists each aggregate of each version directory holding a
parsed file of what is removed, with the rows that go, the table's bytes and the older versions purged;
a retired directory's aggregates are under their own heading as deleted; and `--json` carries the same
as `aggregates`. Each plan is built by hand, as in `test_caselist_remove_plan_output.py`.
"""

from __future__ import annotations

import dataclasses
import json

from debate_cli.commands.caselist_remove import plan_summary, render_plan
from debate_core.application.caselist.removal_plan import AggregateAction, AggregateChange, RemovalPlan, Side
from debate_core.application.ports.evidence_versions import ObjectVersion

from .test_caselist_path_hold_output import new_lines_name_no_one, section
from .test_caselist_remove_output_loose_ends import executed, removed_whole
from .test_caselist_remove_plan_output import SETTINGS, plan_of

CURRENT = "2026.10.27-docx-7"
RETIRED = "2026.10.20-docx-6"


def older(key: str) -> ObjectVersion:
    return ObjectVersion(key=key, version_id="v-older", is_latest=False)


def change(name: str, action: AggregateAction, **fields: object) -> AggregateChange:
    version = RETIRED if action is AggregateAction.DELETE else CURRENT
    key = f"parsed/testcl26/{version}/{name}"
    defaults: dict[str, object] = {"versions": ()}
    return AggregateChange(
        key=key,
        side=Side.BUCKET,
        caselist="testcl26",
        version=version,
        name=name,
        action=action,
        **{**defaults, **fields},  # type: ignore[arg-type]
    )


def a_plan() -> RemovalPlan:
    return dataclasses.replace(
        plan_of((removed_whole(),)),
        aggregates=(
            change(
                "index.jsonl",
                AggregateAction.REWRITE,
                rows=3,
                rows_dropped=1,
                bytes=1200,
                versions=(),
            ),
            change("failures.jsonl", AggregateAction.LEFT, rows=0, rows_dropped=0, bytes=0),
            change(
                "occurrences.jsonl",
                AggregateAction.REWRITE,
                rows=4,
                rows_dropped=2,
                bytes=2600,
                versions=(older(f"parsed/testcl26/{CURRENT}/occurrences.jsonl"),),
            ),
            change("index.jsonl", AggregateAction.DELETE, bytes=900, versions=(older("a"), older("b"))),
        ),
    )


def test_the_aggregates_have_a_section_of_their_own_with_rows_bytes_and_older_versions() -> None:
    text = render_plan(a_plan(), None)

    shown = section(text, "AGGREGATES REWRITTEN WITHOUT THE REMOVED ROWS").splitlines()
    assert shown[0] == (
        "AGGREGATES REWRITTEN WITHOUT THE REMOVED ROWS: 2 of 3 table(s) in 1 version director(ies) holding a "
        "parsed file of it"
    )
    assert shown[2:] == [
        f"  bucket parsed/testcl26/{CURRENT}/index.jsonl  rewritten (-1 of 3 row(s), 1200 bytes, "
        "0 older version(s) purged)",
        f"  bucket parsed/testcl26/{CURRENT}/failures.jsonl  holds none: left as it is (-0 of 0 row(s), "
        "0 bytes, 0 older version(s) purged)",
        f"  bucket parsed/testcl26/{CURRENT}/occurrences.jsonl  rewritten (-2 of 4 row(s), 2600 bytes, "
        "1 older version(s) purged)",
    ]
    new_lines_name_no_one("\n".join(shown))


def test_a_retired_directorys_aggregates_are_under_their_own_heading_as_deleted() -> None:
    shown = section(render_plan(a_plan(), None), "AGGREGATES DELETED IN RETIRED").splitlines()

    assert shown[0] == "AGGREGATES DELETED IN RETIRED VERSION DIRECTORIES: 1 table(s), every version"
    assert shown[-1] == f"  bucket parsed/testcl26/{RETIRED}/index.jsonl  (2 version(s), 900 bytes)"


def test_the_file_section_no_longer_lists_aggregates_with_its_own_objects() -> None:
    text = render_plan(a_plan(), None)
    removed = section(text, "WILL BE REMOVED")

    assert "index.jsonl" not in removed and "occurrences.jsonl" not in removed


def test_an_unreadable_table_is_named_with_its_line_and_what_execute_does() -> None:
    plan = dataclasses.replace(
        a_plan(), aggregates=(change("occurrences.jsonl", AggregateAction.UNREADABLE, unreadable_line=11),)
    )

    shown = section(render_plan(plan, None), "AGGREGATES REWRITTEN").splitlines()

    assert f"  bucket parsed/testcl26/{CURRENT}/occurrences.jsonl  UNREADABLE at line 11" in shown
    assert (
        "  --execute stops before it writes anything. Move each aside or rebuild it, then run again." in shown
    )


def test_the_json_carries_each_aggregate_by_key_with_its_counts() -> None:
    data = json.loads(json.dumps(plan_summary(a_plan(), SETTINGS, None)))

    assert data["aggregates"][2] == {
        "key": f"parsed/testcl26/{CURRENT}/occurrences.jsonl",
        "side": "bucket",
        "caselist": "testcl26",
        "version": CURRENT,
        "action": "rewrite",
        "rows": 4,
        "rows_dropped": 2,
        "bytes": 2600,
        "versions": 1,
        "unreadable_line": None,
    }
    assert [one["action"] for one in data["aggregates"]] == ["rewrite", "left", "rewrite", "delete"]
    assert all(one["kind"] != "parsed_aggregate" for one in data["objects"])


def test_the_execution_says_how_many_it_rewrote_and_that_nothing_is_rebuilt() -> None:
    plan = a_plan()
    report = dataclasses.replace(
        executed(plan), aggregates_rewritten=2, aggregate_rows_dropped=3, aggregates_deleted=1
    )

    text = render_plan(plan, report)
    data = json.loads(json.dumps(plan_summary(plan, SETTINGS, report)))

    assert (
        "Parsed store: 2 aggregate(s) rewritten without 3 row(s); 1 in retired directories deleted. "
        "Nothing is to be rebuilt."
    ) in text.splitlines()
    assert data["aggregates_done"] == {"rewritten": 2, "rows_dropped": 3, "deleted": 1}
