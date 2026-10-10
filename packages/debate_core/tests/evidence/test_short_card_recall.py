"""Near-duplicate recall on short cards, measured apart from overall recall.

`v1-e31-t04` reached precision 1.000 and recall 0.947 on its variant set, and all four misses were on
one short card. Short cards are most of a wiki-converted caselist: an `ABBREVIATED` disclosure is a
card's first and last few words by construction. `v1-e31-t06` therefore measured, separately:

* **Short full cards** (fewer than :data:`SHORT_WORDS` words in the original), clustered by
  `debate_core.evidence.near_duplicates`.
* **Abbreviated disclosures**, which are never clustered by text: they are *linked* to a full card's
  cluster by short cite and opening and closing words (`debate_core.evidence.abbreviated_links`),
  and otherwise stay a cluster of their own.

Over two hand-labelled sets: t04's variant set (`variants.jsonl`, full cards only), and
`short_cards.jsonl`, written and committed with its labels before the measurement existed.
`v1-e31-t08` appended 36 rows to the second, marked `added_by`, again before anything was measured
on them: fixture cases for each mechanism, and hard negatives that share an author, a year and an
opening or closing phrase with a different card. t06's rows are unchanged, and are still measured
on their own so its table can be read row for row. Both go
through :meth:`CaselistCardStatsService.place`, the step the parse pipeline builds its occurrence
table with. Two rows are the *same card* exactly when their labels are equal; precision and recall
are over pairs of rows. Run with `-s` to see the table the session report quotes.

## Which mechanism a miss comes from

`v1-e31-t08` fixes the three mechanisms t06 found, one at a time, so every missed pair is also
attributed to one (:class:`Miss`). The attribution reads only the labels, the cluster each row
landed in and t04's own published rules, so it means the same thing before and after each fix:

* Two full cards: :attr:`Miss.CONFIRMATION` when the pair itself is under t04's thresholds (Jaccard
  0.8, containment 0.9), :attr:`Miss.CANDIDATES` when it passes them and was never compared.
* An abbreviated disclosure and anything else: by the clusters of the full copies whose short cite
  and opening and closing words the abbreviation matches. More than one cluster is
  :attr:`Miss.SPLIT_FULL_COPIES`; none at all is :attr:`Miss.NO_FULL_COPY`.

Nothing here is real: invented authors, invented reviews and invented findings.
"""

from __future__ import annotations

import itertools
import json
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.domain.caselist import SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.abbreviated_links import (
    FullCardWords,
    abbreviation_anchor,
    link_abbreviated,
    short_cite_key,
)
from debate_core.evidence.near_duplicates import (
    NearDuplicateThresholds,
    containment,
    jaccard,
    matching_words,
    shingles,
)
from debate_core.testing.fakes import build_fake_caselist_repository

from .test_near_duplicates import PairCounts, Variant, load_variants

SHORT_CARDS_PATH: Final = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "fingerprints" / "short_cards.jsonl"
)

SHORT_WORDS: Final = 60
"""A card is short when its original body has fewer words than this. The t04 miss was 30 words."""

ADDED_BY_T08: Final = "v1-e31-t08"
"""The `added_by` field of the rows `v1-e31-t08` appended to the short-card set. t06's rows have none."""

T04_THRESHOLDS: Final = NearDuplicateThresholds()
"""t04's confirmation rule, which the attribution of a full-card miss is read against."""


class Miss(StrEnum):
    """The mechanism a missed pair comes from. The first four are `v1-e31-t06`'s three."""

    CONFIRMATION = "confirmation"
    """Mechanism 1. Two full copies whose overlap is under t04's thresholds: on a short card one
    changed word is enough."""

    CANDIDATES = "candidates"
    """Mechanism 1. Two full copies that pass t04's thresholds and were never compared."""

    SPLIT_FULL_COPIES = "split full copies"
    """Mechanism 2. The full copies an abbreviation matches are in more than one cluster."""

    NO_FULL_COPY = "no full copy"
    """Mechanism 3. No full copy matches the abbreviation, so only another abbreviation could."""

    OTHER = "other"
    """None of the three: a full copy the abbreviation's words do not match, for one."""


MISS_COLUMNS: Final = tuple(Miss)


def load_short_cards(*, extended: bool = False) -> list[Variant]:
    """t06's 28 rows, or with `extended` the rows `v1-e31-t08` added after them as well.

    A row's position in the file is its source digest, so t06's rows read the same either way.
    """
    variants: list[Variant] = []
    for position, line in enumerate(SHORT_CARDS_PATH.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        if row.get("added_by") == ADDED_BY_T08 and not extended:
            continue
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


# ------------------------------------------------------------------------------------------------
# Which mechanism a miss comes from
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """One labelled set after placement: what the attribution of a miss reads."""

    variants: Sequence[Variant]
    clusters: dict[str, str]

    def matched_clusters(self, abbreviated: Variant) -> frozenset[str] | None:
        """Clusters of the full copies `abbreviated` matches by t04's link key; `None` without a key."""
        anchor = abbreviation_anchor(abbreviated.card)
        if anchor is None:
            return None
        matched: set[str] = set()
        for variant in self.variants:
            if is_abbreviated(variant):
                continue
            full = FullCardWords(
                self.clusters[variant.variant_id],
                short_cite_key(variant.card.short_cite),
                tuple(matching_words(variant.card.evidence_text)),
            )
            if link_abbreviated(anchor, [full]) is not None:
                matched.add(full.cluster_id)
        return frozenset(matched)

    def mechanism(self, left: Variant, right: Variant) -> Miss:
        """Why a same-card pair that is not in one cluster was missed."""
        if not is_abbreviated(left) and not is_abbreviated(right):
            left_set, right_set = shingles(left.card.evidence_text), shingles(right.card.evidence_text)
            passes = (
                jaccard(left_set, right_set) >= T04_THRESHOLDS.jaccard
                or containment(left_set, right_set) >= T04_THRESHOLDS.containment
            )
            return Miss.CANDIDATES if passes else Miss.CONFIRMATION
        matched = [self.matched_clusters(variant) for variant in (left, right) if is_abbreviated(variant)]
        if any(clusters is not None and len(clusters) > 1 for clusters in matched):
            return Miss.SPLIT_FULL_COPIES
        if all(clusters is not None and not clusters for clusters in matched):
            both_abbreviated = len(matched) == 2
            return Miss.NO_FULL_COPY if both_abbreviated else Miss.OTHER
        return Miss.OTHER


@dataclass(frozen=True)
class Row:
    """One row of the table: the pair counts, and the misses by mechanism."""

    counts: PairCounts
    misses: Counter[Miss] = field(default_factory=Counter[Miss])

    @property
    def figures(self) -> tuple[int, int, int]:
        return (self.counts.true_positives, self.counts.false_positives, self.counts.false_negatives)

    @property
    def by_mechanism(self) -> dict[Miss, int]:
        return {miss: count for miss, count in self.misses.items() if count}


def row_over(placed: Placed, keep: Callable[[Variant, Variant], bool]) -> Row:
    true_positives = false_positives = 0
    misses: Counter[Miss] = Counter()
    for left, right in itertools.combinations(placed.variants, 2):
        if not keep(left, right):
            continue
        same_card = left.label == right.label
        same_cluster = placed.clusters[left.variant_id] == placed.clusters[right.variant_id]
        if same_card and same_cluster:
            true_positives += 1
        elif same_cluster:
            false_positives += 1
        elif same_card:
            misses[placed.mechanism(left, right)] += 1
    return Row(PairCounts(true_positives, false_positives, sum(misses.values())), misses)


def measure() -> dict[str, Row]:
    """Every figure the session report quotes, by the subset of pairs it is over."""
    variant_set = load_variants()
    variants = Placed(variant_set, placed_clusters(variant_set))
    variant_lengths = original_lengths(variant_set)
    short_set = load_short_cards()
    short_cards = Placed(short_set, placed_clusters(short_set))
    short_lengths = original_lengths(short_set)
    extended_set = load_short_cards(extended=True)
    extended = Placed(extended_set, placed_clusters(extended_set))
    extended_lengths = original_lengths(extended_set)

    def short(lengths: dict[str, int]) -> Callable[[Variant, Variant], bool]:
        return lambda left, right: (
            lengths.get(left.label, 0) < SHORT_WORDS or lengths.get(right.label, 0) < SHORT_WORDS
        )

    def both_full(test: Callable[[Variant, Variant], bool]) -> Callable[[Variant, Variant], bool]:
        return lambda left, right: (
            not is_abbreviated(left) and not is_abbreviated(right) and test(left, right)
        )

    return {
        "variant set, all pairs": row_over(variants, lambda _left, _right: True),
        "variant set, pairs with a short card": row_over(variants, short(variant_lengths)),
        "variant set, pairs of long cards only": row_over(
            variants, lambda left, right: not short(variant_lengths)(left, right)
        ),
        "short-card set, all pairs": row_over(short_cards, lambda _left, _right: True),
        "short-card set, full short cards": row_over(short_cards, both_full(short(short_lengths))),
        "short-card set, full long card": row_over(
            short_cards, both_full(lambda left, right: not short(short_lengths)(left, right))
        ),
        "short-card set, abbreviated with a full copy": row_over(
            short_cards, lambda left, right: is_abbreviated(left) != is_abbreviated(right)
        ),
        "short-card set, abbreviated with abbreviated": row_over(
            short_cards, lambda left, right: is_abbreviated(left) and is_abbreviated(right)
        ),
        "extended set, all pairs": row_over(extended, lambda _left, _right: True),
        "extended set, full short cards": row_over(extended, both_full(short(extended_lengths))),
        "extended set, full long cards": row_over(
            extended, both_full(lambda left, right: not short(extended_lengths)(left, right))
        ),
        "extended set, abbreviated with a full copy": row_over(
            extended, lambda left, right: is_abbreviated(left) != is_abbreviated(right)
        ),
        "extended set, abbreviated with abbreviated": row_over(
            extended, lambda left, right: is_abbreviated(left) and is_abbreviated(right)
        ),
    }


@pytest.fixture(scope="module")
def measured() -> dict[str, Row]:
    return measure()


@pytest.fixture(scope="module")
def extended_clusters() -> dict[str, str]:
    """Row id to cluster id for the whole short-card set, t06's rows and t08's placed together."""
    return placed_clusters(load_short_cards(extended=True))


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


def test_the_rows_t08_added_are_what_they_say_they_are() -> None:
    """36 rows after t06's 28, labelled by hand and committed before anything was measured on them.

    Same-card pairs, counted from the labels: ten among the five Kessler copies; ten for Verran
    (three full copies, two abbreviations); six for Ostrander (three full, one abbreviation); one
    for each Pryce card and its abbreviation; six among the four cuts of the Quill towpaths card;
    one for the two cuts of the Sable four-day-week card. Every other added row is a card of its
    own: a hard negative.
    """
    original = load_short_cards()
    extended = load_short_cards(extended=True)
    added = extended[len(original) :]
    assert [variant.variant_id for variant in extended[: len(original)]] == [
        variant.variant_id for variant in original
    ]
    assert (len(extended), len(added)) == (64, 36)
    assert sum(is_abbreviated(variant) for variant in added) == 16
    assert len({variant.label for variant in added}) == 19
    assert not {variant.label for variant in added} & {variant.label for variant in original}
    same_card = Counter(
        (is_abbreviated(left), is_abbreviated(right))
        for left, right in itertools.combinations(extended, 2)
        if left.label == right.label
    )
    full_pairs = same_card[(False, False)]
    mixed_pairs = same_card[(False, True)] + same_card[(True, False)]
    assert (full_pairs, mixed_pairs, same_card[(True, True)]) == (41, 55, 20)
    assert original_lengths(extended)["ostrander-reservoir-levy"] >= SHORT_WORDS
    assert original_lengths(extended)["kessler-night-buses"] < SHORT_WORDS


# ------------------------------------------------------------------------------------------------
# The table
# ------------------------------------------------------------------------------------------------

#: `v1-e31-t06`'s table, copied by hand from its session report ("Short-card recall"): true
#: positive, false positive and false negative pairs per row, against the code as t06 left it.
T06_TABLE: Final[dict[str, tuple[int, int, int]]] = {
    "variant set, all pairs": (71, 0, 4),
    "variant set, pairs with a short card": (2, 0, 4),
    "variant set, pairs of long cards only": (69, 0, 0),
    "short-card set, all pairs": (36, 0, 45),
    "short-card set, full short cards": (17, 0, 7),
    "short-card set, full long card": (1, 0, 0),
    "short-card set, abbreviated with a full copy": (11, 0, 33),
    "short-card set, abbreviated with abbreviated": (7, 0, 5),
}

#: The same misses by mechanism, worked out by hand from the two reports before this was run.
#:
#: * Variant set: t04's report gives the four misses on its one short card as two on the OCR copy
#:   (containment 0.81) and two on the trimmed copy (containment 1.0, never compared).
#: * Full short cards: t06's first mechanism, the typo copy of one card against its five other
#:   copies and the OCR copy of another against its two.
#: * Abbreviated with a full copy: t06's second mechanism, five abbreviations of the card whose typo
#:   copy split off against its six full copies, and one of the card whose OCR copy did against its
#:   three.
#: * Abbreviated with abbreviated: one cut of the first card against its four others, each unlinked
#:   by the same split, and t06's third mechanism, the two cuts of the card with no full copy.
T06_MISSES: Final[dict[str, dict[Miss, int]]] = {
    "variant set, all pairs": {Miss.CONFIRMATION: 2, Miss.CANDIDATES: 2},
    "variant set, pairs with a short card": {Miss.CONFIRMATION: 2, Miss.CANDIDATES: 2},
    "variant set, pairs of long cards only": {},
    "short-card set, all pairs": {Miss.CONFIRMATION: 7, Miss.SPLIT_FULL_COPIES: 37, Miss.NO_FULL_COPY: 1},
    "short-card set, full short cards": {Miss.CONFIRMATION: 7},
    "short-card set, full long card": {},
    "short-card set, abbreviated with a full copy": {Miss.SPLIT_FULL_COPIES: 33},
    "short-card set, abbreviated with abbreviated": {Miss.SPLIT_FULL_COPIES: 4, Miss.NO_FULL_COPY: 1},
}

#: The extended set (t06's 28 rows and t08's 36, placed together) against the code as t06 left it,
#: worked out by hand from the rows before the run. t06's rows contribute what they do above.
#:
#: * Full short cards, 37 same-card pairs. Kessler's five copies are five clusters: ten misses, four
#:   of them pairs where one copy is wholly inside the other (candidates) and six with a changed
#:   word or no overlap (confirmation). Verran's two-typo copy misses its two clean copies.
#: * Full long cards, 4 pairs. Ostrander's two-typo copy misses its two clean copies.
#: * Abbreviated with a full copy, 55 pairs. Every Verran and Ostrander abbreviation matches full
#:   copies in two clusters (9 misses), and so does the Pryce 5 ... 5 cut (1). The Pryce 6 ... 7 cut
#:   links.
#: * Abbreviated with abbreviated, 20 pairs. The two Verran cuts are both unlinked by the split;
#:   the four Quill cuts (6 pairs) and the two Sable cuts have no full copy.
#:
#: **The one false positive was not predicted.** The row that is only the thirteen words two
#: Tolland cards share was labelled a card of its own, on the expectation that it would stay one.
#: Today's banding happens to pair it with the first of the two and not the second, containment is
#: 1.0, and it joins that card. Had the banding paired it with both, the two cards would have
#: merged through it. `v1-e31-t08` has to end with this at zero.
BASELINE_EXTENDED_TABLE: Final[dict[str, tuple[int, int, int]]] = {
    "extended set, all pairs": (39, 1, 77),
    "extended set, full short cards": (18, 1, 19),
    "extended set, full long cards": (2, 0, 2),
    "extended set, abbreviated with a full copy": (12, 0, 43),
    "extended set, abbreviated with abbreviated": (7, 0, 13),
}

BASELINE_EXTENDED_MISSES: Final[dict[str, dict[Miss, int]]] = {
    "extended set, all pairs": {
        Miss.CONFIRMATION: 17,
        Miss.CANDIDATES: 4,
        Miss.SPLIT_FULL_COPIES: 48,
        Miss.NO_FULL_COPY: 8,
    },
    "extended set, full short cards": {Miss.CONFIRMATION: 15, Miss.CANDIDATES: 4},
    "extended set, full long cards": {Miss.CONFIRMATION: 2},
    "extended set, abbreviated with a full copy": {Miss.SPLIT_FULL_COPIES: 43},
    "extended set, abbreviated with abbreviated": {Miss.SPLIT_FULL_COPIES: 5, Miss.NO_FULL_COPY: 8},
}

#: After the short-body step (`v1-e31-t08`, mechanism 1), worked out by hand before the run.
#:
#: * Every full short copy t06's rows missed differs from its original by one word with five
#:   unchanged words either side, so all seven pairs join, and the variant set's four with them.
#: * With no split left among t06's full copies, every one of its abbreviations links: all 44 pairs
#:   with a full copy, and the four abbreviated pairs the split had cost. The orphan pair remains.
#: * Kessler's five copies are one cluster (10 pairs). The copies with *two* typos stay split, short
#:   (Verran) and long (Ostrander), so their abbreviations still match two clusters.
#: * The row that is only two cards' shared opening is inside both, and joins neither.
AFTER_SHORT_BODY_STEP_TABLE: Final[dict[str, tuple[int, int, int]]] = {
    "variant set, all pairs": (75, 0, 0),
    "variant set, pairs with a short card": (6, 0, 0),
    "variant set, pairs of long cards only": (69, 0, 0),
    "short-card set, all pairs": (80, 0, 1),
    "short-card set, full short cards": (24, 0, 0),
    "short-card set, full long card": (1, 0, 0),
    "short-card set, abbreviated with a full copy": (44, 0, 0),
    "short-card set, abbreviated with abbreviated": (11, 0, 1),
    "extended set, all pairs": (93, 0, 23),
    "extended set, full short cards": (35, 0, 2),
    "extended set, full long cards": (2, 0, 2),
    "extended set, abbreviated with a full copy": (45, 0, 10),
    "extended set, abbreviated with abbreviated": (11, 0, 9),
}

AFTER_SHORT_BODY_STEP_MISSES: Final[dict[str, dict[Miss, int]]] = {
    "variant set, all pairs": {},
    "variant set, pairs with a short card": {},
    "variant set, pairs of long cards only": {},
    "short-card set, all pairs": {Miss.NO_FULL_COPY: 1},
    "short-card set, full short cards": {},
    "short-card set, full long card": {},
    "short-card set, abbreviated with a full copy": {},
    "short-card set, abbreviated with abbreviated": {Miss.NO_FULL_COPY: 1},
    "extended set, all pairs": {Miss.CONFIRMATION: 4, Miss.SPLIT_FULL_COPIES: 11, Miss.NO_FULL_COPY: 8},
    "extended set, full short cards": {Miss.CONFIRMATION: 2},
    "extended set, full long cards": {Miss.CONFIRMATION: 2},
    "extended set, abbreviated with a full copy": {Miss.SPLIT_FULL_COPIES: 10},
    "extended set, abbreviated with abbreviated": {Miss.SPLIT_FULL_COPIES: 1, Miss.NO_FULL_COPY: 8},
}

#: After the linking rule tolerates a split (mechanism 2), worked out by hand before the run. Only
#: the extended set's abbreviated rows move, because mechanism 1's fix had already healed every
#: split among t06's own full copies.
#:
#: * The two Verran cuts and the Ostrander cut join the cluster of the clean copies, which holds
#:   two copies to the two-typo copy's one: six more pairs with a full copy, and the pair of Verran
#:   cuts with each other. Their three pairs with the two-typo copies stay apart, as does the split
#:   itself: an abbreviation joins one cluster and merges none.
#: * The Pryce 5 ... 5 cut matches two different cards, which share a third of their text. No link.
AFTER_SPLIT_TOLERANT_LINKING_TABLE: Final[dict[str, tuple[int, int, int]]] = AFTER_SHORT_BODY_STEP_TABLE | {
    "extended set, all pairs": (100, 0, 16),
    "extended set, abbreviated with a full copy": (51, 0, 4),
    "extended set, abbreviated with abbreviated": (12, 0, 8),
}

AFTER_SPLIT_TOLERANT_LINKING_MISSES: Final[dict[str, dict[Miss, int]]] = AFTER_SHORT_BODY_STEP_MISSES | {
    "extended set, all pairs": {Miss.CONFIRMATION: 4, Miss.SPLIT_FULL_COPIES: 4, Miss.NO_FULL_COPY: 8},
    "extended set, abbreviated with a full copy": {Miss.SPLIT_FULL_COPIES: 4},
    "extended set, abbreviated with abbreviated": {Miss.NO_FULL_COPY: 8},
}

BASELINE_TABLE: Final = T06_TABLE | BASELINE_EXTENDED_TABLE
"""Every row against the code as t06 left it: what each fix is measured from."""

EXPECTED_TABLE: Final = AFTER_SPLIT_TOLERANT_LINKING_TABLE
"""What the code under test should measure today. Each fix replaces the rows it changes."""

EXPECTED_MISSES: Final = AFTER_SPLIT_TOLERANT_LINKING_MISSES


def test_the_table_is_as_expected_row_for_row(measured: dict[str, Row]) -> None:
    """t06's eight rows, then the extended set's five, each worked out before it was measured."""
    assert {name: row.figures for name, row in measured.items()} == EXPECTED_TABLE


def test_every_miss_comes_from_one_of_t06s_three_mechanisms(measured: dict[str, Row]) -> None:
    assert {name: row.by_mechanism for name, row in measured.items()} == EXPECTED_MISSES


def test_no_row_is_worse_than_before_the_fixes(measured: dict[str, Row]) -> None:
    """Against the baseline: no row has fewer true positives, and none has a false positive."""
    assert T06_MISSES.keys() | BASELINE_EXTENDED_MISSES.keys() == measured.keys()
    for name, row in measured.items():
        true_positives, false_positives, _ = row.figures
        assert true_positives >= BASELINE_TABLE[name][0], name
        assert false_positives == 0, name


# ------------------------------------------------------------------------------------------------
# One fixture case per mechanism (ac2), and the hard negatives
# ------------------------------------------------------------------------------------------------

NOT_YET: Final = "v1-e31-t08 baseline: fails against the code as t06 left it; the fix removes this mark"


@pytest.mark.parametrize(
    ("copy", "original"),
    [
        ("k1-ocr-join", "k1-original"),
        ("k1-dropped-word", "k1-original"),
        ("s1-typo", "s1-original"),
        ("s4-ocr-split", "s4-original"),
    ],
)
def test_mechanism_1_one_changed_word_keeps_a_short_card_in_its_cluster(
    extended_clusters: dict[str, str], copy: str, original: str
) -> None:
    assert extended_clusters[copy] == extended_clusters[original]


@pytest.mark.parametrize("copy", ["k1-trimmed-end", "k1-trimmed-start"])
def test_mechanism_1_a_short_cards_trimmed_copy_is_compared_with_it(
    extended_clusters: dict[str, str], copy: str
) -> None:
    """Wholly inside the original, sharing a third of its shingles: the banding never pairs them."""
    assert extended_clusters[copy] == extended_clusters["k1-original"]


@pytest.mark.parametrize(
    ("abbreviation", "original"),
    [
        ("a-v1-five-five", "v1-original"),
        ("a-v1-three-six", "v1-original"),
        ("a-w1-five-five", "w1-original"),
    ],
)
def test_mechanism_2_an_abbreviation_links_although_its_full_copies_are_split(
    extended_clusters: dict[str, str], abbreviation: str, original: str
) -> None:
    assert extended_clusters[abbreviation] == extended_clusters[original]


@pytest.mark.xfail(strict=True, reason=NOT_YET)
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("a-orphan-four-four", "a-orphan-three-five"),
        ("a-q1-six-six", "a-q1-four-eight"),
        ("a-q1-six-six", "a-q1-five-four-brackets"),
        ("a-q1-four-eight", "a-q1-five-four-brackets"),
    ],
)
def test_mechanism_3_two_cuts_of_a_card_with_no_full_copy_share_a_cluster(
    extended_clusters: dict[str, str], left: str, right: str
) -> None:
    assert extended_clusters[left] == extended_clusters[right]


@pytest.mark.parametrize(
    ("abbreviation", "original"),
    [
        ("a-s1-three-eight", "s1-original"),
        ("a-s1-five-five", "s1-typo"),
        ("a-s4-three-three", "s4-ocr-split"),
    ],
)
def test_an_abbreviation_links_once_one_changed_word_no_longer_splits_its_full_copies(
    extended_clusters: dict[str, str], abbreviation: str, original: str
) -> None:
    """t06's own 33 misses of this kind: the split was mechanism 1's, so mechanism 1's fix heals it."""
    assert extended_clusters[abbreviation] == extended_clusters[original]


def test_the_copies_two_typos_split_off_stay_split(extended_clusters: dict[str, str]) -> None:
    """Linking an abbreviation never merges the full-card clusters it matches."""
    assert extended_clusters["v1-two-typos"] != extended_clusters["v1-original"]
    assert extended_clusters["w1-two-typos"] != extended_clusters["w1-original"]


def test_linking_abbreviations_never_changes_a_full_cards_cluster(
    extended_clusters: dict[str, str],
) -> None:
    """An abbreviation joins one cluster and merges none: full cards placed alone land the same."""
    full_cards = [variant for variant in load_short_cards(extended=True) if not is_abbreviated(variant)]
    alone = placed_clusters(full_cards)
    assert alone == {variant.variant_id: extended_clusters[variant.variant_id] for variant in full_cards}


def test_every_card_is_placed_once_in_the_order_given() -> None:
    cards = [variant.card for variant in load_short_cards(extended=True)]
    placements = CaselistCardStatsService(build_fake_caselist_repository()).place(cards)
    assert [placement.card for placement in placements] == cards


HARD_NEGATIVES: Final = [
    # t06's: two short cards from one article, and an abbreviation of each.
    ("s1-original", "s2-original"),
    ("a-s1-five-five", "a-s2-five-five"),
    # A whole short card that is another card's first twelve words plus two.
    ("x1-original", "x2-original"),
    # Thirteen shared opening words.
    ("p1-original", "p2-original"),
    ("p0-shared-opening", "p2-original"),
    # The next year's audit: the same sentence with two words different.
    ("r1-original", "r2-original"),
    # Same five opening and thirteen closing words; and the 5 ... 5 cut both match.
    ("y1-original", "y2-original"),
    ("a-y1-five-five", "y2-original"),
    ("a-y1-five-five", "a-y2-six-seven"),
    # Orphans: same author and year, same opening phrase.
    ("a-q1-six-six", "a-q2-six-six"),
    ("a-q1-five-four-brackets", "a-q2-six-six"),
    # ... same closing phrase.
    ("a-q1-six-six", "a-q3-seven-six"),
    ("a-q1-four-eight", "a-q3-seven-six"),
    # ... same three words at each end.
    ("a-q1-three-three", "a-q4-six-six"),
    ("a-q1-six-six", "a-q4-six-six"),
    # ... a cut two different orphans both open and close with.
    ("a-t1-eight-seven", "a-t2-eight-seven"),
    ("a-t1-four-six", "a-t2-eight-seven"),
    # An orphan that opens and closes like another card's linked 3 ... 3 cut.
    ("a-s5-five-five", "a-s4-three-three"),
    ("a-s5-five-five", "s4-original"),
]


@pytest.mark.parametrize(("left", "right"), HARD_NEGATIVES)
def test_hard_negatives_stay_in_separate_clusters(
    extended_clusters: dict[str, str], left: str, right: str
) -> None:
    assert extended_clusters[left] != extended_clusters[right]


def test_a_cut_that_is_only_two_cards_shared_opening_joins_neither(
    extended_clusters: dict[str, str],
) -> None:
    """Thirteen words that two different cards both open with are a cut of either, so of neither."""
    assert extended_clusters["p0-shared-opening"] != extended_clusters["p1-original"]
    assert extended_clusters["p0-shared-opening"] != extended_clusters["p2-original"]


@pytest.mark.parametrize("shuffle_seed", [1, 2, 3])
def test_cluster_ids_do_not_depend_on_the_order_of_the_cards(
    extended_clusters: dict[str, str], shuffle_seed: int
) -> None:
    """Joining short bodies and linking abbreviations are functions of the set of cards."""
    reordered = load_short_cards(extended=True)
    random.Random(shuffle_seed).shuffle(reordered)
    assert placed_clusters(reordered) == extended_clusters
    assert placed_clusters(list(reversed(reordered))) == extended_clusters


def test_report_short_card_recall(measured: dict[str, Row]) -> None:
    """Prints the table the session report quotes."""
    print()
    print(f"{'pairs':46} {'TP':>3} {'FP':>3} {'FN':>3}  precision  recall  misses by mechanism")
    for name, row in measured.items():
        counts = row.counts
        mechanisms = ", ".join(f"{count} {miss}" for miss, count in row.by_mechanism.items()) or "-"
        print(
            f"{name:46} {counts.true_positives:3} {counts.false_positives:3} "
            f"{counts.false_negatives:3}  {counts.precision:9.3f}  {counts.recall:6.3f}  {mechanisms}"
        )


def test_no_two_different_cards_share_a_cluster_on_either_labelled_set(measured: dict[str, Row]) -> None:
    """Precision 1.000 everywhere: the spec forbids a single false positive."""
    assert {name: row.counts.false_positives for name, row in measured.items() if row.figures[1]} == {}
