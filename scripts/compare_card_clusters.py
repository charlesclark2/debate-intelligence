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

**Inside one placement** (`v1-e31-t11-long-card-splits-and-fragment-merges`), with no *before*
needed, so both take seconds on the store's own table:

* **`diagnose`** prints counts only: every body that a body outside its cluster contains and which
  limit kept it out, whether the clusters holding a short cut read as one card that was split or
  as different cards, and the shape of the largest clusters from the inside. With `--before` or
  `--before-rules` it also says, for each divided pair, why its part is no longer with the rest.
  `--preview` diagnoses the placement the checked-out rules would make instead of the store's.
* **`sample --cluster ID`** (or `--largest RANK`) draws pairs of different texts from one cluster,
  for a person to say whether a large cluster is one card. `--least-alike` shows the pairs that
  share the least text first, which is where two cards merged into one cluster would be.
* **`sample --kept-apart-by LIMIT`** draws cuts that `diagnose` counts under one limit, each with
  the smallest body that holds it, for a person to say whether the limit is keeping copies of one
  card apart. It is the evidence for moving a limit, taken before the limit is moved.

**Cluster shapes** (`v1-e31-t21-cluster-shapes-and-sampler`), with no *before* either:

* **`shapes`** prints counts only: for the largest clusters of each caselist (`--largest-clusters`,
  three by default), or one cluster by `--cluster ID`, every pair of the cluster's distinct full
  texts by shape (`debate_core.evidence.pair_shapes`: identical, contained, overlapping,
  sharing a little, sharing nothing), the cluster's distinct short cites and texts with none, and
  its texts' word counts. Its texts are the ones `diagnose` describes the largest clusters by, so
  its share sharing nothing is the figure `diagnose` gives. Each cluster's pairs sharing only one
  or two five-word runs are counted too, and `--every-cluster` counts them over every cluster of
  the caselist (`v1-e31-t20`): one run is enough to pass the clusterer's guard against joining
  texts that share nothing, so the count says whether a stock phrase is bridging different cards.

**Every `sample` asks a person only what a rule cannot decide.** Of the pairs it draws, a pair of
two full cards that is identical, or one inside the other, is the same card, and a pair sharing no
text is two different cards: those are counted and never shown (the PM's ruling of 2026-10-16, in
`debate_core.evidence.pair_shapes`). `--ask-shape SHAPE` shows the pairs of a shape the rule
decides as well, without the rule's verdict, and tallies the person's answers apart, beside the
rule's (`v1-e31-t20`): a short quote two articles both carry is contained in each without being one
card, so the rule's "contained is the same card" is itself measured. A person is shown the rest one
at a time: both texts side by side, or one above the other on a narrow terminal, the text both hold
underlined and each side's own text in bold, trimmed to the shared region when long. One key
answers each, `q` stops and keeps the tallies so far. The tallies keep what the rule decided apart
from what the person did.

**Placements in memory, and saved** (`v1-e31-t20-long-cuts-and-limits`). A rebuild under new rules
takes minutes per caselist, and what it would do can be read before it runs, without writing to the
store. `counts` with neither *before* option places the store's cards by the checked-out rules in
memory, and `--save-after DIR` keeps that placement (digests, indices and ids, no text). Every
command then reads it with `--after DIR` in place of the store's table: `shapes` and `diagnose`
describe it, `sample` draws from it, and `counts` and `sample` compare it with the store's table.
`shapes --preview` and `diagnose --preview` place the cards in memory themselves.

**Operator-run on the real store.** It writes nothing to the store or the repository.
`--before-rules` copies source files, never card text, to a temporary directory it removes, and
`counts --save-before` and `--save-after` write digests and cluster ids where they are told to. It
never prints a card's text, tag or cite except in `sample`, to a terminal, one pair at a time,
cleared before the next; `sample` refuses to run when its input or output is not a terminal, so
nothing it shows can land in a file or a pipe; `sample --save-tallies` appends its closing lines,
which are counts and hold no text, tag, cite, path or digest, to a file. The store itself holds no
path, school or team code (`docs/data/parsed-card-store.md`).

    uv run python scripts/compare_card_clusters.py counts --caselist openev
    uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --before ~/saved/hsld26.jsonl
    uv run python scripts/compare_card_clusters.py sample --caselist hsld26 --before-rules 8c082b5
    uv run python scripts/compare_card_clusters.py diagnose --caselist openev
    uv run python scripts/compare_card_clusters.py sample --caselist hspolicy26 --largest 1 --count 10
    uv run python scripts/compare_card_clusters.py shapes --caselist hspf26 --caselist hsld26
    uv run python scripts/compare_card_clusters.py counts --caselist openev --save-after ~/saved/after
    uv run python scripts/compare_card_clusters.py shapes --caselist openev --after ~/saved/after
    uv run python scripts/compare_card_clusters.py sample --caselist openev --after ~/saved/after \\
        --kept-apart-by under-the-minimum-share --ask-shape contained-under-a-third
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.ports.parsed_store import (
    OCCURRENCES_NAME,
    parse_version_directory,
    source_object_key,
)
from debate_core.domain.debate_files import CardCompleteness, ParsedCard
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.fakes import build_fake_caselist_repository

if TYPE_CHECKING:
    from debate_core.evidence.cluster_diagnosis import CutFinding

__all__ = [
    "ABSORBED_BANDS",
    "ASK_SHAPES",
    "JOINED_BANDS",
    "KEPT_APART_BY",
    "MATCHING_RULE_MODULES",
    "NO_WORDS",
    "STOP_KEY",
    "ClusterChange",
    "Joined",
    "Placement",
    "SampleTallies",
    "classify_pair",
    "cluster_pairs",
    "common_cards",
    "compare",
    "describe_cluster_shapes",
    "describe_pairs_sharing_few_runs",
    "describe_largest_clusters",
    "diagnose",
    "divided_parts",
    "joined_pairs",
    "kept_apart",
    "kept_apart_kind",
    "largest_clusters",
    "main",
    "placements_now",
    "placements_under_rules",
    "read_bodies",
    "read_bodies_and_cites",
    "read_key",
    "read_placements",
    "render_pair",
    "run_sample",
    "size_rank",
    "write_placements",
]

type CardKey = tuple[str, int]
"""A card position: its source's SHA-256 and its first element index."""

#: How many earlier clusters one new cluster is made of, in bands. The last is the alarm.
ABSORBED_BANDS = ((2, 2), (3, 5), (6, 20), (21, 100), (101, None))

#: A person's answers, one key each. The first two are the words a rule's verdict is tallied in.
VERDICTS = {"s": "same card", "d": "different card", "u": "unsure"}

STOP_KEY = "q"
"""Stops a sample and keeps the tallies of the pairs answered so far."""

ANSWER_PROMPT = (
    f"\n[s] same card   [d] different card   [u] unsure   [{STOP_KEY}] stop, keeping the tallies   > "
)

NO_WORDS = "a side has no words"
"""The shape a pair is tallied under when a body has no shingle, and so no shape: a person's to judge."""

#: What `sample --kept-apart-by` can draw: cuts `diagnose` counts as apart from a body that holds
#: them, by the limit that applies (`debate_core.evidence.cluster_diagnosis.CutOutcome`, in the
#: order the cut step applies them since `card-fingerprint-v4`). Names, not the outcomes: this
#: module is imported by `--before-rules` against earlier rules, which the diagnosis cannot read.
KEPT_APART_BY = (
    "ends-held-by-too-many-clusters",
    "held-with-another-passage",
    "own-cluster-and-another",
    "witnesses-in-several-clusters",
    "under-the-minimum-share",
    "unrelated-texts",
    "within-the-rule",
    "lacking-both-ends",
)

#: The bands of a cut's share of the body holding it, as `sample --joined-in-band` names them
#: (`debate_core.evidence.cluster_diagnosis.SHARE_BANDS`).
JOINED_BANDS = {
    "under-a-tenth": "under a tenth",
    "a-tenth-to-a-quarter": "a tenth to a quarter",
    "a-quarter-to-a-half": "a quarter to a half",
    "half-or-more": "half or more",
}

#: The shapes a rule decides, as `sample --ask-shape` names them (`debate_core.evidence.pair_shapes`).
ASK_SHAPES = {
    "identical": "identical",
    "contained-under-a-third": "contained, under a third of the larger",
    "contained-a-third-or-more": "contained, a third or more of the larger",
    "sharing-nothing": "sharing nothing",
}

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

#: How a shown pair is marked: the text both bodies hold, each side's own text, and a note of what
#: was left out. Each word is styled and reset on its own, so a style never runs into the other
#: column.
SHARED_STYLE = "\x1b[4m"  # underlined
OWN_STYLE = "\x1b[1m"  # bold
NOTE_STYLE = "\x1b[2m"  # dim
RESET_STYLE = "\x1b[0m"

SHOWN_IN_FULL_WORDS = 150
"""A side with more words than this is trimmed to the region it shares, with some context."""
CONTEXT_WORDS = 25
"""Words of a trimmed side's own text kept before and after the region it shares."""
SHARED_RUN_EDGE = 10
"""Words kept at each end of a long run of shared text inside a trimmed side; the run is identical
on both sides, so its middle says nothing."""
OWN_RUN_EDGE = 40
"""Words kept at each end of a long run of a trimmed side's own text inside its shared region."""
SIDE_BY_SIDE_COLUMN = 50
"""The narrowest column two texts are shown side by side in; on a narrower terminal, one above the
other."""


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


def read_bodies(
    store: LocalParsedStore, caselist: str, version: str, keys: Iterable[CardKey]
) -> dict[CardKey, str]:
    """The stored body text at `keys`, read from each source's record as JSON and nothing more.

    `read_cards` builds every card of every document, formatting included, which is most of what a
    rebuild's reading costs. The diagnosis compares bodies and needs none of the rest.
    """
    return {key: card["evidence_text"] for key, card in _stored_cards(store, caselist, version, keys).items()}


def read_bodies_and_cites(
    store: LocalParsedStore, caselist: str, version: str, keys: Iterable[CardKey]
) -> dict[CardKey, tuple[str, str | None]]:
    """The stored body and short cite at `keys`, read as `read_bodies` reads them. For `shapes`."""
    return {
        key: (card["evidence_text"], card["short_cite"])
        for key, card in _stored_cards(store, caselist, version, keys).items()
    }


def _stored_cards(
    store: LocalParsedStore, caselist: str, version: str, keys: Iterable[CardKey]
) -> dict[CardKey, dict[str, Any]]:
    """The stored cards at `keys`, as each source's record holds them in JSON."""
    wanted: defaultdict[str, set[int]] = defaultdict(set)
    for sha256, element in keys:
        wanted[sha256].add(element)
    cards: dict[CardKey, dict[str, Any]] = {}
    for sha256 in sorted(wanted):
        path = store.root / source_object_key(caselist, version, sha256)
        with path.open(encoding="utf-8") as stream:
            stream.readline()
            document = json.loads(stream.readline())["document"]
        for card in document["cards"]:
            element = card["provenance"]["first_element_index"]
            if element in wanted[sha256]:
                cards[(sha256, element)] = card
    missing = sum(len(elements) for elements in wanted.values()) - len(cards)
    if missing:
        raise SystemExit(f"{caselist}: {missing} card positions of the table are in no stored document")
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
# Diagnosing one placement
# ------------------------------------------------------------------------------------------------


def full_bodies(
    texts: Mapping[CardKey, str], placed: Mapping[CardKey, Placement]
) -> tuple[dict[str, str], dict[str, str]]:
    """The distinct FULL bodies among `texts`, and the cluster each was placed in, by exact fingerprint."""
    bodies: dict[str, str] = {}
    clusters: dict[str, str] = {}
    for key in sorted(texts):
        placement = placed[key]
        if placement.completeness == "FULL" and placement.exact_fingerprint not in bodies:
            bodies[placement.exact_fingerprint] = texts[key]
            clusters[placement.exact_fingerprint] = placement.cluster_id
    return bodies, clusters


def largest_clusters(placed: Mapping[CardKey, Placement], count: int) -> list[tuple[str, list[CardKey]]]:
    """The `count` clusters with the most card positions, largest first; ties by cluster id."""
    members = _members(placed)
    ranked = sorted(members, key=lambda name: (-len(members[name]), name))
    return [(name, members[name]) for name in ranked[:count]]


def divided_parts(
    before: Mapping[CardKey, Placement], after: Mapping[CardKey, Placement]
) -> list[tuple[set[str], set[str], bool]]:
    """One entry per divided pair: the FULL texts of the part that left, of the rest, and whether
    the part holds a FULL card at all.

    The same pairs `sample --divided` draws from: in an earlier cluster now in several, the part
    with the most cards is the host and each other part left it. The rest is every other part.
    """
    entries: list[tuple[set[str], set[str], bool]] = []
    before, after = common_cards(before, after)
    for _, keys in sorted(_members(before).items()):
        parts: defaultdict[str, list[CardKey]] = defaultdict(list)
        for key in keys:
            parts[after[key].cluster_id].append(key)
        if len(parts) < 2:
            continue
        host = max(parts, key=lambda name: (len(parts[name]), name))
        texts = {
            name: {after[key].exact_fingerprint for key in members if after[key].completeness == "FULL"}
            for name, members in parts.items()
        }
        for name in sorted(parts):
            if name == host:
                continue
            rest = set().union(*(texts[other] for other in parts if other != name))
            entries.append((texts[name], rest, bool(texts[name])))
    return entries


def diagnose(
    texts: Mapping[CardKey, str],
    placed: Mapping[CardKey, Placement],
    *,
    before: Mapping[CardKey, Placement] | None = None,
) -> dict[str, object]:
    """Why `placed` put the stored cards where it did: every cut left outside a cluster that holds
    it, and with `before` each divided pair. Counts only."""
    # Imported here, not at the top: `--before-rules` runs this file against the matching modules
    # of an earlier commit, which the diagnosis may not import from.
    from debate_core.evidence.cluster_diagnosis import diagnose_cuts, tally_cuts

    bodies, clusters = full_bodies(texts, placed)
    census = diagnose_cuts(bodies, clusters)
    result: dict[str, object] = {
        "full_texts": census.texts,
        "short_full_texts": census.short_texts,
        "cuts": tally_cuts(census.findings, census.with_a_copy),
        "witness_refusals": dict(census.witness_refusals),
    }
    if before is not None:
        from debate_core.evidence.near_duplicates import NearDuplicateThresholds, jaccard, shingles

        sets: dict[str, frozenset[str]] = {}

        def are_copies(left: str, right: str) -> bool:
            """One text by the copies' rule: Jaccard over the threshold."""
            for fingerprint in (left, right):
                if fingerprint not in sets:
                    sets[fingerprint] = shingles(bodies[fingerprint])
            return jaccard(sets[left], sets[right]) >= NearDuplicateThresholds().jaccard

        result["divided_pairs"] = _divided_tally(
            divided_parts(before, placed), census.findings, census.with_a_copy, are_copies
        )
    return result


def describe_largest_clusters(
    read: Callable[[Sequence[CardKey]], Mapping[CardKey, str]],
    placed: Mapping[CardKey, Placement],
    *,
    count: int,
    show_cluster_ids: bool = False,
) -> list[dict[str, object]]:
    """The `count` largest clusters of `placed`, each from the inside. Counts, and ids when asked.

    `read` returns the stored bodies at the keys it is given, so only these clusters' are read.
    """
    from debate_core.evidence.cluster_diagnosis import cluster_shape

    shapes: list[dict[str, object]] = []
    for rank, (cluster_id, keys) in enumerate(largest_clusters(placed, count), start=1):
        full = [key for key in keys if placed[key].completeness == "FULL"]
        bodies, _ = full_bodies(read(full), placed)
        copies = Counter(placed[key].exact_fingerprint for key in full)
        shape = cluster_shape(cluster_id, bodies, copies).as_json()
        if not show_cluster_ids:
            del shape["cluster_id"]
        shapes.append({"rank": rank, "cards_not_full": len(keys) - len(full), **shape})
    return shapes


def size_rank(placed: Mapping[CardKey, Placement], cluster_id: str) -> int:
    """1 for the cluster with the most card positions; clusters of one size share a rank."""
    members = _members(placed)
    return 1 + sum(len(keys) > len(members[cluster_id]) for keys in members.values())


def describe_cluster_shapes(
    read: Callable[[Sequence[CardKey]], Mapping[CardKey, tuple[str, str | None]]],
    placed: Mapping[CardKey, Placement],
    clusters: Sequence[tuple[int, str]],
    *,
    show_cluster_ids: bool = False,
) -> list[dict[str, object]]:
    """`clusters` of `placed`, each a rank and a cluster id, by the shapes of the pairs of each
    one's distinct full texts. Counts, and ids when asked.

    `read` returns the stored body and short cite at the keys it is given. The texts are the ones
    `describe_largest_clusters` describes, one body per exact fingerprint of a full card, so the
    pairs sharing nothing are the pairs it counts as sharing nothing. A rank is a place in
    `largest_clusters`' order, as `describe_largest_clusters` numbers them.
    """
    from debate_core.evidence.pair_shapes import cluster_pair_shapes

    members = _members(placed)
    described: list[dict[str, object]] = []
    for rank, cluster_id in clusters:
        keys = members[cluster_id]
        full = [key for key in keys if placed[key].completeness == "FULL"]
        stored = read(full)
        bodies, _ = full_bodies({key: body for key, (body, _) in stored.items()}, placed)
        cites: defaultdict[str, list[str | None]] = defaultdict(list)
        for key in full:
            cites[placed[key].exact_fingerprint].append(stored[key][1])
        entry: dict[str, object] = {
            "rank": rank,
            "cards": len(full),
            "cards_not_full": len(keys) - len(full),
            **cluster_pair_shapes(bodies, cites).as_json(),
        }
        if show_cluster_ids:
            entry["cluster_id"] = cluster_id
        described.append(entry)
    return described


def describe_pairs_sharing_few_runs(
    read: Callable[[Sequence[CardKey]], Mapping[CardKey, str]], placed: Mapping[CardKey, Placement]
) -> dict[str, object]:
    """Over every cluster of `placed`, the pairs of its distinct full texts sharing only one or two
    five-word runs (`debate_core.evidence.pair_shapes.pairs_sharing_few_runs`). Counts only.

    `read` returns the stored bodies at the keys it is given; every full card's is read.
    """
    from debate_core.evidence.pair_shapes import FEW_RUNS, pairs_sharing_few_runs

    full = [key for key in sorted(placed) if placed[key].completeness == "FULL"]
    bodies, clusters = full_bodies(read(full), placed)
    texts: defaultdict[str, dict[str, str]] = defaultdict(dict)
    for fingerprint, body in bodies.items():
        texts[clusters[fingerprint]][fingerprint] = body
    together = [cluster for cluster in texts.values() if len(cluster) > 1]
    totals = dict.fromkeys(range(1, FEW_RUNS + 1), 0)
    pairs = with_one = not_overlapping = 0
    for cluster in together:
        counts = pairs_sharing_few_runs(cluster)
        pairs += len(cluster) * (len(cluster) - 1) // 2
        with_one += any(counts.by_runs.values())
        not_overlapping += counts.not_overlapping
        for runs, count in counts.by_runs.items():
            totals[runs] += count
    return {
        "clusters_with_two_or_more_texts": len(together),
        "pairs": pairs,
        "pairs_sharing_only_few_runs": {str(runs): count for runs, count in totals.items()},
        "of_them_not_overlapping": not_overlapping,
        "clusters_with_a_pair_sharing_only_few_runs": with_one,
    }


def _divided_tally(
    parts: Sequence[tuple[set[str], set[str], bool]],
    findings: Sequence[CutFinding],
    with_a_copy: Sequence[CutFinding] = (),
    are_copies: Callable[[str, str], bool] | None = None,
) -> dict[str, object]:
    from debate_core.evidence.cluster_diagnosis import explain_divided_part

    by_fingerprint = {finding.fingerprint: finding for finding in findings}
    set_aside = {finding.fingerprint: finding for finding in with_a_copy}
    reasons: Counter[tuple[str, str, str, str, tuple[str, ...]]] = Counter()
    for part, rest, has_full_card in parts:
        if not has_full_card:
            reasons[("the part holds no full card", "", "", "", ())] += 1
            continue
        why = explain_divided_part(part, rest, by_fingerprint, set_aside, are_copies=are_copies)
        details = [
            "its containers are nested copies in several clusters" if why.containers_nested else "",
            "the container first by fingerprint is over the share"
            if why.first_container_over_the_share
            else "",
            "it is with a copy that the bodies it left also hold" if why.with_a_copy else "",
        ]
        detail = "; ".join(text for text in details if text)
        reasons[
            (
                why.kind,
                why.outcome.value if why.outcome else "",
                detail,
                why.copies_read.value if why.copies_read else "",
                tuple(sorted({gap.value for gap in why.kept_apart_by})),
            )
        ] += 1
    return {
        "pairs": len(parts),
        "by_reason": [
            {
                "pairs": count,
                "kind": kind,
                "outcome": outcome or None,
                "detail": detail or None,
                "containers_read": read or None,
                "copies_kept_apart_by": list(gaps),
            }
            for (kind, outcome, detail, read, gaps), count in sorted(
                reasons.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def kept_apart(findings: Sequence[CutFinding], limit: str) -> list[tuple[str, str]]:
    """The cuts among `findings` that `limit` keeps apart, each with the body it is shown beside.

    Pairs of exact fingerprints: the cut, and the smallest body confirmed to hold it that may
    witness it (for a cut holding neither end, the first by fingerprint of the bodies holding
    nine-tenths of it). `limit` is one of :data:`KEPT_APART_BY`.
    """
    from debate_core.evidence.cluster_diagnosis import CutOutcome

    outcome = {
        "ends-held-by-too-many-clusters": CutOutcome.TOO_MANY_HOLDERS,
        "held-with-another-passage": CutOutcome.HELD_WITH_ANOTHER_PASSAGE,
        "own-cluster-and-another": CutOutcome.OWN_CLUSTER_AND_ANOTHER,
        "witnesses-in-several-clusters": CutOutcome.SEVERAL_CLUSTERS,
        "under-the-minimum-share": CutOutcome.UNDER_MIN_CUT_SHARE,
        "unrelated-texts": CutOutcome.UNRELATED_TEXTS,
        "within-the-rule": CutOutcome.WITHIN_THE_RULE,
        "lacking-both-ends": CutOutcome.ENDS_NOT_INSIDE,
    }[limit]
    return [
        (finding.fingerprint, finding.smallest_container or min(finding.containers))
        for finding in findings
        if finding.outcome is outcome
    ]


def joined_in_band(
    bodies: Mapping[str, str], before: Mapping[str, str], after: Mapping[str, str], band: str
) -> list[tuple[str, str]]:
    """Cuts newly in the cluster of their smallest witness, with a share of it in `band`.

    `bodies` maps each distinct full text's exact fingerprint to its body; `before` and `after` map
    the same fingerprints to their clusters in two placements. Pairs of exact fingerprints: the cut,
    and the smallest body witnessing it, which `before` had in another cluster and `after` has in
    the cut's. `band` is one of :data:`JOINED_BANDS`' values. What the PM asked of the re-preview
    after lowering `MIN_CUT_SHARE` (2026-10-18): the cuts that the lower share let in.
    """
    from debate_core.evidence.cluster_diagnosis import SHARE_BANDS
    from debate_core.evidence.near_duplicates import CutIndex, witnesses

    index = CutIndex(bodies)
    found: list[tuple[str, str]] = []
    for cut in index.fingerprints:
        if not index.containers(cut):
            continue
        seen = witnesses(cut, after.__getitem__, index)
        if seen is None or len(seen.clusters) != 1:
            continue
        witness = seen.smallest
        if after[witness] != after[cut] or before[witness] == before[cut]:
            continue
        share = index.size(cut) / index.size(witness)
        if next(name for below, name in SHARE_BANDS if share < below) == band:
            found.append((cut, witness))
    return found


def kept_apart_kind(limit: str, cut: str, holder: str) -> str:
    """What a kept-apart pair is tallied under: the limit, whether the cut is short or long, and its
    share of the body it is shown beside, in the diagnosis's bands. Counts only, as every kind is.
    The bands are what a limit is set by: `MIN_CUT_SHARE` is the end of the first, and the share
    before the PM's ruling of 2026-10-18 the end of the second."""
    from debate_core.evidence.cluster_diagnosis import SHARE_BANDS
    from debate_core.evidence.near_duplicates import SHORT_BODY_SHINGLES, shingles

    cut_set, holder_set = shingles(cut), shingles(holder)
    size = "short cut" if len(cut_set) < SHORT_BODY_SHINGLES else "long cut"
    share = len(cut_set) / len(holder_set) if holder_set else 0.0
    band = next(name for below, name in SHARE_BANDS if share < below)
    return f"{limit}, {size}, {band} of the body beside it"


def cluster_pairs(
    cards: Mapping[CardKey, ParsedCard],
    placed: Mapping[CardKey, Placement],
    keys: Sequence[CardKey],
    *,
    count: int,
    seed: int,
    least_alike: bool,
) -> tuple[list[Joined], int]:
    """Pairs of different texts from one cluster, and how many such pairs there are.

    One card stands for each text: the first at that text. Drawn at random, or with `least_alike`
    the pairs sharing the smallest part of the smaller text first, ties in a random order.
    """
    first: dict[str, CardKey] = {}
    for key in sorted(keys):
        first.setdefault(placed[key].exact_fingerprint, key)
    texts = sorted(first)
    pairs = [(left, right) for position, left in enumerate(texts) for right in texts[position + 1 :]]
    chooser = random.Random(seed)
    chooser.shuffle(pairs)
    if least_alike:
        from debate_core.evidence.near_duplicates import containment, shingles

        sets = {text: shingles(cards[first[text]].evidence_text) for text in texts}
        pairs.sort(key=lambda pair: containment(sets[pair[0]], sets[pair[1]]))
    drawn: list[Joined] = []
    for left, right in pairs[:count]:
        abbreviated = sum(placed[first[text]].completeness != "FULL" for text in (left, right))
        kind = ("full with full", "abbreviated with full", "abbreviated with abbreviated")[abbreviated]
        drawn.append(Joined(kind=kind, joiner=first[left], host=first[right]))
    return drawn, len(pairs)


# ------------------------------------------------------------------------------------------------
# The by-eye sample
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Classified:
    """One drawn pair, with its shape and what the rule says of it."""

    caselist: str
    pair: Joined
    left: ParsedCard
    right: ParsedCard
    shape: str
    verdict: str | None
    """The rule's verdict, or `None` for a pair a person is asked about."""


def classify_pair(left: ParsedCard, right: ParsedCard) -> tuple[str, str | None]:
    """A drawn pair's shape, and the rule's verdict on it or `None` when a person must judge it.

    The rule speaks only for two full cards. An abbreviated disclosure's words are not one run of
    its card (`first words … last words`), so a pair holding one is shaped but always asked about,
    and so is a pair whose body has no words.
    """
    from debate_core.evidence.near_duplicates import shingles
    from debate_core.evidence.pair_shapes import pair_shares, rule_verdict

    left_set, right_set = shingles(left.evidence_text), shingles(right.evidence_text)
    if not left_set or not right_set:
        return NO_WORDS, None
    shape = pair_shares(left_set, right_set).shape
    both_full = left.completeness is CardCompleteness.FULL and right.completeness is CardCompleteness.FULL
    verdict = rule_verdict(shape) if both_full else None
    return shape.value, (verdict.value if verdict is not None else None)


@dataclass(frozen=True, slots=True)
class SampleTallies:
    """What a sample drew, what the rule decided and what the person answered. Counts only."""

    drawn: int
    decided: Counter[tuple[str, str, str]]
    """Pairs the rule decided, by kind, shape and verdict: never shown."""
    answered: Counter[tuple[str, str, str]]
    """Pairs the person answered that no rule decides, by kind, shape and verdict."""
    asked: int
    """Pairs shown to the person, answered or not."""
    stopped: bool
    seconds_asking: float
    answered_of_a_decided_shape: Counter[tuple[str, str, str, str]] = field(
        default_factory=Counter[tuple[str, str, str, str]]
    )
    """Pairs of a shape the rule decides, shown because `--ask-shape` named it: by kind, shape,
    the rule's verdict and the person's."""
    asked_of_a_decided_shape: int = 0
    """Of the pairs shown, those of a shape the rule decides."""

    def lines(self) -> list[str]:
        """The lines a sample ends with, after the line saying what was drawn."""
        decided = sum(self.decided.values())
        answered = sum(self.answered.values()) + sum(self.answered_of_a_decided_shape.values())
        summary = f"  Decided by rule {decided} of {self.drawn}; asked {self.asked}"
        if self.asked_of_a_decided_shape:
            summary += f", {self.asked_of_a_decided_shape} of them of a shape the rule decides"
        summary += f"; answered {answered} in {round(self.seconds_asking)} seconds"
        summary += f", stopped with {self.asked - answered} not answered." if self.stopped else "."
        return [
            summary,
            *(
                f"  by rule: {kind}: {shape}: {verdict}: {count}"
                for (kind, shape, verdict), count in sorted(self.decided.items())
            ),
            *(
                f"  asked: {kind}: {shape}: {verdict}: {count}"
                for (kind, shape, verdict), count in sorted(self.answered.items())
            ),
            *(
                f"  asked of a shape the rule decides: {kind}: {shape}: rule {rule}: person {person}: {count}"
                for (kind, shape, rule, person), count in sorted(self.answered_of_a_decided_shape.items())
            ),
        ]


def run_sample(
    pairs: Sequence[tuple[str, Joined, ParsedCard, ParsedCard]],
    *,
    ask: Callable[[str], str],
    show: Callable[[str], None],
    change: str = "Newly in one cluster.",
    columns: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    ask_shapes: Collection[str] = (),
) -> SampleTallies:
    """Count the pairs a rule decides, show the person each of the rest, and return the tallies.

    A decided pair is never shown, unless its shape is one of `ask_shapes` (values of
    :class:`~debate_core.evidence.pair_shapes.PairShape`): then it is shown like any other, without
    the rule's verdict, and the person's answer is tallied apart, beside the rule's. `columns` is
    the terminal's width, read from it when not given.
    """
    classified = [
        _Classified(caselist, pair, left, right, *classify_pair(left, right))
        for caselist, pair, left, right in pairs
    ]
    decided: Counter[tuple[str, str, str]] = Counter()
    for entry in classified:
        if entry.verdict is not None and entry.shape not in ask_shapes:
            decided[(entry.pair.kind, entry.shape, entry.verdict)] += 1
    to_ask = [entry for entry in classified if entry.verdict is None or entry.shape in ask_shapes]
    answered: Counter[tuple[str, str, str]] = Counter()
    answered_of_a_decided_shape: Counter[tuple[str, str, str, str]] = Counter()
    width = columns if columns is not None else shutil.get_terminal_size((100, 40)).columns
    stopped = False
    started = clock()
    for number, entry in enumerate(to_ask, start=1):
        show(CLEAR_TERMINAL)
        show(
            f"Pair {number} of {len(to_ask)} to judge; the rule decided {sum(decided.values())} "
            f"of the {len(classified)} drawn. {entry.caselist}, {entry.pair.kind}. {change}\n"
        )
        show(render_pair(entry.left, entry.right, entry.shape, width))
        key = ""
        while key not in VERDICTS and key != STOP_KEY:
            key = ask(ANSWER_PROMPT).strip().lower()[:1]
        if key == STOP_KEY:
            stopped = True
            break
        if entry.verdict is None:
            answered[(entry.pair.kind, entry.shape, VERDICTS[key])] += 1
        else:
            answered_of_a_decided_shape[(entry.pair.kind, entry.shape, entry.verdict, VERDICTS[key])] += 1
    seconds = clock() - started if to_ask else 0.0
    show(CLEAR_TERMINAL)
    return SampleTallies(
        drawn=len(classified),
        decided=decided,
        answered=answered,
        asked=len(to_ask),
        stopped=stopped,
        seconds_asking=seconds,
        answered_of_a_decided_shape=answered_of_a_decided_shape,
        asked_of_a_decided_shape=sum(entry.verdict is not None for entry in to_ask),
    )


def read_key(prompt: str) -> str:
    """One keypress from the terminal, without Enter.

    Keys pressed while the pair was being drawn are discarded first (`TCSAFLUSH`), so a key pressed
    twice cannot answer a pair nobody has seen. Where there is no `termios`, a line is read instead.
    """
    print(prompt, end="", flush=True)
    try:
        import termios
        import tty
    except ImportError:
        return input()
    descriptor = sys.stdin.fileno()
    saved = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor, termios.TCSAFLUSH)
        key = os.read(descriptor, 1).decode("utf-8", "replace")
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)
    print(key, flush=True)
    return key


# ------------------------------------------------------------------------------------------------
# Showing a pair
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Run:
    """Consecutive words of one side that are all shared or all its own, or a note of words left out."""

    words: tuple[str, ...]
    shared: bool
    note: bool = False


def _marked_words(text: str, other: frozenset[str]) -> list[tuple[str, bool]]:
    """The words of `text` as written, each with whether the other body holds it.

    A word as written is a run of `text` between spaces. Each is matched to the matching words it
    holds, so that the shingles the shares are counted from mark the text a person reads, and is
    marked shared when all of them are. A line-break hyphenation (`commis- sion`) is one matching
    word across two written ones, which are kept together. A word with no matching word (a dash,
    an ellipsis) goes with the word before it. Where the two cannot be lined up, the matching words
    themselves are shown.
    """
    from debate_core.evidence.fingerprints import normalize_for_matching
    from debate_core.evidence.near_duplicates import matching_words
    from debate_core.evidence.pair_shapes import shared_words

    every = matching_words(text)
    flags = shared_words(every, other)
    written: list[str] = []
    for chunk in text.split():
        if (
            written
            and _ENDS_IN_A_HYPHEN.search(normalize_for_matching(written[-1]))
            and _STARTS_WITH_A_WORD.match(normalize_for_matching(chunk))
        ):
            written[-1] = f"{written[-1]} {chunk}"
        else:
            written.append(chunk)
    marked: list[tuple[str, bool]] = []
    position = 0
    for word in written:
        words = matching_words(word)
        if every[position : position + len(words)] != words:
            return list(zip(every, flags, strict=True))
        if words:
            marked.append((word, all(flags[position : position + len(words)])))
        else:
            marked.append((word, marked[-1][1] if marked else False))
        position += len(words)
    if position != len(every):
        return list(zip(every, flags, strict=True))
    return marked


#: The two halves of a line-break hyphenation, as `near_duplicates.matching_words` rejoins them.
_ENDS_IN_A_HYPHEN = re.compile(r"\w-$")
_STARTS_WITH_A_WORD = re.compile(r"\w")


def _runs(marked: Sequence[tuple[str, bool]]) -> list[_Run]:
    runs: list[_Run] = []
    for word, shared in marked:
        if runs and runs[-1].shared == shared and not runs[-1].note:
            runs[-1] = _Run((*runs[-1].words, word), shared)
        else:
            runs.append(_Run((word,), shared))
    return runs


def _note(text: str) -> _Run:
    return _Run((f"[… {text} …]",), shared=False, note=True)


def _trimmed(marked: Sequence[tuple[str, bool]]) -> tuple[list[_Run], int]:
    """The runs a side is shown as, and how many of its words are shown.

    A side of up to :data:`SHOWN_IN_FULL_WORDS` words is shown whole. A longer one is cut to the
    region from its first shared word to its last, with :data:`CONTEXT_WORDS` of its own text on
    each side, and inside that region a long shared run keeps its two ends and a long run of its own
    text keeps more of its two ends. Each cut is replaced by a note of how many words it held.
    """
    if len(marked) <= SHOWN_IN_FULL_WORDS:
        return _runs(marked), len(marked)
    shared = [index for index, (_, flag) in enumerate(marked) if flag]
    if not shared:
        kept = marked[:SHOWN_IN_FULL_WORDS]
        return [*_runs(kept), _note(f"{len(marked) - len(kept)} more words not shown")], len(kept)
    start = max(0, shared[0] - CONTEXT_WORDS)
    end = min(len(marked), shared[-1] + 1 + CONTEXT_WORDS)
    runs: list[_Run] = [_note(f"{start} words before not shown")] if start else []
    shown = 0
    for run in _runs(marked[start:end]):
        edge = SHARED_RUN_EDGE if run.shared else OWN_RUN_EDGE
        if len(run.words) > 3 * edge:
            left_out = len(run.words) - 2 * edge
            what = "shared" if run.shared else "of its own"
            runs += [
                _Run(run.words[:edge], run.shared),
                _note(f"{left_out} words {what} not shown"),
                _Run(run.words[-edge:], run.shared),
            ]
            shown += 2 * edge
        else:
            runs.append(run)
            shown += len(run.words)
    if end < len(marked):
        runs.append(_note(f"{len(marked) - end} words after not shown"))
    return runs, shown


def _wrapped(runs: Sequence[_Run], width: int) -> list[tuple[str, int]]:
    """`runs` as lines of at most `width` visible characters: each line styled, with its visible
    length. A note is a line of its own."""
    lines: list[tuple[str, int]] = []
    parts: list[str] = []
    used = 0

    def finish() -> None:
        nonlocal parts, used
        if parts:
            lines.append((" ".join(parts), used))
        parts, used = [], 0

    for run in runs:
        style = NOTE_STYLE if run.note else SHARED_STYLE if run.shared else OWN_STYLE
        if run.note:
            finish()
        for word in run.words:
            for start in range(0, len(word), width):
                piece = word[start : start + width]
                if used and used + 1 + len(piece) > width:
                    finish()
                parts.append(f"{style}{piece}{RESET_STYLE}")
                used += len(piece) + (1 if len(parts) > 1 else 0)
        if run.note:
            finish()
    finish()
    return lines


def render_pair(left: ParsedCard, right: ParsedCard, shape: str, columns: int) -> str:
    """Two cards for a person to compare: counts and shares at the top, then both texts with the
    text both hold underlined and each side's own text in bold, side by side when `columns` allows.

    Shown only on a terminal, by `run_sample`.
    """
    from debate_core.evidence.near_duplicates import shingles

    sets = (shingles(left.evidence_text), shingles(right.evidence_text))
    shared = len(sets[0] & sets[1])
    sides: list[tuple[str, list[tuple[str, int]]]] = []
    side_by_side = columns >= 2 * SIDE_BY_SIDE_COLUMN + 3
    width = (columns - 3) // 2 if side_by_side else max(20, columns)
    header: list[str] = [f"Shape: {shape}."]
    for label, card, own, other in (("A", left, sets[0], sets[1]), ("B", right, sets[1], sets[0])):
        written = card.evidence_text.split()
        share = (
            f"{shared / len(own):.0%} of its five-word runs are in the other" if own else "no five-word runs"
        )
        if written:
            runs, shown = _trimmed(_marked_words(card.evidence_text, other))
        else:
            runs, shown = [_note(f"no body; cite {card.full_cite}")], 0
        showing = f" Showing {shown} of them." if shown < len(written) else ""
        header.append(
            f"{label}: {card.completeness}, {len(written)} words, cite {card.short_cite or '(none)'}; "
            f"{share}.{showing}"
        )
        sides.append((label, _wrapped(runs, width)))
    header.append(
        f"{SHARED_STYLE}Underlined{RESET_STYLE}: text both hold. "
        f"{OWN_STYLE}Bold{RESET_STYLE}: text only that side holds."
    )
    body: list[str] = []
    if side_by_side:
        (_, left_lines), (_, right_lines) = sides
        body.append(f"{'A':<{width}} │ B")
        for row in range(max(len(left_lines), len(right_lines))):
            text, used = left_lines[row] if row < len(left_lines) else ("", 0)
            other_text, _ = right_lines[row] if row < len(right_lines) else ("", 0)
            body.append(f"{text}{' ' * (width - used)} │ {other_text}".rstrip())
    else:
        for label, lines in sides:
            body += [f"--- {label}", *(text for text, _ in lines), ""]
    return "\n".join([*header, "", *body]) + "\n"


# ------------------------------------------------------------------------------------------------
# The command line
# ------------------------------------------------------------------------------------------------


def _saved(path: Path, caselist: str) -> dict[CardKey, Placement]:
    """A placement `counts` saved (`--save-before`, `--save-after`): a file, or a directory of
    `<caselist>.jsonl`."""
    return read_placements(path / f"{caselist}.jsonl" if path.is_dir() else path)


def _load(
    arguments: argparse.Namespace, store: LocalParsedStore, caselist: str
) -> tuple[str, dict[CardKey, Placement], dict[CardKey, Placement]]:
    """The version directory read, and the placements before and after.

    *After* is `--after`'s saved placement when given, else the store's table when a *before* is
    given, else the store's cards placed in memory by the checked-out rules. *Before* is
    `--before`'s, or `--before-rules`', or else the store's table.
    """
    version = current_version(store, caselist)
    held = read_placements(store.root / caselist / version / OCCURRENCES_NAME)
    after = _saved(arguments.after, caselist) if arguments.after is not None else None
    if arguments.before is not None:
        return version, _saved(arguments.before, caselist), held if after is None else after
    if arguments.before_rules is not None:
        earlier = placements_under_rules(_module_at(arguments.before_rules), arguments.data_dir, caselist)
        return version, earlier, held if after is None else after
    if after is not None:
        return version, held, after
    from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

    cards = read_cards(store, caselist, version, held)
    return version, held, placements_now(cards, FINGERPRINT_VERSION)


def _one_placement(
    arguments: argparse.Namespace, store: LocalParsedStore, caselist: str
) -> tuple[str, dict[CardKey, Placement], dict[CardKey, Placement], str]:
    """For a command that reads one placement: the version directory, the store's table, the
    placement to read and what it is. `--after`'s saved placement, or with `--preview` the store's
    cards placed in memory by the checked-out rules, or else the store's table."""
    version = current_version(store, caselist)
    held = read_placements(store.root / caselist / version / OCCURRENCES_NAME)
    if getattr(arguments, "after", None) is not None:
        return version, held, _saved(arguments.after, caselist), "a placement counts saved"
    if getattr(arguments, "preview", False):
        from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

        placed = placements_now(read_cards(store, caselist, version, held), FINGERPRINT_VERSION)
        return version, held, placed, "the checked-out rules, in memory"
    return version, held, held, "the store's table"


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
        if arguments.save_after is not None:
            write_placements(after, arguments.save_after / f"{caselist}.jsonl")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


def _diagnose(arguments: argparse.Namespace) -> int:
    store = LocalParsedStore(arguments.data_dir)
    results: dict[str, dict[str, object]] = {}
    for caselist in arguments.caselist:
        started = time.monotonic()
        version, held, placed, what = _one_placement(arguments, store, caselist)
        before: dict[CardKey, Placement] | None = None
        if arguments.before is not None:
            before = _saved(arguments.before, caselist)
        elif arguments.before_rules is not None:
            before = placements_under_rules(_module_at(arguments.before_rules), arguments.data_dir, caselist)
        elif placed is not held:
            before = held
        result: dict[str, object] = {"version_directory": version}
        if not arguments.only_largest_clusters:
            result.update(diagnose(read_bodies(store, caselist, version, placed), placed, before=before))
        result.update(
            placement=what,
            fingerprint_version=", ".join(sorted({p.fingerprint_version for p in placed.values()})),
            cards=len(placed),
            clusters=len({placement.cluster_id for placement in placed.values()}),
            largest_clusters=describe_largest_clusters(
                lambda keys: read_bodies(store, caselist, version, keys),  # noqa: B023 - called in this pass
                placed,
                count=arguments.largest_clusters,
                show_cluster_ids=arguments.show_cluster_ids,
            ),
            seconds=round(time.monotonic() - started, 1),
        )
        results[caselist] = result
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


def _shapes(arguments: argparse.Namespace) -> int:
    """`shapes`: the largest clusters of each caselist, or one by id, by the shapes of their pairs."""
    store = LocalParsedStore(arguments.data_dir)
    if arguments.cluster is not None and len(arguments.caselist) != 1:
        raise SystemExit("--cluster reads one caselist: give --caselist once")
    results: dict[str, dict[str, object]] = {}
    for caselist in arguments.caselist:
        started = time.monotonic()
        version, _, placed, what = _one_placement(arguments, store, caselist)
        ranked = [name for name, _ in largest_clusters(placed, len(placed))]
        if arguments.cluster is not None:
            cluster_id = _resolve_cluster(placed, arguments.cluster, None)
            chosen = [(1 + ranked.index(cluster_id), cluster_id)]
        else:
            chosen = list(enumerate(ranked[: arguments.largest_clusters], start=1))
        results[caselist] = {
            "version_directory": version,
            "placement": what,
            "fingerprint_version": ", ".join(sorted({p.fingerprint_version for p in placed.values()})),
            "cards": len(placed),
            "clusters": len({placement.cluster_id for placement in placed.values()}),
            "described_clusters": describe_cluster_shapes(
                lambda keys: read_bodies_and_cites(store, caselist, version, keys),  # noqa: B023 - called in this pass
                placed,
                chosen,
                show_cluster_ids=arguments.show_cluster_ids,
            ),
        }
        if arguments.every_cluster:
            results[caselist]["pairs_sharing_only_few_runs_over_every_cluster"] = (
                describe_pairs_sharing_few_runs(
                    lambda keys: read_bodies(store, caselist, version, keys),  # noqa: B023 - called in this pass
                    placed,
                )
            )
        results[caselist]["seconds"] = round(time.monotonic() - started, 1)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


def _report_tallies(arguments: argparse.Namespace, drew: str, tallies: SampleTallies) -> None:
    """Print what a sample ends with, and append it to `--save-tallies` when given: counts only.

    The next sample's first pair clears the terminal and its scrollback, the last sample's tallies
    with it. A file keeps them, so several samples can be run one after another. The first line is
    what was drawn, with the seed, as before `v1-e31-t21`; the rest keep the rule's verdicts apart
    from the person's, each by kind, shape and verdict.
    """
    lines = [drew, *tallies.lines()]
    print("\n".join(lines))
    if arguments.save_tallies is not None:
        saved: Path = arguments.save_tallies
        saved.parent.mkdir(parents=True, exist_ok=True)
        with saved.open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")


def _ask_shapes(arguments: argparse.Namespace) -> frozenset[str]:
    """The decided shapes `--ask-shape` names, as `PairShape` values."""
    return frozenset(ASK_SHAPES[name] for name in arguments.ask_shape or ())


def _resolve_cluster(placed: Mapping[CardKey, Placement], cluster: str | None, rank: int | None) -> str:
    """The cluster id `--cluster` (an id, or the start of one) or `--largest` (a rank) names."""
    if rank is not None:
        ranked = largest_clusters(placed, rank)
        if rank < 1 or len(ranked) < rank:
            raise SystemExit(f"--largest {rank}: the placement has {len(_members(placed))} clusters")
        return ranked[rank - 1][0]
    assert cluster is not None  # noqa: S101 - argparse requires one of the two
    matching = sorted({p.cluster_id for p in placed.values() if p.cluster_id.startswith(cluster.lower())})
    if len(matching) != 1:
        raise SystemExit(f"--cluster: {len(matching)} cluster ids start with what was given; one must")
    return matching[0]


def _sample_cluster(arguments: argparse.Namespace, store: LocalParsedStore, seed: int) -> int:
    """`sample --cluster` and `sample --largest`: pairs of different texts inside one cluster."""
    if len(arguments.caselist) != 1:
        raise SystemExit("--cluster and --largest read one caselist: give --caselist once")
    (caselist,) = arguments.caselist
    print(f"Reading {caselist} ...", flush=True)
    version, _, placed, _ = _one_placement(arguments, store, caselist)
    cluster_id = _resolve_cluster(placed, arguments.cluster, arguments.largest)
    keys = _members(placed)[cluster_id]
    rank = size_rank(placed, cluster_id)
    cards = read_cards(store, caselist, version, keys)
    drawn, available = cluster_pairs(
        cards, placed, keys, count=arguments.count, seed=seed, least_alike=arguments.least_alike
    )
    pairs = [(caselist, pair, cards[pair.joiner], cards[pair.host]) for pair in drawn]
    tallies = run_sample(
        pairs,
        ask=read_key,
        show=lambda text: print(text, end="", flush=True),
        ask_shapes=_ask_shapes(arguments),
        change="In one cluster now.",
    )
    texts = len({placed[key].exact_fingerprint for key in keys})
    how = "the least alike" if arguments.least_alike else "at random"
    _report_tallies(
        arguments,
        f"Drew {len(pairs)} of {available} pairs of different texts, {how}, from {caselist}'s cluster of "
        f"{len(keys)} cards and {texts} texts (size rank {rank}), seed {seed}.",
        tallies,
    )
    return 0


def _sample_kept_apart(arguments: argparse.Namespace, store: LocalParsedStore, seed: int) -> int:
    """`sample --kept-apart-by`: cuts one limit keeps out, each beside the smallest body holding it."""
    from debate_core.evidence.cluster_diagnosis import diagnose_cuts

    candidates: list[tuple[str, str, Joined]] = []
    for caselist in arguments.caselist:
        print(f"Reading {caselist} ...", flush=True)
        version, _, placed, _ = _one_placement(arguments, store, caselist)
        bodies, clusters = full_bodies(read_bodies(store, caselist, version, placed), placed)
        first: dict[str, CardKey] = {}
        for key in sorted(placed):
            if placed[key].completeness == "FULL":
                first.setdefault(placed[key].exact_fingerprint, key)
        for cut, holder in kept_apart(diagnose_cuts(bodies, clusters).findings, arguments.kept_apart_by):
            kind = kept_apart_kind(arguments.kept_apart_by, bodies[cut], bodies[holder])
            pair = Joined(kind=kind, joiner=first[cut], host=first[holder])
            candidates.append((caselist, version, pair))
    drawn = random.Random(seed).sample(candidates, min(arguments.count, len(candidates)))
    pairs: list[tuple[str, Joined, ParsedCard, ParsedCard]] = []
    for caselist, version, pair in drawn:
        cards = read_cards(store, caselist, version, [pair.joiner, pair.host])
        pairs.append((caselist, pair, cards[pair.joiner], cards[pair.host]))
    tallies = run_sample(
        pairs,
        ask=read_key,
        show=lambda text: print(text, end="", flush=True),
        ask_shapes=_ask_shapes(arguments),
        change="Apart now. B is the smallest body that holds A.",
    )
    _report_tallies(
        arguments,
        f"Drew {len(pairs)} of {len(candidates)} cuts kept apart by {arguments.kept_apart_by}, seed {seed}.",
        tallies,
    )
    return 0


def _sample_joined_in_band(arguments: argparse.Namespace, store: LocalParsedStore, seed: int) -> int:
    """`sample --joined-in-band`: cuts newly with their smallest witness, by their share of it."""
    band = JOINED_BANDS[arguments.joined_in_band]
    candidates: list[tuple[str, str, Joined]] = []
    for caselist in arguments.caselist:
        print(f"Reading {caselist} ...", flush=True)
        version, before, after = _load(arguments, store, caselist)
        before, after = common_cards(before, after)
        bodies, clusters = full_bodies(read_bodies(store, caselist, version, after), after)
        earlier = {
            placement.exact_fingerprint: placement.cluster_id
            for placement in before.values()
            if placement.completeness == "FULL"
        }
        first: dict[str, CardKey] = {}
        for key in sorted(after):
            if after[key].completeness == "FULL":
                first.setdefault(after[key].exact_fingerprint, key)
        for cut, witness in joined_in_band(bodies, earlier, clusters, band):
            kind = kept_apart_kind("newly joined", bodies[cut], bodies[witness])
            candidates.append((caselist, version, Joined(kind=kind, joiner=first[cut], host=first[witness])))
    drawn = random.Random(seed).sample(candidates, min(arguments.count, len(candidates)))
    pairs: list[tuple[str, Joined, ParsedCard, ParsedCard]] = []
    for caselist, version, pair in drawn:
        cards = read_cards(store, caselist, version, [pair.joiner, pair.host])
        pairs.append((caselist, pair, cards[pair.joiner], cards[pair.host]))
    tallies = run_sample(
        pairs,
        ask=read_key,
        show=lambda text: print(text, end="", flush=True),
        ask_shapes=_ask_shapes(arguments),
        change="Newly in one cluster. B is the smallest body that holds A.",
    )
    _report_tallies(
        arguments,
        f"Drew {len(pairs)} of {len(candidates)} cuts newly joined {band} of their smallest witness, "
        f"seed {seed}.",
        tallies,
    )
    return 0


def _sample(arguments: argparse.Namespace) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "sample shows card text, so it runs only with a terminal for input and output.", file=sys.stderr
        )
        return 2
    store = LocalParsedStore(arguments.data_dir)
    seed = arguments.seed if arguments.seed is not None else random.SystemRandom().randrange(10**9)
    if arguments.least_alike and arguments.cluster is None and arguments.largest is None:
        raise SystemExit("--least-alike orders the pairs inside one cluster: give --cluster or --largest")
    if arguments.joined_in_band is not None:
        if arguments.divided or any(
            option is not None for option in (arguments.cluster, arguments.largest, arguments.kept_apart_by)
        ):
            raise SystemExit(
                "--joined-in-band draws newly joined cuts: "
                "no --divided, --cluster, --largest or --kept-apart-by"
            )
        return _sample_joined_in_band(arguments, store, seed)
    inside_one_placement = (arguments.cluster, arguments.largest, arguments.kept_apart_by)
    if any(option is not None for option in inside_one_placement):
        if arguments.divided or arguments.before is not None or arguments.before_rules is not None:
            raise SystemExit(
                "--cluster, --largest and --kept-apart-by read one placement: "
                "no --before, --before-rules or --divided"
            )
        if arguments.kept_apart_by is not None:
            return _sample_kept_apart(arguments, store, seed)
        return _sample_cluster(arguments, store, seed)
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
    tallies = run_sample(
        pairs,
        ask=read_key,
        show=lambda text: print(text, end="", flush=True),
        change=change,
        ask_shapes=_ask_shapes(arguments),
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    what = "divided" if arguments.divided else "newly joined"
    _report_tallies(arguments, f"Drew {len(pairs)} of {len(candidates)} {what} pairs, seed {seed}.", tallies)
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
    for name, handler in (
        ("counts", _counts),
        ("sample", _sample),
        ("diagnose", _diagnose),
        ("shapes", _shapes),
        ("place", _place),
    ):
        command = commands.add_parser(name)
        command.add_argument("--caselist", action="append", required=True, help="Repeat for several.")
        command.set_defaults(handler=handler)
        if name == "place":
            continue  # run by --before-rules in a child process; prints digests and ids
        placement = command.add_mutually_exclusive_group()
        placement.add_argument(
            "--after",
            type=Path,
            metavar="PATH",
            help="Read the placement `counts --save-after` saved (a <caselist>.jsonl, or the directory "
            "holding them) instead of the store's table: the 'after' when comparing.",
        )
        if name in ("diagnose", "shapes"):
            placement.add_argument(
                "--preview",
                action="store_true",
                help="Read the placement the checked-out rules would make of the store's cards, placed "
                "in memory, instead of the store's table. Takes about as long as a rebuild; nothing is "
                "written.",
            )
        if name == "shapes":
            which = command.add_mutually_exclusive_group()
            which.add_argument(
                "--largest-clusters",
                type=int,
                default=3,
                metavar="COUNT",
                help="How many of each caselist's largest clusters to describe. Default 3.",
            )
            which.add_argument(
                "--cluster",
                metavar="ID",
                help="Describe this cluster of the placement read instead (an id, or the start of one "
                "that no other id shares).",
            )
            command.add_argument(
                "--show-cluster-ids",
                action="store_true",
                help="Print each described cluster's id, a digest, for `sample --cluster`.",
            )
            command.add_argument(
                "--every-cluster",
                action="store_true",
                help="Also count, over every cluster, the pairs of distinct full texts sharing only one "
                "or two five-word runs. Reads every full card's body.",
            )
            continue  # one placement, the store's: no before
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
            command.add_argument(
                "--save-after",
                type=Path,
                metavar="DIRECTORY",
                help="Also write the 'after' placements there as <caselist>.jsonl, to pass as --after. "
                "Digests, indices and ids, no text.",
            )
        if name == "sample":
            command.add_argument(
                "--count",
                type=int,
                default=20,
                help="Pairs to draw. Those a rule decides are counted and not shown. Default 20.",
            )
            command.add_argument("--seed", type=int)
            command.add_argument(
                "--divided",
                action="store_true",
                help="Draw pairs that shared a cluster before and no longer do.",
            )
            inside = command.add_mutually_exclusive_group()
            inside.add_argument(
                "--cluster",
                metavar="ID",
                help="Draw pairs of different texts from this cluster of the store's table (an id, or "
                "the start of one that no other id shares).",
            )
            inside.add_argument(
                "--largest",
                type=int,
                metavar="RANK",
                help="The same, for the cluster with the RANK-th most cards: 1 is the largest.",
            )
            command.add_argument(
                "--joined-in-band",
                choices=JOINED_BANDS,
                metavar="BAND",
                help="Draw cuts newly in the cluster of their smallest witness whose share of it is in "
                f"this band, each beside that witness. One of: {', '.join(JOINED_BANDS)}. Reads every "
                "body first.",
            )
            inside.add_argument(
                "--kept-apart-by",
                choices=KEPT_APART_BY,
                metavar="LIMIT",
                help="Draw cuts the store's table keeps out of a cluster that holds them, each with "
                f"the smallest body holding it. One of: {', '.join(KEPT_APART_BY)}.",
            )
            command.add_argument(
                "--save-tallies",
                type=Path,
                metavar="FILE",
                help="Also append the closing lines, which hold counts and no card text, to this file.",
            )
            command.add_argument(
                "--least-alike",
                action="store_true",
                help="With --cluster or --largest: the pairs sharing the least text first, not at random.",
            )
            command.add_argument(
                "--ask-shape",
                action="append",
                choices=sorted(ASK_SHAPES),
                metavar="SHAPE",
                help="Show the person the pairs of this shape, which the rule decides, and tally their "
                "answers apart from the rule's. Repeat for several. One of: "
                f"{', '.join(sorted(ASK_SHAPES))}.",
            )
        if name == "diagnose":
            command.add_argument(
                "--largest-clusters",
                type=int,
                default=3,
                metavar="COUNT",
                help="How many of the largest clusters to describe from the inside. Default 3.",
            )
            command.add_argument(
                "--only-largest-clusters",
                action="store_true",
                help="Skip the cuts: read and describe the largest clusters alone, which takes seconds.",
            )
            command.add_argument(
                "--show-cluster-ids",
                action="store_true",
                help="Print each described cluster's id, a digest, for `sample --cluster`.",
            )
    arguments = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = arguments.handler
    return handler(arguments)


if __name__ == "__main__":
    sys.exit(main())
