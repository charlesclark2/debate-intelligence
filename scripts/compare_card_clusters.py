#!/usr/bin/env python3
"""Compare a parsed store's card clusters before and after the matching rules change.

`v1-e31-t08-short-card-recall` changed which cards share a cluster (`card-fingerprint-v2`). The
labelled sets say the change is right on 99 invented rows. This says what it does to a real
caselist's occurrence table, in two ways:

* **`counts`** prints counts only: clusters before and after, how many merged, how many abbreviated
  disclosures newly linked, and the largest cluster before and after. One cluster taking in
  hundreds of others would be a false-positive signal, and is what the `absorbed` figures are for.
* **`sample`** draws newly joined pairs at random and shows each on the terminal for a person to
  judge: same card, different card, unsure (Goal criterion ac5). Only the tallies are printed at
  the end.

**Before and after.** A cluster placement is one cluster id per card position. *After* is what
the store's `occurrences.jsonl` holds now, and *before* is one of:

* `--before FILE`: a copy of that file saved before `caselist parse` rebuilt it. Seconds.
* `--before-rules REF`: the store's cards placed in memory by the matching rules as they were at
  git ref `REF`. For when no earlier table exists for these cards: a re-parse under a new parser
  version writes a new directory, and its first occurrence table is already the new rules'. Takes
  about as long as a rebuild.
* neither: *before* is the store's file and *after* is the store's cards placed in memory by the
  checked-out rules. A preview of the next rebuild, which takes about as long as one.

`sample --divided` shows the opposite change: pairs that shared a cluster before and no longer do.

**Operator-run on the real store.** It writes nothing to the store or the repository.
`--before-rules` copies source files, never card text, to a temporary directory it removes, and
`counts --save-before` writes digests and cluster ids where it is told to. It never
prints a card's text, tag or cite except in `sample`, to a terminal, one pair at a time, cleared
before the next; `sample` refuses to run when its input or output is not a terminal, so nothing it
shows can land in a file or a pipe. The store itself holds no path, school or team code
(`docs/data/parsed-card-store.md`).

    uv run python scripts/compare_card_clusters.py counts --caselist openev
    uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --before ~/saved/hsld26.jsonl
    uv run python scripts/compare_card_clusters.py sample --caselist hsld26 --before-rules 8c082b5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.ports.parsed_store import (
    OCCURRENCES_NAME,
    parse_version_directory,
    source_object_key,
)
from debate_core.domain.debate_files import ParsedCard
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.fakes import build_fake_caselist_repository

__all__ = [
    "ABSORBED_BANDS",
    "MATCHING_RULE_MODULES",
    "ClusterChange",
    "Joined",
    "Placement",
    "common_cards",
    "compare",
    "joined_pairs",
    "main",
    "placements_now",
    "placements_under_rules",
    "read_placements",
    "run_sample",
    "write_placements",
]

type CardKey = tuple[str, int]
"""A card position: its source's SHA-256 and its first element index."""

#: How many earlier clusters one new cluster is made of, in bands. The last is the alarm.
ABSORBED_BANDS = ((2, 2), (3, 5), (6, 20), (21, 100), (101, None))

VERDICTS = {"s": "same card", "d": "different card", "u": "unsure"}

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_SOURCE = REPO_ROOT / "packages" / "debate_core" / "src"

#: The modules that decide a card's cluster, relative to the `debate_core` package. `--before-rules`
#: takes these four from a git ref and everything else from the checkout, so the store's records
#: are read by today's models and placed by that ref's rules.
MATCHING_RULE_MODULES = (
    "evidence/fingerprints.py",
    "evidence/near_duplicates.py",
    "evidence/abbreviated_links.py",
    "application/caselist_card_stats.py",
)

#: Clear the screen and its scrollback, and move to the top: a pair is not left on the terminal.
CLEAR_TERMINAL = "\x1b[2J\x1b[3J\x1b[H"


@dataclass(frozen=True, slots=True)
class Placement:
    """Where one card position was placed, as an occurrence row records it."""

    cluster_id: str
    membership: str
    completeness: str
    exact_fingerprint: str
    fingerprint_version: str


@dataclass(frozen=True, slots=True)
class ClusterChange:
    """What changed between two placements of the same card positions. Counts only."""

    cards: int
    """Card positions in both placements: everything else here is over these."""
    cards_only_before: int
    cards_only_after: int
    before_version: str
    after_version: str
    clusters_before: int
    clusters_after: int
    clusters_merged_into_another: int
    """Earlier clusters that now share a cluster with a larger earlier cluster."""
    clusters_made_of_several: int
    """New clusters made of more than one earlier cluster."""
    absorbed: dict[str, int]
    """New clusters by how many earlier clusters each is made of."""
    most_absorbed: int
    clusters_divided: int
    """Earlier clusters whose cards are now in more than one cluster."""
    newly_linked_to_a_full_card: int
    newly_grouped_with_abbreviated_cards: int
    no_longer_linked: int
    largest_before: int
    largest_after: int
    largest_before_distinct_texts: int
    largest_after_distinct_texts: int
    exact_fingerprints_changed: int

    def as_json(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Joined:
    """One earlier cluster that joined a larger one: a card from each, for a person to compare."""

    kind: str
    joiner: CardKey
    host: CardKey


# ------------------------------------------------------------------------------------------------
# Reading placements
# ------------------------------------------------------------------------------------------------


def read_placements(occurrences: Path) -> dict[CardKey, Placement]:
    """Every card position in an `occurrences.jsonl`. A card's rows differ only by disclosure."""
    placed: dict[CardKey, Placement] = {}
    with occurrences.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            placed[(row["source_sha256"], row["first_element_index"])] = Placement(
                cluster_id=row["cluster_id"],
                membership=row["membership"],
                completeness=row["completeness"],
                exact_fingerprint=row["exact_fingerprint"],
                fingerprint_version=row["fingerprint_version"],
            )
    return placed


def write_placements(placed: Mapping[CardKey, Placement], path: Path) -> None:
    """Save placements in the shape `read_placements` reads: digests, indices and ids, no text.

    For `counts --save-before`: placing a caselist under earlier rules takes minutes, and the
    sample that follows should not have to do it again.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for (sha256, element), placement in sorted(placed.items()):
            row = {"source_sha256": sha256, "first_element_index": element}
            row.update({name: getattr(placement, name) for name in Placement.__dataclass_fields__})
            stream.write(json.dumps(row, sort_keys=True) + "\n")


def current_version(store: LocalParsedStore, caselist: str) -> str:
    """The newest version directory of `caselist` that holds an occurrence table."""
    versions = asyncio.run(store.version_directories(caselist))
    built = [name for name in versions if (store.root / caselist / name / OCCURRENCES_NAME).is_file()]
    if not built:
        raise SystemExit(f"{caselist}: no version directory under {store.root} holds {OCCURRENCES_NAME}")
    return max(built, key=parse_version_directory)


def read_cards(
    store: LocalParsedStore, caselist: str, version: str, keys: Iterable[CardKey]
) -> dict[CardKey, ParsedCard]:
    """The stored cards at `keys`, without their formatting, as the rebuild reads them."""
    wanted: defaultdict[str, set[int]] = defaultdict(set)
    for sha256, element in keys:
        wanted[sha256].add(element)
    cards: dict[CardKey, ParsedCard] = {}
    for sha256 in sorted(wanted):
        record = asyncio.run(store.read_document(caselist, version, sha256))
        if record is None:
            raise SystemExit(f"{caselist}: {source_object_key(caselist, version, sha256)} has no document")
        # The store holds no disclosure path; the card model needs one, and nothing here reads it.
        for card in record.to_parsed_document(f"{sha256}.docx").cards:
            if card.provenance.first_element_index in wanted[sha256]:
                cards[(sha256, card.provenance.first_element_index)] = card.model_copy(
                    update={"formatting_spans": (), "font_size_spans": ()}
                )
    return cards


def placements_now(cards: Mapping[CardKey, ParsedCard], fingerprint_version: str) -> dict[CardKey, Placement]:
    """Place `cards` with the checked-out matching rules, as the next rebuild will."""
    ordered = sorted(cards)
    placed = CaselistCardStatsService(build_fake_caselist_repository()).place([cards[key] for key in ordered])
    return {
        key: Placement(
            cluster_id=placement.cluster_id,
            membership=str(placement.membership),
            completeness=str(placement.card.completeness),
            exact_fingerprint=placement.fingerprint,
            fingerprint_version=fingerprint_version,
        )
        for key, placement in zip(ordered, placed, strict=True)
    }


def _module_at(ref: str) -> Callable[[str], bytes]:
    def read(module: str) -> bytes:
        path = f"{ref}:packages/debate_core/src/debate_core/{module}"
        shown = subprocess.run(["git", "-C", str(REPO_ROOT), "show", path], capture_output=True, check=False)
        if shown.returncode != 0:
            raise SystemExit(f"git has no {path}: {shown.stderr.decode('utf-8', 'replace').strip()}")
        return shown.stdout

    return read


def placements_under_rules(
    read_module: Callable[[str], bytes], data_dir: Path, caselist: str
) -> dict[CardKey, Placement]:
    """Place a caselist's stored cards with other matching rules, in a process of their own.

    `read_module` returns the source of each of :data:`MATCHING_RULE_MODULES`. They replace those
    modules in a temporary copy of the package, which a child process imports ahead of the
    installed one. The child prints one line of digests and ids per card and no text.
    """
    with tempfile.TemporaryDirectory(prefix="card-matching-rules-") as temporary:
        package = Path(temporary) / "debate_core"
        shutil.copytree(PACKAGE_SOURCE / "debate_core", package, ignore=shutil.ignore_patterns("__pycache__"))
        for module in MATCHING_RULE_MODULES:
            (package / module).write_bytes(read_module(module))
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (temporary, environment.get("PYTHONPATH", "")) if part
        )
        child = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--data-dir",
                str(data_dir),
                "place",
                "--caselist",
                caselist,
            ],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
    if child.returncode != 0:
        # The child's error names a module and a line, and at worst a digest: never card text.
        raise SystemExit(f"placing {caselist} under the other rules failed:\n{child.stderr.strip()[-2000:]}")
    placed: dict[CardKey, Placement] = {}
    for line in child.stdout.splitlines():
        sha256, element, *fields = json.loads(line)
        placed[(sha256, element)] = Placement(*fields)
    return placed


def _place(arguments: argparse.Namespace) -> int:
    """The child of `placements_under_rules`: the store's cards, placed by whatever rules it imports."""
    from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

    store = LocalParsedStore(arguments.data_dir)
    for caselist in arguments.caselist:
        version = current_version(store, caselist)
        held = read_placements(store.root / caselist / version / OCCURRENCES_NAME)
        placed = placements_now(read_cards(store, caselist, version, held), FINGERPRINT_VERSION)
        for (sha256, element), placement in sorted(placed.items()):
            fields = [getattr(placement, name) for name in Placement.__dataclass_fields__]
            print(json.dumps([sha256, element, *fields]))
    return 0


# ------------------------------------------------------------------------------------------------
# Comparing
# ------------------------------------------------------------------------------------------------


def _members(placed: Mapping[CardKey, Placement]) -> dict[str, list[CardKey]]:
    members: defaultdict[str, list[CardKey]] = defaultdict(list)
    for key in sorted(placed):
        members[placed[key].cluster_id].append(key)
    return dict(members)


def _band(count: int) -> str:
    for low, high in ABSORBED_BANDS:
        if high is None:
            if count >= low:
                return f"{low} or more"
        elif low <= count <= high:
            return str(low) if low == high else f"{low} to {high}"
    raise ValueError(count)


def common_cards(
    before: Mapping[CardKey, Placement], after: Mapping[CardKey, Placement]
) -> tuple[dict[CardKey, Placement], dict[CardKey, Placement]]:
    """Both placements, kept to the card positions they share.

    A pull between the saved table and the rebuild adds sources, and a removal takes them away.
    What changed for a card is only meaningful where it is in both.
    """
    shared = before.keys() & after.keys()
    return {key: before[key] for key in shared}, {key: after[key] for key in shared}


def compare(before: Mapping[CardKey, Placement], after: Mapping[CardKey, Placement]) -> ClusterChange:
    """What moved between two placements, over the card positions both cover."""
    only_before, only_after = len(before.keys() - after.keys()), len(after.keys() - before.keys())
    before, after = common_cards(before, after)
    old, new = _members(before), _members(after)
    made_of = {cluster: {before[key].cluster_id for key in keys} for cluster, keys in new.items()}
    spread = {cluster: {after[key].cluster_id for key in keys} for cluster, keys in old.items()}
    several = {cluster: parts for cluster, parts in made_of.items() if len(parts) > 1}
    absorbed = Counter(_band(len(parts)) for parts in several.values())
    has_full = {
        cluster for cluster, keys in new.items() if any(after[k].completeness == "FULL" for k in keys)
    }

    linked = grouped = unlinked = 0
    for key, now in after.items():
        was = before[key]
        if was.membership == "UNLINKED" and now.membership == "ABBREVIATED_LINK":
            if now.cluster_id in has_full:
                linked += 1
            else:
                grouped += 1
        elif was.membership == "ABBREVIATED_LINK" and now.membership == "UNLINKED":
            unlinked += 1

    def largest(
        members: Mapping[str, Sequence[CardKey]], placed: Mapping[CardKey, Placement]
    ) -> tuple[int, int]:
        if not members:
            return 0, 0
        cluster = max(members, key=lambda name: (len(members[name]), name))
        return len(members[cluster]), len({placed[key].exact_fingerprint for key in members[cluster]})

    largest_before, texts_before = largest(old, before)
    largest_after, texts_after = largest(new, after)
    return ClusterChange(
        cards=len(after),
        cards_only_before=only_before,
        cards_only_after=only_after,
        before_version=", ".join(sorted({placement.fingerprint_version for placement in before.values()})),
        after_version=", ".join(sorted({placement.fingerprint_version for placement in after.values()})),
        clusters_before=len(old),
        clusters_after=len(new),
        clusters_merged_into_another=sum(len(parts) - 1 for parts in several.values()),
        clusters_made_of_several=len(several),
        absorbed={_band(low): absorbed.get(_band(low), 0) for low, _ in ABSORBED_BANDS},
        most_absorbed=max((len(parts) for parts in made_of.values()), default=0),
        clusters_divided=sum(len(parts) > 1 for parts in spread.values()),
        newly_linked_to_a_full_card=linked,
        newly_grouped_with_abbreviated_cards=grouped,
        no_longer_linked=unlinked,
        largest_before=largest_before,
        largest_after=largest_after,
        largest_before_distinct_texts=texts_before,
        largest_after_distinct_texts=texts_after,
        exact_fingerprints_changed=sum(
            before[key].exact_fingerprint != after[key].exact_fingerprint for key in after
        ),
    )


def joined_pairs(before: Mapping[CardKey, Placement], after: Mapping[CardKey, Placement]) -> list[Joined]:
    """One pair per earlier cluster that joined a larger one, in a fixed order.

    In a new cluster made of several earlier clusters, the earlier cluster with the most cards is
    the host and each of the others joined it. The pair is the first card of each.
    """
    pairs: list[Joined] = []
    before, after = common_cards(before, after)
    for _, keys in sorted(_members(after).items()):
        parts: defaultdict[str, list[CardKey]] = defaultdict(list)
        for key in keys:
            parts[before[key].cluster_id].append(key)
        if len(parts) < 2:
            continue
        host = max(parts, key=lambda name: (len(parts[name]), name))
        for name in sorted(parts):
            if name == host:
                continue
            joiner, hosted = parts[name][0], parts[host][0]
            abbreviated = sum(after[key].completeness != "FULL" for key in (joiner, hosted))
            kind = ("full with full", "abbreviated with full", "abbreviated with abbreviated")[abbreviated]
            pairs.append(Joined(kind=kind, joiner=joiner, host=hosted))
    return pairs


# ------------------------------------------------------------------------------------------------
# The by-eye sample
# ------------------------------------------------------------------------------------------------


def _show(card: ParsedCard, label: str) -> str:
    words = len(card.evidence_text.split())
    text = card.evidence_text if card.evidence_text.strip() else f"(no body) {card.full_cite}"
    return f"--- {label}: {card.completeness}, {words} words, cite {card.short_cite or '(none)'}\n{text}\n"


def run_sample(
    pairs: Sequence[tuple[str, Joined, ParsedCard, ParsedCard]],
    *,
    ask: Callable[[str], str],
    show: Callable[[str], None],
    change: str = "Newly in one cluster.",
) -> Counter[tuple[str, str]]:
    """Show each pair, take a verdict for it, and return the tallies by kind and verdict."""
    tallies: Counter[tuple[str, str]] = Counter()
    for number, (caselist, pair, joiner, host) in enumerate(pairs, start=1):
        show(CLEAR_TERMINAL)
        show(f"Pair {number} of {len(pairs)} ({caselist}, {pair.kind}). {change}\n\n")
        show(_show(joiner, "A"))
        show("\n")
        show(_show(host, "B"))
        verdict = ""
        while verdict not in VERDICTS:
            verdict = ask("\n[s] same card   [d] different card   [u] unsure   > ").strip().lower()[:1]
        tallies[(pair.kind, VERDICTS[verdict])] += 1
    show(CLEAR_TERMINAL)
    return tallies


# ------------------------------------------------------------------------------------------------
# The command line
# ------------------------------------------------------------------------------------------------


def _load(
    arguments: argparse.Namespace, store: LocalParsedStore, caselist: str
) -> tuple[str, dict[CardKey, Placement], dict[CardKey, Placement]]:
    """The version directory read, and the placements before and after."""
    version = current_version(store, caselist)
    held = read_placements(store.root / caselist / version / OCCURRENCES_NAME)
    if arguments.before is not None:
        before: Path = arguments.before
        return version, read_placements(before / f"{caselist}.jsonl" if before.is_dir() else before), held
    if arguments.before_rules is not None:
        earlier = placements_under_rules(_module_at(arguments.before_rules), arguments.data_dir, caselist)
        return version, earlier, held
    from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

    cards = read_cards(store, caselist, version, held)
    return version, held, placements_now(cards, FINGERPRINT_VERSION)


def _counts(arguments: argparse.Namespace) -> int:
    store = LocalParsedStore(arguments.data_dir)
    results: dict[str, dict[str, object]] = {}
    for caselist in arguments.caselist:
        started = time.monotonic()
        _, before, after = _load(arguments, store, caselist)
        change = compare(before, after)
        results[caselist] = {**change.as_json(), "seconds": round(time.monotonic() - started, 1)}
        if arguments.save_before is not None:
            write_placements(before, arguments.save_before / f"{caselist}.jsonl")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


def _sample(arguments: argparse.Namespace) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "sample shows card text, so it runs only with a terminal for input and output.", file=sys.stderr
        )
        return 2
    store = LocalParsedStore(arguments.data_dir)
    seed = arguments.seed if arguments.seed is not None else random.SystemRandom().randrange(10**9)
    candidates: list[tuple[str, str, Joined]] = []
    counts: dict[str, dict[str, object]] = {}
    for caselist in arguments.caselist:
        print(f"Reading {caselist} ...", flush=True)
        version, before, after = _load(arguments, store, caselist)
        counts[caselist] = compare(before, after).as_json()
        # A pair that was divided is a pair that joined, read from after to before.
        changed = joined_pairs(after, before) if arguments.divided else joined_pairs(before, after)
        candidates.extend((caselist, version, pair) for pair in changed)
    drawn = random.Random(seed).sample(candidates, min(arguments.count, len(candidates)))
    pairs: list[tuple[str, Joined, ParsedCard, ParsedCard]] = []
    for caselist, version, pair in drawn:
        cards = read_cards(store, caselist, version, [pair.joiner, pair.host])
        pairs.append((caselist, pair, cards[pair.joiner], cards[pair.host]))
    change = "No longer in one cluster." if arguments.divided else "Newly in one cluster."
    tallies = run_sample(pairs, ask=input, show=lambda text: print(text, end="", flush=True), change=change)
    print(json.dumps(counts, indent=2, sort_keys=True))
    what = "divided" if arguments.divided else "newly joined"
    print(f"Drew {len(pairs)} of {len(candidates)} {what} pairs, seed {seed}.")
    for (kind, verdict), count in sorted(tallies.items()):
        print(f"  {kind}: {verdict}: {count}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".debate-research" / "dev",
        help="The data directory whose parsed/ store is read. Default: the dev data directory.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("counts", _counts), ("sample", _sample), ("place", _place)):
        command = commands.add_parser(name)
        command.add_argument("--caselist", action="append", required=True, help="Repeat for several.")
        command.set_defaults(handler=handler)
        if name == "place":
            continue  # run by --before-rules in a child process; prints digests and ids
        earlier = command.add_mutually_exclusive_group()
        earlier.add_argument(
            "--before",
            type=Path,
            help="An occurrences.jsonl saved before the rebuild, or a directory of <caselist>.jsonl.",
        )
        earlier.add_argument(
            "--before-rules",
            metavar="GIT_REF",
            help="Place the store's cards with the matching rules as they were at this git ref.",
        )
        if name == "counts":
            command.add_argument(
                "--save-before",
                type=Path,
                metavar="DIRECTORY",
                help="Also write the 'before' placements there as <caselist>.jsonl, to pass as --before.",
            )
        if name == "sample":
            command.add_argument("--count", type=int, default=20)
            command.add_argument("--seed", type=int)
            command.add_argument(
                "--divided",
                action="store_true",
                help="Draw pairs that shared a cluster before and no longer do.",
            )
    arguments = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = arguments.handler
    return handler(arguments)


if __name__ == "__main__":
    sys.exit(main())
