"""Near-duplicate recall on short cards, measured apart from overall recall (`v1-e31-t06`).

`v1-e31-t04` reached precision 1.000 and recall 0.947 on its variant set, and all four misses were on
one short card. Short cards are most of a wiki-converted caselist: an `ABBREVIATED` disclosure is a
card's first and last few words by construction. So this measures, separately:

* **Short full cards** (fewer than :data:`SHORT_WORDS` words in the original), clustered by the
  seeded MinHash and 32x4 LSH banding of `debate_core.evidence.near_duplicates`.
* **Abbreviated disclosures**, which are never clustered by text: they are *linked* to a full card's
  cluster when exactly one full card has the same short cite and their opening and closing words
  (`debate_core.evidence.abbreviated_links`), and otherwise stay a cluster of their own.

Over two hand-labelled sets: t04's variant set (`variants.jsonl`, full cards only), and
`short_cards.jsonl`, written and committed with its labels before this measurement existed. Both go
through :meth:`CaselistCardStatsService.place`, the step the parse pipeline builds its occurrence
table with. Two rows are the *same card* exactly when their labels are equal; precision and recall
are over pairs of rows. Run with `-s` to see the table the session report quotes.

Nothing here is real: invented authors, invented reviews and invented findings.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.domain.caselist import SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.testing.fakes import build_fake_caselist_repository

from .test_near_duplicates import PairCounts, Variant, load_variants

SHORT_CARDS_PATH: Final = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "fingerprints" / "short_cards.jsonl"
)

SHORT_WORDS: Final = 60
"""A card is short when its original body has fewer words than this. The t04 miss was 30 words."""


def load_short_cards() -> list[Variant]:
    variants: list[Variant] = []
    for position, line in enumerate(SHORT_CARDS_PATH.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        card = ParsedCard(
            tag=row["tag"],
            short_cite=row["short_cite"],
            full_cite=row["full_cite"],
            evidence_text=row["evidence_text"],
            completeness=CardCompleteness(row["completeness"]),
            match_source=StyleMatchSource.VERBATIM,
            confidence=1.0,
            provenance=FileImportProvenance(
                source_sha256=f"{position + 1000:064x}",
                source_path=f"short-cards/{row['id']}.docx",
                origin=SourceOrigin.CASELIST_ARCHIVE,
                caselist="testcl26",
                snapshot=date(2026, 9, 1),
                first_element_index=0,
                last_element_index=0,
                parser_version="short-cards",
                profile_version="short-cards",
            ),
        )
        variants.append(Variant(variant_id=row["id"], label=row["card"], card=card))
    return variants


def placed_clusters(variants: Sequence[Variant]) -> dict[str, str]:
    """Variant id to cluster id, through the placement step the parse pipeline uses."""
    placements = CaselistCardStatsService(build_fake_caselist_repository()).place([v.card for v in variants])
    return {
        variant.variant_id: placement.cluster_id
        for variant, placement in zip(variants, placements, strict=True)
    }


def counts_over(
    variants: Sequence[Variant], clusters: dict[str, str], keep: Callable[[Variant, Variant], bool]
) -> PairCounts:
    true_positives = false_positives = false_negatives = 0
    for left, right in itertools.combinations(variants, 2):
        if not keep(left, right):
            continue
        same_card = left.label == right.label
        same_cluster = clusters[left.variant_id] == clusters[right.variant_id]
        if same_card and same_cluster:
            true_positives += 1
        elif same_cluster:
            false_positives += 1
        elif same_card:
            false_negatives += 1
    return PairCounts(true_positives, false_positives, false_negatives)


def original_lengths(variants: Sequence[Variant]) -> dict[str, int]:
    """Words in each label's longest full copy: the card as it was cut, before any trimming."""
    lengths: dict[str, int] = {}
    for variant in variants:
        if variant.card.completeness is CardCompleteness.FULL:
            words = len(variant.card.evidence_text.split())
            lengths[variant.label] = max(words, lengths.get(variant.label, 0))
    return lengths


def is_abbreviated(variant: Variant) -> bool:
    return variant.card.completeness is not CardCompleteness.FULL


def measure() -> dict[str, PairCounts]:
    """Every figure the session report quotes, by the subset of pairs it is over."""
    variant_set = load_variants()
    variant_clusters = placed_clusters(variant_set)
    variant_lengths = original_lengths(variant_set)
    short_set = load_short_cards()
    short_clusters = placed_clusters(short_set)
    short_lengths = original_lengths(short_set)

    def short(lengths: dict[str, int]) -> Callable[[Variant, Variant], bool]:
        return lambda left, right: (
            lengths.get(left.label, 0) < SHORT_WORDS or lengths.get(right.label, 0) < SHORT_WORDS
        )

    def both_full(test: Callable[[Variant, Variant], bool]) -> Callable[[Variant, Variant], bool]:
        return lambda left, right: (
            not is_abbreviated(left) and not is_abbreviated(right) and test(left, right)
        )

    return {
        "variant set, all pairs": counts_over(variant_set, variant_clusters, lambda _left, _right: True),
        "variant set, pairs with a short card": counts_over(
            variant_set, variant_clusters, short(variant_lengths)
        ),
        "variant set, pairs of long cards only": counts_over(
            variant_set, variant_clusters, lambda left, right: not short(variant_lengths)(left, right)
        ),
        "short-card set, all pairs": counts_over(short_set, short_clusters, lambda _left, _right: True),
        "short-card set, full short cards": counts_over(
            short_set, short_clusters, both_full(short(short_lengths))
        ),
        "short-card set, full long card": counts_over(
            short_set, short_clusters, both_full(lambda left, right: not short(short_lengths)(left, right))
        ),
        "short-card set, abbreviated with a full copy": counts_over(
            short_set, short_clusters, lambda left, right: is_abbreviated(left) != is_abbreviated(right)
        ),
        "short-card set, abbreviated with abbreviated": counts_over(
            short_set, short_clusters, lambda left, right: is_abbreviated(left) and is_abbreviated(right)
        ),
    }


@pytest.fixture(scope="module")
def measured() -> dict[str, PairCounts]:
    return measure()


def test_the_short_card_set_is_what_it_says_it_is() -> None:
    short_set = load_short_cards()
    lengths = original_lengths(short_set)
    assert len(short_set) == 28
    assert sum(is_abbreviated(variant) for variant in short_set) == 12
    assert {label for label, words in lengths.items() if words < SHORT_WORDS} == {
        "ilmar-tidal-sensors",
        "ilmar-gate-maintenance",
        "brannock-ferry-fares",
        "osei-library-hours",
    }
    assert lengths["hollins-weekly-collection"] >= SHORT_WORDS
    assert sum(1 for left, right in itertools.combinations(short_set, 2) if left.label == right.label) == 81


def test_the_variant_set_reproduces_t04s_figures(measured: dict[str, PairCounts]) -> None:
    """The placement step agrees with t04's own clustering of the variant set: 71, 0, 4."""
    overall = measured["variant set, all pairs"]
    assert (overall.true_positives, overall.false_positives, overall.false_negatives) == (71, 0, 4)


def test_report_short_card_recall(measured: dict[str, PairCounts]) -> None:
    """Prints the table; asserts only that no subset merged two different cards."""
    print()
    for name, counts in measured.items():
        print(
            f"{name:48} TP {counts.true_positives:3}  FP {counts.false_positives:2}  "
            f"FN {counts.false_negatives:3}  precision {counts.precision:.3f}  recall {counts.recall:.3f}"
        )
    assert all(counts.false_positives == 0 for counts in measured.values())
