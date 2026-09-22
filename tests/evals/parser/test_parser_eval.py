"""The parser evaluation, in its tiers.

* **Harness tests** (no marker) run the whole evaluation — path map, hash checks, parse, score,
  gate — over the invented file in `synthetic.py`. They run on every PR and prove the machinery
  works where the real files never are.
* **The PR subset** (`eval`) runs over the six manifest files marked `pr_subset`, on a machine
  that holds them. It is part of the default `pytest` run there and must finish in under 30 s.
* **The full labeled set** (`eval` and `slow`) runs over all thirty, in the validate-dev slow tier
  and nightly on the operator's machine.

Both real tiers **skip** where there is no path map (a CI runner, a fresh clone) or where the
tier's labels are not all corrected yet, saying which. They **fail** when a file has changed under
its labels, when the parser refuses a file, or when a unit F1 drops more than 0.01 below the
committed baseline (ac4). Reports are written to `build/eval-reports/`, which is gitignored.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.corpus import (
    EvaluationSetupError,
    load_path_map,
    run_evaluation,
)
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    DebateFormat,
    LabelStatus,
    Manifest,
    ManifestEntry,
    TemplateFamily,
    load_label_files,
    load_manifest,
)
from tests.evals.parser.metrics import render_markdown
from tests.evals.parser.synthetic import build_synthetic_file

from debate_core.domain.style_profile import StructuralUnit

BASELINE_PATH = REPOSITORY_ROOT / "tests" / "evals" / "baselines" / "parser.json"
REPORT_DIRECTORY = REPOSITORY_ROOT / "build" / "eval-reports"
PR_SUBSET_BUDGET_SECONDS = 30.0


# --------------------------------------------------------------------------------------------
# The harness, on an invented file (every PR)
# --------------------------------------------------------------------------------------------


def _synthetic_setup(
    tmp_path: Path, content: bytes | None = None, status: LabelStatus = LabelStatus.CORRECTED
):  # type: ignore[no-untyped-def]
    synthetic = build_synthetic_file(status)
    path = tmp_path / "evaluation-file.docx"
    path.write_bytes(synthetic.content if content is None else content)
    entry = ManifestEntry(
        sha256=synthetic.sha256,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
        pr_subset=True,
    )
    return Manifest(entries=(entry,)), {synthetic.sha256: synthetic.labels}, {synthetic.sha256: path}


PERFECT_BASELINE: dict[str, Any] = {
    "parser_version": "2026.09.20-docx-1",
    "tiers": {
        "full": {
            "overall": {
                "POCKET": 1.0,
                "HAT": 1.0,
                "BLOCK": 1.0,
                "TAG": 1.0,
                "CITE": 1.0,
                "EVIDENCE": 1.0,
                "ANALYTIC": 1.0,
            }
        }
    },
}


def test_the_harness_scores_the_invented_file_against_its_hand_written_labels(tmp_path: Path) -> None:
    manifest, labels, path_map = _synthetic_setup(tmp_path)
    report = run_evaluation(
        tier="full", manifest=manifest, labels=labels, path_map=path_map, baseline=PERFECT_BASELINE
    )
    overall = report["groups"]["overall"]
    for unit in ("POCKET", "HAT", "BLOCK", "TAG", "CITE", "EVIDENCE", "ANALYTIC", "OTHER"):
        assert overall["units"][unit]["f1"] == 1.0, unit
    assert overall["cards"] == {
        "labeled": 2, "predicted": 2, "boundary_matches": 2, "boundary_exact_match": 1.0,
        "card_precision": 1.0, "completeness_correct": 2, "completeness_accuracy": 1.0,
    }  # fmt: skip
    assert overall["spans"]["underline"]["f1"] == 1.0
    assert overall["spans"]["highlight"]["f1"] == 1.0
    assert report["gate"] == {"passed": True, "failures": [], "notes": []}
    assert report["files"] == 1


def test_the_harness_gate_fails_when_the_labels_and_parser_disagree(tmp_path: Path) -> None:
    """Label the analytic a tag: the parser's (correct) ANALYTIC now scores as a missed TAG."""
    manifest, labels, path_map = _synthetic_setup(tmp_path)
    ((sha, label_file),) = labels.items()
    paragraphs = list(label_file.paragraphs)
    paragraphs[7] = paragraphs[7].model_copy(update={"unit": StructuralUnit.TAG})

    mislabeled = {sha: replace(label_file, paragraphs=tuple(paragraphs))}
    report = run_evaluation(
        tier="full", manifest=manifest, labels=mislabeled, path_map=path_map, baseline=PERFECT_BASELINE
    )
    assert report["groups"]["overall"]["units"]["TAG"]["f1"] == 0.8  # tp 2, fn 1: 4 / 5
    assert report["gate"]["passed"] is False
    assert "overall TAG: F1 0.8000" in report["gate"]["failures"][0]


def test_the_harness_refuses_a_file_that_changed_under_its_labels(tmp_path: Path) -> None:
    manifest, labels, path_map = _synthetic_setup(tmp_path, content=build_synthetic_file().content + b"\0")
    with pytest.raises(EvaluationSetupError, match="labels are for"):
        run_evaluation(
            tier="full", manifest=manifest, labels=labels, path_map=path_map, baseline=PERFECT_BASELINE
        )


def test_the_harness_refuses_uncorrected_prelabels(tmp_path: Path) -> None:
    manifest, labels, path_map = _synthetic_setup(tmp_path, status=LabelStatus.PRELABELED)
    with pytest.raises(EvaluationSetupError, match="the parser cannot grade itself"):
        run_evaluation(
            tier="full", manifest=manifest, labels=labels, path_map=path_map, baseline=PERFECT_BASELINE
        )


def test_the_harness_refuses_a_missing_file(tmp_path: Path) -> None:
    manifest, labels, _ = _synthetic_setup(tmp_path)
    with pytest.raises(EvaluationSetupError, match="not found on this machine"):
        run_evaluation(tier="full", manifest=manifest, labels=labels, path_map={}, baseline=PERFECT_BASELINE)


def test_the_harness_fails_a_tier_with_no_baseline(tmp_path: Path) -> None:
    manifest, labels, path_map = _synthetic_setup(tmp_path)
    report = run_evaluation(
        tier="pr-subset", manifest=manifest, labels=labels, path_map=path_map, baseline={}
    )
    assert report["gate"]["passed"] is False


def test_the_path_map_is_refused_inside_the_repository() -> None:
    with pytest.raises(EvaluationSetupError, match="outside the repository"):
        load_path_map(REPOSITORY_ROOT / "build" / "parser-eval-paths.json")


def test_the_committed_baseline_names_a_parser_version() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["parser_version"]
    if baseline["tiers"]:
        assert baseline["established_by_report"], (
            "a baseline is committed with the coach-reviewed report behind it"
        )


# --------------------------------------------------------------------------------------------
# The real tiers (only where the files are)
# --------------------------------------------------------------------------------------------


def _run_real_tier(tier: str) -> dict[str, Any]:
    path_map = load_path_map()
    if path_map is None:
        pytest.skip("no evaluation path map on this machine; the real corpus never reaches CI")
    manifest = load_manifest()
    labels = load_label_files()
    entries = manifest.pr_subset if tier == "pr-subset" else manifest.entries
    not_ready = [
        e
        for e in entries
        if e.sha256 not in labels or labels[e.sha256].header.status is LabelStatus.PRELABELED
    ]
    if not_ready:
        pytest.skip(f"{len(not_ready)} of {len(entries)} {tier} files are not yet corrected by a person")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    report = run_evaluation(tier=tier, manifest=manifest, labels=labels, path_map=path_map, baseline=baseline)
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stem = "parser" if tier == "full" else "parser-pr-subset"
    (REPORT_DIRECTORY / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIRECTORY / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    return report


@pytest.mark.eval
def test_the_labeled_pr_subset_holds_the_baseline() -> None:
    started = time.monotonic()
    report = _run_real_tier("pr-subset")
    elapsed = time.monotonic() - started
    assert report["gate"]["passed"], "\n".join(report["gate"]["failures"])
    assert elapsed < PR_SUBSET_BUDGET_SECONDS, f"the PR subset took {elapsed:.1f} s"


@pytest.mark.eval
@pytest.mark.slow
def test_the_full_labeled_set_holds_the_baseline() -> None:
    report = _run_real_tier("full")
    assert report["gate"]["passed"], "\n".join(report["gate"]["failures"])
