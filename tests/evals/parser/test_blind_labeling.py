"""The evaluation report's account of files labeled blind (v1-e31-t18 ac5).

A blind file was corrected with the pre-label hidden, so how many of its rows differ from the
pre-label, beside the same figure for the other corrected files of its stratum, says whether
accepting a default has inflated the scores. The figures below are worked out by hand.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from tests.evals.parser.corpus import run_evaluation
from tests.evals.parser.labels_schema import (
    Category,
    DebateFormat,
    FileLabelHeader,
    LabelFile,
    LabelStatus,
    ManifestEntry,
    ParagraphLabel,
    ReviewerRole,
    TemplateFamily,
)
from tests.evals.parser.metrics import blind_comparison, render_markdown, report_json
from tests.evals.parser.synthetic import TEST_DIGEST_KEY
from tests.evals.parser.test_parser_eval import PERFECT_BASELINE, _synthetic_setup

from debate_core.domain.style_profile import StructuralUnit


def _digest(letter: str) -> str:
    return letter * 64


def _entry(letter: str, category: Category, family: TemplateFamily) -> ManifestEntry:
    return ManifestEntry(
        digest=_digest(letter), category=category, season="2025-26", debate_format=DebateFormat.LD,
        template_family=family,
    )  # fmt: skip


def _labels(letter: str, rows: int, changed: int | None, *, blind: bool = False,
            status: LabelStatus = LabelStatus.CORRECTED) -> LabelFile:  # fmt: skip
    corrected = status is not LabelStatus.PRELABELED
    return LabelFile(
        header=FileLabelHeader(
            digest=_digest(letter),
            paragraph_count=rows,
            blocks=((0, rows - 1),),
            status=status,
            prelabel_parser_version="test",
            corrected_by=ReviewerRole.COACH if corrected else None,
            reviewed_by=ReviewerRole.COACH if status is LabelStatus.COACH_REVIEWED else None,
            rows_changed_from_prelabel=changed if corrected else None,
            labeled_blind=blind,
        ),
        paragraphs=tuple(
            ParagraphLabel(index=i, length=0, text_digest="0" * 64, unit=StructuralUnit.OTHER)
            for i in range(rows)
        ),
        cards=(),
        spans=(),
    )


TEAM, CASELIST = Category.TEAM, Category.CASELIST
VERBATIM, HEURISTIC = TemplateFamily.VERBATIM, TemplateFamily.OTHER_HEURISTIC
ENTRIES = (
    _entry("a", TEAM, VERBATIM),
    _entry("b", TEAM, VERBATIM),
    _entry("c", TEAM, VERBATIM),
    _entry("d", TEAM, HEURISTIC),
    _entry("e", TEAM, VERBATIM),
    _entry("f", CASELIST, VERBATIM),
    _entry("9", TEAM, VERBATIM),
)
LABELS = {
    _digest("a"): _labels("a", 40, 10, blind=True),
    _digest("b"): _labels("b", 50, 5),
    _digest("c"): _labels("c", 30, 3, status=LabelStatus.COACH_REVIEWED),
    _digest("d"): _labels("d", 20, 8),
    _digest("e"): _labels("e", 25, None, status=LabelStatus.PRELABELED),
    _digest("f"): _labels("f", 10, 1, blind=True),
    _digest("9"): _labels("9", 20, 6, blind=True),
}


def test_each_blind_file_is_compared_with_the_other_corrected_files_of_its_stratum() -> None:
    """a: 10 of 40 against b and c, 8 of 80 (d is another family; e is not corrected; 9 is blind
    too, and a blind file is never what another is compared with). f: 1 of 10, and no other
    caselist Verbatim file is corrected. 9: 6 of 20 against b and c."""
    assert blind_comparison(ENTRIES, LABELS) == [
        {
            "file": "a" * 16,
            "stratum": "team, verbatim",
            "labeled_rows": 40,
            "rows_changed": 10,
            "share_changed": 0.25,
            "stratum_others": {"files": 2, "labeled_rows": 80, "rows_changed": 8, "share_changed": 0.1},
        },
        {
            "file": "f" * 16,
            "stratum": "caselist, verbatim",
            "labeled_rows": 10,
            "rows_changed": 1,
            "share_changed": 0.1,
            "stratum_others": {"files": 0, "labeled_rows": 0, "rows_changed": 0, "share_changed": None},
        },
        {
            "file": "9" * 16,
            "stratum": "team, verbatim",
            "labeled_rows": 20,
            "rows_changed": 6,
            "share_changed": 0.3,
            "stratum_others": {"files": 2, "labeled_rows": 80, "rows_changed": 8, "share_changed": 0.1},
        },
    ]


def test_no_blind_file_means_an_empty_comparison() -> None:
    sighted = {digest: replace(labels, header=labels.header.model_copy(update={"labeled_blind": False}))
               for digest, labels in LABELS.items()}  # fmt: skip

    assert blind_comparison(ENTRIES, sighted) == []


def _report(blind: list[dict[str, Any]]) -> dict[str, Any]:
    return report_json(
        tier="full", parser_version="v1", profile_version="p1", plan_id="plan0001", groups={},
        per_file={}, gate_failures=[], gate_notes=[], label_status={"CORRECTED": 2}, blind_labeling=blind,
    )  # fmt: skip


def test_the_markdown_report_names_the_blind_files_and_both_figures() -> None:
    markdown = render_markdown(_report(blind_comparison(ENTRIES, LABELS)))

    section = markdown[markdown.index("## Labeled blind") :]
    assert (
        "| `aaaaaaaaaaaaaaaa` | team, verbatim | 10 of 40 (0.250) | 8 of 80 (0.100), in 2 files |" in section
    )
    assert (
        "| `ffffffffffffffff` | caselist, verbatim | 1 of 10 (0.100) | no other corrected file |" in section
    )


def test_the_markdown_report_says_when_no_file_was_labeled_blind() -> None:
    markdown = render_markdown(_report([]))

    assert "## Labeled blind" in markdown
    assert "No file has been labeled blind." in markdown


def test_a_blind_label_file_changes_no_metric_and_not_the_gate(tmp_path: Path) -> None:
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path)
    (digest, sighted), *_ = labels.items()
    sighted = replace(sighted, header=sighted.header.model_copy(update={"rows_changed_from_prelabel": 2}))
    blind = replace(sighted, header=sighted.header.model_copy(update={"labeled_blind": True}))

    def run(label_file: LabelFile) -> dict[str, Any]:
        return run_evaluation(tier="full", manifest=manifest, labels={digest: label_file}, path_map=path_map,
                              plan=plan, key=TEST_DIGEST_KEY, baseline=PERFECT_BASELINE)  # fmt: skip

    with_blind, without = run(blind), run(sighted)

    assert with_blind["blind_labeling"] == [
        {"file": digest[:16], "stratum": "team, verbatim", "labeled_rows": 11, "rows_changed": 2,
         "share_changed": 0.1818,
         "stratum_others": {"files": 0, "labeled_rows": 0, "rows_changed": 0, "share_changed": None}},
    ]  # fmt: skip
    assert without["blind_labeling"] == []
    assert {k: v for k, v in with_blind.items() if k != "blind_labeling"} == {
        k: v for k, v in without.items() if k != "blind_labeling"
    }
    assert with_blind["gate"]["passed"] is True
