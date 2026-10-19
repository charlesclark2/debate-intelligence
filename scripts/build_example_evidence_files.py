"""Build one evidence file per format from v1-e33-t01's example recipes, for v1-e33-t02 ac6.

The coach opens each file in Word with Verbatim and says whether Word asks to repair it; the operator
also runs the CardMirror round-trip over them (ADR-0014). This script makes those three files.

**Every card is synthetic.** t01's example recipes name fingerprints no card has, so each card
reference gets one synthetic source document of its own, built in memory with
`debate_core.testing.docx_builder`: a tag, a cite and a body holding the run shapes the writer copies
(named and direct underline, emphasis, bold, highlight colours, font sizes, a tracked insertion, a
tracked deletion and a comment). Each recipe keeps its structure, headings, analytics and tag
overrides; its fingerprints, and its pins' source hashes and element indices, are replaced in memory
by the synthetic cards' (PM ruling, 2026-10-19). t01's files and guide are not changed.

The files are written outside the repository, which the script checks: built files are never
committed. Each `.docx` is written with its `.provenance.json` sidecar.

No inline script metadata here on purpose: this script imports debate_core, so it must run in the
workspace environment.

Usage:
  uv run scripts/build_example_evidence_files.py --output ~/e33-example-files
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml

from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile, FileBuildRequest
from debate_core.domain.caselist import Side
from debate_core.domain.file_provenance import provenance_sidecar_name
from debate_core.domain.file_recipe import FileRecipe
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import FileBuilderWorld, SourceCard, SyntheticDisclosure

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "tests" / "fixtures" / "file_builder" / "recipes"

#: The request time written into every sidecar, so two runs write the same bytes.
BUILT_AT: Final = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

_AUTHORS: Final = ("Lindqvist", "Okonkwo", "Achterberg", "Marsh", "Ferreira", "Nakamura", "Osei", "Brandt")
_TEAMS: Final = (("Maple Grove", "QX"), ("Cedar Hollow", "ZaLu"))
_AUTHOR_ATTRIBUTES: Final = 'w:author="Synthetic Editor" w:date="2026-09-01T10:00:00Z"'


def synthetic_card(number: int, recipe_title: str) -> bytes:
    """One source document holding one card, numbered so that no two bodies are alike."""
    author = _AUTHORS[number % len(_AUTHORS)]
    year = 20 + number % 7
    tag = paragraph_xml(run_xml(f"{recipe_title}: synthetic claim number {number}"), style="Heading4")
    cite = paragraph_xml(
        run_xml(f"{author} {year}", character_style="Style13ptBold")
        + run_xml(f", Fellow, Synthetic Institute {number}, Synthetic Review of Policy, 20{year}")
    )
    body = paragraph_xml(
        run_xml(f"Synthetic evidence {number} begins in small print, ", half_points=16)
        + run_xml("then the part a debater reads", character_style="StyleUnderline", highlight="cyan")
        + run_xml(", then ", half_points=16)
        + run_xml("an emphasised warrant", character_style="Emphasis", bold=True, highlight="green")
        + run_xml(" and ", half_points=16)
        + run_xml("a directly underlined stretch", underline="single", highlight="yellow", half_points=22)
        + run_xml(f" before it closes on item {number}.", half_points=16)
    )
    tracked = (
        '<w:p><w:commentRangeStart w:id="1"/>'
        '<w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">A tracked insertion </w:t></w:r>'
        f'<w:ins w:id="2" {_AUTHOR_ATTRIBUTES}><w:r><w:rPr><w:rStyle w:val="StyleUnderline"/>'
        '<w:highlight w:val="cyan"/></w:rPr><w:t>is kept</w:t></w:r></w:ins>'
        f'<w:del w:id="3" {_AUTHOR_ATTRIBUTES}><w:r><w:delText xml:space="preserve"> and dropped</w:delText>'
        "</w:r></w:del>"
        '<w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve"> as the parser reads it.</w:t></w:r>'
        '<w:commentRangeEnd w:id="1"/>'
        '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="1"/></w:r></w:p>'
    )
    return build_docx(tag + cite + body + tracked)


def _card_refs(document: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for pocket in document["structure"]:
        blocks = [block for hat in pocket.get("hats") or () for block in hat["blocks"]]
        blocks += list(pocket.get("blocks") or ())
        refs.extend(item for block in blocks for item in block["items"] if "fingerprint" in item)
    return refs


async def build_example(path: Path, parser: DebateDocxParser) -> tuple[FileRecipe, BuiltEvidenceFile]:
    """One of t01's example recipes, built from synthetic sources."""
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    world = FileBuilderWorld(parser=parser, caselist=document["caselist"], event=document["format"])
    side = Side(document["side"])
    cards: dict[str, SourceCard] = {}
    pinned: list[str] = []
    for number, ref in enumerate(_card_refs(document), start=1):
        pin = ref.get("pin")
        school, team = _TEAMS[number % len(_TEAMS)]
        disclosure = SyntheticDisclosure(
            school=pin.get("school", school) if pin else school,
            team_code=pin.get("team_code", team) if pin else team,
            side=Side(pin["side"]) if pin and "side" in pin else side,
            tournament=pin.get("tournament", "Riverbend Invitational") if pin else "Riverbend Invitational",
            round=pin.get("round", f"Round {number}") if pin else f"Round {number}",
            path=f"synthetic/{number}.docx",
        )
        (card,) = await world.add_source(synthetic_card(number, document["title"]), disclosure=disclosure)
        ref["fingerprint"] = card.fingerprint
        if pin:
            pin["source_sha256"] = card.occurrence.source_sha256
            pin["element_index"] = card.occurrence.first_element_index
            pinned.append(card.fingerprint)
        cards[card.fingerprint] = card
    recipe = FileRecipe.model_validate(document)
    resolved = world.resolve(recipe, cards, pinned=pinned)
    writer = DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser)
    result = await writer.build(FileBuildRequest(resolved, BUILT_AT))
    if not isinstance(result, BuiltEvidenceFile):
        raise SystemExit(f"{path.name} was refused: " + "; ".join(str(one) for one in result.refusals))
    return recipe, result


def _inside_a_git_tree(directory: Path) -> bool:
    return any((parent / ".git").exists() for parent in (directory, *directory.parents))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, required=True, help="a directory outside any git working tree")
    args = ap.parse_args(argv)
    output: Path = args.output.expanduser().resolve()
    if _inside_a_git_tree(output):
        print(
            f"refused: {output} is inside a git working tree; built files are never committed",
            file=sys.stderr,
        )
        return 2
    output.mkdir(parents=True, exist_ok=True)
    parser = DebateDocxParser()
    for path in sorted(RECIPES.glob("*.yaml")):
        recipe, built = asyncio.run(build_example(path, parser))
        name = f"{path.stem}.docx"
        (output / name).write_bytes(built.docx)
        (output / provenance_sidecar_name(name)).write_bytes(built.manifest_json)
        print(f"{recipe.format}: {output / name} ({len(built.manifest.cards)} cards)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
