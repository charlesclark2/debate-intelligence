#!/usr/bin/env python3
"""Count a parsed store's cards by tag and by the rule that read the tag. Counts only (`v1-e31-t32`).

For the re-parse after a parser bump that adds a tag rule: the cards before and after, read from a
copy of the bucket restored before the bump and one restored after the cloud run's full re-parse
(`caselist restore-run-state --into <copy>`), not re-parsed here. For each caselist and each of its
version directories that holds an index: the sources recorded as parsed, the cards, the cards with no
tag, and the cards whose tag `v1-e31-t24`'s bold-tag rule read and `v1-e31-t32`'s unbolded-tail rule
read. A card's rule ids name the rule that read its tag.

**Read-only, and nothing but counts leaves it.** It reads the stored documents in place and writes
nothing. Its output on stdout is counts, caselist names and version names: no card text, tag, cite,
file name, path or digest.

    uv run python scripts/count_tags_by_rule.py --data-dir ~/t32-after
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from debate_core.integrations.docx_parser.parser import BOLD_TAG_RULE, BOLD_TAG_WITH_AN_UNBOLDED_TAIL_RULE

__all__ = ["count", "main"]


def _version(directory: Path) -> dict[str, int]:
    sources = sum(
        json.loads(line).get("outcome") == "PARSED"
        for line in (directory / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    counts = {
        "sources": sources,
        "cards": 0,
        "no_tag": 0,
        "tagged_by_bold_tag": 0,
        "tagged_by_unbolded_tail": 0,
    }
    for stored in sorted(directory.glob("sha256/**/*.jsonl")):
        # Split on newlines only: a card's text may hold U+2028, which `splitlines` also splits on.
        for line in stored.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("record") != "document":
                continue
            for card in record["document"]["cards"]:
                counts["cards"] += 1
                if not (card.get("tag") or "").strip():
                    counts["no_tag"] += 1
                rules = [rule.split(":", 1)[0] for rule in card.get("rule_ids", ())]
                counts["tagged_by_bold_tag"] += BOLD_TAG_RULE in rules
                counts["tagged_by_unbolded_tail"] += BOLD_TAG_WITH_AN_UNBOLDED_TAIL_RULE in rules
    return counts


def count(data_dir: Path) -> dict[str, dict[str, dict[str, int]]]:
    """The counts by caselist, then by version directory."""
    parsed = data_dir / "parsed"
    if not parsed.is_dir():
        raise SystemExit(f"no parsed store in {data_dir.name}")
    found: dict[str, dict[str, dict[str, int]]] = {}
    for caselist in sorted(path for path in parsed.iterdir() if path.is_dir()):
        versions = sorted(path for path in caselist.iterdir() if (path / "index.jsonl").is_file())
        if versions:
            found[caselist.name] = {version.name: _version(version) for version in versions}
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data-dir", type=Path, required=True, help="A data directory, or a restored copy.")
    arguments = parser.parse_args(argv)
    output: dict[str, Any] = {
        "rules": {"bold_tag": BOLD_TAG_RULE, "unbolded_tail": BOLD_TAG_WITH_AN_UNBOLDED_TAIL_RULE},
        "caselists": count(arguments.data_dir.expanduser()),
    }
    json.dump(output, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
