#!/usr/bin/env python3
"""Run the parser evaluation over the labeled files on this machine, and write its reports.

The pytest tiers (`tests/evals/parser/test_parser_eval.py`) gate on the committed baseline; this
script is what the operator runs to look at the numbers, and the only way the baseline changes.

    # Score one tier; reports go to build/eval-reports/ (gitignored)
    uv run python scripts/run_parser_eval.py --tier full

    # Establish or refresh the baseline, with the report the coach reviews committed beside it
    uv run python scripts/run_parser_eval.py --write-baseline \\
        --report docs/data/parser-eval-2026-10.md

**The baseline is never updated without a coach-reviewed report in the same PR** (the spec's
forbidden list). `--write-baseline` therefore insists on a `--report` path under `docs/data/`,
writes the report there, records that path in the baseline, and refuses to run unless at least
three label files — one team, one caselist, one camp — are `COACH_REVIEWED`. The coach reads the
written report before it is committed.

Nothing it writes names a file: groups and scores, keyed by SHA-256 in the JSON only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.evals.parser.corpus import EvaluationSetupError, load_path_map, run_evaluation  # noqa: E402
from tests.evals.parser.digests import require_key  # noqa: E402
from tests.evals.parser.labels_schema import (  # noqa: E402
    Category,
    LabelStatus,
    load_label_files,
    load_manifest,
    load_sampling_plan,
)
from tests.evals.parser.metrics import GATED_GROUPS, render_markdown  # noqa: E402

BASELINE_PATH = REPO_ROOT / "tests" / "evals" / "baselines" / "parser.json"
REPORT_DIRECTORY = REPO_ROOT / "build" / "eval-reports"
DOCS_DATA = REPO_ROOT / "docs" / "data"


def _baseline_tier(report: dict[str, Any]) -> dict[str, dict[str, float]]:
    """The gated groups' unit F1, as the baseline stores them."""
    tier: dict[str, dict[str, float]] = {}
    for name in GATED_GROUPS:
        group = report["groups"].get(name)
        if group is None:
            continue
        tier[name] = {
            unit: counts["f1"]
            for unit, counts in group["units"].items()
            if unit != "OTHER" and counts["f1"] is not None
        }
    return tier


def _coach_review_shortfall(manifest_categories: dict[str, Category], labels: dict[str, Any]) -> str | None:
    reviewed = {
        manifest_categories[digest]
        for digest, label in labels.items()
        if label.header.status is LabelStatus.COACH_REVIEWED and digest in manifest_categories
    }
    count = sum(1 for label in labels.values() if label.header.status is LabelStatus.COACH_REVIEWED)
    missing = sorted(category.value for category in set(Category) - reviewed)
    if count < 3 or missing:
        return (
            f"{count} file(s) are COACH_REVIEWED; need 3 covering team, caselist and camp "
            f"(missing: {missing})"
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tier", choices=("pr-subset", "full", "both"), default="both")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument(
        "--report", type=Path, help="With --write-baseline: the report to commit, under docs/data/."
    )
    args = parser.parse_args(argv)

    path_map = load_path_map()
    if path_map is None:
        print(
            "no evaluation path map on this machine; run scripts/select_eval_files.py first", file=sys.stderr
        )
        return 2
    key = require_key()
    manifest = load_manifest()
    plan = load_sampling_plan()
    labels = load_label_files()
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    if args.write_baseline:
        report_path = (args.report or Path()).resolve()
        if args.report is None or not report_path.is_relative_to(DOCS_DATA):
            print(
                "--write-baseline needs --report docs/data/<name>.md, the report the coach reviews",
                file=sys.stderr,
            )
            return 2
        shortfall = _coach_review_shortfall({e.digest: e.category for e in manifest.entries}, labels)
        if shortfall:
            print(f"refusing to write a baseline: {shortfall}", file=sys.stderr)
            return 2
        baseline = {}  # measure afresh; the old baseline is what is being replaced

    tiers = ("pr-subset", "full") if args.write_baseline or args.tier == "both" else (args.tier,)
    reports: dict[str, dict[str, Any]] = {}
    for tier in tiers:
        try:
            reports[tier] = run_evaluation(
                tier=tier,
                manifest=manifest,
                labels=labels,
                path_map=path_map,
                plan=plan,
                key=key,
                baseline=baseline,
            )
        except EvaluationSetupError as error:
            print(f"{tier}: {error}", file=sys.stderr)
            return 1
        REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
        stem = "parser" if tier == "full" else "parser-pr-subset"
        (REPORT_DIRECTORY / f"{stem}.json").write_text(
            json.dumps(reports[tier], indent=2) + "\n", encoding="utf-8"
        )
        (REPORT_DIRECTORY / f"{stem}.md").write_text(render_markdown(reports[tier]), encoding="utf-8")
        gate = reports[tier]["gate"]
        print(f"{tier}: {reports[tier]['files']} files, gate {'PASSED' if gate['passed'] else 'FAILED'}")
        for line in gate["failures"] + gate["notes"]:
            print(f"  {line}")

    if not args.write_baseline:
        return 0 if all(report["gate"]["passed"] for report in reports.values()) else 1

    full = reports["full"]
    new_baseline = {
        "parser_version": full["parser_version"],
        "profile_version": full["profile_version"],
        "status": "ESTABLISHED",
        # The gate refuses rather than compares when this moves: a metric over one sample and a
        # metric over another are two measurements, not a regression (ac4).
        "sampling_plan_id": plan.plan_id,
        "labeled_rows": full["sampling"]["labeled_rows"],
        "total_rows": full["sampling"]["total_rows"],
        "established_on": date.today().isoformat(),
        "established_by_report": str(report_path.relative_to(REPO_ROOT)),
        "label_status": full["label_status"],
        "tiers": {tier: _baseline_tier(report) for tier, report in reports.items()},
    }
    BASELINE_PATH.write_text(json.dumps(new_baseline, indent=2) + "\n", encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_markdown(full)
        + "\n## PR subset\n\n"
        + render_markdown(reports["pr-subset"]).split("\n", 1)[1].replace("\n## ", "\n### "),
        encoding="utf-8",
    )
    print(
        f"baseline written for parser {full['parser_version']}; "
        f"report written to {new_baseline['established_by_report']}"
    )
    print("Have the coach review the report before committing it with the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
