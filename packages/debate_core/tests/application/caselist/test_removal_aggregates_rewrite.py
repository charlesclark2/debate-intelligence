"""A removal's rewrite of one table, and the check it passes before it is written (`v1-e30-t33`, (c)).

Rows here are the fields the rewrite reads, nothing more; the digests are made up. The checks:
rows after equal rows before less the rows naming the removed file; every kept line is the table's,
byte for byte; a line it cannot read stops it with nothing written.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.removal_aggregates import (
    AggregateRewriteRefused,
    RowsRemoved,
    UnreadableAggregateLine,
    check_rewrite,
    rewrite_directory,
    rewrite_table,
)
from debate_core.application.ports.suppression import SuppressionEntry, SuppressionState

REMOVED: Final = hashlib.sha256(b"removed").hexdigest()
KEPT: Final = hashlib.sha256(b"kept").hexdigest()
WITHDRAWN_PATH: Final = hashlib.sha256(b"a withdrawn disclosure").hexdigest()
OTHER_PATH: Final = hashlib.sha256(b"another disclosure").hexdigest()


def line(**fields: object) -> bytes:
    return (json.dumps(fields, sort_keys=True, separators=(",", ":")) + "\n").encode()


def table(tmp_path: Path, name: str, *lines: bytes) -> Path:
    path = tmp_path / "read" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(lines))
    return path


WHOLE: Final = RowsRemoved(whole=frozenset({REMOVED}))


def test_a_rewrite_keeps_every_other_line_byte_for_byte_in_order(tmp_path: Path) -> None:
    kept = [line(source_sha256=KEPT, n=1), b"\n", line(source_sha256=KEPT, n=2, odd="  spaced ")]
    source = table(tmp_path, "index.jsonl", kept[0], line(source_sha256=REMOVED), kept[1], kept[2])
    target = tmp_path / "written" / "index.jsonl"

    result = rewrite_table("index.jsonl", source, target, WHOLE, table="t")

    assert target.read_bytes() == b"".join(kept)
    assert (result.rows, result.rows_dropped) == (3, 1)
    assert result.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result.rewritten_sha256 == hashlib.sha256(target.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "bad", [b"not json\n", b"[1, 2]\n", line(no_source="x"), line(source_sha256="ABC"), b"\xff\xfe\n"]
)
def test_a_line_it_cannot_read_stops_it_with_nothing_written(tmp_path: Path, bad: bytes) -> None:
    source = table(tmp_path, "occurrences.jsonl", line(source_sha256=REMOVED), bad)
    target = tmp_path / "written" / "occurrences.jsonl"

    with pytest.raises(UnreadableAggregateLine) as stopped:
        rewrite_table("occurrences.jsonl", source, target, WHOLE, table="t")

    assert stopped.value.line == 2
    assert not target.exists()
    assert list(target.parent.iterdir()) == [], "no part-written file either"


def test_the_check_refuses_a_rewrite_that_left_out_a_row_naming_nothing_removed(tmp_path: Path) -> None:
    source = table(tmp_path, "index.jsonl", line(source_sha256=KEPT), line(source_sha256=REMOVED))
    target = tmp_path / "written" / "index.jsonl"
    result = rewrite_table("index.jsonl", source, target, WHOLE, table="t")
    target.write_bytes(b"")

    with pytest.raises(AggregateRewriteRefused):
        check_rewrite(source, target, WHOLE, result, table="t")


def test_the_check_refuses_a_kept_line_that_is_not_the_tables_bytes(tmp_path: Path) -> None:
    source = table(tmp_path, "index.jsonl", line(source_sha256=KEPT, n=1), line(source_sha256=REMOVED))
    target = tmp_path / "written" / "index.jsonl"
    result = rewrite_table("index.jsonl", source, target, WHOLE, table="t")
    target.write_bytes(line(source_sha256=KEPT, n=2))

    with pytest.raises(AggregateRewriteRefused):
        check_rewrite(source, target, WHOLE, result, table="t")


def test_the_check_refuses_a_rewrite_holding_a_line_the_table_did_not(tmp_path: Path) -> None:
    source = table(tmp_path, "index.jsonl", line(source_sha256=KEPT))
    target = tmp_path / "written" / "index.jsonl"
    result = rewrite_table("index.jsonl", source, target, WHOLE, table="t")
    target.write_bytes(line(source_sha256=KEPT) + line(source_sha256=KEPT))

    with pytest.raises(AggregateRewriteRefused):
        check_rewrite(source, target, WHOLE, result, table="t")


def test_the_check_refuses_a_rewrite_whose_count_is_not_the_one_reported(tmp_path: Path) -> None:
    source = table(tmp_path, "index.jsonl", line(source_sha256=KEPT), line(source_sha256=REMOVED))
    target = tmp_path / "written" / "index.jsonl"
    result = rewrite_table("index.jsonl", source, target, WHOLE, table="t")

    with pytest.raises(AggregateRewriteRefused):
        check_rewrite(source, target, WHOLE, replace(result, rows_dropped=0), table="t")
    check_rewrite(source, target, WHOLE, result, table="t")


def withdrawn() -> RowsRemoved:
    """A disclosure of `KEPT` withdrawn while another holder keeps the file."""
    entry = SuppressionEntry.model_validate(
        {
            "action": "SUPPRESS",
            "sha256": KEPT,
            "disclosure": WITHDRAWN_PATH,
            "recorded_at": "2026-11-05T00:00:00Z",
            "reason": "REQUESTED_BY_TEAM",
            "request_id": "RM-2026-91",
        }
    )
    return RowsRemoved(asked=frozenset({KEPT}), state=SuppressionState.from_entries([entry]))


def test_a_withdrawal_drops_the_rows_of_its_disclosure_and_keeps_the_entry(tmp_path: Path) -> None:
    rule = withdrawn()
    index = table(tmp_path, "index.jsonl", line(source_sha256=KEPT))
    occurrences = table(
        tmp_path,
        "occurrences.jsonl",
        line(source_sha256=KEPT, disclosure=WITHDRAWN_PATH, snapshot="2026-10-27"),
        line(source_sha256=KEPT, disclosure=OTHER_PATH, snapshot="2026-10-27"),
    )

    assert rewrite_table("index.jsonl", index, None, rule, table="t").rows_dropped == 0
    assert rewrite_table("occurrences.jsonl", occurrences, None, rule, table="t").rows_dropped == 1


def test_camp_path_lines_are_restamped_with_the_rewritten_tables_digest(tmp_path: Path) -> None:
    release, other = "2026-policy", "2027-policy"
    rows = [
        line(source_sha256=REMOVED, snapshot=release, disclosure=None),
        line(source_sha256=KEPT, snapshot=other, disclosure=None),
    ]
    occurrences = table(tmp_path, "occurrences.jsonl", *rows)
    old = hashlib.sha256(occurrences.read_bytes()).hexdigest()
    stamped = [
        line(
            source_sha256=REMOVED,
            snapshot=release,
            camp_path_disclosure=OTHER_PATH,
            occurrence_table_sha256=old,
        ),
        line(
            source_sha256=KEPT, snapshot=other, camp_path_disclosure=OTHER_PATH, occurrence_table_sha256=old
        ),
    ]
    beside = table(tmp_path, "camp_paths.jsonl", *stamped)
    into = tmp_path / "written"
    into.mkdir()

    done = rewrite_directory(
        {"occurrences.jsonl": occurrences, "camp_paths.jsonl": beside}, WHOLE, label="openev", into=into
    )

    new = hashlib.sha256((into / "occurrences.jsonl").read_bytes()).hexdigest()
    assert (into / "occurrences.jsonl").read_bytes() == rows[1]
    assert (into / "camp_paths.jsonl").read_bytes() == stamped[1].replace(old.encode(), new.encode())
    assert {name: getattr(result, "rows_dropped", None) for name, result in done.items()} == {
        "occurrences.jsonl": 1,
        "camp_paths.jsonl": 1,
    }


def test_a_camp_row_is_asked_by_the_camp_paths_its_table_gives_it(tmp_path: Path) -> None:
    """A camp file withdrawn from one camp path: the release's rows stay while another path is live."""
    rule = RowsRemoved(
        asked=frozenset({KEPT}),
        state=SuppressionState.from_entries(
            [
                SuppressionEntry.model_validate(
                    {
                        "action": "SUPPRESS",
                        "sha256": KEPT,
                        "disclosure": WITHDRAWN_PATH,
                        "recorded_at": "2026-11-05T00:00:00Z",
                        "reason": "REQUESTED_BY_CAMP",
                        "request_id": "RM-2026-91",
                    }
                )
            ]
        ),
    )
    occurrences = table(
        tmp_path, "occurrences.jsonl", line(source_sha256=KEPT, snapshot="2026-policy", disclosure=None)
    )
    old = hashlib.sha256(occurrences.read_bytes()).hexdigest()
    beside = table(
        tmp_path,
        "camp_paths.jsonl",
        *(
            line(
                source_sha256=KEPT,
                snapshot="2026-policy",
                camp_path_disclosure=path,
                occurrence_table_sha256=old,
            )
            for path in (WITHDRAWN_PATH, OTHER_PATH)
        ),
    )

    done = rewrite_directory(
        {"occurrences.jsonl": occurrences, "camp_paths.jsonl": beside}, rule, label="openev"
    )

    assert {name: getattr(result, "rows_dropped", None) for name, result in done.items()} == {
        "occurrences.jsonl": 0,
        "camp_paths.jsonl": 1,
    }
    emptied = RowsRemoved(
        asked=rule.asked, emptied_releases=frozenset({(KEPT, "2026-policy")}), state=rule.state
    )
    done = rewrite_directory(
        {"occurrences.jsonl": occurrences, "camp_paths.jsonl": beside}, emptied, label="openev"
    )
    assert {name: getattr(result, "rows_dropped", None) for name, result in done.items()} == {
        "occurrences.jsonl": 1,
        "camp_paths.jsonl": 2,
    }
