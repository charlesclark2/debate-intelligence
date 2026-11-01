"""`files check` and `files build` name each warned or failed card, its check and why (`v1-e33-t12`).

After the checks table, one line per WARN or FAIL result, in the `.quality.md`'s words and order:
`WARN cite-present card 6 (f3ef62b7c151): the card has no cite`, and a result about the whole file
without the card part. `--json` carries the same results under one additive key, `quality.findings`,
each shaped as `<file>.quality.json`'s `results` entries are. A file with no WARN or FAIL prints exactly
the table it printed before.

The reports here are built by hand from :class:`CheckResult` values, and every expected line and entry
is written out from them.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Final

from debate_cli.output import CliOutput, TableSpec
from debate_cli.presenters.files_presenter import Rendered, build_rendered, check_rendered
from debate_core.application.file_build_service import (
    BuildCounts,
    BuildStatus,
    BuiltFiles,
    FileBuildResult,
    FileCheckResult,
)
from debate_core.application.file_quality_service import CheckedFile
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, FileQualityReport, QualityCheck

VERSIONS: Final[dict[str, Any]] = {
    "checker_version": "2026.10.22-file-checks-2",
    "parser_version": "2026.10.27-docx-7",
    "style_profile_version": "2026.09.20-verbatim-1",
    "fingerprint_version": "card-fingerprint-v4",
    "builder_version": "2026.10.24-file-writer-4",
    "docx_sha256": "d" * 64,
    "card_count": 6,
    "manifest_card_count": 6,
}
FIRST: Final = "a1a1a1a1a1a1" + "1" * 52
SECOND: Final = "b2b2b2b2b2b2" + "2" * 52
FIFTH: Final = "e5e5e5e5e5e5" + "5" * 52
SIXTH: Final = "f3ef62b7c151" + "6" * 52
BUILT: Final = Path("/files/built/nhi/states-cp.docx")
CITE_DIFFERS: Final = (
    "the built card's cite differs from the source card's (built 0ad4ba573a4a…, source 6cef145454f2…)"
)

#: Given out of the report's order, and with PASS results among them, on purpose.
RESULTS: Final = (
    CheckResult(
        check=QualityCheck.SIDECAR,
        status=CheckStatus.PASS,
        message="the sidecar is valid and describes this file",
    ),
    CheckResult(
        check=QualityCheck.CITE_PRESENT,
        status=CheckStatus.PASS,
        card_position=5,
        fingerprint=FIFTH,
        message="the card has a cite with a short cite",
    ),
    CheckResult(
        check=QualityCheck.CITE_PRESENT,
        status=CheckStatus.WARN,
        card_position=6,
        fingerprint=SIXTH,
        message="the card has no cite",
    ),
    CheckResult(
        check=QualityCheck.DUPLICATE_CARDS,
        status=CheckStatus.WARN,
        card_position=2,
        fingerprint=SECOND,
        message="a near-duplicate of card 4",
    ),
    CheckResult(
        check=QualityCheck.HEADING_STRUCTURE,
        status=CheckStatus.FAIL,
        section_path=("Politics DA", "Link"),
        paragraph_index=7,
        message="a tag with no block above it, in a file that has blocks",
    ),
    CheckResult(
        check=QualityCheck.MANIFEST_ALIGNMENT,
        status=CheckStatus.FAIL,
        message="the sidecar lists 6 card(s) and the document 5",
    ),
    CheckResult(
        check=QualityCheck.EVIDENCE_IDENTITY,
        status=CheckStatus.FAIL,
        card_position=1,
        fingerprint=FIRST,
        message=CITE_DIFFERS,
    ),
)

#: What a person reads after the table, in the report's order: check by check, then as given.
NAMED: Final = [
    "Failures and warnings:",
    "  FAIL evidence-identity card 1 (a1a1a1a1a1a1): the built card's cite differs from the source card's "
    "(built 0ad4ba573a4a…, source 6cef145454f2…)",
    "  WARN cite-present card 6 (f3ef62b7c151): the card has no cite",
    "  WARN duplicate-cards card 2 (b2b2b2b2b2b2): a near-duplicate of card 4",
    "  FAIL heading-structure paragraph 7, under Politics DA > Link: a tag with no block above it, in a file "
    "that has blocks",
    "  FAIL manifest-alignment: the sidecar lists 6 card(s) and the document 5",
]

#: The same results under `--json`'s `quality.findings`.
FINDINGS: Final = [
    {
        "check": "evidence-identity",
        "status": "FAIL",
        "card_position": 1,
        "fingerprint": FIRST,
        "section_path": None,
        "paragraph_index": None,
        "message": CITE_DIFFERS,
    },
    {
        "check": "cite-present",
        "status": "WARN",
        "card_position": 6,
        "fingerprint": SIXTH,
        "section_path": None,
        "paragraph_index": None,
        "message": "the card has no cite",
    },
    {
        "check": "duplicate-cards",
        "status": "WARN",
        "card_position": 2,
        "fingerprint": SECOND,
        "section_path": None,
        "paragraph_index": None,
        "message": "a near-duplicate of card 4",
    },
    {
        "check": "heading-structure",
        "status": "FAIL",
        "card_position": None,
        "fingerprint": None,
        "section_path": ["Politics DA", "Link"],
        "paragraph_index": 7,
        "message": "a tag with no block above it, in a file that has blocks",
    },
    {
        "check": "manifest-alignment",
        "status": "FAIL",
        "card_position": None,
        "fingerprint": None,
        "section_path": None,
        "paragraph_index": None,
        "message": "the sidecar lists 6 card(s) and the document 5",
    },
]

#: Every key the two payloads had before this task, in order; `quality` gains `findings` and nothing else.
CHECK_KEYS: Final = ["file", "quality", "reports", "notes"]
BUILD_KEYS: Final = [
    "recipe",
    "recipe_hash",
    "status",
    "refusal",
    "recipe_errors",
    "card_problems",
    "unattributed",
    "files",
    "counts",
    "warnings",
    "quality",
]
QUALITY_KEYS: Final = ["status", "checks", "failing_checks", "findings"]


def report_of(results: tuple[CheckResult, ...]) -> FileQualityReport:
    return FileQualityReport.from_results(results, **VERSIONS)


def clean_results() -> tuple[CheckResult, ...]:
    return tuple(result for result in RESULTS if result.status is CheckStatus.PASS)


def checked(results: tuple[CheckResult, ...]) -> FileCheckResult:
    return FileCheckResult(
        checked=CheckedFile(
            report=report_of(results),
            json_path=BUILT.with_name(f"{BUILT.name}.quality.json"),
            markdown_path=BUILT.with_name(f"{BUILT.name}.quality.md"),
        )
    )


def built(results: tuple[CheckResult, ...]) -> FileBuildResult:
    report = report_of(results)
    return FileBuildResult(
        recipe_path=Path("/recipes/states-cp.yaml"),
        status=BuildStatus.QUALITY_FAILED if report.status is CheckStatus.FAIL else BuildStatus.BUILT,
        recipe_hash="c" * 64,
        files=BuiltFiles(
            docx=BUILT,
            provenance=BUILT.with_name(f"{BUILT.name}.provenance.json"),
            quality_json=BUILT.with_name(f"{BUILT.name}.quality.json"),
            quality_markdown=BUILT.with_name(f"{BUILT.name}.quality.md"),
        ),
        counts=BuildCounts(cards_placed=6, sources_used=6, tag_overrides=0, analytics=0),
        quality=report,
    )


def printed(display: TableSpec | str | None) -> list[str]:
    """What a person reads on stdout for `display`, line by line."""
    stdout = io.StringIO()
    CliOutput(stdout=stdout, stderr=io.StringIO(), width=100).success("files check", {}, display=display)
    return stdout.getvalue().splitlines()


def after_the_table(rendered: Rendered) -> list[str]:
    """The lines printed below the table's bottom border (none of these tables has a caption)."""
    lines = printed(rendered.display)
    bottom = max(index for index, line in enumerate(lines) if line.startswith("└"))
    return [line.rstrip() for line in lines[bottom + 1 :]]


def test_files_check_prints_each_warn_and_fail_after_the_table_as_the_quality_report_does() -> None:
    assert after_the_table(check_rendered(checked(RESULTS))) == NAMED


def test_files_build_prints_each_warn_and_fail_after_the_table_as_the_quality_report_does() -> None:
    assert after_the_table(build_rendered(built(RESULTS))) == NAMED


def test_a_card_is_named_by_its_position_in_the_file_counted_from_one() -> None:
    (only,) = [result for result in RESULTS if result.card_position == 6]
    assert after_the_table(check_rendered(checked((only,)))) == [
        "Failures and warnings:",
        "  WARN cite-present card 6 (f3ef62b7c151): the card has no cite",
    ]


def test_json_carries_each_warn_and_fail_under_one_new_key_and_keeps_every_key_it_had() -> None:
    for rendered, keys in (
        (check_rendered(checked(RESULTS)), CHECK_KEYS),
        (build_rendered(built(RESULTS)), BUILD_KEYS),
    ):
        payload: dict[str, Any] = dict(rendered.payload)
        assert list(payload) == keys
        assert list(payload["quality"]) == QUALITY_KEYS
        assert payload["quality"]["findings"] == FINDINGS
        assert payload["quality"]["failing_checks"] == [
            "evidence-identity",
            "heading-structure",
            "manifest-alignment",
        ]


def test_a_failed_builds_and_checks_error_details_carry_the_findings() -> None:
    for rendered in (check_rendered(checked(RESULTS)), build_rendered(built(RESULTS))):
        assert rendered.failure is not None
        details: dict[str, Any] = dict(rendered.failure.details)
        assert details["quality"]["findings"] == FINDINGS


def test_a_file_with_no_warn_or_fail_prints_exactly_the_table_it_printed_before() -> None:
    """The table as `v1-e33-t03` and `t04` printed it, written out by hand: nothing below it.

    With one row more since `v1-e33-t15`, `placeholders-replaced`, which a file without the CP text
    slot passes.
    """
    rows = [
        [check, "PASS", "0", "0"]
        for check in (
            "sidecar",
            "evidence-identity",
            "cite-present",
            "duplicate-cards",
            "heading-structure",
            "manifest-alignment",
            "provenance-complete",
            "suppression",
            "placeholders-replaced",
        )
    ]
    columns = ["Check", "Status", "Failures", "Warnings"]
    check_table = TableSpec(
        columns=columns, rows=rows, title="Checked: PASS, 6 card(s), writer 2026.10.24-file-writer-4"
    )
    build_table = TableSpec(
        columns=columns,
        rows=rows,
        title=f"Built {BUILT}: 6 card(s) placed from 6 source(s), 0 tag override(s), 0 warning(s)",
    )
    assert printed(check_rendered(checked(clean_results())).display) == printed(check_table)
    assert printed(build_rendered(built(clean_results())).display) == printed(build_table)
    assert after_the_table(check_rendered(checked(clean_results()))) == []
    payload: dict[str, Any] = dict(check_rendered(checked(clean_results())).payload)
    assert payload["quality"]["findings"] == []


def test_the_quality_failed_hint_says_the_findings_are_listed_above_and_names_the_full_report() -> None:
    """t12's follow-up (`v1-e33-t15`): the findings are printed above the panel now, card by card."""
    hint = "Each finding is listed above; the .quality.md beside the file has the full report."
    for rendered in (check_rendered(checked(RESULTS)), build_rendered(built(RESULTS))):
        assert rendered.failure is not None
        assert rendered.failure.code == "QUALITY_FAILED"
        assert rendered.failure.hint == hint
