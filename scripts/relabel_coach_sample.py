#!/usr/bin/env python3
"""The coach's relabelling sitting for the answering stance (`v1-e32-t46`), in the coach's terminal.

Shows the listed rows of the coach's sample, mixed with control rows drawn at random from the other
labelled rows (by `--seed`), in one random order and unmarked. Each card shows the coach's own tag and
headings from the CSV, the side its file was disclosed on (read from this machine's store at the snapshot),
and the coach's label; nothing about the model's answers, the recordings or the score. The coach types a
label, `at:<id>` for a card that answers the position, or presses Enter to keep it; a label the evaluation
would refuse is asked again. Before anything is written the CSV is copied beside itself
(`<name>.before-stance-relabel.csv`), and the sitting refuses to start when a copy already there differs
from the sample. Only changed labels are written, once, at the end; stopping early (Ctrl-C) writes nothing.
The end prints counts only: changed and unchanged, listed and control.

No card text leaves the terminal: nothing is logged or written but the coach's labels. Run it, then
`landscape evaluate --check-sample` reads the result. The rules are
:mod:`debate_core.application.coach_sample_relabel`. The runbook's block passes the sample, its rows file,
the session's listed rows and the seed (`docs/runbooks/landscape-model-evaluation-record.md`).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import shutil
import sys
from datetime import date
from pathlib import Path

from debate_cli.build_info import settings_loader
from debate_cli.container import ServiceContainer, validating_routing
from debate_core.application.coach_sample_relabel import (
    CONTROL_ROWS,
    copy_path,
    relabel_counts,
    relabelled_sample,
    run_sitting,
    shown_rows,
    sitting_rows,
)
from debate_core.application.errors import DomainError

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"


def _rows(text: str) -> list[int]:
    return [int(one) for one in text.split(",") if one.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--caselist", required=True)
    parser.add_argument("--snapshot", required=True, type=date.fromisoformat)
    parser.add_argument("--sample", required=True, type=Path, help="The coach's labelled CSV.")
    parser.add_argument("--sample-rows", required=True, type=Path, help="The rows file written beside it.")
    parser.add_argument("--rows", required=True, type=_rows, help="The listed sample rows, comma-separated.")
    parser.add_argument("--seed", required=True, type=int, help="Draws the controls and the order.")
    parser.add_argument("--controls", type=int, default=CONTROL_ROWS)
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    arguments = parser.parse_args(argv)

    sample = arguments.sample.expanduser()
    copy = copy_path(sample)
    if copy.exists() and copy.read_bytes() != sample.read_bytes():
        print(
            f"Stopped: {copy} already exists and differs from the sample. Move it aside first; nothing was "
            "written.",
            file=sys.stderr,
        )
        return 1
    with sample.open(encoding="utf-8", newline="") as handle:
        text = handle.read()
    print("Reading the store at the snapshot for each card's side (about half a minute)...", flush=True)
    services = ServiceContainer(settings_loader=validating_routing(settings_loader()))
    service = services.landscape_evaluation(config_dir=arguments.config_dir, record=False)
    try:
        with arguments.sample_rows.expanduser().open(encoding="utf-8") as rows:
            found = asyncio.run(
                service.sample_sides(
                    arguments.caselist, io.StringIO(text), list(rows), snapshot=arguments.snapshot
                )
            )
        order = sitting_rows(
            arguments.rows,
            [one.sample_row for one in found.labelled if one.sample_row is not None],
            controls=arguments.controls,
            seed=arguments.seed,
        )
    except (DomainError, ValueError) as refused:
        print(f"Stopped: {refused}. Nothing was written.", file=sys.stderr)
        return 1
    shutil.copy2(sample, copy)
    if copy.read_bytes() != sample.read_bytes():
        print(f"Stopped: the copy at {copy} does not match the sample. Nothing was written.", file=sys.stderr)
        return 1
    print(f"A copy of the sample is kept at {copy}.")
    print(f"{len(order)} cards. Type a label, at:<id> for a card that answers the position, or press Enter.")
    try:
        changes = run_sitting(order, shown_rows(text, found.sides), found.taxonomy, ask=input, say=print)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped: nothing was written; the sample is as it was.")
        return 1
    if changes:
        incoming = sample.with_name(f".{sample.name}.incoming")
        with incoming.open("w", encoding="utf-8", newline="") as handle:
            handle.write(relabelled_sample(text, changes))
        os.replace(incoming, sample)
    counts = relabel_counts(order, set(changes))
    print(
        f"Done. Listed: {counts['listed']['changed']} changed, {counts['listed']['unchanged']} unchanged. "
        f"Control: {counts['control']['changed']} changed, {counts['control']['unchanged']} unchanged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
