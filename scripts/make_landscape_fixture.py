#!/usr/bin/env python3
"""Write the synthetic caselists the landscape report is tested against (`v1-e32-t03`, `v1-e32-t04`).

`tests/fixtures/landscape/synthetic_caselist/` holds the report's inputs for one invented Policy
caselist, `synthpolicy26`: its taxonomy, the coach's overrides, the E30 disclosures (who disclosed
which file on which side in which round, in which weekly snapshot), the E31 card fingerprints and
clusters, and the `v1-e32-t02` classification of every card. Every school, team code, tournament,
tag and cite in it is invented here; team codes are doubled letters such as `XX`, so a scan of a
report for them means something.

**This script writes inputs only.** What the report should say about them is written by hand, in
`tests/fixtures/landscape/golden/` (working agreement 6): a golden produced by the code under test
could not contradict it.

    uv run python scripts/make_landscape_fixture.py

The fixture is small enough to count on paper: 20 sources, 24 disclosure rows, 16 rounds in range
by 8 teams through the second snapshot, 58 cards of the first 15 sources (56 of them in range). Its
README says what each part exercises. Owned by `v1-e32-t03`; `v1-e32-t10` gave the DA and advantage
cards their headings for the impact rule, `v1-e32-t14` the scenario and chain-role headings and the
cards that test them (and the aliases its sub-headings are read below), and `v1-e32-t04` the third
weekly window that its trends are tested on (a rising, a falling and a new position, and a file
carried into it under a new path).

`v1-e32-t04` also writes `tests/fixtures/landscape/topic_change_caselist/`: a separate two-snapshot
Lincoln-Douglas caselist whose topic changes between its snapshots, with the `topics.yaml` that says
so, for the rule that a trend never compares two topics.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "debate_core" / "src"))

from debate_core.domain.caselist import Disclosure, Event, RoundLabel, Side  # noqa: E402
from debate_core.domain.landscape import Taxonomy  # noqa: E402
from debate_core.domain.landscape_classification import (  # noqa: E402
    ClassificationMethod,
    ItemKind,
    OverrideRules,
    PositionClassification,
    PositionRole,
    card_item_id,
)
from debate_core.domain.landscape_report import LandscapeCard  # noqa: E402

FIXTURE: Final = REPO_ROOT / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
CASELIST: Final = "synthpolicy26"
TOPIC: Final = "synthetic-policy-topic"
TAXONOMY_VERSION: Final = "1.2.0"
FIRST: Final = date(2026, 9, 8)
SECOND: Final = date(2026, 9, 15)
LATER: Final = date(2026, 9, 22)
"""The third snapshot, after the t03 report's date: its disclosures are out of that report's range."""
_PARAGRAPHS_PER_CARD: Final = 3

ALIASES: Final = {
    "costs-advantage": ("costs advantage",),
    "innovation-advantage": ("innovation advantage",),
    "spending-da": ("spending da",),
    "election-da": ("midterms da",),
    "hospital-closures-da": ("hospital closures da",),
    "provider-strikes-da": ("provider strikes da",),
    "cap-k": ("capitalism k",),
}
"""The headings the cards' paths name each position by: `v1-e32-t14` reads a card's sub-headings below
the one that placed it, which the matcher's rule finds by these."""

POSITIONS: Final = (
    ("single-payer-aff", "Single payer", "aff", "aff", None),
    ("public-option-aff", "Public option", "aff", "aff", None),
    ("costs-advantage", "Costs advantage", "advantage", "aff", "single-payer-aff"),
    ("innovation-advantage", "Innovation advantage", "advantage", "aff", None),
    ("spending-da", "Spending DA", "da", "neg", None),
    ("election-da", "Midterms DA", "da", "neg", None),
    ("hospital-closures-da", "Hospital closures DA", "da", "neg", None),
    ("provider-strikes-da", "Provider strikes DA", "da", "neg", None),
    ("states-cp", "States CP", "cp", "neg", None),
    ("courts-cp", "Courts CP", "cp", "neg", None),
    ("cap-k", "Capitalism K", "k", "neg", None),
    ("nhi-t", "T: national health insurance", "t", "neg", None),
    ("condo-bad", "Condo bad", "theory", "aff", None),
    ("pics-bad", "PICs bad", "theory", "aff", None),
)
"""(id, label, kind, side, parent), in file order."""

TEAMS: Final = {
    "XX": "Ashgrove Fictional",
    "YY": "Ashgrove Fictional",
    "ZZ": "Birchmoor",
    "QQ": "Birchmoor",
    "VV": "Cedarvale Fictional",
    "WW": "Cedarvale Fictional",
    "JJ": "Driftwood Fictional",
    "KK": "Driftwood Fictional",
}
"""Team code to school. Birchmoor is one address word, as the real archive spells a school, so the
school view links its teams' pages (`v1-e32-t18`); the others are display names, which get none."""

FIRST_TOURNAMENT: Final = "Fictional Invitational"
SECOND_TOURNAMENT: Final = "Imaginary Classic"
LATER_TOURNAMENT: Final = "Later Tournament"


def _source(name: str) -> str:
    """`a1` is `a1a1…a1`: a digest that sorts and reads at a glance."""
    return name * 32


def _cluster(number: int) -> str:
    return f"{number:02d}" * 32


def _exact(number: int, copy: str) -> str:
    """Copy `a` of cluster 2 is `0202…020a`: near-duplicates share a cluster, not a fingerprint."""
    return f"{number:02d}" * 31 + f"0{copy}"


DISCLOSURES: Final = (
    ("a1", "XX", Side.AFF, FIRST_TOURNAMENT, "R1", FIRST),
    ("a1", "XX", Side.AFF, FIRST_TOURNAMENT, "R1", SECOND),
    ("b1", "YY", Side.NEG, FIRST_TOURNAMENT, "R1", FIRST),
    ("a2", "ZZ", Side.AFF, FIRST_TOURNAMENT, "R2", FIRST),
    ("b2", "QQ", Side.NEG, FIRST_TOURNAMENT, "R2", FIRST),
    ("a3", "VV", Side.AFF, FIRST_TOURNAMENT, "R3", FIRST),
    ("b3", "WW", Side.NEG, FIRST_TOURNAMENT, "R3", FIRST),
    ("b1", "JJ", Side.NEG, FIRST_TOURNAMENT, "R4", FIRST),
    ("a1", "XX", Side.AFF, SECOND_TOURNAMENT, "R1", SECOND),
    ("a4", "KK", Side.AFF, SECOND_TOURNAMENT, "R1", SECOND),
    ("b4", "YY", Side.NEG, SECOND_TOURNAMENT, "R1", SECOND),
    ("b5", "ZZ", Side.NEG, SECOND_TOURNAMENT, "R2", SECOND),
    ("a5", "QQ", Side.AFF, SECOND_TOURNAMENT, "R2", SECOND),
    ("b6", "WW", Side.NEG, SECOND_TOURNAMENT, "R3", SECOND),
    ("a6", "JJ", Side.AFF, SECOND_TOURNAMENT, "R3", SECOND),
    ("b7", "VV", Side.UNKNOWN, None, None, SECOND),
    ("b8", "KK", Side.NEG, SECOND_TOURNAMENT, "R4", SECOND),
    ("b9", "YY", Side.NEG, LATER_TOURNAMENT, "R1", LATER),
    ("ac", "XX", Side.AFF, LATER_TOURNAMENT, "R2", LATER),
    ("ad", "ZZ", Side.AFF, LATER_TOURNAMENT, "R3", LATER),
    ("ae", "VV", Side.AFF, LATER_TOURNAMENT, "R4", LATER),
    ("bc", "QQ", Side.NEG, LATER_TOURNAMENT, "R2", LATER),
    ("bd", "KK", Side.NEG, LATER_TOURNAMENT, "R3", LATER),
)
"""(source, team code, side, tournament, round, snapshot), one row per manifest row.

`a1`'s first row is carried from the first window into the second (the same round, listed twice),
and `b1` is one file two teams disclosed (two rounds). `b7`'s filename gave no side, tournament or
round. `b9` and the `ac`-`bd` rows are the third window, after the t03 report's date.
"""

RENAMED: Final = (("a4", "KK", Side.AFF, SECOND_TOURNAMENT, "R1", LATER, 2),)
"""(source, team code, side, tournament, round, snapshot, sequence): a file carried into a later window.

`a4` is listed again in the third window, unchanged, under a new path: the per-team sequence number
between the side and the tournament went up when the team added rounds (`v1-e30-t03`). It is the
round first seen in the second window, so the third window's trends must not count it.
"""


@dataclass(frozen=True, slots=True)
class FixtureCard:
    cluster: int
    copy: str
    tag: str
    cite: str
    position: str | None = None
    role: PositionRole | None = PositionRole.READS
    method: ClassificationMethod | None = ClassificationMethod.ALIAS
    headings: tuple[str, ...] = ()
    """The normalized headings over the card, which `v1-e32-t10`'s impact rule reads."""
    answers: tuple[bool, ...] = ()
    """Beside each heading, whether it answers (`AT:`); empty when none does (`v1-e32-t14`)."""


def _unplaced(cluster: int, tag: str, cite: str) -> FixtureCard:
    return FixtureCard(cluster, "a", tag, cite, None, None, None)


_INHERITED: Final = ClassificationMethod.INHERITED
_KEYWORD: Final = ClassificationMethod.TAG_KEYWORD
_ANSWERS: Final = PositionRole.ANSWERS
_COSTS_TAG: Final = "Single payer cuts administrative costs"
_COSTS: Final = ("costs advantage",)
_INNOVATION: Final = ("innovation advantage",)
_SPENDING: Final = ("spending da",)
_MIDTERMS: Final = ("midterms da",)
_COSTS_SCENARIO: Final = (*_COSTS, "scenario 1 economic collapse")

CARDS: Final = {
    "a1": (
        FixtureCard(
            1, "a", "Single payer is the only path to universal coverage", "Brandt 24", "single-payer-aff"
        ),
        FixtureCard(
            2, "a", _COSTS_TAG, "Okafor 25", "costs-advantage", method=_INHERITED, headings=_COSTS_SCENARIO
        ),
        FixtureCard(
            2,
            "d",
            "2. Extinction from economic collapse",
            "Okafor 25",
            "costs-advantage",
            method=_INHERITED,
            headings=_COSTS_SCENARIO,
        ),
        FixtureCard(
            4,
            "a",
            "Spending DA non-unique",
            "Grant 26",
            "spending-da",
            role=_ANSWERS,
            headings=(*_SPENDING, "uq"),
        ),
        _unplaced(5, "Coverage gaps kill", "Patel 25"),
    ),
    "a2": (
        FixtureCard(2, "b", _COSTS_TAG, "Okafor 25", "costs-advantage", headings=(*_COSTS, "no link")),
        FixtureCard(
            6,
            "a",
            "Single payer frees capital for research",
            "Moreau 25",
            "innovation-advantage",
            headings=(*_INNOVATION, "i l"),
        ),
        _unplaced(7, "Framing comes first", "Vance 22"),
        FixtureCard(8, "a", "Competition lowers premiums", "Liang 26", "public-option-aff", method=_KEYWORD),
    ),
    "a3": (
        FixtureCard(9, "a", "A public option competes prices down", "Liang 26", "public-option-aff"),
        FixtureCard(2, "a", _COSTS_TAG, "Okafor '25", "costs-advantage", method=_INHERITED, headings=_COSTS),
        _unplaced(10, "Solvency is immediate", "Reyes 24"),
        FixtureCard(
            35,
            "a",
            "Single payer solves within a year",
            "Reyes 25",
            "costs-advantage",
            headings=(*_COSTS, "solvency"),
        ),
        FixtureCard(
            36,
            "a",
            "Drug prices drive the deficit",
            "Haddad 24",
            "costs-advantage",
            role=_ANSWERS,
            headings=(*_COSTS, "internal link"),
        ),
        FixtureCard(
            37,
            "a",
            "Extinction from a debt crisis",
            "Okafor 26",
            "costs-advantage",
            headings=(*_COSTS, "debt crisis impact"),
        ),
    ),
    "a4": (
        FixtureCard(
            6,
            "a",
            "Single payer frees capital for research",
            "Moreau 25",
            "innovation-advantage",
            headings=_INNOVATION,
        ),
        FixtureCard(
            3,
            "b",
            "Bulk purchasing lowers drug prices",
            "Haddad 23",
            "costs-advantage",
            headings=(*_COSTS, "drug prices impact"),
        ),
        _unplaced(11, "Inherency: the status quo fails", "Nguyen 26"),
    ),
    "a5": (
        FixtureCard(
            2, "c", _COSTS_TAG, "Okafor 25", "costs-advantage", headings=(*_COSTS, "economic collapse")
        ),
        FixtureCard(27, "a", "Conditionality is a voting issue", "Feldman 22", "condo-bad"),
        FixtureCard(12, "a", "Extra evidence", "Ito 19", None, None, ClassificationMethod.OVERRIDE),
        FixtureCard(38, "a", "U: premiums are rising now", "Vance 26", "costs-advantage", headings=_COSTS),
    ),
    "a6": (
        FixtureCard(
            1, "b", "Single payer is the only path to universal coverage", "Brandt 24", "single-payer-aff"
        ),
        FixtureCard(
            6,
            "c",
            "Independently, research funding prevents extinction",
            "Moreau 25",
            "innovation-advantage",
            method=_INHERITED,
            headings=_INNOVATION,
        ),
        _unplaced(13, "Medical debt is rising", "Okoro 26"),
        FixtureCard(
            31, "a", "Spending is already high", "Mori 25", "spending-da", headings=(*_SPENDING, "impact")
        ),
        FixtureCard(
            45,
            "a",
            "Reform energizes the base",
            "Ward 25",
            "election-da",
            headings=(*_MIDTERMS, "internal link"),
        ),
    ),
    "b1": (
        FixtureCard(
            14, "a", "Spending triggers a debt spiral", "Ito 26", "spending-da", headings=(*_SPENDING, "link")
        ),
        FixtureCard(
            15,
            "a",
            "Debt ceiling fights are near",
            "Ruiz 26",
            "spending-da",
            method=_INHERITED,
            headings=(*_SPENDING, "cedarvale crash", "turns case"),
        ),
        FixtureCard(16, "a", "States can implement single payer", "Kowal 24", "states-cp"),
        FixtureCard(
            17,
            "a",
            "Costs advantage is inevitable anyway",
            "Shah 25",
            "costs-advantage",
            _ANSWERS,
            _INHERITED,
            (*_COSTS, "impact"),
        ),
    ),
    "b2": (
        FixtureCard(
            14,
            "b",
            "Spending triggers a debt spiral",
            "Ito 26",
            "spending-da",
            headings=(*_SPENDING, "impact"),
        ),
        FixtureCard(
            18,
            "a",
            "Healthcare markets commodify care",
            "Nadler 21",
            "cap-k",
            headings=("capitalism k", "impact"),
        ),
        _unplaced(19, "Uniqueness overwhelms the link", "Cole 26"),
        FixtureCard(
            39,
            "a",
            "Recession spreads worldwide",
            "Park 25",
            "spending-da",
            headings=(*_SPENDING, "recession"),
        ),
    ),
    "b3": (
        FixtureCard(
            20,
            "a",
            "Health reform costs the incumbents the midterms",
            "Abara 26",
            "election-da",
            headings=(*_MIDTERMS, "no impact"),
        ),
        FixtureCard(
            21, "a", "National health insurance means a single government insurer", "Ostrova 20", "nhi-t"
        ),
        FixtureCard(22, "a", "Courts can mandate coverage", "Bell 23", "courts-cp", method=_KEYWORD),
        FixtureCard(
            43,
            "a",
            "Incumbents already trail",
            "Abara 25",
            "election-da",
            headings=(*_MIDTERMS, "uniqueness"),
            answers=(False, True),
        ),
    ),
    "b4": (
        FixtureCard(
            20,
            "b",
            "Reform loses the midterms",
            "Abara 26",
            "election-da",
            headings=(*_MIDTERMS, "impact defense"),
        ),
        FixtureCard(18, "a", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        FixtureCard(
            23,
            "a",
            "Rural hospitals close under single payer",
            "Duarte 26",
            "hospital-closures-da",
            headings=("hospital closures da", "impact"),
        ),
        FixtureCard(44, "a", "The link: reform polls badly", "Ward 26", "election-da", headings=_MIDTERMS),
    ),
    "b5": (
        FixtureCard(16, "a", "States can implement single payer", "Kowal 24", "states-cp"),
        FixtureCard(
            14,
            "c",
            "Spending triggers a debt spiral",
            "Ito 2026",
            "spending-da",
            method=_INHERITED,
            headings=_SPENDING,
        ),
        FixtureCard(
            40, "a", "Spending is at a record high now", "Ito 25", "spending-da", headings=(*_SPENDING, "u")
        ),
        FixtureCard(
            41,
            "a",
            "Deficits spike interest rates",
            "Lee 26",
            "spending-da",
            headings=(*_SPENDING, "internal link"),
        ),
        FixtureCard(
            42,
            "a",
            "Rate spikes cause a recession",
            "Park 26",
            "spending-da",
            headings=(*_SPENDING, "recession impact"),
        ),
    ),
    "b6": (
        FixtureCard(29, "a", "Insurance means private carriers too", "Lund 21", "nhi-t"),
        FixtureCard(
            24,
            "a",
            "Nurses strike over reimbursement cuts",
            "Dube 25",
            "provider-strikes-da",
            method=_INHERITED,
            headings=("provider strikes da", "impact turns"),
        ),
    ),
    "b7": (
        FixtureCard(18, "b", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        _unplaced(25, "Off-case overview", "Imai 26"),
        FixtureCard(32, "a", "We meet their interpretation", "Pryor 24", "nhi-t", role=_ANSWERS),
        FixtureCard(
            33,
            "a",
            "2. Extinction outweighs",
            "Sato 26",
            "election-da",
            role=_ANSWERS,
            headings=(*_MIDTERMS, "impact"),
        ),
    ),
    "b8": (
        _unplaced(30, "Case turns", "Soto 25"),
        FixtureCard(26, "a", "PICs are legitimate", "Hart 24", "pics-bad", role=_ANSWERS),
    ),
    "b9": (
        FixtureCard(18, "c", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        FixtureCard(28, "a", "The plan is a tax", "Iqbal 26", "spending-da", headings=(*_SPENDING, "impact")),
    ),
    "ac": (
        FixtureCard(
            6,
            "d",
            "Single payer frees capital for research",
            "Moreau 25",
            "innovation-advantage",
            headings=_INNOVATION,
        ),
        FixtureCard(
            1, "c", "Single payer is the only path to universal coverage", "Brandt 24", "single-payer-aff"
        ),
    ),
    "ad": (
        FixtureCard(
            6,
            "e",
            "Single payer frees capital for research",
            "Moreau 25",
            "innovation-advantage",
            headings=_INNOVATION,
        ),
    ),
    "ae": (
        FixtureCard(
            34,
            "a",
            "Research spillovers save lives",
            "Quint 26",
            "innovation-advantage",
            headings=_INNOVATION,
        ),
    ),
    "bc": (FixtureCard(18, "d", "Healthcare markets commodify care", "Nadler 21", "cap-k"),),
    "bd": (
        FixtureCard(18, "e", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        FixtureCard(22, "b", "Courts can mandate coverage", "Bell 23", "courts-cp"),
    ),
}
"""Each source's cards, in document order: card `n` starts at paragraph `3n`."""

_CONFIDENCE: Final = {
    ClassificationMethod.ALIAS: 1.0,
    ClassificationMethod.OVERRIDE: 1.0,
    ClassificationMethod.INHERITED: 0.9,
    ClassificationMethod.TAG_KEYWORD: 0.5,
}
"""t02's fixed confidence per method (its Decisions 1 and 4)."""

OVERRIDES: Final = {
    "schema_version": 1,
    "topic_id": TOPIC,
    "overrides": [{"heading": "extra", "position_id": None}],
}


def taxonomy() -> Taxonomy:
    return Taxonomy.model_validate(
        {
            "topic_id": TOPIC,
            "taxonomy_version": TAXONOMY_VERSION,
            "event": "POLICY",
            "positions": [
                {
                    "id": one,
                    "label": label,
                    "kind": kind,
                    "side": side,
                    **({"parent": parent} if parent else {}),
                    **({"aliases": list(ALIASES[one])} if one in ALIASES else {}),
                }
                for one, label, kind, side, parent in POSITIONS
            ],
        }
    )


def _disclosure(
    caselist: str,
    event: Event,
    school: str,
    row: tuple[str, str, Side, str | None, str | None, date],
    sequence: int | None = None,
) -> Disclosure:
    """One manifest row, filed as OpenCaselist names a file; `sequence` goes between side and tournament."""
    source, code, side, tournament, played, snapshot = row
    parts = [school.replace(" ", ""), code, side.value.title()]
    parts += [str(sequence)] if sequence is not None else []
    parts += [tournament.replace(" ", "")] if tournament else []
    parts += [played] if played else []
    return Disclosure(
        source_sha256=_source(source),
        caselist=caselist,
        snapshot=snapshot,
        event=event,
        school=school,
        team_code=code,
        side=side,
        tournament=tournament,
        round_label=RoundLabel.from_raw(played) if played else None,
        source_path=f"{school}/{school} {code}/{'-'.join(parts)}.docx",
    )


def disclosures() -> list[Disclosure]:
    rows = [_disclosure(CASELIST, Event.POLICY, TEAMS[row[1]], row) for row in DISCLOSURES]
    rows += [
        _disclosure(
            CASELIST, Event.POLICY, TEAMS[code], (source, code, side, tournament, played, snapshot), sequence
        )
        for source, code, side, tournament, played, snapshot, sequence in RENAMED
    ]
    return rows


def cards(planted_cards: dict[str, tuple[FixtureCard, ...]] = CARDS) -> list[LandscapeCard]:
    return [
        LandscapeCard(
            source_sha256=_source(source),
            element_index=index * _PARAGRAPHS_PER_CARD,
            exact_fingerprint=_exact(card.cluster, card.copy),
            cluster_id=_cluster(card.cluster),
            tag=card.tag,
            short_cite=card.cite,
            headings=card.headings,
            heading_answers=card.answers,
        )
        for source, planted in planted_cards.items()
        for index, card in enumerate(planted)
    ]


def classifications(
    planted_cards: dict[str, tuple[FixtureCard, ...]] = CARDS, taxonomy_version: str = TAXONOMY_VERSION
) -> list[PositionClassification]:
    rows: list[PositionClassification] = []
    for source, planted in planted_cards.items():
        for index, card in enumerate(planted):
            element = index * _PARAGRAPHS_PER_CARD
            rows.append(
                PositionClassification(
                    item_id=card_item_id(_source(source), element),
                    item_kind=ItemKind.CARD,
                    source_sha256=_source(source),
                    first_element_index=element,
                    position_id=card.position,
                    role=card.role if card.position else None,
                    confidence=_CONFIDENCE[card.method] if card.method else 0.0,
                    rationale="synthetic fixture: placed as the fixture table says",
                    method=card.method,
                    taxonomy_version=taxonomy_version,
                )
            )
    return rows


def _jsonl(rows: list[Disclosure] | list[LandscapeCard] | list[PositionClassification]) -> str:
    return "".join(json.dumps(row.model_dump(mode="json"), sort_keys=True) + "\n" for row in rows)


TOPIC_CHANGE_FIXTURE: Final = REPO_ROOT / "tests" / "fixtures" / "landscape" / "topic_change_caselist"
TOPIC_CHANGE_CASELIST: Final = "synthld26"
OLD_TOPIC: Final = "synthetic-ld-jul-aug"
NEW_TOPIC: Final = "synthetic-ld-sep-oct"
NEW_TOPIC_VERSION: Final = "1.0.0"
LAST_OF_OLD_TOPIC: Final = date(2026, 8, 25)
FIRST_OF_NEW_TOPIC: Final = date(2026, 9, 1)
TOPIC_CHANGE_TEAMS: Final = {"QX": "Maple Grove", "RV": "Larch Point"}

TOPIC_CHANGE_TOPICS: Final = {
    "schema_version": 1,
    "topics": [
        {
            "id": OLD_TOPIC,
            "event": "LD",
            "caselists": [{"caselist": TOPIC_CHANGE_CASELIST, "from": "2026-07-01", "to": "2026-08-31"}],
        },
        {
            "id": NEW_TOPIC,
            "event": "LD",
            "taxonomy_version": NEW_TOPIC_VERSION,
            "caselists": [{"caselist": TOPIC_CHANGE_CASELIST, "from": "2026-09-01", "to": "2026-10-31"}],
        },
    ],
}
"""The topic map: one snapshot on each topic, the old one with no taxonomy, as LD's rotate."""

TOPIC_CHANGE_POSITIONS: Final = (
    ("restored-ecosystems-contention", "Restored ecosystems", "contention", "aff", None),
    ("biopower-k", "Biopower K", "k", "neg", None),
)

TOPIC_CHANGE_DISCLOSURES: Final = (
    ("e1", "QX", Side.AFF, "Summer Fictional Open", "R1", LAST_OF_OLD_TOPIC),
    ("f1", "RV", Side.NEG, "Summer Fictional Open", "R1", LAST_OF_OLD_TOPIC),
    ("e2", "QX", Side.AFF, "Autumn Fictional Classic", "R1", FIRST_OF_NEW_TOPIC),
    ("f2", "RV", Side.NEG, "Autumn Fictional Classic", "R1", FIRST_OF_NEW_TOPIC),
)
"""The same two teams on each topic: `e1` and `f1` on the old one, `e2` and `f2` on the new."""

TOPIC_CHANGE_CARDS: Final = {
    "e2": (
        FixtureCard(
            40, "a", "Revived species restore food webs", "Okonjo 26", "restored-ecosystems-contention"
        ),
    ),
    "f2": (FixtureCard(41, "a", "Conservation governs life itself", "Arendt 25", "biopower-k"),),
}
"""Only the new topic's files are classified: the old topic has no taxonomy."""


def topic_change_taxonomy() -> Taxonomy:
    return Taxonomy.model_validate(
        {
            "topic_id": NEW_TOPIC,
            "taxonomy_version": NEW_TOPIC_VERSION,
            "event": "LD",
            "positions": [
                {"id": one, "label": label, "kind": kind, "side": side}
                for one, label, kind, side, _ in TOPIC_CHANGE_POSITIONS
            ],
        }
    )


def topic_change_disclosures() -> list[Disclosure]:
    return [
        _disclosure(TOPIC_CHANGE_CASELIST, Event.LD, TOPIC_CHANGE_TEAMS[row[1]], row)
        for row in TOPIC_CHANGE_DISCLOSURES
    ]


def write_topic_change_caselist() -> None:
    TOPIC_CHANGE_FIXTURE.mkdir(parents=True, exist_ok=True)
    (TOPIC_CHANGE_FIXTURE / "topics.yaml").write_text(
        yaml.safe_dump(TOPIC_CHANGE_TOPICS, sort_keys=False), encoding="utf-8"
    )
    (TOPIC_CHANGE_FIXTURE / "taxonomy.yaml").write_text(
        yaml.safe_dump(
            topic_change_taxonomy().model_dump(mode="json", exclude_defaults=True), sort_keys=False
        ),
        encoding="utf-8",
    )
    (TOPIC_CHANGE_FIXTURE / "disclosures.jsonl").write_text(
        _jsonl(topic_change_disclosures()), encoding="utf-8"
    )
    (TOPIC_CHANGE_FIXTURE / "cards.jsonl").write_text(_jsonl(cards(TOPIC_CHANGE_CARDS)), encoding="utf-8")
    (TOPIC_CHANGE_FIXTURE / "classifications.jsonl").write_text(
        _jsonl(classifications(TOPIC_CHANGE_CARDS, NEW_TOPIC_VERSION)), encoding="utf-8"
    )
    print(f"wrote {TOPIC_CHANGE_FIXTURE.relative_to(REPO_ROOT)}")


def main() -> None:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    OverrideRules.model_validate(OVERRIDES)
    (FIXTURE / "taxonomy.yaml").write_text(
        yaml.safe_dump(taxonomy().model_dump(mode="json", exclude_defaults=True), sort_keys=False),
        encoding="utf-8",
    )
    (FIXTURE / "overrides.yaml").write_text(yaml.safe_dump(OVERRIDES, sort_keys=False), encoding="utf-8")
    (FIXTURE / "disclosures.jsonl").write_text(_jsonl(disclosures()), encoding="utf-8")
    (FIXTURE / "cards.jsonl").write_text(_jsonl(cards()), encoding="utf-8")
    (FIXTURE / "classifications.jsonl").write_text(_jsonl(classifications()), encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(REPO_ROOT)}")
    write_topic_change_caselist()


if __name__ == "__main__":
    main()
