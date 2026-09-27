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
from tests.evals.parser.digests import load_key
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    DebateFormat,
    FileSamplingPlan,
    LabelStatus,
    Manifest,
    ManifestEntry,
    SamplingPlan,
    TemplateFamily,
    load_label_files,
    load_manifest,
    load_sampling_plan,
)
from tests.evals.parser.metrics import render_markdown
from tests.evals.parser.synthetic import TEST_DIGEST_KEY, build_synthetic_file

from debate_core.domain.style_profile import StructuralUnit

BASELINE_PATH = REPOSITORY_ROOT / "tests" / "evals" / "baselines" / "parser.json"
REPORT_DIRECTORY = REPOSITORY_ROOT / "build" / "eval-reports"
PR_SUBSET_BUDGET_SECONDS = 30.0
SYNTHETIC_PLAN_ID = "abcdef0123456789"


def _run(manifest, labels, path_map, plan, *, tier="full", baseline=None):  # type: ignore[no-untyped-def]
    return run_evaluation(
        tier=tier,
        manifest=manifest,
        labels=labels,
        path_map=path_map,
        plan=plan,
        key=TEST_DIGEST_KEY,
        baseline=PERFECT_BASELINE if baseline is None else baseline,
    )


# --------------------------------------------------------------------------------------------
# The harness, on an invented file (every PR)
# --------------------------------------------------------------------------------------------


def _synthetic_setup(  # type: ignore[no-untyped-def]
    tmp_path: Path,
    content: bytes | None = None,
    status: LabelStatus = LabelStatus.CORRECTED,
    blocks: tuple[tuple[int, int], ...] | None = None,
):
    """A manifest, labels, path map and plan for the invented file, shaped like the real ones."""
    synthetic = build_synthetic_file(status, blocks=blocks, plan_id=SYNTHETIC_PLAN_ID)
    path = tmp_path / "evaluation-file.docx"
    path.write_bytes(synthetic.content if content is None else content)
    entry = ManifestEntry(
        digest=synthetic.digest,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
        pr_subset=True,
    )
    plan = SamplingPlan(
        plan_id=SYNTHETIC_PLAN_ID,
        generated_on="2026-09-23",
        parser_version="hand-written",
        files=(
            FileSamplingPlan(
                digest=synthetic.digest,
                paragraphs=synthetic.labels.header.paragraph_count,
                blocks=synthetic.labels.blocks,
                full=blocks is None,
            ),
        ),
    )
    return (
        Manifest(entries=(entry,)),
        {synthetic.digest: synthetic.labels},
        {synthetic.digest: path},
        plan,
    )


PERFECT_BASELINE: dict[str, Any] = {
    "parser_version": "2026.09.20-docx-1",
    "sampling_plan_id": SYNTHETIC_PLAN_ID,
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
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path)
    report = run_evaluation(
        tier="full",
        manifest=manifest,
        labels=labels,
        path_map=path_map,
        plan=plan,
        key=TEST_DIGEST_KEY,
        baseline=PERFECT_BASELINE,
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
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path)
    ((digest, label_file),) = labels.items()
    paragraphs = list(label_file.paragraphs)
    paragraphs[7] = paragraphs[7].model_copy(update={"unit": StructuralUnit.TAG})

    mislabeled = {digest: replace(label_file, paragraphs=tuple(paragraphs))}
    report = run_evaluation(
        tier="full",
        manifest=manifest,
        labels=mislabeled,
        path_map=path_map,
        plan=plan,
        key=TEST_DIGEST_KEY,
        baseline=PERFECT_BASELINE,
    )
    assert report["groups"]["overall"]["units"]["TAG"]["f1"] == 0.8  # tp 2, fn 1: 4 / 5
    assert report["gate"]["passed"] is False
    assert "overall TAG: F1 0.8000" in report["gate"]["failures"][0]


def test_the_harness_refuses_a_file_that_changed_under_its_labels(tmp_path: Path) -> None:
    manifest, labels, path_map, plan = _synthetic_setup(
        tmp_path, content=build_synthetic_file().content + b"\0"
    )
    with pytest.raises(EvaluationSetupError, match="labels are for"):
        _run(manifest, labels, path_map, plan)


def test_the_harness_refuses_uncorrected_prelabels(tmp_path: Path) -> None:
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path, status=LabelStatus.PRELABELED)
    with pytest.raises(EvaluationSetupError, match="the parser cannot grade itself"):
        _run(manifest, labels, path_map, plan)


def test_the_harness_refuses_a_missing_file(tmp_path: Path) -> None:
    manifest, labels, _, plan = _synthetic_setup(tmp_path)
    with pytest.raises(EvaluationSetupError, match="not found on this machine"):
        _run(manifest, labels, {}, plan)


def test_the_harness_fails_a_tier_with_no_baseline(tmp_path: Path) -> None:
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path)
    report = _run(manifest, labels, path_map, plan, tier="pr-subset", baseline={})
    assert report["gate"]["passed"] is False


def test_the_harness_scores_a_sampled_file_over_its_blocks_only(tmp_path: Path) -> None:
    """Blocks 0-7 hold the first card and the analytic; the second card (8-10) is outside them."""
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path, blocks=((0, 7),))
    report = _run(manifest, labels, path_map, plan)
    assert report["sampling"] == {
        "plan_id": SYNTHETIC_PLAN_ID,
        "labeled_rows": 8,
        "total_rows": 11,
        "rate": 0.7273,
    }
    overall = report["groups"]["overall"]
    assert overall["units"]["ANALYTIC"]["support"] == 1
    assert overall["units"]["TAG"]["support"] == 1  # the tag at 8 is outside the block
    # One card labeled and one judged: the card at 8-10 is unlabeled and unjudged, not a false positive.
    assert overall["cards"]["labeled"] == 1
    assert overall["cards"]["predicted"] == 1
    assert overall["cards"]["boundary_exact_match"] == 1.0
    assert report["gate"]["passed"] is True


def test_the_harness_refuses_labels_made_under_a_different_plan(tmp_path: Path) -> None:
    """Relabeling under a new plan without re-baselining would compare two different samples."""
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path)
    moved = SamplingPlan(
        plan_id="0123456789abcdef",
        generated_on=plan.generated_on,
        parser_version=plan.parser_version,
        files=plan.files,
    )
    with pytest.raises(EvaluationSetupError, match="were made under plan"):
        _run(manifest, labels, path_map, moved)


def test_the_gate_refuses_when_the_baseline_was_measured_over_another_plan(tmp_path: Path) -> None:
    manifest, labels, path_map, plan = _synthetic_setup(tmp_path)
    baseline = {**PERFECT_BASELINE, "sampling_plan_id": "0123456789abcdef"}
    report = _run(manifest, labels, path_map, plan, baseline=baseline)
    assert report["gate"]["passed"] is False
    assert "two samples are two measurements" in report["gate"]["failures"][0]


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
    key = load_key()
    if path_map is None or key is None:
        pytest.skip("no evaluation path map or digest key on this machine; the corpus never reaches CI")
    manifest = load_manifest()
    plan = load_sampling_plan()
    labels = load_label_files()
    entries = manifest.pr_subset if tier == "pr-subset" else manifest.entries
    not_ready = [
        e
        for e in entries
        if e.digest not in labels or labels[e.digest].header.status is LabelStatus.PRELABELED
    ]
    if not_ready:
        pytest.skip(f"{len(not_ready)} of {len(entries)} {tier} files are not yet corrected by a person")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    report = run_evaluation(
        tier=tier,
        manifest=manifest,
        labels=labels,
        path_map=path_map,
        plan=plan,
        key=key,
        baseline=baseline,
    )
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


# --------------------------------------------------------------------------------------------
# The committed sampling plan
# --------------------------------------------------------------------------------------------


def test_the_committed_plan_covers_every_manifest_file_and_samples_what_ac1_asks() -> None:
    manifest = load_manifest()
    plan = load_sampling_plan()
    assert {file.digest for file in plan.files} == {entry.digest for entry in manifest.entries}
    for entry in manifest.pr_subset:
        assert plan.of(entry.digest).full, "the PR subset gates every PR, so it is labeled in full"
    for file in plan.files:
        assert file.blocks, "every file contributes rows"
        for first, last in file.blocks:
            assert (
                last - first + 1 >= plan.minimum_block or file.full or file.paragraphs <= plan.minimum_block
            )
    sampled = [file for file in plan.files if not file.full]
    rate = sum(file.labeled_rows for file in sampled) / sum(file.paragraphs for file in sampled)
    assert 0.20 <= rate <= 0.35, f"about a quarter of every non-subset file; got {rate:.1%}"
