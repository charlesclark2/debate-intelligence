"""Write the lossless writer's base document from the style profile (v1-e33-t02).

`packages/debate_core/src/debate_core/integrations/docx_file_writer/templates/base.docx` holds the
style table every built evidence file uses. It is generated from the E31 style profile's writer
definitions by `debate_core.integrations.docx_file_writer.base_template.render_base_template`, never
taken from a source document, and committed. A test regenerates it in memory and fails when the
committed file differs; `--check` runs the same comparison from the command line.

`--team-styles` takes the `word/styles.xml` of a team's Verbatim template, committed and scrubbed,
for the styles the profile names (PM ruling 2026-10-19). None is committed yet.

No inline script metadata here on purpose: this script imports debate_core, so it must run in the
workspace environment (`uv run scripts/build_file_base_template.py`).

Usage:
  uv run scripts/build_file_base_template.py            # write base.docx
  uv run scripts/build_file_base_template.py --check    # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from debate_core.evidence.style_profile_loader import load_style_profile
from debate_core.integrations.docx_file_writer.base_template import render_base_template

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "packages/debate_core/src/debate_core/integrations/docx_file_writer/templates/base.docx"


def expected_bytes(team_styles: Path | None = None) -> bytes:
    """The base document as the profile renders it now."""
    team = team_styles.read_bytes() if team_styles is not None else None
    return render_base_template(load_style_profile(), team_styles_xml=team)


def main(argv: Sequence[str] | None = None, *, path: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report a stale file instead of rewriting it")
    ap.add_argument("--team-styles", type=Path, default=None, help="a scrubbed team styles.xml")
    args = ap.parse_args(argv)
    target = path or BASE_PATH
    shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    expected = expected_bytes(args.team_styles)

    if target.is_file() and target.read_bytes() == expected:
        print(f"OK: {shown} is up to date")
        return 0
    if args.check:
        print(f"stale: {shown}", file=sys.stderr)
        print("Run: uv run scripts/build_file_base_template.py", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(expected)
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
