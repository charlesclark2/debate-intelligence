"""`synthetic26`: an invented Policy caselist as this machine's stores hold one, for `landscape report`.

`v1-e32-t05`'s run service, its command and its smoke check read a caselist the way a real run does:
weekly manifests, the parsed card store with its occurrence table, and `config/landscape/` beside
it. :func:`plant_synthetic_run` writes all of that under one directory. Every school, team code,
tournament, tag and cite is invented.

## The caselist

Two weekly snapshots, 2026-09-08 and 2026-09-15, four sources by three teams, nine cards:

| Source | Disclosed | Team, side, round | Cards, by their heading under `1AC` or `1NC`
|---|---|---|---
| `aff-one` | 09-08 | Quillmere Academy QW, aff, Lantern Classic R1 | Single Payer; Costs Advantage; Solvency
| `neg-one` | 09-08 | Brindle Valley ZT, neg, Lantern Classic R1 | Spending DA (twice); States CP
| `neg-two` | 09-15 | Harrowgate Prep PX, neg, Thistle Open R2 | Spending DA; Framing
| `aff-two` | 09-15 | Harrowgate Prep PX, aff, Thistle Open R3 | Costs Advantage

So, by hand: seven cards sit under a heading an alias names (`single payer` once, `costs advantage`
twice, `spending da` three times, `states cp` once) and two under one nothing names (`solvency`,
`framing`). The first spending card of `neg-one` and the one of `neg-two` are one E31 cluster, as
are the two costs cards.

`aff-two`'s file also holds a plan text, written as a real `.docx` in the blob store: "The United
States federal government should establish single payer health insurance", under a `Plan` heading.
`v1-e32-t09`'s plan-text reading names single payer from it, so with the aff seam wired that round is
identified by `PLAN_TEXT`, and `aff-one` by its placed card.

`planted_tags` replaces a card's tag by its `(source, index)`: how a test puts a team code or a
school in a report, so the scan has something to find.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from debate_core.application.ports.parsed_store import (
    OCCURRENCES_NAME,
    PARSED_PREFIX,
    OccurrenceRecord,
)
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.landscape_store import PARSER_VERSION, PROFILE_VERSION, PlantedCard, PlantedCaselist

__all__ = [
    "SYNTHETIC_RUN_CASELIST",
    "SYNTHETIC_RUN_SNAPSHOTS",
    "SYNTHETIC_RUN_TODAY",
    "SYNTHETIC_RUN_TOPIC",
    "SyntheticRun",
    "plant_synthetic_run",
]

SYNTHETIC_RUN_CASELIST: Final = "synthetic26"
SYNTHETIC_RUN_TOPIC: Final = "policy-synthetic-topic"
SYNTHETIC_RUN_SNAPSHOTS: Final = (date(2026, 9, 8), date(2026, 9, 15))
SYNTHETIC_RUN_TODAY: Final = date(2026, 9, 17)
"""Two days after the newest snapshot: not stale."""

_FINGERPRINT_VERSION: Final = "card-fingerprint-v4"
_PARAGRAPHS_PER_CARD: Final = 3

TOPICS: Final = f"""\
schema_version: 1
topics:
  - id: {SYNTHETIC_RUN_TOPIC}
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {{caselist: {SYNTHETIC_RUN_CASELIST}, from: 2026-09-01, to: 2026-12-31}}
  - id: ld-synthetic-topic
    event: LD
    caselists:
      - {{caselist: synthld26, from: 2026-09-01, to: 2026-12-31}}
"""

TAXONOMY: Final = f"""\
schema_version: 1
topic_id: {SYNTHETIC_RUN_TOPIC}
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {{id: single-payer-aff, label: Single payer, kind: aff, side: aff, aliases: [single payer]}}
  - {{id: costs-advantage, label: Costs advantage, kind: advantage, side: aff, aliases: [costs advantage]}}
  - {{id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}}
  - {{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}}
"""


@dataclass(frozen=True, slots=True)
class _Card:
    headings: tuple[str, ...]
    tag: str
    cite: str
    cluster: str


@dataclass(frozen=True, slots=True)
class _Source:
    name: str
    snapshot: str
    path: str
    cards: tuple[_Card, ...]
    plan: str | None = None


SOURCES: Final = (
    _Source(
        "aff-one",
        "2026-09-08",
        "Quillmere Academy/QW/Quillmere Academy-QW-Aff-Lantern Classic-Round 1.docx",
        (
            _Card(("1AC", "Single Payer"), "Single payer covers everyone", "Okonkwo 26", "plan"),
            _Card(("1AC", "Costs Advantage"), "Premiums are rising fast", "Delacroix 25", "costs"),
            _Card(("1AC", "Solvency"), "Public financing is cheaper", "Varga 26", "solvency"),
        ),
    ),
    _Source(
        "neg-one",
        "2026-09-08",
        "Brindle Valley/ZT/Brindle Valley-ZT-Neg-Lantern Classic-Round 1.docx",
        (
            _Card(("1NC", "Spending DA"), "New spending triggers a crowd-out", "Halvorsen 26", "spending"),
            _Card(("1NC", "Spending DA"), "Crowd-out tanks the bond market", "Mbeki 25", "bonds"),
            _Card(("1NC", "States CP"), "The states should establish it", "Pryce 26", "states"),
        ),
    ),
    _Source(
        "neg-two",
        "2026-09-15",
        "Harrowgate Prep/PX/Harrowgate Prep-PX-Neg-Thistle Open-Round 2.docx",
        (
            _Card(("1NC", "Spending DA"), "New spending triggers a crowd-out", "Halvorsen 26", "spending"),
            _Card(("1NC", "Framing"), "Probability first", "Szabo 24", "framing"),
        ),
    ),
    _Source(
        "aff-two",
        "2026-09-15",
        "Harrowgate Prep/PX/Harrowgate Prep-PX-Aff-Thistle Open-Round 3.docx",
        (_Card(("1AC", "Costs Advantage"), "Premiums are rising fast", "Delacroix 25", "costs"),),
        plan="The United States federal government should establish single payer health insurance.",
    ),
)


@dataclass(frozen=True, slots=True)
class SyntheticRun:
    data_dir: Path
    config_dir: Path


def plant_synthetic_run(
    root: Path, *, planted_tags: Mapping[tuple[str, int], str] | None = None
) -> SyntheticRun:
    """Write `synthetic26`'s stores under `root/data` and its configuration under `root/config`."""
    planted = dict(planted_tags or {})
    data_dir = root / "data"
    store = PlantedCaselist(data_dir, SYNTHETIC_RUN_CASELIST)
    occurrences: list[OccurrenceRecord] = []
    for source in SOURCES:
        tags = [planted.get((source.name, index), card.tag) for index, card in enumerate(source.cards)]
        digest = store.source(
            source.name,
            [
                PlantedCard(card.headings, tag=tag, short_cite=card.cite)
                for card, tag in zip(source.cards, tags, strict=True)
            ],
            disclosures=[(source.snapshot, source.path)],
            content=_plan_file(source.plan) if source.plan is not None else None,
        )
        for index, (card, tag) in enumerate(zip(source.cards, tags, strict=True)):
            first = index * _PARAGRAPHS_PER_CARD
            occurrences.append(
                OccurrenceRecord.model_validate(
                    {
                        "caselist": SYNTHETIC_RUN_CASELIST,
                        "snapshot": source.snapshot,
                        "last_snapshot": source.snapshot,
                        "source_sha256": digest,
                        "parser_version": PARSER_VERSION,
                        "profile_version": PROFILE_VERSION,
                        "fingerprint_version": _FINGERPRINT_VERSION,
                        "disclosure": disclosure_digest(SYNTHETIC_RUN_CASELIST, source.path),
                        "first_element_index": first,
                        "last_element_index": first + 2,
                        "exact_fingerprint": _digest(f"{tag}|{card.cite}"),
                        "cluster_id": _digest(card.cluster),
                        "membership": "NEAR_DUPLICATE",
                        "completeness": "FULL",
                    }
                )
            )
    table = data_dir / PARSED_PREFIX / SYNTHETIC_RUN_CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    table.write_text(
        "".join(one.model_dump_json() + "\n" for one in sorted(occurrences, key=_occurrence_order)),
        encoding="utf-8",
    )
    config_dir = root / "config"
    (config_dir / "taxonomies").mkdir(parents=True, exist_ok=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{SYNTHETIC_RUN_TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return SyntheticRun(data_dir=data_dir, config_dir=config_dir)


def _plan_file(plan: str) -> bytes:
    return build_docx(
        paragraph_xml(run_xml("Plan"), style="Heading3") + paragraph_xml(run_xml(plan), style="Analytic")
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _occurrence_order(record: OccurrenceRecord) -> tuple[str, int]:
    return (record.source_sha256, record.first_element_index)
