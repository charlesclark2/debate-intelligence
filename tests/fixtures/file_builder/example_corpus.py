"""A synthetic corpus for one of t01's example recipes, as `files build` reads it (`v1-e33-t03` ac1, ac6).

Also for the synthetic counterplan recipe in `counterplans/` (`v1-e33-t15`), whose position the taxonomy
marks a counterplan (`kind="cp"`), so that `files suggest` drafts it as one: its first block opens with
the CP text slot.

t01's examples (`recipes/`) name fingerprints no card has: a fingerprint is a digest of a card's text,
so no corpus can be made to match them. As `scripts/build_example_evidence_files.py` does for
`v1-e33-t02` (PM ruling, 2026-10-19), each card reference gets one synthetic source of its own, and the
recipe keeps its structure, headings, analytics, tag overrides and pins' disclosure fields while its
fingerprints, and its pins' source hashes and element indices, are replaced by the synthetic cards'.
The examples themselves are not changed: the rewritten recipe is written beside the archive.

What :func:`example_corpus` writes, under the directory it is given:

* **one weekly archive**, `<caselist>-<MMDD>.zip`, filing each source at the path OpenCaselist would
  give it: the school, team code, side, tournament and round a pin names, or an invented team's;
* **the rewritten recipe**, `<example name>.yaml`;
* **`config/landscape/`**: a topic for the recipe's caselist and a taxonomy holding the recipe's
  position, read on the recipe's side under the heading every source files its card under, so `files
  suggest` has a landscape to read.

The caller imports the archive with `caselist import` and parses it with `caselist parse`, through the
CLI, so the occurrence table and the caselist records are the real pipeline's. Each source is built in
memory with `debate_core.testing.docx_builder`: a heading, a tag, a cite and a body. Every school, team
code, tournament, author and word is invented.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import yaml

from debate_core.domain.caselist import Side, SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.fingerprints import card_fingerprint
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

__all__ = ["COUNTERPLANS", "EXAMPLES", "ExampleCard", "ExampleCorpus", "example_corpus"]

EXAMPLES: Final = Path(__file__).resolve().parent / "recipes"

#: A counterplan's recipe, beside t01's examples rather than among them (`v1-e33-t15`).
COUNTERPLANS: Final = Path(__file__).resolve().parent / "counterplans"

#: The heading every source files its card under, and the alias of the recipe's position.
SOURCE_HEADING: Final = "Synthetic Position"
SOURCE_HEADING_ALIAS: Final = "synthetic position"

#: The snapshot the archive is filed as, unless a pin names a later one.
DEFAULT_SNAPSHOT: Final = date(2026, 9, 15)

_AUTHORS: Final = ("Lindqvist", "Okonkwo", "Achterberg", "Marsh", "Ferreira", "Nakamura", "Osei", "Brandt")
_TEAMS: Final = (("Maple Grove", "QX"), ("Cedar Hollow", "ZaLu"))
_TOURNAMENT: Final = "Riverbend Invitational"
_SIDE_WORDS: Final = {Side.AFF: "Aff", Side.NEG: "Neg", Side.PRO: "Pro", Side.CON: "Con"}


@dataclass(frozen=True, slots=True)
class ExampleCard:
    """One card reference of the recipe, in recipe order, and the synthetic source it now names."""

    number: int
    fingerprint: str
    source_sha256: str
    element_index: int
    tag_override: bool
    pinned: bool


@dataclass(frozen=True, slots=True)
class ExampleCorpus:
    caselist: str
    snapshot: date
    archive: Path
    recipe: Path
    config_dir: Path
    cards: tuple[ExampleCard, ...]
    analytics: int


def source_document(number: int, title: str) -> bytes:
    """One source holding one card under :data:`SOURCE_HEADING`, numbered so no two are alike."""
    author = _AUTHORS[number % len(_AUTHORS)]
    year = 20 + number % 7
    return build_docx(
        paragraph_xml(run_xml(SOURCE_HEADING), style="Heading3")
        + paragraph_xml(run_xml(f"{title}: synthetic claim number {number}"), style="Heading4")
        + paragraph_xml(
            run_xml(f"{author} {year}", character_style="Style13ptBold")
            + run_xml(f", Fellow, Synthetic Institute {number}, Synthetic Review of Policy, 20{year}")
        )
        + paragraph_xml(
            run_xml(f"Synthetic evidence {number} begins in small print, ", half_points=16)
            + run_xml("then the part a debater reads", character_style="StyleUnderline", highlight="cyan")
            + run_xml(", then ", half_points=16)
            + run_xml("an emphasised warrant", character_style="Emphasis", bold=True, highlight="green")
            + run_xml(f" before it closes on item {number}.", half_points=16)
        )
    )


def _card_refs(document: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for pocket in document["structure"]:
        blocks = [block for hat in pocket.get("hats") or () for block in hat["blocks"]]
        blocks += list(pocket.get("blocks") or ())
        refs.extend(item for block in blocks for item in block["items"] if "fingerprint" in item)
    return refs


def _analytics(document: dict[str, Any]) -> int:
    return sum(len([item for item in items if "analytic" in item]) for items in _block_items(document))


def _block_items(document: dict[str, Any]) -> list[list[dict[str, Any]]]:
    found: list[list[dict[str, Any]]] = []
    for pocket in document["structure"]:
        blocks = [block for hat in pocket.get("hats") or () for block in hat["blocks"]]
        blocks += list(pocket.get("blocks") or ())
        found.extend(block["items"] for block in blocks)
    return found


def _parsed_card(content: bytes, parser: DebateDocxParser) -> tuple[str, int]:
    """The one card's exact fingerprint and first paragraph, as `caselist parse` will record them."""
    source = SourceDocument(
        sha256="0" * 64,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspolicy26",
        first_seen_snapshot=DEFAULT_SNAPSHOT,
        last_seen_snapshot=DEFAULT_SNAPSHOT,
    )
    parsed = parser.parse(content, source, source_path="synthetic.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    (card,) = parsed.cards
    return card_fingerprint(card).exact_fingerprint, card.provenance.first_element_index


def example_corpus(example: Path, directory: Path, *, kind: str = "da") -> ExampleCorpus:
    """The archive, rewritten recipe and landscape configuration for `example`, under `directory`.

    `kind` is the taxonomy's kind for the recipe's position: `da` for t01's examples, `cp` for a
    counterplan's.
    """
    document: dict[str, Any] = yaml.safe_load(example.read_text(encoding="utf-8"))
    caselist: str = document["caselist"]
    side = Side(document["side"])
    refs = _card_refs(document)
    pinned_days = [
        date.fromisoformat(str(ref["pin"]["snapshot"])) for ref in refs if ref.get("pin", {}).get("snapshot")
    ]
    snapshot = max([DEFAULT_SNAPSHOT, *pinned_days])
    parser = DebateDocxParser()
    cards: list[ExampleCard] = []
    buffer = BytesIO()
    root = f"{caselist}-{snapshot:%m%d}"
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for number, ref in enumerate(refs, start=1):
            pin: dict[str, Any] | None = ref.get("pin")
            school, team = _TEAMS[number % len(_TEAMS)]
            school = str(pin.get("school", school)) if pin else school
            team = str(pin.get("team_code", team)) if pin else team
            read_on = Side(pin["side"]) if pin and "side" in pin else side
            tournament = str(pin.get("tournament", _TOURNAMENT)) if pin else _TOURNAMENT
            round_raw = str(pin.get("round", f"Round {number}")) if pin else f"Round {number}"
            content = source_document(number, document["title"])
            name = f"{school}-{team}-{_SIDE_WORDS[read_on]}-{tournament}-{round_raw}.docx"
            archive.writestr(f"{root}/{school}/{team}/{name}", content)
            fingerprint, element_index = _parsed_card(content, parser)
            sha = hashlib.sha256(content).hexdigest()
            ref["fingerprint"] = fingerprint
            if pin:
                pin["source_sha256"] = sha
                pin["element_index"] = element_index
                if "snapshot" in pin:
                    pin["snapshot"] = snapshot.isoformat()
            cards.append(
                ExampleCard(
                    number=number,
                    fingerprint=fingerprint,
                    source_sha256=sha,
                    element_index=element_index,
                    tag_override="tag_override" in ref,
                    pinned=pin is not None,
                )
            )
    directory.mkdir(parents=True, exist_ok=True)
    archive_path = directory / f"{root}.zip"
    archive_path.write_bytes(buffer.getvalue())
    recipe_path = directory / example.name
    recipe_path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    config_dir = directory / "config" / "landscape"
    _write_landscape_config(config_dir, document, snapshot, kind)
    return ExampleCorpus(
        caselist=caselist,
        snapshot=snapshot,
        archive=archive_path,
        recipe=recipe_path,
        config_dir=config_dir,
        cards=tuple(cards),
        analytics=_analytics(document),
    )


def _write_landscape_config(config_dir: Path, document: dict[str, Any], snapshot: date, kind: str) -> None:
    """A topic covering the archive's snapshot, and the recipe's position, of `kind`, read on its side."""
    side = Side(document["side"])
    position_side = "aff" if side in (Side.AFF, Side.PRO) else "neg"
    (config_dir / "taxonomies").mkdir(parents=True, exist_ok=True)
    (config_dir / "topics.yaml").write_text(
        "schema_version: 1\n"
        "topics:\n"
        f"  - id: {document['topic']}\n"
        f"    event: {document['format']}\n"
        "    taxonomy_version: 1.0.0\n"
        "    caselists:\n"
        f"      - {{caselist: {document['caselist']}, "
        f"from: {snapshot.year}-08-01, to: {snapshot.year}-12-31}}\n",
        encoding="utf-8",
    )
    (config_dir / "taxonomies" / f"{document['topic']}.yaml").write_text(
        "schema_version: 1\n"
        f"topic_id: {document['topic']}\n"
        "taxonomy_version: 1.0.0\n"
        f"event: {document['format']}\n"
        "positions:\n"
        f"  - {{id: {document['position']}, label: Synthetic position, kind: {kind}, side: {position_side}, "
        f"aliases: [{SOURCE_HEADING_ALIAS}]}}\n",
        encoding="utf-8",
    )
