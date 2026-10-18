"""Record each newly released prompt version in prompts/prompts.lock.json.

A released prompt version is immutable (v1-e05-t04-prompt-registry). The lock file pins the sha256
of each released version's body, with its output schema and task class, and
`packages/debate_core/tests/integrations/models/test_prompt_lock.py` fails when a released prompt no
longer matches it.

This script only ever adds entries. It refuses, writing nothing, when a released version already in
the lock has changed, has been deleted or has been set back to draft, because rewriting that entry
is exactly the edit the lock exists to catch. The fix is a new version, in a new file.

No inline script metadata here on purpose: this script imports debate_core, so it must run in the
workspace environment (`uv run scripts/lock_prompts.py`), not in an isolated one.

Usage:
  uv run scripts/lock_prompts.py            # add the newly released versions to the lock
  uv run scripts/lock_prompts.py --check    # exit 1 if the lock is not up to date, writing nothing
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from debate_core.application.errors import DomainError
from debate_core.integrations.models.prompt_lock import (
    LOCK_FILE_NAME,
    LockProblemKind,
    PromptLock,
    compare_lock,
    extend_lock,
)
from debate_core.integrations.models.prompt_registry import DEFAULT_PROMPT_DIRECTORY, PromptRegistry

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="report what is out of date instead of writing")
    parser.add_argument(
        "--prompts",
        type=Path,
        default=ROOT / DEFAULT_PROMPT_DIRECTORY,
        help="the prompt directory (default: prompts/ in this checkout)",
    )
    parser.add_argument(
        "--lock", type=Path, default=None, help="the lock file (default: <prompts>/prompts.lock.json)"
    )
    args = parser.parse_args(argv)
    lock_path: Path = args.lock or args.prompts / LOCK_FILE_NAME

    try:
        registry = PromptRegistry.load(args.prompts)
        lock = PromptLock.read(lock_path)
        problems = compare_lock(registry, lock)
        if args.check:
            for problem in problems:
                print(f"{lock_path}: {problem.detail}", file=sys.stderr)
            return 1 if problems else 0
        extended = extend_lock(registry, lock)
    except DomainError as error:
        print(f"lock_prompts: {error}", file=sys.stderr)
        return 1

    added = [problem for problem in problems if problem.kind is LockProblemKind.UNLOCKED]
    if not added:
        print(f"{lock_path} is up to date")
        return 0
    extended.write(lock_path)
    for problem in added:
        print(f"locked {problem.prompt_id}@{problem.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
