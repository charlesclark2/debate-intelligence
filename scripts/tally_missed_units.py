#!/usr/bin/env python3
"""Tally where the labelled evaluation's missed cites, tags and highlights go, as counts (`v1-e31-t31`).

Read-only over the evaluation files on this machine (the path map and key beside it, as
`scripts/run_parser_eval.py` reads them), parsed by this checkout's parser. Prints JSON counts and
nothing from inside a file: no text, no file name, no style name.

    uv run python scripts/tally_missed_units.py --tier full

Takes about three seconds over the thirty files.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.evals.parser.corpus import load_path_map, parse_evaluation_file  # noqa: E402
from tests.evals.parser.digests import keyed_digest, require_key  # noqa: E402
from tests.evals.parser.labels_schema import ManifestEntry, load_label_files, load_manifest  # noqa: E402
from tests.evals.parser.missed_units import FileCounts, ReadingParser, count_file, tally  # noqa: E402

from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--tier", choices=("pr-subset", "full"), default="full")
    args = parser.parse_args(argv)

    path_map = load_path_map()
    if path_map is None:
        print("no evaluation path map on this machine", file=sys.stderr)
        return 2
    key = require_key()
    manifest = load_manifest()
    labels = load_label_files()
    entries = manifest.pr_subset if args.tier == "pr-subset" else manifest.entries

    reading = ReadingParser()
    counted: list[tuple[ManifestEntry, FileCounts]] = []
    for entry in entries:
        path = path_map.get(entry.digest)
        if path is None or not path.is_file():
            print(f"{entry.digest[:16]}: not found on this machine", file=sys.stderr)
            return 1
        content = path.read_bytes()
        if keyed_digest(content, key) != entry.digest:
            print(f"{entry.digest[:16]}: the file at its mapped path has changed", file=sys.stderr)
            return 1
        document = parse_evaluation_file(reading, entry, content)
        counted.append((entry, count_file(entry, labels[entry.digest], document, reading)))

    result = {
        "parser_version": DOCX_PARSER_VERSION,
        "tier": args.tier,
        "files": len(entries),
        **tally(counted),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
