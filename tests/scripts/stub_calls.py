"""The call recorder the deploy scripts' tests give their stubbed tools (`v1-e40-t14`, `v1-e39-t21`).

Each stub starts with `STUB_PREAMBLE`, which records the stub's name and argv in a file of its own,
under the next call number free in `$STUB_CALL_DIR`. `read_calls` reads them back in call-number
order.

Why not one shared log: both deploy scripts pipe `aws ecr get-login-password` into `docker login`, so
two stubs run at once, and when both appended to one log, a printf at a time, their words
interleaved. Under load a record read `aws --regiondocker us-east-1 ...`, and most interleavings
merged the two records into one `dockeraws ...` line, which dropped the `aws` call without failing
anything. `mkdir` either creates a call number's directory or fails because another call has it, so
no two calls share one, and a call made after another has finished always gets a higher number.
"""

from __future__ import annotations

import shutil
from pathlib import Path

STUB_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob
call_number=0
for recorded in "${STUB_CALL_DIR}"/*; do call_number=$((call_number + 1)); done
until mkdir "${STUB_CALL_DIR}/${call_number}" 2> /dev/null; do call_number=$((call_number + 1)); done
{
  printf '%s' "$(basename "$0")"
  for argument in "$@"; do printf '\\t%s' "${argument}"; done
} > "${STUB_CALL_DIR}/${call_number}/argv"
"""


def write_stub(directory: Path, name: str, body: str) -> None:
    """An executable stub called `name` that records its call, then runs `body`."""
    path = directory / name
    path.write_text(STUB_PREAMBLE + body, encoding="utf-8")
    path.chmod(0o755)


def clear_calls(call_dir: Path) -> None:
    """An empty `call_dir`, for the script's run to record into."""
    shutil.rmtree(call_dir, ignore_errors=True)
    call_dir.mkdir()


def read_calls(call_dir: Path) -> list[list[str]]:
    """Every recorded call, as the tool's name then its arguments, in call-number order."""
    return [
        (call / "argv").read_text(encoding="utf-8").split("\t")
        for call in sorted(call_dir.iterdir(), key=lambda call: int(call.name))
    ]
