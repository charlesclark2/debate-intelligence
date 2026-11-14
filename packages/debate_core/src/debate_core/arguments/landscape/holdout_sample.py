"""The held-out coach sample (`v1-e32-t50`): a second sample, sharing no card with the first, never tuned on.

The bar was read on the coach's first sample (`v1-e32-t21`), and three prompt versions were tuned on it.
Before any route is declared to meet the bar, a second sample is drawn by the same rule and read as a holdout.
The PM's ruling of 2026-11-14 sets it:

* **The same rule.** :func:`~debate_core.arguments.landscape.local_classifier.coach_sample`: unplaced cards
  only, strata cut on the proxy model's confidence at its threshold and at the median below it, kinds in
  turn, seeded-digest order, at most one card per document. Only the shares differ: 60, 40 and 20
  (:data:`HOLDOUT_STRATA`), 120 cards. The seed is the ruling's date (:data:`HOLDOUT_SEED`).
* **No card of the first sample.** A first-sample card is any of its drawn cards, all of them, not only
  the ones the coach labelled. A candidate is left out (:func:`holdout_sample`) when it is in the
  near-duplicate cluster of a first-sample card (any copy of the same evidence, any cut), has the exact
  fingerprint of one (checked as well), is read alike to one (the same headings with their answer flags
  and the same tag's words, :attr:`~debate_core.arguments.landscape.matcher.MatchItem.fingerprint`), or
  comes from a document of the first sample. Inside the holdout, at most one card per cluster.
* **Every identity is the parser's**, read from one occurrence table
  (:class:`~debate_core.application.ports.parsed_store.OccurrenceRecord`): cluster ids are comparable only
  within one table. A first-sample card the table does not hold cannot be shown absent from the holdout,
  so the draw stops (:class:`FirstSampleCardsMissing`), with a count and never which card. A candidate the
  table does not hold is left out and counted.
* **Never tuned on.** The rows file's header says `"holdout": true` (:func:`holdout_sample_lines`), and an
  evaluation of it reports counts and scores only (:func:`is_holdout`).

Pure: identities, rows and comparisons in, the sample and its counts out. Nothing here holds a tag, a heading
or a team; the counts are numbers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from debate_core.arguments.landscape.local_classifier import (
    UNPLACED,
    CoachSample,
    Comparison,
    FeatureRow,
    SampleItem,
    coach_sample,
    sample_lines,
)
from debate_core.domain.landscape import Taxonomy

__all__ = [
    "HOLDOUT_KEY",
    "HOLDOUT_SEED",
    "HOLDOUT_STRATA",
    "CardIdentity",
    "FirstSampleCardsMissing",
    "HoldoutDraw",
    "HoldoutExclusions",
    "holdout_header",
    "holdout_sample",
    "holdout_sample_lines",
    "is_holdout",
]

HOLDOUT_SEED: Final = 20261114
"""The held-out sample's seed, the date of the PM's ruling (2026-11-14): its split, solver and draw."""

HOLDOUT_STRATA: Final = (
    ("at-or-above-threshold", 60),
    ("just-below-threshold", 40),
    ("far-below-threshold", 20),
)
"""The first sample's strata, their shares doubled: 120 cards (the PM's ruling of 2026-11-14)."""

HOLDOUT_KEY: Final = "holdout"
"""The rows file's header key that marks a held-out sample: reported as counts and scores only."""


@dataclass(frozen=True, slots=True)
class CardIdentity:
    """What a card is, by the parser and by the matcher: never what it says."""

    item_id: str
    source_sha256: str
    read_fingerprint: str
    """:attr:`~debate_core.arguments.landscape.matcher.MatchItem.fingerprint`: headings and tag as read."""
    exact_fingerprint: str | None = None
    """The SHA-256 of its normalized evidence body; None when the occurrence table holds no row for it."""
    cluster_id: str | None = None
    """Its near-duplicate cluster in that table; None when the table holds no row for it."""


@dataclass(frozen=True, slots=True)
class HoldoutExclusions:
    """How many candidates each rule kept out of the holdout, and what it was measured against: counts only.

    The rules overlap: a card can be in a first-sample cluster and document both, and is counted under each
    rule it meets and once in :attr:`excluded`."""

    first_sample_cards: int
    first_sample_documents: int
    first_sample_clusters: int
    candidates: int
    """Unplaced cards the stratifying model predicts: what the first sample was drawn from."""
    same_cluster: int
    same_exact_fingerprint: int
    same_read_fingerprint: int
    same_document: int
    no_occurrence_row: int
    excluded: int
    """Candidates any rule kept out."""
    eligible: int
    """Candidates no rule kept out: what the holdout is drawn from, and its populations count."""
    one_per_cluster: int = 0
    """Eligible cards not drawn because they share a cluster with a drawn card."""

    def as_json(self) -> dict[str, int]:
        return {
            "first_sample_cards": self.first_sample_cards,
            "first_sample_documents": self.first_sample_documents,
            "first_sample_clusters": self.first_sample_clusters,
            "candidates": self.candidates,
            "same_cluster": self.same_cluster,
            "same_exact_fingerprint": self.same_exact_fingerprint,
            "same_read_fingerprint": self.same_read_fingerprint,
            "same_document": self.same_document,
            "no_occurrence_row": self.no_occurrence_row,
            "excluded": self.excluded,
            "eligible": self.eligible,
            "one_per_cluster": self.one_per_cluster,
        }


class FirstSampleCardsMissing(ValueError):
    """First-sample cards with no occurrence row: the holdout cannot be shown to share none of them."""

    def __init__(self, missing: int, of: int) -> None:
        super().__init__(
            f"{missing} of the first sample's {of} cards have no row in the occurrence table, so the holdout "
            "cannot be shown to share no card with them; the draw stopped and wrote nothing"
        )
        self.missing = missing
        self.of = of


@dataclass(frozen=True, slots=True)
class HoldoutDraw:
    """The held-out sample, and the exclusions that kept the first sample out of it."""

    sample: CoachSample
    exclusions: HoldoutExclusions
    seed: int
    strata: tuple[tuple[str, int], ...]


def holdout_sample(
    taxonomy: Taxonomy,
    rows: Sequence[FeatureRow],
    comparisons: Mapping[str, Comparison],
    identities: Mapping[str, CardIdentity],
    first_sample: Iterable[SampleItem],
    *,
    stratified_by: str,
    seed: int = HOLDOUT_SEED,
    strata: Sequence[tuple[str, int]] = HOLDOUT_STRATA,
) -> HoldoutDraw:
    """The held-out sample of `rows`, drawn as the first was, every card of `first_sample` kept out.

    `identities` names each card by item id, from the occurrence table of the reading `rows` were built
    from. Raises :class:`FirstSampleCardsMissing` when a first-sample card has no identity or no occurrence
    row. The rules are the module's; each candidate is measured against every first-sample card drawn.
    """
    first = list(first_sample)
    known = [identities.get(item.item_id) for item in first]
    missing = sum(one is None or one.cluster_id is None for one in known)
    if missing:
        raise FirstSampleCardsMissing(missing, len(first))
    found = [cast(CardIdentity, one) for one in known]
    clusters = {one.cluster_id for one in found}
    exact = {one.exact_fingerprint for one in found}
    read = {one.read_fingerprint for one in found}
    documents = {item.source_sha256 for item in first}
    model = comparisons[stratified_by]
    candidates = [
        row for row in rows if row.placement == UNPLACED and model.predictions.get(row.item_id) is not None
    ]
    counts = {"cluster": 0, "exact": 0, "read": 0, "document": 0, "none": 0}
    kept_out: set[str] = set()
    for row in candidates:
        identity = identities.get(row.item_id)
        met = {
            "cluster": identity is not None and identity.cluster_id in clusters,
            "exact": identity is not None and identity.exact_fingerprint in exact,
            "read": identity is not None and identity.read_fingerprint in read,
            "document": row.source_sha256 in documents,
            "none": identity is None or identity.cluster_id is None,
        }
        for rule, hit in met.items():
            counts[rule] += hit
        if any(met.values()):
            kept_out.add(row.item_id)
    eligible = [row for row in rows if row.item_id not in kept_out]
    cluster_of = {
        item_id: identity.cluster_id
        for item_id, identity in identities.items()
        if identity.cluster_id is not None and item_id not in kept_out
    }
    shares = tuple(strata)
    sample = coach_sample(
        taxonomy,
        eligible,
        comparisons,
        stratified_by=stratified_by,
        seed=seed,
        strata=shares,
        cluster_of=cluster_of,
    )
    drawn = {item.item_id for item in sample.items}
    drawn_clusters = {cluster_of[item_id] for item_id in drawn if item_id in cluster_of}
    passed_over = sum(
        row.item_id not in drawn and cluster_of.get(row.item_id) in drawn_clusters
        for row in candidates
        if row.item_id not in kept_out
    )
    return HoldoutDraw(
        sample=sample,
        exclusions=HoldoutExclusions(
            first_sample_cards=len(first),
            first_sample_documents=len(documents),
            first_sample_clusters=len(clusters),
            candidates=len(candidates),
            same_cluster=counts["cluster"],
            same_exact_fingerprint=counts["exact"],
            same_read_fingerprint=counts["read"],
            same_document=counts["document"],
            no_occurrence_row=counts["none"],
            excluded=len(kept_out),
            eligible=len(candidates) - len(kept_out),
            one_per_cluster=passed_over,
        ),
        seed=seed,
        strata=shares,
    )


def holdout_sample_lines(draw: HoldoutDraw, *, drawn_from: Mapping[str, object]) -> list[str]:
    """The rows file of a held-out sample.

    :func:`~debate_core.arguments.landscape.local_classifier.sample_lines`, with its header marked
    `"holdout": true`, and the seed, the strata's shares, the exclusions' counts and `drawn_from` (the
    snapshot, the store's version directory, the parser and fingerprint versions) beside it."""
    lines = sample_lines(draw.sample)
    header = cast(dict[str, Any], json.loads(lines[0]))
    header |= {
        HOLDOUT_KEY: True,
        "seed": draw.seed,
        "strata": dict(draw.strata),
        "exclusions": draw.exclusions.as_json(),
        "drawn_from": dict(drawn_from),
    }
    return [json.dumps(header, sort_keys=True, separators=(",", ":")) + "\n", *lines[1:]]


def holdout_header(rows: Iterable[str]) -> dict[str, Any] | None:
    """The header of a held-out sample's rows file; None for any other, the first sample's included."""
    first = next((line for line in rows if line.strip()), None)
    try:
        loaded: object = json.loads(first) if first is not None else None
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    header = cast(dict[str, Any], loaded)
    return header if header.get(HOLDOUT_KEY) is True else None


def is_holdout(rows: Iterable[str]) -> bool:
    """Whether a rows file is a held-out sample's: its header says `"holdout": true`."""
    return holdout_header(rows) is not None
