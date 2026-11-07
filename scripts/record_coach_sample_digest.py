#!/usr/bin/env python3
"""Record, once, the SHA-256 of a coach's labels file that no sitting has recorded (`v1-e32-t58`).

Every command that scores, replays or re-records against the coach's labels refuses a file whose SHA-256 is
not the one its sidecar, `<name>.sha256` beside it, records, and refuses a file with no sidecar. The coach's
sitting (`scripts/relabel_coach_sample.py`) writes the sidecar after the file. A file a sitting wrote before
the sidecar existed has none, and this is the step that records it: run by the operator, once per file.

It records the digest only when the file's SHA-256 is the one `--expect` gives (the one the sitting's record
gives, never one read off the file just now), and it never overwrites a sidecar: the sidecar is opened for
exclusive creation. Either refusal writes nothing and exits 1. It reads no row; it prints digests and paths
only. The rules are :mod:`debate_core.application.coach_sample_labels_file`; the runbook's block is in
`docs/runbooks/landscape-model-evaluation-record.md`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from debate_core.application.coach_sample_labels_file import (
    LabelsDigestAlreadyRecorded,
    LabelsFileNotTheExpectedOne,
    digest_path,
    record_first_digest,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")


def _sha256(text: str) -> str:
    digest = text.strip().lower()
    if not _SHA256.fullmatch(digest):
        raise argparse.ArgumentTypeError("a SHA-256 is 64 hex digits")
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sample", required=True, type=Path, help="The coach's labelled CSV.")
    parser.add_argument(
        "--expect", required=True, type=_sha256, help="The SHA-256 the file must have, from its sitting's record."
    )
    arguments = parser.parse_args(argv)
    sample = arguments.sample.expanduser()
    try:
        digest = record_first_digest(sample, expect=arguments.expect)
    except (LabelsDigestAlreadyRecorded, LabelsFileNotTheExpectedOne) as refused:
        print(f"Refused: {refused}. {refused.hint}", file=sys.stderr)
        return 1
    except OSError as failed:
        print(f"Refused: the labels file could not be read or its sidecar written ({type(failed).__name__}).",
              file=sys.stderr)
        return 1
    print(f"Recorded {digest} for {sample.name} in {digest_path(sample)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
