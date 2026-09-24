#!/usr/bin/env python3
"""Generate the parser evaluation's sampling plan, once, before any labeling begins.

Labeling all thirty files in full is about 5,800 rows of judgment work. The spec samples instead:
the six-file PR subset in full, because it gates every pull request, and about a quarter of every
other file in contiguous blocks of at least 20 paragraphs. The method — deterministic from each
file's keyed digest, weighted toward the blocks holding the rare units — is
:mod:`tests.evals.parser.sampling`.

Run it on the machine that holds the corpus: it parses each file to pre-label it, because the
weighting needs to know which paragraphs the parser thinks are `POCKET`, `UNDERTAG` or `ANALYTIC`.
Those pre-labels are used for the weighting and thrown away; the labels a person corrects are
written separately by `scripts/prelabel_docx.py`.

    uv run python scripts/plan_eval_sampling.py

It writes `tests/fixtures/debate_files/eval/sampling-plan.json`, which is committed, and prints
per-file row counts. **Nothing it writes names a file**: every key is the keyed digest.

Re-running it with the same manifest, key and parser produces the same plan. Re-running it after
the manifest or the parser changes produces a *different* `plan_id`, and the baseline records the
plan it was measured over — so the gate refuses rather than comparing two different samples. That
is why this runs once, before labeling, and not again without a deliberate re-baseline.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.evals.parser.corpus import (  # noqa: E402
    EvaluationSetupError,
    load_evaluation_document,
    load_path_map,
)
from tests.evals.parser.digests import require_key  # noqa: E402
from tests.evals.parser.labels_schema import (  # noqa: E402
    MANIFEST_PATH,
    MINIMUM_BLOCK_PARAGRAPHS,
    SAMPLING_PLAN_PATH,
    TARGET_SAMPLING_RATE,
    load_manifest,
    load_sampling_plan,
)
from tests.evals.parser.sampling import build_sampling_plan  # noqa: E402

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=SAMPLING_PLAN_PATH)
    parser.add_argument("--target-rate", type=float, default=TARGET_SAMPLING_RATE)
    parser.add_argument("--minimum-block", type=int, default=MINIMUM_BLOCK_PARAGRAPHS)
    args = parser.parse_args(argv)

    key = require_key()
    path_map = load_path_map()
    if path_map is None:
        print(
            "no evaluation path map on this machine; run scripts/select_eval_files.py first", file=sys.stderr
        )
        return 2
    manifest = load_manifest(args.manifest)

    units = {}
    parser_version = ""
    for entry in manifest.entries:
        try:
            document = load_evaluation_document(entry, path_map, key)
        except EvaluationSetupError as error:
            print(str(error), file=sys.stderr)
            return 1
        units[entry.digest] = [section.unit for section in document.sections]
        parser_version = document.parser_version

    plan = build_sampling_plan(
        manifest,
        units,
        parser_version=parser_version,
        generated_on=date.today(),
        target_rate=args.target_rate,
        minimum_block=args.minimum_block,
    )
    if args.output.exists():
        existing = load_sampling_plan(args.output)
        if existing.plan_id != plan.plan_id:
            print(
                f"replacing sampling plan {existing.plan_id} with {plan.plan_id}: any labels already "
                "corrected under the old plan no longer match it, and the baseline must be re-measured",
                file=sys.stderr,
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    subset = sum(1 for file_plan in plan.files if file_plan.full)
    print(
        f"sampling plan {plan.plan_id}: {plan.labeled_rows} of {plan.total_rows} paragraphs "
        f"({plan.rate:.1%}), {subset} file(s) labeled in full"
    )
    for file_plan in sorted(plan.files, key=lambda p: (not p.full, p.digest)):
        blocks = ", ".join(f"{first}-{last}" for first, last in file_plan.blocks)
        print(
            f"  {file_plan.digest[:12]}… {file_plan.labeled_rows:5d} of {file_plan.paragraphs:5d} "
            f"({file_plan.rate:5.1%}) {'full  ' if file_plan.full else 'blocks'} {blocks}"
        )
    print(f"written to {args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
