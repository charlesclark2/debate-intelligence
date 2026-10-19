"""What `caselist status`'s error panels print, and its two new findings (`v1-e30-t24`).

Each report is built by hand, field by field, as in `test_caselist_status_held_paths.py`: the
renderers are functions of what they are given. The comparison behind them is in
`packages/debate_core/tests/application/caselist/`, and the command end to end in
`tests/smoke/test_caselist_remove_smoke.py` and `packages/debate_cli/tests/test_caselist_publish.py`.

* **The panels (item 4).** A failing status printed its whole `--json` details record in the panel,
  under the table that already counts it: about 1,000 lines of sha256 in prod on 2026-10-18, for
  four unpublished snapshots. The `CASELIST_DRIFT` panel now prints counts and digest prefixes of at
  most twelve characters, one line per differing snapshot. The `REMOVAL_RESIDUE` panel, the other
  one status raises with that record, does the same. The JSON keeps every field.
* **A withdrawn copy's residue (item 1)** fails the command as `REMOVAL_RESIDUE`.
* **An upload an import refused at a held path (item 3)**, that the re-run has not listed, is named
  by caselist, digest prefix and request, and its request is owed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from typing import Final

from rich.console import Console

from debate_cli.commands.caselist import (
    _status_failure,  # pyright: ignore[reportPrivateUsage]
    _status_table,  # pyright: ignore[reportPrivateUsage]
    status_summary,
)
from debate_cli.output import CommandFailure, _render_failure  # pyright: ignore[reportPrivateUsage]
from debate_core.application.caselist.removal_residue import CaselistResidue, ResidueFile, WithdrawnCopy
from debate_core.application.caselist.status_service import CaselistStatusReport

from .test_caselist_remove_plan_output import CASELIST, IDENTIFYING, SETTINGS
from .test_caselist_status_held_paths import snapshot

WHOLE_DIGEST: Final = re.compile(r"[0-9a-f]{64}")
DIGEST_PREFIX: Final = re.compile(r"\b[0-9a-f]{12,}\b")
SOURCES_PER_WEEK: Final = 250
"""About what an unpublished prod week of hsld26 is missing from the bucket."""
WEEKS: Final = ("2026-09-29", "2026-10-06", "2026-10-13")
WITHDRAWN: Final = "c0ffee000000" + "2" * 52
REMOVED: Final = "deadbeef0000" + "3" * 52
REQUEST: Final = "RM-2026-07"


def digests(week: str, count: int) -> tuple[str, ...]:
    return tuple(sorted(hashlib.sha256(f"{week}/{one}".encode()).hexdigest() for one in range(count)))


def unpublished(week: str) -> object:
    """A week this machine imported and never published: no manifest and no source in the bucket."""
    return snapshot(
        week,
        manifest_present=False,
        sources=SOURCES_PER_WEEK,
        local_files=SOURCES_PER_WEEK,
        published_sources=0,
        missing_sources=digests(week, SOURCES_PER_WEEK),
    )


def three_weeks_unpublished() -> CaselistStatusReport:
    """Ten weeks in the bucket, and the last three not: the prod status of 2026-10-18, in small."""
    agreeing = [snapshot(f"2026-07-{day:02d}") for day in range(1, 29, 4)]
    return CaselistStatusReport(snapshots=(*agreeing, *(unpublished(week) for week in WEEKS)))  # type: ignore[arg-type]


def panel_text(failure: CommandFailure) -> str:
    """The panel as a person's terminal shows it, wide enough that no line wraps."""
    console = Console(file=io.StringIO(), width=2000, record=True, color_system=None)
    console.print(_render_failure(failure))
    return console.export_text()


def panel_lines(failure: CommandFailure) -> list[str]:
    """The panel's lines of text, its border taken off."""
    return [
        line.strip("│ ").rstrip()
        for line in panel_text(failure).splitlines()
        if line.strip() and not line.lstrip().startswith(("╭", "╰"))
    ]


class TestTheDriftPanel:
    def test_it_prints_no_whole_digest(self) -> None:
        report = three_weeks_unpublished()

        shown = panel_text(_status_failure(report, status_summary(report, SETTINGS)))

        assert WHOLE_DIGEST.findall(shown) == []
        assert all(len(prefix) <= 12 for prefix in DIGEST_PREFIX.findall(shown))

    def test_it_prints_at_most_one_line_per_differing_snapshot(self) -> None:
        """The message names each of them, and below it one line each counts what differs: no line
        for a snapshot that agrees, and nothing that grows with the sources a week holds."""
        report = three_weeks_unpublished()
        failure = _status_failure(report, status_summary(report, SETTINGS))

        lines = panel_lines(failure)

        for week in WEEKS:
            counted = [line for line in lines if line.startswith(f"{CASELIST} {week}:")]
            assert len(counted) == 1, lines
            assert f"{SOURCES_PER_WEEK} source(s) not in the bucket" in counted[0]
        assert not [line for line in lines if line.startswith(f"{CASELIST} 2026-07-")]
        assert len(lines) <= len(WEEKS) + 8, lines

    def test_a_snapshots_line_says_each_kind_of_difference_by_count(self) -> None:
        mismatched = snapshot(
            "2026-09-15",
            checksum_mismatches=(
                f"manifests/{CASELIST}/2026-09-15.jsonl",
                f"raw/caselist/{CASELIST}/sha256/aa/bb/{'ab' * 32}",
            ),
            missing_local=digests("local", 2),
            suppressed_rows=digests("rows", 5),
        )
        report = CaselistStatusReport(snapshots=(mismatched,))

        (line,) = [
            one
            for one in panel_lines(_status_failure(report, status_summary(report, SETTINGS)))
            if one.startswith(f"{CASELIST} 2026-09-15:")
        ]

        assert line == (
            f"{CASELIST} 2026-09-15: manifest mismatch, 2 source(s) not on this machine "
            f"(sha256 {', '.join(one[:12] for one in digests('local', 2))}), 1 source mismatch(es) "
            f"(sha256 {'ab' * 6}), 5 suppressed row(s) "
            f"(sha256 {', '.join(one[:12] for one in digests('rows', 5)[:3])} and 2 more)"
        )

    def test_the_json_keeps_every_field(self) -> None:
        """`--json` puts the failure's details in `error.details`, which are still the whole report."""
        report = three_weeks_unpublished()
        payload = status_summary(report, SETTINGS)

        failure = _status_failure(report, payload)

        assert failure.details == payload
        snapshots = failure.details["snapshots"]
        assert isinstance(snapshots, list)
        missing = [entry["missing_sources"] for entry in snapshots if isinstance(entry, dict)]
        assert missing[-len(WEEKS) :] == [list(digests(week, SOURCES_PER_WEEK)) for week in WEEKS]


def residue_left(files: int, *, withdrawn: bool = False) -> CaselistStatusReport:
    """Every snapshot agrees, and the bucket holds versions of removed files, or a withdrawn copy."""
    return CaselistStatusReport(
        snapshots=tuple(snapshot(f"2026-07-{day:02d}") for day in range(1, 29, 2)),
        residue=(
            CaselistResidue(
                caselist=CASELIST,
                checked=True,
                files=tuple(ResidueFile(sha256=one, noncurrent_versions=1) for one in digests("gone", files)),
                withdrawn_copies=(WithdrawnCopy(sha256=WITHDRAWN, request_id=REQUEST, current_objects=1),)
                if withdrawn
                else (),
            ),
        ),
    )


class TestTheResiduePanel:
    """The other panel status raises with the whole record as its details."""

    def test_it_prints_counts_and_prefixes_and_keeps_every_field_in_the_json(self) -> None:
        report = residue_left(4)
        payload = status_summary(report, SETTINGS)

        failure = _status_failure(report, payload)

        assert failure.code == "REMOVAL_RESIDUE"
        lines = panel_lines(failure)
        assert WHOLE_DIGEST.findall("\n".join(lines)) == []
        assert not [line for line in lines if line.startswith("snapshots: [")], "the record, dumped"
        assert len(lines) <= 8, lines
        assert failure.details == payload


class TestAWithdrawnCopyLeftFailsTheCommand:
    def test_it_is_removal_residue_named_by_caselist_prefix_and_request(self) -> None:
        report = residue_left(0, withdrawn=True)

        failure = _status_failure(report, status_summary(report, SETTINGS))

        assert not report.in_sync
        assert failure.code == "REMOVAL_RESIDUE"
        told = " ".join(failure.message.split())
        assert (
            f"{CASELIST}: 1 current object(s), 0 noncurrent version(s) and 0 delete marker(s) of 1 file(s) "
            f"withdrawn from {CASELIST} (sha256 {WITHDRAWN[:12]}, {REQUEST})"
        ) in told
        assert WITHDRAWN not in told

    def test_beside_a_removed_files_residue_both_are_named(self) -> None:
        report = residue_left(1, withdrawn=True)

        told = " ".join(_status_failure(report, status_summary(report, SETTINGS)).message.split())

        assert f"of 1 file(s) (sha256 {digests('gone', 1)[0][:12]})" in told
        assert f"withdrawn from {CASELIST} (sha256 {WITHDRAWN[:12]}, {REQUEST})" in told

    def test_the_table_no_longer_says_the_clean_line_and_says_what_to_run(self) -> None:
        caption = " ".join((_status_table(residue_left(0, withdrawn=True), SETTINGS).caption or "").split())

        assert f"WITHDRAWN COPIES LEFT in {CASELIST}:" in caption
        assert "REMOVAL RESIDUE in" not in caption, "the copy has a line of its own"
        assert "No version of a removed file is left" not in caption
        assert "Run that removal again, dry run first, then --execute" in caption


class TestAnUploadRefusedAtImport:
    def report(self) -> CaselistStatusReport:
        from debate_core.application.caselist.status_service import RefusedAtImport

        return CaselistStatusReport(
            snapshots=(snapshot("2026-10-06"),),
            refused_at_import=(RefusedAtImport(caselist=CASELIST, sha256=WITHDRAWN, request_id=REQUEST),),
        )

    def test_its_request_is_owed_and_the_command_still_succeeds(self) -> None:
        report = self.report()

        assert report.removals_owed == (REQUEST,)
        assert report.in_sync

    def test_the_table_names_it_by_caselist_prefix_and_request_and_says_what_to_run(self) -> None:
        caption = _status_table(self.report(), SETTINGS).caption or ""
        told = " ".join(caption.split())

        assert (
            f"REFUSED AT IMPORT AT A HELD PATH in {CASELIST}: 1 upload(s) the same removal has not yet "
            f"listed (sha256 {WITHDRAWN[:12]}, {REQUEST})."
        ) in told
        assert (
            "A held row, a held upload in the inbox or an upload an import refused at a held path means "
            f"{REQUEST} is owed again: run the same removal again"
        ) in told
        assert WITHDRAWN not in caption
        assert not [word for word in IDENTIFYING if word in caption]

    def test_the_json_gives_one_entry_per_caselist_by_count_prefix_and_request(self) -> None:
        data = status_summary(self.report(), SETTINGS)

        assert data["refused_at_import"] == [
            {"caselist": CASELIST, "uploads": 1, "sha256_prefixes": [WITHDRAWN[:12]], "requests": [REQUEST]}
        ]
        assert data["removals_owed"] == [REQUEST]
        assert WITHDRAWN not in json.dumps(data)
