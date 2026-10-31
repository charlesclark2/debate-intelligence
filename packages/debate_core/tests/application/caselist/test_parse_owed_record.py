"""The parse-owed file: what it holds, what it refuses, and what clears it (`v1-e40-t08`).

:class:`~debate_core.application.caselist_sync.ParseOwed` is the run's record of the parses it
owes. The whole-run behaviour is `packages/debate_cli/tests/bucket_mode/test_parse_owed.py`'s; these
pin the record itself: caselist slugs, snapshot names and parser versions and nothing else (the
spec's forbidden list), a removal clearing only the snapshots it reached, and a file that cannot be
read never taken for nothing owed. Every body is written by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist_sync import (
    FullParseOwed,
    ParseOwed,
    ParseOwedUnreadable,
    ParsesOwed,
    PendingSnapshot,
    parses_owed_sentence,
)

WEEK: Final = PendingSnapshot(caselist="hsld26", snapshot="2026-10-21")
LATER_WEEK: Final = PendingSnapshot(caselist="hsld26", snapshot="2026-10-28")
CAMP: Final = PendingSnapshot(caselist="openev", snapshot="2026-policy")
BUMP: Final = FullParseOwed(caselist="hsld26", parser_version="2026.10.27-docx-7")


def body(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_what_is_owed_is_written_in_the_order_owed_and_read_back(tmp_path: Path) -> None:
    record = ParseOwed(tmp_path / "caselist-sync-parse-owed.json")

    record.owe(snapshots=[WEEK, CAMP])
    record.owe(snapshots=[CAMP, LATER_WEEK], full_parses=[BUMP])

    assert body(record.path) == {
        "full_parses": [{"caselist": "hsld26", "parser_version": "2026.10.27-docx-7"}],
        "snapshots": [
            {"caselist": "hsld26", "snapshot": "2026-10-21"},
            {"caselist": "openev", "snapshot": "2026-policy"},
            {"caselist": "hsld26", "snapshot": "2026-10-28"},
        ],
    }
    assert record.read() == ParsesOwed(snapshots=(WEEK, CAMP, LATER_WEEK), full_parses=(BUMP,))
    assert record.read().caselists == ("hsld26", "openev")


def test_a_published_parsed_store_clears_every_entry_of_its_caselist_and_removes_the_file_at_the_last(
    tmp_path: Path,
) -> None:
    written: list[Path] = []
    record = ParseOwed(tmp_path / "caselist-sync-parse-owed.json", on_written=written.append)
    record.owe(snapshots=[WEEK, CAMP], full_parses=[BUMP])

    record.clear_caselist("hsld26")
    assert record.read() == ParsesOwed(snapshots=(CAMP,))
    record.clear_caselist("openev")

    assert not record.path.exists(), "no file when nothing is owed"
    assert written == [record.path] * 3, "each write and the removal are saved, in bucket mode to the bucket"


def test_a_removal_clears_the_snapshots_it_reached_and_nothing_else(tmp_path: Path) -> None:
    record = ParseOwed(tmp_path / "caselist-sync-parse-owed.json")
    record.owe(snapshots=[WEEK, LATER_WEEK, CAMP], full_parses=[BUMP])

    record.clear_snapshots([WEEK, PendingSnapshot(caselist="hspf26", snapshot="2026-10-21")])

    assert record.read() == ParsesOwed(snapshots=(LATER_WEEK, CAMP), full_parses=(BUMP,)), (
        "the other week of the same caselist, the camp release and the full parse stay owed"
    )


@pytest.mark.parametrize(
    "entry",
    [
        PendingSnapshot(caselist="hsld26", snapshot="manifests/hsld26/2026-10-21.jsonl"),
        PendingSnapshot(caselist="hsld26", snapshot="Cedar Hollow ZaLu"),
        PendingSnapshot(caselist="hsld26", snapshot="ZaLu"),
        PendingSnapshot(caselist="Cedar Hollow/ZaLu", snapshot="2026-10-21"),
        PendingSnapshot(caselist="/Users/someone/.debate-research/dev", snapshot="2026-10-21"),
    ],
)
def test_a_snapshot_entry_that_is_not_a_slug_and_a_snapshot_name_is_refused_and_nothing_written(
    tmp_path: Path, entry: PendingSnapshot
) -> None:
    record = ParseOwed(tmp_path / "caselist-sync-parse-owed.json")
    record.owe(snapshots=[WEEK])
    before = record.path.read_bytes()

    with pytest.raises(ValueError, match="no place in the store|caselist"):
        record.owe(snapshots=[CAMP, entry])

    assert record.path.read_bytes() == before


@pytest.mark.parametrize("version", ["docx-7", "Cedar Hollow ZaLu", "2026.10.27-docx-7/hsld26", "../x"])
def test_a_full_parse_entry_that_is_not_a_parser_version_is_refused(tmp_path: Path, version: str) -> None:
    record = ParseOwed(tmp_path / "caselist-sync-parse-owed.json")

    with pytest.raises(ValueError, match="parser version"):
        record.owe(full_parses=[FullParseOwed(caselist="hsld26", parser_version=version)])

    assert not record.path.exists()


@pytest.mark.parametrize(
    "written",
    [
        "not json",
        '{"snapshots": []}',
        '{"snapshots": [{"caselist": "hsld26", "snapshot": "2026-10-21", "path": "x"}], "full_parses": []}',
        '{"snapshots": [{"caselist": "hsld26", "snapshot": "ZaLu"}], "full_parses": []}',
    ],
)
def test_a_file_that_is_not_what_is_written_is_unreadable_and_never_written_over(
    tmp_path: Path, written: str
) -> None:
    record = ParseOwed(tmp_path / "caselist-sync-parse-owed.json")
    record.path.write_text(written, encoding="utf-8")

    with pytest.raises(ParseOwedUnreadable) as unreadable:
        record.read()
    for change in (lambda: record.owe(snapshots=[WEEK]), lambda: record.clear_caselist("hsld26")):
        with pytest.raises(ParseOwedUnreadable):
            change()

    assert record.path.read_text(encoding="utf-8") == written
    assert "ZaLu" not in str(unreadable.value), "it quotes nothing the file holds"


def test_what_runs_and_status_say() -> None:
    owed = ParsesOwed(
        snapshots=(WEEK, CAMP),
        full_parses=(BUMP, FullParseOwed(caselist="openev", parser_version="2026.10.27-docx-7")),
    )

    assert parses_owed_sentence(owed) == (
        "Parse owed: hsld26 2026-10-21, openev 2026-policy. The next caselist pull parses and publishes "
        "them, whether or not it imports anything. Full parse owed under parser version "
        "2026.10.27-docx-7: hsld26, openev. The next caselist pull parses and publishes it before it "
        "builds the search index."
    )
    assert parses_owed_sentence(ParsesOwed()) is None
