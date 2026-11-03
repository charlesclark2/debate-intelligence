"""Write the search index manifest's JSON Schema to docs/data/search-index-manifest.schema.json.

`v1-e39-t02`'s `tub index build` writes `manifest.json` beside every index it builds, a
`SearchIndexManifest`. Its schema is the published contract `tub index publish`, the pilot's function
(`v1-e39-t03`) and the weekly refresh (`v1-e39-t09`) read it by, so it is generated from the model in
`debate_core.domain.search_index` by `render_search_index_manifest_schema`, never written by hand.

Drift is caught the way `v1-e33-t02` catches it for the provenance sidecar: a test in the default
selection (`test_search_index_manifest_schema_committed_matches_the_models` in
`packages/debate_core/tests/application/test_search_index_build.py`) regenerates the schema in memory
and fails when the committed file differs. `--check` runs the same comparison from the command line.

No inline script metadata here on purpose: this script imports debate_core, so it must run in the
workspace environment (`uv run scripts/export_search_index_schema.py`), not in an isolated one.

Usage:
  uv run scripts/export_search_index_schema.py            # write the schema file
  uv run scripts/export_search_index_schema.py --check    # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from debate_core.domain.search_index import (
    SEARCH_INDEX_MANIFEST_SCHEMA_FILENAME,
    render_search_index_manifest_schema,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "data" / SEARCH_INDEX_MANIFEST_SCHEMA_FILENAME


def serialize(schema: dict[str, object]) -> str:
    """Render the schema deterministically: 2-space indent, UTF-8, trailing newline."""
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def expected_text() -> str:
    """The schema file's text as the models render it now."""
    return serialize(render_search_index_manifest_schema())


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
        print("Run: uv run scripts/export_search_index_schema.py", file=sys.stderr)
        return 1
    target.write_text(expected_text(), encoding="utf-8")
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
