#!/usr/bin/env python3
"""The coach's sitting for the held-out sample (`v1-e32-t50`), in the coach's terminal.

Shows the held-out sample's rows `--rows` (`1-60`, then `61-120` in the second sitting), in the sample's own
order: each card's tag and headings from the coach's CSV and the side its file was disclosed on (read from
this machine's store at the holdout's snapshot), and nothing of a model, a score, a stratum or a mark. The
coach types a label, `at:<id>` for a card that answers its position, `none` or `unsure`, with a second label
after a comma if they accept one; Enter leaves a card as it is. A label the evaluation would refuse is asked
again.

With `--side-rows 16,33,57` (the second sitting's end, the PM's ruling of 2026-11-14), the first sample's rows
follow as a part of their own, each with its tag, headings, side and the coach's label: the coach types
`at:<id>`, `also <label>` or `side`. A `side` answer writes nothing and is named on the last line.

Both files are guarded (`v1-e32-t58`): each must match its sidecar before the sitting starts. Everything is
written once, at the end; stopping early (Ctrl-C) writes nothing. A changed file is first kept as a dated copy
beside it, then written through its `.incoming` file, then its new sidecar. The end prints counts only.

No card text leaves the terminal: nothing is logged or written but the coach's labels. The rules are
:mod:`debate_core.application.holdout_sitting`; the runbook's blocks pass the files
(`docs/runbooks/landscape-model-evaluation-record.md`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from debate_cli.build_info import settings_loader
from debate_cli.container import ServiceContainer, validating_routing
from debate_core.application.coach_sample_labels_file import (
    LabelsFileRefused,
    read_labels_file,
    write_sitting,
)
from debate_core.application.coach_sample_relabel import rewritten_cells, shown_rows
from debate_core.application.errors import DomainError
from debate_core.application.holdout_sitting import (
    SideRowAnswers,
    holdout_counts,
    run_holdout_sitting,
    run_side_rows,
    side_rule_line,
    sitting_range,
)
from debate_core.arguments.landscape.holdout_mark import is_holdout

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"


def _row_list(text: str) -> tuple[int, ...]:
    return sitting_range(text)


@dataclass(frozen=True)
class _Sample:
    path: Path
    text: str
    rows: list[str]


def _read(sample: Path, rows: Path) -> _Sample:
    path = sample.expanduser()
    text = read_labels_file(path)
    with rows.expanduser().open(encoding="utf-8") as stream:
        return _Sample(path, text, list(stream))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--caselist", required=True)
    parser.add_argument("--snapshot", required=True, type=date.fromisoformat, help="The holdout's snapshot.")
    parser.add_argument("--sample", required=True, type=Path, help="The coach's holdout CSV.")
    parser.add_argument("--sample-rows", required=True, type=Path, help="The holdout's rows file.")
    parser.add_argument(
        "--rows", required=True, type=_row_list, help="The rows of this sitting: 1-60 or 61-120."
    )
    parser.add_argument("--side-rows", type=_row_list, help="The first sample's rows that follow: 16,33,57.")
    parser.add_argument("--first-sample", type=Path, help="The coach's first-sample CSV, with --side-rows.")
    parser.add_argument("--first-sample-rows", type=Path, help="Its rows file, with --side-rows.")
    parser.add_argument("--first-snapshot", type=date.fromisoformat, help="Its snapshot, with --side-rows.")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    arguments = parser.parse_args(argv)
    side = arguments.side_rows is not None
    given = [
        one is not None
        for one in (arguments.first_sample, arguments.first_sample_rows, arguments.first_snapshot)
    ]
    if (side and not all(given)) or (not side and any(given)):
        print(
            "Stopped: --side-rows needs --first-sample, --first-sample-rows and --first-snapshot, and "
            "they need it. Nothing was written.",
            file=sys.stderr,
        )
        return 2
    try:
        holdout = _read(arguments.sample, arguments.sample_rows)
        first = _read(arguments.first_sample, arguments.first_sample_rows) if side else None
    except LabelsFileRefused as refused:
        print(f"Stopped: {refused}. {refused.hint}", file=sys.stderr)
        return 1
    if not is_holdout(holdout.rows) or (first is not None and is_holdout(first.rows)):
        print(
            "Stopped: --sample-rows must be the held-out sample's rows file and --first-sample-rows the "
            "first sample's. Nothing was written.",
            file=sys.stderr,
        )
        return 1
    print("Reading the store at the snapshot for each card's side (about half a minute)...", flush=True)
    services = ServiceContainer(settings_loader=validating_routing(settings_loader()))
    service = services.landscape_evaluation(config_dir=arguments.config_dir, record=False)
    try:
        taxonomy = asyncio.run(service.taxonomy_at(arguments.caselist, arguments.snapshot))
        sides = asyncio.run(
            service.sides_by_row(arguments.caselist, holdout.rows, snapshot=arguments.snapshot)
        )
        shown = shown_rows(holdout.text, sides)
        missing = [row for row in arguments.rows if row not in shown]
        if missing:
            raise ValueError(f"row {missing[0]} is not in the held-out sample")
        first_shown, first_taxonomy = None, taxonomy
        if first is not None:
            first_sides = asyncio.run(
                service.sides_by_row(arguments.caselist, first.rows, snapshot=arguments.first_snapshot)
            )
            first_shown = shown_rows(first.text, first_sides)
            first_taxonomy = asyncio.run(service.taxonomy_at(arguments.caselist, arguments.first_snapshot))
            absent = [row for row in arguments.side_rows if row not in first_shown]
            if absent:
                raise ValueError(f"row {absent[0]} is not in the first sample")
    except (DomainError, ValueError) as refused:
        print(f"Stopped: {refused}. Nothing was written.", file=sys.stderr)
        return 1
    print(
        f"{len(arguments.rows)} cards. Type a label (an id, at:<id> for a card that answers the position, "
        "none or unsure), and a second label after a comma if you accept one; Enter leaves a card as it is."
    )
    try:
        changes = run_holdout_sitting(arguments.rows, shown, taxonomy, ask=input, say=print)
        answers = (
            run_side_rows(arguments.side_rows, first_shown, first_taxonomy, ask=input, say=print)
            if first_shown is not None
            else SideRowAnswers(cells={}, side_rule=())
        )
    except (KeyboardInterrupt, EOFError):
        print("\nStopped: nothing was written; both files are as they were.")
        return 1
    at = datetime.now()
    if changes:
        written = write_sitting(holdout.path, rewritten_cells(holdout.text, changes), at=at)
        print(
            f"The holdout file this sitting replaced is kept at {written.copy}; "
            f"its new SHA-256: {written.digest}."
        )
    if first is not None and answers.cells:
        written = write_sitting(first.path, rewritten_cells(first.text, answers.cells), at=at)
        print(
            f"The first-sample file it replaced is kept at {written.copy}; its new SHA-256: {written.digest}."
        )
    counts = holdout_counts(arguments.rows, shown, changes)
    print(
        f"Done. {len(arguments.rows)} cards: {counts['labelled']} labelled "
        f"({counts['second_labels']} with a second label), {counts['unsure']} unsure, "
        f"{counts['blank']} left blank."
    )
    if first is not None:
        print(
            f"The first sample's rows: {len(answers.cells)} written, {len(answers.side_rule)} answered side."
        )
        print(side_rule_line(answers.side_rule))
    return 0


if __name__ == "__main__":
    sys.exit(main())
