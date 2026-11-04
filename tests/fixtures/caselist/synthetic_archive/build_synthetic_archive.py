"""A tiny invented weekly caselist archive for the end-to-end caselist scenario (`v1-e09-t05` ac4).

Nothing here came from a real caselist (`docs/policies/caselist-data-use.md`, the PM's ruling 3 for
this task): the caselist `synthcl26`, the schools `Maple Grove` and `Cedar Hollow`, the team codes `QX`
and `ZaLu`, the tournament, the authors and every word of every card are invented, written here. The
two schools and codes are the invented ones `build_synthetic_archives.py` already uses.

## The archive

`synthcl26-0915.zip`, one weekly snapshot (2026-09-15) of a Policy caselist, laid out as OpenCaselist
lays one out::

    synthcl26-0915/<School>/<TeamCode>/<School>-<TeamCode>-<Side>-<Tournament>-<Round>.docx

| Member | Body |
|---|---|
| `Maple Grove/QX/Maple Grove-QX-Aff-Riverbend Invitational-Round 1.docx` | the affirmative: cards 1 and 2 |
| `Maple Grove/QX/Maple Grove-QX-Aff-Riverbend Invitational-Round 1 (1).docx` | the same bytes, re-uploaded |
| `Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Riverbend Invitational-Round 1.docx` | the negative: 3 and 4 |

So an import sees **three** files, **two** distinct SHA-256 values: two NEW and one DUPLICATE.

## The cards

Each source is a block heading (Heading 3), then per card a tag (Heading 4), a cite and one body
paragraph. :data:`CARDS` holds every card's words; the body's text is the card's evidence, exactly.

| Card | Source | Heading | Placed by |
|---|---|---|---|
| 1 | affirmative | `Grid Reliability Advantage` | the alias `grid reliability advantage` of `grid-adv` |
| 2 | affirmative | `Grid Reliability Advantage` | the same alias |
| 3 | negative | `Spending DA` | the alias `spending da` of `spending-da` |
| 4 | negative | `Off-case one` | no alias: the model stage, replayed from `cassettes/`: `spending-da` |

## The landscape configuration

`config/landscape/`: a topic `synth` (Policy) covering `synthcl26` from 2026-08-01, and its taxonomy,
1.0.0, with the two positions above. `files build` needs no landscape; `landscape report` reads it.

## The recipe

`synth-grid-adv.yaml`: one affirmative file for `grid-adv`, one pocket, one block holding cards 1 and
2 by fingerprint, in that order. A fingerprint is a digest of a card as the parser reads it, so it is
computed here (as `tests/fixtures/file_builder/example_corpus.py` computes the examples'), never typed.

## Determinism

Document bodies are literals and every zip entry has a fixed timestamp and compression, so two builds
give the same bytes, and the source SHA-256 values are fixed.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Final

import yaml

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

__all__ = [
    "CARDS",
    "CASELIST",
    "DIRECTORY",
    "SNAPSHOT",
    "SyntheticArchive",
    "SyntheticCard",
    "build_synthetic_archive",
]

DIRECTORY: Final = Path(__file__).resolve().parent
CASELIST: Final = "synthcl26"
SNAPSHOT: Final = date(2026, 9, 15)
TOPIC: Final = "synth"
TOURNAMENT: Final = "Riverbend Invitational"
ROOT: Final = f"{CASELIST}-{SNAPSHOT:%m%d}"
RECIPE_NAME: Final = "synth-grid-adv.yaml"
_ZIP_TIME: Final = (2026, 9, 15, 6, 0, 0)


@dataclass(frozen=True, slots=True)
class SyntheticCard:
    number: int
    heading: str
    tag: str
    author: str
    cite_rest: str
    small: str
    """The body's first run, in 8 pt: the part nobody reads."""
    underlined: str
    """The body's underlined, highlighted run."""
    closing: str

    @property
    def evidence(self) -> str:
        """The card's evidence text: its body paragraph, every run, as written."""
        return self.small + self.underlined + self.closing

    def xml(self) -> str:
        return (
            paragraph_xml(run_xml(self.tag), style="Heading4")
            + paragraph_xml(run_xml(self.author, character_style="Style13ptBold") + run_xml(self.cite_rest))
            + paragraph_xml(
                run_xml(self.small, half_points=16)
                + run_xml(self.underlined, character_style="StyleUnderline", highlight="cyan")
                + run_xml(self.closing, half_points=16)
            )
        )


CARDS: Final = (
    SyntheticCard(
        1,
        "Grid Reliability Advantage",
        "Rooftop arrays keep the invented grid running through heat waves",
        "Lindqvist 25",
        ", Engineer, Synthetic Grid Institute, Synthetic Energy Review, 2025",
        "During the invented heat wave of the year 2031, ",
        "rooftop arrays carried the evening load across the valley",
        " while two older plants tripped offline for most of a week.",
    ),
    SyntheticCard(
        2,
        "Grid Reliability Advantage",
        "Storage beside the arrays prevents the blackout the status quo invites",
        "Okonkwo 24",
        ", Fellow, Synthetic Storage Council, Synthetic Utility Quarterly, 2024",
        "Planners in the invented basin found that ",
        "batteries sited beside the arrays held the frequency steady",
        " during each of the nine faults recorded on the synthetic network.",
    ),
    SyntheticCard(
        3,
        "Spending DA",
        "New subsidies blow through the invented spending cap",
        "Achterberg 26",
        ", Analyst, Synthetic Budget Office, Synthetic Fiscal Notes, 2026",
        "The invented appropriations committee warned that ",
        "any new subsidy line breaches the cap this session",
        " and forces cuts the committee has already said it will not make.",
    ),
    SyntheticCard(
        4,
        "Off-case one",
        "A breach of the cap triggers automatic cuts to every invented program",
        "Marsh 26",
        ", Professor, Synthetic University, Synthetic Review of Budgets, 2026",
        "Under the invented statute, ",
        "a breach of the cap starts automatic cuts within thirty days",
        " to every program on the synthetic schedule, popular or not.",
    ),
)


def _source(cards: tuple[SyntheticCard, ...]) -> bytes:
    """The cards in order, each heading written once, above the first card filed under it."""
    body = ""
    heading = None
    for card in cards:
        if card.heading != heading:
            heading = card.heading
            body += paragraph_xml(run_xml(heading), style="Heading3")
        body += card.xml()
    return build_docx(body)


AFFIRMATIVE: Final = _source(CARDS[:2])
NEGATIVE: Final = _source(CARDS[2:])

AFFIRMATIVE_PATH: Final = f"Maple Grove/QX/Maple Grove-QX-Aff-{TOURNAMENT}-Round 1.docx"
REUPLOAD_PATH: Final = f"Maple Grove/QX/Maple Grove-QX-Aff-{TOURNAMENT}-Round 1 (1).docx"
NEGATIVE_PATH: Final = f"Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-{TOURNAMENT}-Round 1.docx"


@dataclass(frozen=True, slots=True)
class SyntheticArchive:
    archive: Path
    recipe: Path
    config_dir: Path
    source_sha256: dict[int, str]
    """Card number → the SHA-256 of the source file it is in."""
    fingerprints: dict[int, str]
    """Card number → its exact fingerprint, as `caselist parse` records it."""


def archive_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, body in (
            (AFFIRMATIVE_PATH, AFFIRMATIVE),
            (REUPLOAD_PATH, AFFIRMATIVE),
            (NEGATIVE_PATH, NEGATIVE),
        ):
            info = zipfile.ZipInfo(f"{ROOT}/{member}", date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    return buffer.getvalue()


def _fingerprints(content: bytes) -> list[str]:
    source = SourceDocument(
        sha256="0" * 64,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    parsed = DebateDocxParser().parse(content, source, source_path="synthetic.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    return [card_fingerprint(card).exact_fingerprint for card in parsed.cards]


def _recipe(fingerprints: dict[int, str]) -> str:
    document = {
        "schema_version": 1,
        "title": "Grid reliability advantage",
        "topic": TOPIC,
        "format": "POLICY",
        "caselist": CASELIST,
        "position": "grid-adv",
        "side": "AFF",
        "status": "ready",
        "fingerprint_version": FINGERPRINT_VERSION,
        "structure": [
            {
                "pocket": "Grid Reliability Advantage",
                "blocks": [
                    {
                        "block": "The grid holds with rooftop solar",
                        "items": [{"fingerprint": fingerprints[1]}, {"fingerprint": fingerprints[2]}],
                    }
                ],
            }
        ],
    }
    header = "# Synthetic recipe for the end-to-end caselist scenario (v1-e09-t05); every word is invented.\n"
    return header + yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


def _write_landscape_config(config_dir: Path) -> None:
    (config_dir / "taxonomies").mkdir(parents=True, exist_ok=True)
    (config_dir / "topics.yaml").write_text(
        "schema_version: 1\n"
        "topics:\n"
        f"  - id: {TOPIC}\n"
        "    event: POLICY\n"
        "    taxonomy_version: 1.0.0\n"
        "    caselists:\n"
        f"      - {{caselist: {CASELIST}, from: 2026-08-01, to: 2026-12-31}}\n",
        encoding="utf-8",
    )
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(
        "schema_version: 1\n"
        f"topic_id: {TOPIC}\n"
        "taxonomy_version: 1.0.0\n"
        "event: POLICY\n"
        "positions:\n"
        "  - {id: grid-adv, label: Grid reliability advantage, kind: advantage, side: aff, "
        "aliases: [grid reliability advantage]}\n"
        "  - {id: spending-da, label: Spending disadvantage, kind: da, side: neg, aliases: [spending da]}\n",
        encoding="utf-8",
    )


def build_synthetic_archive(directory: Path) -> SyntheticArchive:
    """Write the archive, the recipe and `config/landscape/` under `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f"{ROOT}.zip"
    archive.write_bytes(archive_bytes())
    affirmative, negative = _fingerprints(AFFIRMATIVE), _fingerprints(NEGATIVE)
    fingerprints: dict[int, str] = dict(zip((1, 2, 3, 4), [*affirmative, *negative], strict=True))
    recipe = directory / RECIPE_NAME
    recipe.write_text(_recipe(fingerprints), encoding="utf-8")
    config_dir = directory / "config" / "landscape"
    _write_landscape_config(config_dir)
    shas = {1: hashlib.sha256(AFFIRMATIVE).hexdigest(), 3: hashlib.sha256(NEGATIVE).hexdigest()}
    return SyntheticArchive(
        archive=archive,
        recipe=recipe,
        config_dir=config_dir,
        source_sha256={1: shas[1], 2: shas[1], 3: shas[3], 4: shas[3]},
        fingerprints=fingerprints,
    )
