"""Write the file recipe's JSON Schema to docs/data/file-recipe.schema.json (v1-e33-t01).

The schema is the published contract for a recipe as written: `files suggest` (v1-e33-t03) emits
recipes that validate against it, and an editor can check a recipe against it as the coach types.
It is generated from the models in `debate_core.domain.file_recipe` by
`debate_core.application.file_recipes.render_recipe_schema`, never written by hand.

Drift is caught the way `scripts/export_schemas.py` catches it for the domain schemas: a test in the
default selection (`tests/scripts/test_export_recipe_schema.py`) regenerates the schema in memory
and fails when the committed file differs, so a model change and its schema change land together.
`--check` runs the same comparison from the command line.

No inline script metadata here on purpose: this script imports debate_core, so it must run in the
workspace environment (`uv run scripts/export_recipe_schema.py`), not in an isolated one.

Usage:
  uv run scripts/export_recipe_schema.py            # write the schema file
  uv run scripts/export_recipe_schema.py --check    # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from debate_core.application.file_recipes import RECIPE_SCHEMA_FILENAME, render_recipe_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "data" / RECIPE_SCHEMA_FILENAME


def serialize(schema: dict[str, object]) -> str:
    """Render the schema deterministically: 2-space indent, UTF-8, trailing newline."""
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def expected_text() -> str:
    """The schema file's text as the models render it now."""
    return serialize(render_recipe_schema())


def is_current(path: Path) -> bool:
    """Whether `path` holds exactly what the models render."""
    return path.is_file() and path.read_text(encoding="utf-8") == expected_text()


def main(argv: Sequence[str] | None = None, *, path: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report a stale file instead of rewriting it")
    args = ap.parse_args(argv)
    target = path or SCHEMA_PATH
    shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target

    if is_current(target):
        print(f"OK: {shown} is up to date")
        return 0
    if args.check:
        print(f"stale: {shown}", file=sys.stderr)
        print("Run: uv run scripts/export_recipe_schema.py", file=sys.stderr)
        return 1
    target.write_text(expected_text(), encoding="utf-8")
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
