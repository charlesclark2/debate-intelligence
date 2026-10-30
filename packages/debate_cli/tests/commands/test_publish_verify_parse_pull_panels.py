"""What the failure panels of `caselist publish`, `verify`, `caselist parse` and `caselist pull` print (`v1-e30-t27`).

`v1-e30-t24` made `caselist status`'s panels print counts and digest prefixes instead of the whole
`--json` record (`test_caselist_status_panels.py`). These four commands still printed theirs whole:
a key per line of the payload, each list of sha256 in full, the bucket keys, and in `caselist
publish` and `caselist pull` a message that joins every failed digest. Each panel now prints counts,
at most three twelve-character prefixes per kind of digest with how many more there are, one line
per caselist, snapshot or stage that differs, and a closing line saying every value is under
`error.details` in `--json`.

`--json` is not changed by any of it. Each failure's envelope is compared whole, byte for byte,
with the one the code before this task wrote for the same failure, recorded under
`failure_envelopes/` before any source changed; a key dropped, renamed or reshaped fails.

Each report is built by hand, field by field, as in `test_caselist_status_panels.py`: the failure
builders are functions of what they are given. The commands end to end are in
`test_caselist_publish.py`, `test_caselist_parse.py`, `test_verify_command.py` and
`test_caselist_pull.py`.
"""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_cli.commands.caselist import (
    _publish_failure,  # pyright: ignore[reportPrivateUsage]
    publish_summary,
)
from debate_cli.commands.caselist_parse import (
    _failure as _parse_failure,  # pyright: ignore[reportPrivateUsage]
)
from debate_cli.commands.caselist_parse import (
    _publish_failure as _parsed_publish_failure,  # pyright: ignore[reportPrivateUsage]
)
from debate_cli.commands.caselist_parse import parse_summary, publish_only_summary
from debate_cli.commands.caselist_pull import (
    _pull_failure,  # pyright: ignore[reportPrivateUsage]
    pull_summary,
)
from debate_cli.commands.verify import (
    _invalid_manifest,  # pyright: ignore[reportPrivateUsage]
    _unverified,  # pyright: ignore[reportPrivateUsage]
)
from debate_cli.output import CliOutput, CommandFailure, OutputMode
from debate_core.application.caselist.parsed_publish import ParsedObjectOutcome, ParsedPublishReport
from debate_core.application.caselist.publish_plan import (
    HeldRow,
    ManifestAction,
    PlannedSource,
    PublishPlan,
    SnapshotPlan,
    SourceAction,
)
from debate_core.application.caselist.publish_service import (
    ManifestOutcome,
    PublishReport,
    SnapshotOutcome,
    SourceOutcome,
    SourceResult,
)
from debate_core.application.caselist_parse import ParsePlan, ParseRunReport, StoreTotals
from debate_core.application.caselist_sync import (
    DriftKind,
    ParsedStoreOwed,
    RunSummary,
    SnapshotDrift,
    StageOutcome,
    StageRecord,
    SyncStage,
)
from debate_core.application.verify_manifest import (
    CardVerdict,
    InvalidManifest,
    ManifestVerificationReport,
    ReportedReason,
)
from debate_core.domain import VerificationStatus
from debate_core.evidence.verification_types import ReasonCode

from .test_caselist_remove_plan_output import CASELIST, SETTINGS
from .test_caselist_status_panels import DIGEST_PREFIX, WHOLE_DIGEST, digests, panel_lines, panel_text

ENVELOPES: Final = Path(__file__).parent / "failure_envelopes"
"""Each failure's `--json` envelope as the code before `v1-e30-t27` wrote it, one line per file."""

CLOSING_LINE: Final = "every value: in full under error.details of --json"
MANY: Final = 40
"""Far more digests of one kind than a panel names: it names three and counts the rest."""
AGREEING: Final = "2026-09-29"
WEEKS: Final = ("2026-10-06", "2026-10-13")
"""The two snapshots that differ, in every report below that has snapshots."""
VERSION: Final = "2026.10.20-docx-1"
MANIFEST_PATH: Final = "/Users/someone/Documents/cards/Lakeshore Open aff.json"
"""Where a person's manifest was: a path under their home directory, which names a tournament."""

#: What may never be in a panel: bucket keys, which are paths, and a path on this machine.
PATH_PARTS: Final = ("raw/", "manifests/", "parsed/", "sha256/", "/Users/", "Lakeshore")


def source_key(digest: str) -> str:
    return f"raw/caselist/{CASELIST}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def manifest_key(week: str) -> str:
    return f"manifests/{CASELIST}/{week}.jsonl"


def parsed_key(digest: str) -> str:
    return f"parsed/{CASELIST}/{VERSION}/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jsonl"


# ------------------------------------------------------------------------------------------------
# The reports, by hand
# ------------------------------------------------------------------------------------------------


def planned(digest: str, action: SourceAction) -> PlannedSource:
    return PlannedSource(sha256=digest, size=1000, key=source_key(digest), action=action)


def snapshot_plan(
    week: str,
    sources: tuple[PlannedSource, ...],
    *,
    suppressed_rows: tuple[str, ...] = (),
    held_rows: tuple[HeldRow, ...] = (),
    held_skipped_rows: tuple[str, ...] = (),
) -> SnapshotPlan:
    return SnapshotPlan(
        caselist=CASELIST,
        snapshot=week,
        sources=sources,
        manifest_key=manifest_key(week),
        manifest_size=500,
        manifest_action=ManifestAction.UPLOAD,
        suppressed_rows=suppressed_rows,
        held_rows=held_rows,
        held_skipped_rows=held_skipped_rows,
    )


def blocked_publish() -> PublishReport:
    """A dry run whose plan blocks two weeks: one by its sources, one by rows a removal stops."""
    agreeing = snapshot_plan(AGREEING, tuple(planned(one, SourceAction.UPLOAD) for one in digests("up", 4)))
    by_sources = snapshot_plan(
        WEEKS[0],
        (
            *(planned(one, SourceAction.MISSING_LOCALLY) for one in digests("missing", MANY)),
            *(planned(one, SourceAction.MISMATCHED) for one in digests("mismatched", 2)),
            *(planned(one, SourceAction.UPLOAD) for one in digests("fine", 3)),
        ),
    )
    by_rows = snapshot_plan(
        WEEKS[1],
        tuple(planned(one, SourceAction.UPLOAD) for one in digests("later", 2)),
        suppressed_rows=digests("suppressed", 5),
        held_rows=tuple(HeldRow(one, "RM-2026-07") for one in digests("held", 2)),
        held_skipped_rows=("RM-2026-09",),
    )
    return PublishReport(plan=PublishPlan(CASELIST, (agreeing, by_sources, by_rows)), applied=False)


def source_outcome(digest: str, result: SourceResult, code: str | None = None) -> SourceOutcome:
    message = None if code is None else f"{code}: the store did not confirm it"
    return SourceOutcome(sha256=digest, key=source_key(digest), result=result, error_code=code, error_message=message)


def incomplete_publish() -> PublishReport:
    """An applied run: one week complete, one withheld by its failed sources, one whose manifest failed."""
    complete = tuple(source_outcome(one, SourceResult.UPLOADED) for one in digests("up", 4))
    withheld = (
        *(source_outcome(one, SourceResult.FAILED, "STORE_UNAVAILABLE") for one in digests("failed", MANY)),
        source_outcome(digests("checksum", 1)[0], SourceResult.FAILED, "CHECKSUM_MISMATCH"),
        *(source_outcome(one, SourceResult.SKIPPED) for one in digests("skipped", 3)),
    )
    manifest_failed = tuple(source_outcome(one, SourceResult.SKIPPED) for one in digests("later", 2))
    plan = PublishPlan(
        CASELIST,
        tuple(
            snapshot_plan(week, tuple(planned(outcome.sha256, SourceAction.UPLOAD) for outcome in outcomes))
            for week, outcomes in ((AGREEING, complete), (WEEKS[0], withheld), (WEEKS[1], manifest_failed))
        ),
    )
    return PublishReport(
        plan=plan,
        applied=True,
        snapshots=(
            SnapshotOutcome(CASELIST, AGREEING, manifest_key(AGREEING), complete, ManifestOutcome.UPLOADED),
            SnapshotOutcome(
                CASELIST,
                WEEKS[0],
                manifest_key(WEEKS[0]),
                withheld,
                ManifestOutcome.WITHHELD,
                manifest_error="withheld: 251 source(s) not confirmed",
            ),
            SnapshotOutcome(
                CASELIST,
                WEEKS[1],
                manifest_key(WEEKS[1]),
                manifest_failed,
                ManifestOutcome.FAILED,
                manifest_error="the store did not answer",
                manifest_error_code="STORE_UNAVAILABLE",
            ),
        ),
    )


def parsed_publish(*, failed: int = 30) -> ParsedPublishReport:
    """A parsed store's publish that left `failed` source objects and one aggregate unconfirmed."""
    objects = (
        *(
            ParsedObjectOutcome(parsed_key(one), SourceResult.UPLOADED, aggregate=False)
            for one in digests("parsed", 6)
        ),
        *(
            ParsedObjectOutcome(
                parsed_key(one),
                SourceResult.FAILED,
                aggregate=False,
                error_code="STORE_UNAVAILABLE",
                error_message="StoreUnavailable: the store did not answer",
            )
            for one in digests("unconfirmed", failed)
        ),
        ParsedObjectOutcome(
            f"parsed/{CASELIST}/{VERSION}/occurrences.jsonl",
            SourceResult.FAILED,
            aggregate=True,
            error_code="CHECKSUM_MISMATCH",
            error_message="the bucket's digest is not this file's",
        ),
    )
    return ParsedPublishReport(
        caselist=CASELIST,
        version=VERSION,
        prefix=f"parsed/{CASELIST}/{VERSION}",
        objects=objects,
        aggregates_withheld=True,
    )


def parse_run() -> ParseRunReport:
    """A run of 300 sources, 50 of the 290 it tried to read failed: 17.2%, over a 5% threshold."""
    plan = ParsePlan(
        caselist=CASELIST,
        version=VERSION,
        new_version=False,
        superseded=None,
        parser_version=VERSION,
        profile_version="2026.10.01",
        snapshot=None,
        reparse=False,
        sources=(),
        in_scope=420,
        suppressed=2,
        to_parse=(None,) * 300,  # type: ignore[arg-type]
        suppression=None,  # type: ignore[arg-type]
    )
    return ParseRunReport(
        plan=plan,
        applied=True,
        threshold=0.05,
        workers=4,
        parsed=240,
        cards=1800,
        unsupported={"PDF": 10},
        failed={"UNREADABLE_DOCX": 40, "PARSE_TIMEOUT": 10},
        store=StoreTotals(sources=418, parsed=358, unsupported=10, failed=50, cards=2700, occurrences=2900, clusters=2100),
        elapsed_seconds=12.5,
    )


def incomplete_pull() -> RunSummary:
    """A run whose publish left two weeks incomplete, whose report found one, and whose parse owes a publish.

    The reasons are the sentences `caselist_sync` writes: the publish stage's names every failed
    digest whole, as `PublishReport.failed_sha256` gives them.
    """
    started = datetime(2026, 10, 27, 6, 0, tzinfo=UTC)
    failed_publish = "; ".join(
        f"{CASELIST} {week}: " + ", ".join(found)
        for week, found in ((WEEKS[0], digests("failed", MANY)), (WEEKS[1], digests("later", 2)))
    )
    drift = SnapshotDrift(CASELIST, WEEKS[0], (DriftKind.MISSING,))
    return RunSummary(
        run_id="20261027T060000Z",
        started_at=started,
        finished_at=started,
        dry_run=False,
        caselists=(CASELIST,),
        stages=(
            StageRecord(SyncStage.DOWNLOAD, StageOutcome.COMPLETED, "2 archive(s) downloaded"),
            StageRecord(SyncStage.IMPORT, StageOutcome.COMPLETED, "2 archive(s) imported"),
            StageRecord(
                SyncStage.PUBLISH,
                StageOutcome.FAILED,
                f"12 object(s) published; incomplete: {failed_publish}",
                error_codes=("STORE_UNAVAILABLE",),
            ),
            StageRecord(
                SyncStage.PARSE,
                StageOutcome.FAILED,
                f"parsed 40 source(s); the parsed store of {CASELIST} is not published",
                error_codes=("STORE_UNAVAILABLE",),
                hint=f"Run `debate-research caselist parse --caselist {CASELIST} --publish-only` to publish it.",
            ),
            StageRecord(
                SyncStage.REPORT,
                StageOutcome.FAILED,
                f"1 snapshot(s) confirmed; not in sync: {drift.sentence}",
                error_codes=("CASELIST_DRIFT",),
                drift=(drift,),
            ),
        ),
        archives_downloaded=2,
        files_imported=257,
        objects_published=12,
        snapshots_imported=WEEKS,
        pending_publish=tuple(f"{CASELIST} {week}" for week in WEEKS),
        parsed_stores_owed=(ParsedStoreOwed(CASELIST, publish_only=True),),
    )


SNAPSHOTS: Final = ("01JB7Q0000000000000000SNAP", "01JB7Q0000000000000000SNBQ")


def verdict(position: int, status: VerificationStatus, snapshot: str | None, *codes: ReasonCode) -> CardVerdict:
    return CardVerdict(
        position=position,
        card_id=f"0CARD00000000000000000000{position}",
        tag=f"Card {position}",
        status=status,
        reasons=tuple(ReportedReason(code=code, detail=f"{code.value} at offset 3") for code in codes),
        snapshot_id=snapshot,
        checks_run=(),
        verifier_version=None,
    )


def unverified_manifest() -> ManifestVerificationReport:
    """Six cards: two verified, three unverified from two snapshots, and one that names no snapshot."""
    verified, unverified = VerificationStatus.VERIFIED, VerificationStatus.UNVERIFIED
    return ManifestVerificationReport(
        manifest_version=2,
        generated_at=datetime(2026, 10, 27, 12, 0, tzinfo=UTC),
        cards=(
            verdict(0, verified, SNAPSHOTS[0]),
            verdict(1, unverified, SNAPSHOTS[0], ReasonCode.TEXT_MISMATCH),
            verdict(2, unverified, SNAPSHOTS[0], ReasonCode.TEXT_MISMATCH, ReasonCode.SPAN_OUT_OF_RANGE),
            verdict(3, verified, SNAPSHOTS[1]),
            verdict(4, unverified, SNAPSHOTS[1], ReasonCode.SNAPSHOT_MISSING),
            verdict(5, unverified, None, ReasonCode.CARD_INVALID),
        ),
    )


# ------------------------------------------------------------------------------------------------
# Each failure, as its command builds it
# ------------------------------------------------------------------------------------------------


def publish_blocked() -> CommandFailure:
    report = blocked_publish()
    return _publish_failure(report, publish_summary(report, SETTINGS))


def publish_incomplete() -> CommandFailure:
    report = incomplete_publish()
    return _publish_failure(report, publish_summary(report, SETTINGS))


def parse_rate_exceeded() -> CommandFailure:
    report, published = parse_run(), parsed_publish()
    failure = _parse_failure(report, published, parse_summary(report, published, SETTINGS))
    assert failure is not None
    return failure


def parse_publish_incomplete() -> CommandFailure:
    published = parsed_publish()
    failure = _parsed_publish_failure(published, publish_only_summary(published, SETTINGS))
    assert failure is not None
    return failure


def pull_incomplete() -> CommandFailure:
    summary = incomplete_pull()
    return _pull_failure(summary, pull_summary(summary, SETTINGS))


def verify_unverified() -> CommandFailure:
    report = unverified_manifest()
    return _unverified(report, report.model_dump(mode="json"))


def verify_invalid_manifest() -> CommandFailure:
    invalid = InvalidManifest("$.cards[3].tag", "None is not of type 'string'", violations=2)
    return _invalid_manifest(invalid, MANIFEST_PATH)


#: Each failure, with the command it is the failure of: the name its envelope is recorded under.
FAILURES: Final = {
    "caselist publish, PUBLISH_BLOCKED": ("caselist publish", publish_blocked),
    "caselist publish, PUBLISH_INCOMPLETE": ("caselist publish", publish_incomplete),
    "caselist parse, PARSE_FAILURE_RATE_EXCEEDED": ("caselist parse", parse_rate_exceeded),
    "caselist parse, PARSED_PUBLISH_INCOMPLETE": ("caselist parse", parse_publish_incomplete),
    "caselist pull, CASELIST_PULL_INCOMPLETE": ("caselist pull", pull_incomplete),
    "verify, UNVERIFIED": ("verify", verify_unverified),
    "verify, INVALID_MANIFEST": ("verify", verify_invalid_manifest),
}


def envelope_file(name: str) -> Path:
    """`caselist publish, PUBLISH_BLOCKED` is recorded in `caselist-publish-PUBLISH_BLOCKED.json`."""
    return ENVELOPES / f"{re.sub(r'[ ,]+', '-', name)}.json"


def envelope_of(failure: CommandFailure, command: str) -> str:
    """The `--json` envelope the command writes for `failure`, exactly as it reaches stdout."""
    stdout = io.StringIO()
    CliOutput(OutputMode.JSON, stdout=stdout, stderr=io.StringIO()).failure(failure, command=command)
    return stdout.getvalue()


def lines_starting(failure: CommandFailure, start: str) -> list[str]:
    return [line for line in panel_lines(failure) if line.startswith(start)]


# ------------------------------------------------------------------------------------------------
# Every panel
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FAILURES)
class TestEveryPanel:
    def test_it_prints_no_whole_digest(self, name: str) -> None:
        shown = panel_text(FAILURES[name][1]())

        assert WHOLE_DIGEST.findall(shown) == []
        assert all(len(prefix) <= 12 for prefix in DIGEST_PREFIX.findall(shown)), shown

    def test_it_prints_no_key_and_no_path(self, name: str) -> None:
        shown = panel_text(FAILURES[name][1]())

        assert [part for part in PATH_PARTS if part in shown] == [], shown

    def test_it_ends_by_saying_every_value_is_in_the_json(self, name: str) -> None:
        lines = panel_lines(FAILURES[name][1]())

        assert CLOSING_LINE in lines, lines

    def test_the_json_envelope_is_the_one_written_before(self, name: str) -> None:
        """Every field of `error`, `details` whole among them, byte for byte as before `v1-e30-t27`."""
        command, build = FAILURES[name]

        assert envelope_of(build(), command) == envelope_file(name).read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------
# One line per thing that differs, and a few prefixes per kind
# ------------------------------------------------------------------------------------------------


class TestThePublishPanels:
    def test_a_blocked_plan_prints_one_line_per_blocked_snapshot(self) -> None:
        failure = publish_blocked()

        lines = panel_lines(failure)

        assert lines_starting(failure, f"{CASELIST} {AGREEING}") == []
        assert lines_starting(failure, f"{CASELIST} {WEEKS[0]}:") == [
            f"{CASELIST} {WEEKS[0]}: {MANY} source(s) missing from this machine "
            f"(sha256 {', '.join(one[:12] for one in digests('missing', MANY)[:3])} and {MANY - 3} more), "
            f"2 source(s) mismatched in the bucket (sha256 {', '.join(one[:12] for one in digests('mismatched', 2))})"
        ]
        assert lines_starting(failure, f"{CASELIST} {WEEKS[1]}:") == [
            f"{CASELIST} {WEEKS[1]}: manifest withheld for 5 suppressed row(s) "
            f"(sha256 {', '.join(one[:12] for one in digests('suppressed', 5)[:3])} and 2 more), "
            f"2 row(s) at a held path (sha256 {', '.join(one[:12] for one in digests('held', 2))}), "
            "1 skipped member row(s) at a held path (RM-2026-09)"
        ]
        assert len(lines) <= len(WEEKS) + 7, lines

    def test_a_blocked_plans_message_names_no_digest_and_the_json_keeps_them_all(self) -> None:
        failure = publish_blocked()

        assert panel_lines(failure)[0] == (
            f"{MANY + 2} source(s) cannot be published as planned (a checksum mismatch in the bucket, "
            "or missing from this machine)"
        )
        assert len(WHOLE_DIGEST.findall(failure.message)) == MANY + 2

    def test_an_incomplete_run_prints_one_line_per_incomplete_snapshot(self) -> None:
        failure = publish_incomplete()

        lines = panel_lines(failure)

        assert lines_starting(failure, f"{CASELIST} {AGREEING}") == []
        assert lines_starting(failure, f"{CASELIST} {WEEKS[0]}:") == [
            f"{CASELIST} {WEEKS[0]}: manifest withheld, {MANY + 1} source(s) failed "
            f"(sha256 {', '.join(one[:12] for one in sorted((*digests('failed', MANY), *digests('checksum', 1)))[:3])} "
            f"and {MANY - 2} more): CHECKSUM_MISMATCH 1, STORE_UNAVAILABLE {MANY}"
        ]
        assert lines_starting(failure, f"{CASELIST} {WEEKS[1]}:") == [
            f"{CASELIST} {WEEKS[1]}: manifest failed (STORE_UNAVAILABLE)"
        ]
        assert lines[0] == f"2 snapshot(s) not complete in the bucket; {MANY + 1} source(s) failed"
        assert len(lines) <= len(WEEKS) + 7, lines


class TestTheParsePanels:
    def test_a_failure_rate_over_the_threshold_prints_counts_and_the_publish_by_prefix(self) -> None:
        failure = parse_rate_exceeded()

        lines = panel_lines(failure)

        assert f"failed: PARSE_TIMEOUT 10, UNREADABLE_DOCX 40" in lines
        assert "failure rate: 17.2% of the 290 source(s) tried, over the 5.0% threshold" in lines
        assert len(lines_starting(failure, "publish:")) == 1
        assert len(lines) <= 9, lines

    def test_an_incomplete_publish_names_a_few_objects_by_prefix_and_counts_the_rest(self) -> None:
        failure = parse_publish_incomplete()

        (line,) = lines_starting(failure, "not confirmed:")

        assert line == (
            "not confirmed: 30 source file(s) "
            f"(sha256 {', '.join(one[:12] for one in digests('unconfirmed', 30)[:3])} and 27 more), "
            "1 aggregate(s) (occurrences.jsonl): CHECKSUM_MISMATCH 1, STORE_UNAVAILABLE 30"
        )
        assert "aggregates: withheld" in panel_lines(failure)
        assert len(panel_lines(failure)) <= 8, panel_lines(failure)


class TestThePullPanel:
    def test_it_prints_one_line_per_failed_stage_and_no_line_for_one_that_completed(self) -> None:
        failure = pull_incomplete()

        lines = panel_lines(failure)

        assert lines[0] == "3 stage(s) of the caselist pull did not complete: publish, parse, report"
        for stage in ("publish", "parse", "report"):
            assert len(lines_starting(failure, f"{stage}:")) == 1, lines
        assert lines_starting(failure, "download:") == lines_starting(failure, "import:") == []
        assert len(lines) <= 3 + 8, lines

    def test_the_publish_stages_digests_are_a_few_prefixes_and_a_count(self) -> None:
        (line,) = lines_starting(pull_incomplete(), "publish:")

        assert line == (
            f"publish: 12 object(s) published; incomplete: {CASELIST} {WEEKS[0]}: "
            f"(sha256 {', '.join(one[:12] for one in digests('failed', MANY)[:3])} and {MANY - 3} more); "
            f"{CASELIST} {WEEKS[1]}: (sha256 {', '.join(one[:12] for one in digests('later', 2))})"
        )

    def test_the_parse_fix_command_stays_readable_in_the_hint(self) -> None:
        """`v1-e34-t31`'s per-caselist command is the fix, not the record: it stays whole."""
        shown = " ".join(panel_text(pull_incomplete()).split())

        assert f"debate-research caselist parse --caselist {CASELIST} --publish-only" in shown


class TestTheVerifyPanels:
    def test_unverified_cards_print_counts_and_one_line_per_snapshot(self) -> None:
        failure = verify_unverified()

        lines = panel_lines(failure)

        assert "cards: 6 in the manifest, 2 verified, 4 unverified" in lines
        assert "reasons: CARD_INVALID 1, SNAPSHOT_MISSING 1, SPAN_OUT_OF_RANGE 1, TEXT_MISMATCH 2" in lines
        assert lines_starting(failure, f"snapshot {SNAPSHOTS[0]}:") == [
            f"snapshot {SNAPSHOTS[0]}: 2 card(s) unverified (TEXT_MISMATCH, SPAN_OUT_OF_RANGE)"
        ]
        assert lines_starting(failure, f"snapshot {SNAPSHOTS[1]}:") == [
            f"snapshot {SNAPSHOTS[1]}: 1 card(s) unverified (SNAPSHOT_MISSING)"
        ]
        assert lines_starting(failure, "no snapshot named:") == [
            "no snapshot named: 1 card(s) unverified (CARD_INVALID)"
        ]
        assert len(lines) <= 3 + 6, lines

    def test_an_invalid_manifest_names_where_it_is_invalid_and_not_the_file(self) -> None:
        lines = panel_lines(verify_invalid_manifest())

        assert "json_path: $.cards[3].tag" in lines
        assert "violations: 2" in lines
        assert not [line for line in lines if MANIFEST_PATH in line or line.startswith("manifest:")]
