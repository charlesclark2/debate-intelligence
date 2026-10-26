"""A file built from a draft recipe says DRAFT in its header analytic (`v1-e33-t03` ac2).

`files suggest` writes recipes with `status: draft`, and `files build --allow-draft` builds one. The
header analytic is the first paragraph a reader sees, so it is where the file says it was built from
a recipe the coach has not marked ready. A ready recipe's header is unchanged, word for word.

The sidecar records the recipe's status too (`v1-e33-t05`, PM amendment 2026-10-24), which is what
`files publish` reads to refuse a file built from a draft.

Every source is synthetic, built in memory with `debate_core.testing.docx_builder`.
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Final

import pytest
from lxml import etree

from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile, FileBuildRequest
from debate_core.domain.file_recipe import FileRecipe, RecipeStatus
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.package import W_NAMESPACE
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import FileBuilderWorld

PARSER: Final = DebateDocxParser()
BUILT_AT: Final = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
W: Final = f"{{{W_NAMESPACE}}}"

SOURCE: Final = build_docx(
    paragraph_xml(run_xml("Moratoria raise prices for every ratepayer"), style="Heading4")
    + paragraph_xml(
        run_xml("Lindqvist 26", character_style="Style13ptBold")
        + run_xml(", Senior Fellow, Synthetic Energy Review, 2026")
    )
    + paragraph_xml(
        run_xml("A moratorium ", half_points=16)
        + run_xml("freezes supply", character_style="StyleUnderline", highlight="cyan")
        + run_xml(" while demand rises.", half_points=16)
    )
)

READY_HEADER: Final = (
    "Disclosed cards (FILE_IMPORT) from hspolicy26, each copied from the file that disclosed it and not "
    "verified by this platform."
)


def built_with(status: RecipeStatus) -> BuiltEvidenceFile:
    """The file the writer builds from a one-card recipe of `status`."""
    world = FileBuilderWorld(parser=PARSER)
    (card,) = asyncio.run(world.add_source(SOURCE))
    recipe = world.recipe([("Prices", [{"fingerprint": card.fingerprint}])])
    recipe = FileRecipe.model_validate({**recipe.model_dump(mode="json"), "status": str(status)})
    writer = DocxEvidenceFileWriter(snapshots=world.snapshots, parser=PARSER)
    built = asyncio.run(
        writer.build(FileBuildRequest(world.resolve(recipe, {card.fingerprint: card}), BUILT_AT))
    )
    assert isinstance(built, BuiltEvidenceFile), built
    return built


def header_of(status: RecipeStatus) -> tuple[str | None, str]:
    """The built file's first paragraph, its style and text, for the recipe built with `status`."""
    built = built_with(status)
    with zipfile.ZipFile(BytesIO(built.docx)) as package:
        body = etree.fromstring(package.read("word/document.xml")).find(f"{W}body")
    assert body is not None
    first = body.find(f"{W}p")
    assert first is not None
    style = first.find(f"{W}pPr/{W}pStyle")
    text = "".join(str(part) for part in first.itertext())
    return (style.get(f"{W}val") if style is not None else None, text)


def test_a_draft_recipes_header_analytic_says_draft() -> None:
    style, text = header_of(RecipeStatus.DRAFT)
    assert style == "Analytic"
    assert text == f"DRAFT: built from a recipe the coach has not marked ready. {READY_HEADER}"


def test_a_ready_recipes_header_analytic_is_unchanged() -> None:
    assert header_of(RecipeStatus.READY) == ("Analytic", READY_HEADER)


@pytest.mark.parametrize("status", list(RecipeStatus))
def test_the_sidecar_records_the_recipes_status(status: RecipeStatus) -> None:
    built = built_with(status)
    assert built.manifest.recipe_status is status
    assert json.loads(built.manifest_json)["recipe_status"] == str(status)
