#!/usr/bin/env python3
"""Late disclosures in one snapshot, counted: their share and the topic-word check (`v1-e32-t51`).

A disclosure is late when its tournament spelling was first seen in a snapshot dated before the start of
the topic range covering the snapshot, and holds none of that topic's own tournament entry spellings
(`debate_core.application.landscape_late_disclosures` has the rule). For hsld26's snapshot of 2026-11-10:
spellings first seen on or before 2026-11-03, Florida Blue Key's excluded.

The topic-word check classes each source by the words its cards' tags and headings hold. The words are
given here, never kept in code, and decide nothing:

    uv run python scripts/count_late_disclosures.py --data-dir <restored copy> --caselist hsld26 \
        --snapshot 2026-11-10 --topic-word de-extinct --other-topic-word "space col" \
        --other-topic-word coloniz

It prints one JSON object of counts, dates, public configuration and the late tournament spellings two
schools or more use that hold no school or team-code word; every other spelling is counted, not named.
No tag, heading, path, school or team code is printed. It reads the manifests, the suppression list and
the parsed store, opens no database, writes nothing and calls no model. Exit 2 refuses, on stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_late_disclosures import TopicWords, count_late_disclosures
from debate_core.integrations.landscape.yaml_taxonomy_repository import TOPICS_FILE, load_topic_map
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"


async def _run(arguments: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    data_dir: Path = arguments.data_dir.expanduser()
    if not data_dir.is_dir():
        raise FileNotFoundError(f"no data directory at {data_dir}")
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    counted = await count_late_disclosures(
        store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic_map=load_topic_map(arguments.config_dir / TOPICS_FILE),
        caselist=arguments.caselist,
        snapshot=arguments.snapshot,
        words=TopicWords(topic=tuple(arguments.topic_word), other=tuple(arguments.other_topic_word)),
        version=arguments.version,
    )
    return {**counted.as_json(), "runtime_seconds": round(time.perf_counter() - started, 1)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir", type=Path, required=True, help="A data directory, e.g. a restored copy."
    )
    parser.add_argument("--caselist", required=True, help="The caselist slug, e.g. hsld26.")
    parser.add_argument("--snapshot", type=date.fromisoformat, required=True, help="YYYY-MM-DD.")
    parser.add_argument(
        "--topic-word",
        action="append",
        required=True,
        help="A word of the snapshot's topic; repeat for more.",
    )
    parser.add_argument(
        "--other-topic-word",
        action="append",
        required=True,
        help="A word of the topic late files would be on; repeat for more.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml. Default: this checkout's config/landscape.",
    )
    parser.add_argument("--version", help="The parsed store's version directory. Default: the newest.")
    arguments = parser.parse_args(argv)
    try:
        result = asyncio.run(_run(arguments))
    except (DomainError, ValueError, OSError) as error:
        print(f"Refused: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
