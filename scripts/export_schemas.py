"""Write the published JSON Schemas into packages/debate_core/schemas/.

One file per domain entity (`*.schema.json`), plus the documents `debate-research verify` reads and
writes (v1-e03-t06-verify-command): the card manifest (`card_manifest.v1.json`, whose cards refer
to `card.schema.json`) and the command's `--json` result (`verify_result.v1.json`).

The committed schemas are the published contract for the domain model, so they are generated
rather than hand-written and they are checked in. `packages/debate_core/tests/domain/
test_schemas.py` and `tests/evidence/test_manifest.py` regenerate them in memory and fail if what is
committed has drifted, which means a field change and its schema change always land together.

No inline script metadata here on purpose: this script imports debate_core, so it must run in the
workspace environment (`uv run scripts/export_schemas.py`), not in an isolated one.

Usage:
  uv run scripts/export_schemas.py            # write the schema files
  uv run scripts/export_schemas.py --check    # exit 1 if any committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from debate_core.application.verify_manifest import VERIFY_RESULT_SCHEMA_FILENAME, render_verify_result_schema
from debate_core.domain import render_schemas
from debate_core.evidence.manifest import CARD_MANIFEST_SCHEMA_FILENAME, render_card_manifest_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "packages" / "debate_core" / "schemas"


def serialize(schema: dict[str, object]) -> str:
    """Render one schema deterministically: 2-space indent, UTF-8, trailing newline."""
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def published_schemas() -> dict[str, dict[str, object]]:
    """Every schema this script writes, keyed by file name."""
    schemas: dict[str, dict[str, object]] = dict(render_schemas())
    schemas[CARD_MANIFEST_SCHEMA_FILENAME] = render_card_manifest_schema()
    schemas[VERIFY_RESULT_SCHEMA_FILENAME] = render_verify_result_schema()
    return schemas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report stale files instead of rewriting them")
    args = ap.parse_args()

    schemas = published_schemas()
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    expected = {name: serialize(schema) for name, schema in schemas.items()}
    stale: list[str] = []
    for name, text in sorted(expected.items()):
        path = SCHEMA_DIR / name
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        stale.append(name)
        if not args.check:
            path.write_text(text, encoding="utf-8")

    orphans = sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json") if p.name not in expected)
    for name in orphans:
        if not args.check:
            (SCHEMA_DIR / name).unlink()

    relative = SCHEMA_DIR.relative_to(ROOT)
    if args.check:
        if stale or orphans:
            for name in stale:
                print(f"stale: {relative / name}", file=sys.stderr)
            for name in orphans:
                print(f"not produced by any exported model: {relative / name}", file=sys.stderr)
            print("Run: uv run scripts/export_schemas.py", file=sys.stderr)
            return 1
        print(f"OK: {len(expected)} schemas in {relative} are up to date")
        return 0

    for name in stale:
        print(f"wrote {relative / name}")
    for name in orphans:
        print(f"removed {relative / name}")
    print(f"OK: {len(expected)} schemas in {relative}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
