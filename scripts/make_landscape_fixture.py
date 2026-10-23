#!/usr/bin/env python3
"""Write the synthetic two-snapshot caselist the landscape report is tested against (`v1-e32-t03`).

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

The fixture is small enough to count on paper: 15 sources, 18 disclosure rows, 16 rounds in range
by 8 teams, 44 cards (42 of them in range). Its README says what each part exercises. Owned by `v1-e32-t03`.
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
"""A snapshot after the report's date: its disclosure is out of range."""
_PARAGRAPHS_PER_CARD: Final = 3

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
    "ZZ": "Birchmoor Fictional",
    "QQ": "Birchmoor Fictional",
    "VV": "Cedarvale Fictional",
    "WW": "Cedarvale Fictional",
    "JJ": "Driftwood Fictional",
    "KK": "Driftwood Fictional",
}
"""Team code to school."""

FIRST_TOURNAMENT: Final = "Fictional Invitational"
SECOND_TOURNAMENT: Final = "Imaginary Classic"


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
    ("b9", "YY", Side.NEG, "Later Tournament", "R1", LATER),
)
"""(source, team code, side, tournament, round, snapshot), one row per manifest row.

`a1`'s first row is carried from the first window into the second (the same round, listed twice),
and `b1` is one file two teams disclosed (two rounds). `b7`'s filename gave no side, tournament or
round. `b9` is disclosed after the report's date.
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


def _unplaced(cluster: int, tag: str, cite: str) -> FixtureCard:
    return FixtureCard(cluster, "a", tag, cite, None, None, None)


_INHERITED: Final = ClassificationMethod.INHERITED
_KEYWORD: Final = ClassificationMethod.TAG_KEYWORD
_ANSWERS: Final = PositionRole.ANSWERS
_COSTS_TAG: Final = "Single payer cuts administrative costs"

CARDS: Final = {
    "a1": (
        FixtureCard(
            1, "a", "Single payer is the only path to universal coverage", "Brandt 24", "single-payer-aff"
        ),
        FixtureCard(2, "a", _COSTS_TAG, "Okafor 25", "costs-advantage", method=_INHERITED),
        FixtureCard(
            2, "d", "Administrative costs collapse", "Okafor 25", "costs-advantage", method=_INHERITED
        ),
        FixtureCard(4, "a", "Spending DA non-unique", "Grant 26", "spending-da", role=_ANSWERS),
        _unplaced(5, "Coverage gaps kill", "Patel 25"),
    ),
    "a2": (
        FixtureCard(2, "b", _COSTS_TAG, "Okafor 25", "costs-advantage"),
        FixtureCard(6, "a", "Single payer frees capital for research", "Moreau 25", "innovation-advantage"),
        _unplaced(7, "Framing comes first", "Vance 22"),
        FixtureCard(8, "a", "Competition lowers premiums", "Liang 26", "public-option-aff", method=_KEYWORD),
    ),
    "a3": (
        FixtureCard(9, "a", "A public option competes prices down", "Liang 26", "public-option-aff"),
        FixtureCard(2, "a", _COSTS_TAG, "Okafor '25", "costs-advantage", method=_INHERITED),
        _unplaced(10, "Solvency is immediate", "Reyes 24"),
    ),
    "a4": (
        FixtureCard(6, "a", "Single payer frees capital for research", "Moreau 25", "innovation-advantage"),
        FixtureCard(3, "b", "Bulk purchasing lowers drug prices", "Haddad 23", "costs-advantage"),
        _unplaced(11, "Inherency: the status quo fails", "Nguyen 26"),
    ),
    "a5": (
        FixtureCard(2, "c", _COSTS_TAG, "Okafor 25", "costs-advantage"),
        FixtureCard(27, "a", "Conditionality is a voting issue", "Feldman 22", "condo-bad"),
        FixtureCard(12, "a", "Extra evidence", "Ito 19", None, None, ClassificationMethod.OVERRIDE),
    ),
    "a6": (
        FixtureCard(
            1, "b", "Single payer is the only path to universal coverage", "Brandt 24", "single-payer-aff"
        ),
        FixtureCard(6, "c", "Research funding rises", "Moreau 25", "innovation-advantage", method=_INHERITED),
        _unplaced(13, "Medical debt is rising", "Okoro 26"),
    ),
    "b1": (
        FixtureCard(14, "a", "Spending triggers a debt spiral", "Ito 26", "spending-da"),
        FixtureCard(15, "a", "Debt ceiling fights are near", "Ruiz 26", "spending-da", method=_INHERITED),
        FixtureCard(16, "a", "States can implement single payer", "Kowal 24", "states-cp"),
        FixtureCard(
            17,
            "a",
            "Costs advantage is inevitable anyway",
            "Shah 25",
            "costs-advantage",
            _ANSWERS,
            _INHERITED,
        ),
    ),
    "b2": (
        FixtureCard(14, "b", "Spending triggers a debt spiral", "Ito 26", "spending-da"),
        FixtureCard(18, "a", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        _unplaced(19, "Uniqueness overwhelms the link", "Cole 26"),
    ),
    "b3": (
        FixtureCard(20, "a", "Health reform costs the incumbents the midterms", "Abara 26", "election-da"),
        FixtureCard(
            21, "a", "National health insurance means a single government insurer", "Ostrova 20", "nhi-t"
        ),
        FixtureCard(22, "a", "Courts can mandate coverage", "Bell 23", "courts-cp", method=_KEYWORD),
    ),
    "b4": (
        FixtureCard(20, "b", "Reform loses the midterms", "Abara 26", "election-da"),
        FixtureCard(18, "a", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        FixtureCard(23, "a", "Rural hospitals close under single payer", "Duarte 26", "hospital-closures-da"),
    ),
    "b5": (
        FixtureCard(16, "a", "States can implement single payer", "Kowal 24", "states-cp"),
        FixtureCard(14, "c", "Spending triggers a debt spiral", "Ito 2026", "spending-da", method=_INHERITED),
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
        ),
    ),
    "b7": (
        FixtureCard(18, "b", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        _unplaced(25, "Off-case overview", "Imai 26"),
    ),
    "b8": (
        _unplaced(30, "Case turns", "Soto 25"),
        FixtureCard(26, "a", "PICs are legitimate", "Hart 24", "pics-bad", role=_ANSWERS),
    ),
    "b9": (
        FixtureCard(18, "c", "Healthcare markets commodify care", "Nadler 21", "cap-k"),
        FixtureCard(28, "a", "The plan is a tax", "Iqbal 26", "spending-da"),
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
                }
                for one, label, kind, side, parent in POSITIONS
            ],
        }
    )


def disclosures() -> list[Disclosure]:
    rows: list[Disclosure] = []
    for source, code, side, tournament, played, snapshot in DISCLOSURES:
        school = TEAMS[code]
        parts = [school.replace(" ", ""), code, side.value.title()]
        parts += [tournament.replace(" ", "")] if tournament else []
        parts += [played] if played else []
        rows.append(
            Disclosure(
                source_sha256=_source(source),
                caselist=CASELIST,
                snapshot=snapshot,
                event=Event.POLICY,
                school=school,
                team_code=code,
                side=side,
                tournament=tournament,
                round_label=RoundLabel.from_raw(played) if played else None,
                source_path=f"{school}/{school} {code}/{'-'.join(parts)}.docx",
            )
        )
    return rows


def cards() -> list[LandscapeCard]:
    return [
        LandscapeCard(
            source_sha256=_source(source),
            element_index=index * _PARAGRAPHS_PER_CARD,
            exact_fingerprint=_exact(card.cluster, card.copy),
            cluster_id=_cluster(card.cluster),
            tag=card.tag,
            short_cite=card.cite,
        )
        for source, planted in CARDS.items()
        for index, card in enumerate(planted)
    ]


def classifications() -> list[PositionClassification]:
    rows: list[PositionClassification] = []
    for source, planted in CARDS.items():
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
                    taxonomy_version=TAXONOMY_VERSION,
                )
            )
    return rows


def _jsonl(rows: list[Disclosure] | list[LandscapeCard] | list[PositionClassification]) -> str:
    return "".join(json.dumps(row.model_dump(mode="json"), sort_keys=True) + "\n" for row in rows)


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


if __name__ == "__main__":
    main()
