#!/usr/bin/env python3
"""Count the pairs card matching keeps apart that `v1-e31-t29` may recover. Counts only.

Per caselist, over the store's own occurrence table in its newest version directory that holds one
(the placement the store holds now, not a new one), by `debate_core.evidence.recall_shapes`:

* **neither end**: bodies nine-tenths inside a body in another cluster that holds neither of
  their ends, so the clusterer never compares the two: long and short, by how many clusters hold
  such a body, by the body's share of the smallest, and how many of those also hold a passage the
  body does not overlap (a witness the rules would refuse anyway);
* **trims sharing nothing**: two passages of one holder that share no five-word run, as pairs,
  by what their cards carry beside them (the same tag and cite, or not) and by how many of the
  holder's words are in neither trim (none: the holder is the two end to end);
* **the witness refusal**: every body holding two passages that do not overlap, by its length in
  words, and the bodies the refusal keeps out of every cluster holding them.

**Read-only, and nothing but counts leaves it.** It reads the parsed store in place and writes
nothing to the data directory. Its output on stdout is counts and the names of shapes: no card
text, tag, cite, file name, path or digest. `--save-candidates FILE` also writes the store positions
of what was counted (source digests and paragraph indices, no text), for
`scripts/sample_matching_recall.py` to draw from. The file goes neither in the repository nor in the
data directory. Progress goes to stderr.

    uv run python scripts/count_matching_recall.py \\
        --save-candidates ~/t29-matching-recall-candidates.jsonl > ~/t29-matching-recall-counts.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compare_card_clusters import (  # noqa: E402
    CardKey,
    Placement,
    _stored_cards,
    current_version,
    full_bodies,
    read_placements,
)
from count_card_boundaries import CASELISTS, outside_the_repository_and_the_store  # noqa: E402

from debate_core.application.ports.parsed_store import OCCURRENCES_NAME  # noqa: E402
from debate_core.evidence.cluster_diagnosis import CutOutcome, diagnose_cuts  # noqa: E402
from debate_core.evidence.near_duplicates import SHORT_BODY_SHINGLES, CutIndex  # noqa: E402
from debate_core.evidence.recall_shapes import (  # noqa: E402
    HOLDER_WORD_BANDS,
    WORDS_IN_NEITHER_BANDS,
    Label,
    band,
    label,
    neither_end_pairs,
    refusing_holders,
    tally_neither_end,
    tally_refusals,
    tally_trims,
    trims_sharing_nothing,
)
from debate_core.integrations.local.parsed_store import LocalParsedStore  # noqa: E402

__all__ = ["CANDIDATES_SHOWN", "count_caselist", "main"]

CANDIDATES_SHOWN = "~/t29-matching-recall-candidates.jsonl"


def _first_position(placed: Mapping[CardKey, Placement]) -> dict[str, CardKey]:
    """For each full body, the first store position that carries it."""
    first: dict[str, CardKey] = {}
    for key in sorted(placed):
        if placed[key].completeness == "FULL":
            first.setdefault(placed[key].exact_fingerprint, key)
    return first


def count_caselist(data_dir: Path, caselist: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The counts for one caselist, and the positions they were counted from."""
    started = time.monotonic()
    store = LocalParsedStore(data_dir)
    version = current_version(store, caselist)
    placed = read_placements(store.root / caselist / version / OCCURRENCES_NAME)
    full = [key for key in placed if placed[key].completeness == "FULL"]
    _progress(f"{caselist}: reading {len(full):,} full cards of {version}")
    cards = _stored_cards(store, caselist, version, full)
    bodies, clusters = full_bodies({key: card["evidence_text"] for key, card in cards.items()}, placed)
    labels: defaultdict[str, set[Label]] = defaultdict(set)
    for key, card in cards.items():
        labels[placed[key].exact_fingerprint].add(label(card.get("tag"), card.get("full_cite")))
    read_at = time.monotonic()

    _progress(f"{caselist}: finding which of {len(bodies):,} full texts hold which")
    index = CutIndex(bodies)
    census = diagnose_cuts(bodies, clusters, index=index)
    cluster_of = clusters.__getitem__
    neither_end = neither_end_pairs(census, index, cluster_of)
    trims = trims_sharing_nothing(index, cluster_of, labels)
    holders = refusing_holders(index)
    kept_out = [
        finding for finding in census.findings if finding.outcome is CutOutcome.HELD_WITH_ANOTHER_PASSAGE
    ]
    finished = time.monotonic()

    counts: dict[str, Any] = {
        "version_directory": version,
        "fingerprint_version": ", ".join(
            sorted({placement.fingerprint_version for placement in placed.values()})
        ),
        "cards": len(placed),
        "full_texts": len(bodies),
        "neither_end": tally_neither_end(neither_end),
        "trims_sharing_nothing": tally_trims(trims),
        "witness_refusal": tally_refusals(holders, kept_out, index),
        "seconds": {"reading": round(read_at - started), "counting": round(finished - read_at)},
    }
    at = _first_position(placed)
    rows: list[dict[str, Any]] = [
        {
            "caselist": caselist,
            "shape": "neither-end",
            "group": "long" if pair.shingles >= SHORT_BODY_SHINGLES else "short",
            "cut": list(at[pair.cut]),
            "container": list(at[pair.container]),
        }
        for pair in neither_end
    ]
    rows += [
        {
            "caselist": caselist,
            "shape": "trims",
            "group": pair.beside.value,
            "words_in_neither": band(pair.words_in_neither, WORDS_IN_NEITHER_BANDS),
            "holder": list(at[pair.holder]),
            "pieces": [list(at[pair.first]), list(at[pair.second])],
        }
        for pair in trims
    ]
    rows += [
        {
            "caselist": caselist,
            "shape": "refusing-holder",
            "group": band(holder.words, HOLDER_WORD_BANDS),
            "sharing_nothing": holder.sharing_nothing,
            "holder": list(at[holder.holder]),
        }
        for holder in holders
    ]
    return counts, rows


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".debate-research" / "dev",
        help="The data directory whose parsed store is read. Default: the dev data directory.",
    )
    parser.add_argument(
        "--caselist", action="append", help=f"Repeat for several. Default: {', '.join(CASELISTS)}."
    )
    parser.add_argument(
        "--save-candidates",
        type=Path,
        help=f"Also write the positions counted (digests, indices) here, e.g. {CANDIDATES_SHOWN}.",
    )
    arguments = parser.parse_args(argv)
    saved = (
        outside_the_repository_and_the_store(
            arguments.save_candidates, arguments.data_dir, "--save-candidates"
        )
        if arguments.save_candidates
        else None
    )
    started = time.monotonic()
    results: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    for caselist in arguments.caselist or CASELISTS:
        counts, found = count_caselist(arguments.data_dir, caselist)
        results[caselist] = counts
        candidates.extend(found)
    print(
        json.dumps(
            {"caselists": results, "seconds": round(time.monotonic() - started)}, indent=1, sort_keys=True
        )
    )
    if saved is not None:
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in candidates), encoding="utf-8"
        )
        _progress(f"{len(candidates):,} candidates written to {saved.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
