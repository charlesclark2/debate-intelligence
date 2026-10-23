"""The quality report model, its renderers and its schema (`v1-e33-t04`, node report-model, ac5).

The Markdown expected below is written by hand from the results each test builds (working agreement 6).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from debate_core.evidence.file_checks.report import (
    CHECKER_VERSION,
    FILE_QUALITY_SCHEMA_FILENAME,
    CheckResult,
    CheckStatus,
    FileQualityReport,
    QualityCheck,
    quality_report_names,
    render_file_quality_report_schema,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[5]
SCHEMA_PATH = ROOT / "docs" / "data" / FILE_QUALITY_SCHEMA_FILENAME

FINGERPRINT_ONE = "a1" * 32
FINGERPRINT_TWO = "b2" * 32
DOCX_SHA = "c3" * 32

VERSIONS = {
    "checker_version": CHECKER_VERSION,
    "parser_version": "2026.10.18-docx-5",
    "style_profile_version": "2026.10.18-verbatim-4",
    "fingerprint_version": "card-fingerprint-v4",
    "builder_version": "2026.10.19-file-writer-2",
    "sidecar_parser_version": "2026.10.18-docx-5",
    "docx_sha256": DOCX_SHA,
    "recipe_hash": "d4" * 32,
    "card_count": 2,
    "manifest_card_count": 2,
}


def _result(
    check: QualityCheck, status: CheckStatus, position: int | None = None, **extra: object
) -> CheckResult:
    fingerprint = {1: FINGERPRINT_ONE, 2: FINGERPRINT_TWO}.get(position or 0)
    return CheckResult.model_validate(
        {
            "check": check,
            "status": status,
            "card_position": position,
            "fingerprint": fingerprint,
            "message": extra.pop("message", "ok"),
            **extra,
        }
    )


def _passing() -> list[CheckResult]:
    results = [_result(QualityCheck.SIDECAR, CheckStatus.PASS)]
    for position in (1, 2):
        results.append(_result(QualityCheck.EVIDENCE_IDENTITY, CheckStatus.PASS, position))
        results.append(_result(QualityCheck.CITE_PRESENT, CheckStatus.PASS, position))
    results.append(_result(QualityCheck.HEADING_STRUCTURE, CheckStatus.PASS))
    return results


def test_a_report_with_only_passes_and_warnings_passes() -> None:
    results = [
        *_passing(),
        _result(QualityCheck.CITE_PRESENT, CheckStatus.WARN, 2, message="the card has no short cite"),
    ]
    report = FileQualityReport.from_results(results, **VERSIONS)
    assert report.status is CheckStatus.PASS
    cite = report.summary(QualityCheck.CITE_PRESENT)
    assert (cite.status, cite.failures, cite.warnings) == (CheckStatus.WARN, 0, 1)
    assert not report.failed(QualityCheck.CITE_PRESENT)


def test_one_failing_result_fails_the_report_and_its_check() -> None:
    results = [*_passing(), _result(QualityCheck.EVIDENCE_IDENTITY, CheckStatus.FAIL, 2, message="x")]
    report = FileQualityReport.from_results(results, **VERSIONS)
    assert report.status is CheckStatus.FAIL
    assert report.failed(QualityCheck.EVIDENCE_IDENTITY)
    assert report.summary(QualityCheck.EVIDENCE_IDENTITY).failures == 1
    assert not report.failed(QualityCheck.CITE_PRESENT)


def test_every_check_is_summarised_once_in_a_fixed_order_and_results_are_grouped_by_check() -> None:
    results = list(reversed(_passing()))
    report = FileQualityReport.from_results(results, **VERSIONS)
    assert [summary.check for summary in report.checks] == list(QualityCheck)
    assert [result.check for result in report.results] == [
        QualityCheck.SIDECAR,
        QualityCheck.EVIDENCE_IDENTITY,
        QualityCheck.EVIDENCE_IDENTITY,
        QualityCheck.CITE_PRESENT,
        QualityCheck.CITE_PRESENT,
        QualityCheck.HEADING_STRUCTURE,
    ]
    assert report.summary(QualityCheck.SUPPRESSION).status is CheckStatus.PASS


def test_a_report_cannot_say_pass_over_a_failing_result() -> None:
    good = FileQualityReport.from_results(
        [*_passing(), _result(QualityCheck.SIDECAR, CheckStatus.FAIL, message="x")], **VERSIONS
    )
    document = good.model_dump(mode="json")
    document["status"] = "PASS"
    with pytest.raises(ValidationError, match="fails exactly when"):
        FileQualityReport.model_validate(document)


def test_a_summary_must_count_its_results() -> None:
    document = FileQualityReport.from_results(_passing(), **VERSIONS).model_dump(mode="json")
    document["checks"][1]["failures"] = 1
    with pytest.raises(ValidationError, match="does not count its results"):
        FileQualityReport.model_validate(document)


def test_a_report_status_is_never_warn() -> None:
    document = FileQualityReport.from_results(_passing(), **VERSIONS).model_dump(mode="json")
    document["status"] = "WARN"
    with pytest.raises(ValidationError):
        FileQualityReport.model_validate(document)


def test_the_reports_sit_beside_the_built_file_named_as_its_sidecar_is() -> None:
    assert quality_report_names("nhi-politics.docx") == (
        "nhi-politics.docx.quality.json",
        "nhi-politics.docx.quality.md",
    )


# -- ac5: the JSON and its schema ------------------------------------------------------------


def test_the_committed_schema_is_what_the_model_renders() -> None:
    assert SCHEMA_PATH.is_file(), "missing; run: uv run scripts/export_file_quality_schema.py"
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == render_file_quality_report_schema(), (
        "stale; run: uv run scripts/export_file_quality_schema.py"
    )


def test_the_json_validates_against_the_committed_schema_and_records_the_versions_and_status() -> None:
    report = FileQualityReport.from_results(
        [*_passing(), _result(QualityCheck.SUPPRESSION, CheckStatus.FAIL, 1, message="x")], **VERSIONS
    )
    document = json.loads(report.to_json_bytes())
    jsonschema.validate(document, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    assert document["checker_version"] == CHECKER_VERSION
    assert document["parser_version"] == "2026.10.18-docx-5"
    assert document["style_profile_version"] == "2026.10.18-verbatim-4"
    assert document["status"] == "FAIL"
    assert report.to_json_bytes().endswith(b"}\n")


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "WARN"), ("checker_version", None), ("parser_version", ""), ("style_profile_version", None)],
)
def test_the_schema_refuses_a_report_without_its_versions_or_with_a_warn_status(
    field: str, value: object
) -> None:
    document = json.loads(FileQualityReport.from_results(_passing(), **VERSIONS).to_json_bytes())
    document[field] = value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


# -- the Markdown ------------------------------------------------------------------------------


def test_the_markdown_gives_pass_or_fail_per_check_and_card_and_names_cards_by_position_and_prefix() -> None:
    results = [
        *_passing(),
        _result(QualityCheck.CITE_PRESENT, CheckStatus.WARN, 2, message="the card has no short cite"),
        _result(
            QualityCheck.HEADING_STRUCTURE,
            CheckStatus.FAIL,
            section_path=("Politics DA", "Link"),
            paragraph_index=7,
            message="a TAG heading under no BLOCK, in a file that has blocks",
        ),
    ]
    report = FileQualityReport.from_results(results, **VERSIONS)
    expected = """\
# Built-file quality report

| | |
|---|---|
| Overall | **FAIL** |
| Built file (SHA-256) | `c3c3c3c3c3c3c3c3` |
| Cards in the file / in the sidecar | 2 / 2 |
| Checker | `2026.10.22-file-checks-2` |
| Parser | `2026.10.18-docx-5` |
| Style profile | `2026.10.18-verbatim-4` |
| Fingerprints | `card-fingerprint-v4` |
| Writer (from the sidecar) | `2026.10.19-file-writer-2` |

## Checks

| Check | Status | Failures | Warnings | What it asks |
|---|---|---|---|---|
| `sidecar` | PASS | 0 | 0 | The provenance sidecar is readable, valid and describes these bytes. |
| `evidence-identity` | PASS | 0 | 0 | Each card's evidence text, cite, formatting and fingerprint are its source card's, re-parsed from both files. |
| `cite-present` | WARN | 0 | 1 | Each card has a cite with a short cite (warned, never failed). |
| `duplicate-cards` | PASS | 0 | 0 | No fingerprint appears twice; near-duplicate cards are warnings. |
| `heading-structure` | FAIL | 1 | 0 | Headings nest pocket > hat > block > tag, no level skipped, in profile styles. |
| `manifest-alignment` | PASS | 0 | 0 | The sidecar and the document agree card for card, in order. |
| `provenance-complete` | PASS | 0 | 0 | Each card's provenance is complete in the sidecar, and the file's text holds no provenance line. |
| `suppression` | PASS | 0 | 0 | No card comes from a source or disclosure on the suppression list. |

## Cards

| Card | Fingerprint | `evidence-identity` | `cite-present` |
|---|---|---|---|
| 1 | `a1a1a1a1a1a1` | PASS | PASS |
| 2 | `b2b2b2b2b2b2` | PASS | WARN |

## Failures and warnings

* **WARN** `cite-present` card 2 (`b2b2b2b2b2b2`): the card has no short cite
* **FAIL** `heading-structure` paragraph 7, under Politics DA > Link: a TAG heading under no BLOCK, in a file that has blocks
"""  # noqa: E501 - the expected Markdown table rows are as long as the report writes them
    assert render_markdown(report) == expected


def test_the_markdown_of_a_clean_file_says_none_under_failures() -> None:
    markdown = render_markdown(FileQualityReport.from_results(_passing(), **VERSIONS))
    assert markdown.endswith("## Failures and warnings\n\nNone.\n")
    assert FINGERPRINT_ONE not in markdown, "a card is named by its fingerprint's prefix, not the whole"
