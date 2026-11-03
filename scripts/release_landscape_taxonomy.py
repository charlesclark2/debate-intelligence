#!/usr/bin/env python3
"""Record a topic's position ids as released, in `config/landscape/released.yaml`.

`v1-e32-t08-released-position-ids`. The operator runs this when a landscape report under a new
`taxonomy_version` is first published, and commits the lock file it writes (in a PM batch or the
next task's pull request). From then on `tests/config/test_landscape_released_ids.py` refuses a
taxonomy edit that deletes one of those ids, changes its kind or side, or changes that version's
positions without a bump.

It reads the committed configuration only (`config/landscape/`), and refuses, writing nothing, when
the topic's taxonomy file is not at exactly `--version` (so a lock written late cannot record a
later edit), when that version is already in the lock, or when the configuration already breaks
the released ids.

    uv run python scripts/release_landscape_taxonomy.py --topic policy-2026-27-nhi --version 1.1.0
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from debate_core.application.errors import DomainError
from debate_core.integrations.landscape.released_ids import RELEASED_FILE, write_release

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--topic", required=True, help="The topic id, as topics.yaml names it.")
    parser.add_argument(
        "--version", required=True, help="The taxonomy_version the published report counted under."
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml, taxonomies/ and released.yaml. Default: config/landscape.",
    )
    arguments = parser.parse_args(argv)
    try:
        release = write_release(arguments.config_dir, arguments.topic, arguments.version)
    except (DomainError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    print(
        f"Released {release.topic_id} {release.taxonomy_version}: {len(release.positions)} position ids "
        f"written to {arguments.config_dir / RELEASED_FILE}."
    )
    print("Run `uv run pytest tests/config` and commit the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
