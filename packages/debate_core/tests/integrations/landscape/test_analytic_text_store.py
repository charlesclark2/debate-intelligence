"""The analytic-text cache file (`v1-e32-t11-negative-analytic-texts`).

`<data_dir>/landscape/analytic_texts/<caselist>.jsonl`, beside `v1-e32-t09`'s plan-text cache, holds one
source's reading per line, sorted, so the same readings always write the same bytes; a line that is not
a reading is an error naming its line. A reading holds digests, indexes and ids, never a paragraph's
text (the PM's ruling of 2026-10-24). Every digest here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from debate_core.application.ports.analytic_text_store import (
    AnalyticTextKey,
    AnalyticTextStore,
    CachedAnalyticTexts,
)
from debate_core.domain.landscape_classification import PositionRole
from debate_core.domain.landscape_texts import AnalyticTextKind, AnalyticTextReading, TextForm, TextPlacement
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.landscape.analytic_text_store import LocalAnalyticTextStore

PATH = Path("landscape") / "analytic_texts" / "sample.jsonl"


def reading(digit: str, *, readable: bool = True) -> CachedAnalyticTexts:
    return CachedAnalyticTexts(
        source_sha256=digit * 64,
        parser_version="2026.10.20-docx-6",
        rules_digest="f" * 64,
        readable=readable,
        readings=(
            AnalyticTextReading(
                kind=AnalyticTextKind.CP_TEXT,
                form=TextForm.BY_PLACE,
                label_element_index=5,
                element_index=5,
                unit=StructuralUnit.ANALYTIC,
                kept=False,
                digest="e" * 64,
                placement=TextPlacement.PLACED,
                position_id="states-cp",
                role=PositionRole.READS,
            ),
            AnalyticTextReading(
                kind=AnalyticTextKind.OVERVIEW,
                form=TextForm.LABEL,
                label_element_index=9,
                element_index=9,
                unit=StructuralUnit.BLOCK,
                kept=False,
                placement=TextPlacement.NO_HEADING,
            ),
        )
        if readable
        else (),
        refused_by_guard=1 if readable else 0,
    )


def test_it_is_an_analytic_text_store(tmp_path: Path) -> None:
    assert isinstance(LocalAnalyticTextStore(tmp_path), AnalyticTextStore)


@pytest.mark.anyio
async def test_a_caselist_never_written_has_no_readings(tmp_path: Path) -> None:
    assert await LocalAnalyticTextStore(tmp_path).read("sample") == ()


@pytest.mark.anyio
async def test_readings_round_trip_and_write_the_same_bytes_in_any_order(tmp_path: Path) -> None:
    store = LocalAnalyticTextStore(tmp_path)
    await store.replace("sample", [reading("b"), reading("a", readable=False)])
    first = (tmp_path / PATH).read_bytes()
    await store.replace("sample", [reading("a", readable=False), reading("b")])
    assert (tmp_path / PATH).read_bytes() == first
    assert sorted(await store.read("sample"), key=lambda one: one.source_sha256) == [
        reading("a", readable=False),
        reading("b"),
    ]


@pytest.mark.anyio
async def test_replace_makes_the_readings_the_whole_cache(tmp_path: Path) -> None:
    store = LocalAnalyticTextStore(tmp_path)
    await store.replace("sample", [reading("a"), reading("b")])
    await store.replace("sample", [reading("c")])
    assert await store.read("sample") == (reading("c"),)
    assert await store.read("other") == ()


@pytest.mark.anyio
async def test_a_line_that_is_not_a_reading_names_its_line(tmp_path: Path) -> None:
    store = LocalAnalyticTextStore(tmp_path)
    await store.replace("sample", [reading("a")])
    path = tmp_path / PATH
    path.write_text(path.read_text(encoding="utf-8") + '{"source_sha256": "nope"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        await store.read("sample")


def test_a_reading_is_keyed_by_source_parser_and_rules() -> None:
    assert reading("a").key == AnalyticTextKey("a" * 64, "2026.10.20-docx-6", "f" * 64)


def test_a_reading_has_no_field_for_text() -> None:
    assert set(CachedAnalyticTexts.model_fields) == {
        "source_sha256",
        "parser_version",
        "rules_digest",
        "readable",
        "readings",
        "refused_by_guard",
        "planks_refused_by_guard",
        "plank_labels",
    }
    # A plank (v1-e32-t16) adds its CP text's paragraph, the advantages' ids and a count, and a CP text shown
    # whole (v1-e32-t35) the paragraphs of its lines: never words.
    assert set(AnalyticTextReading.model_fields) == {
        "kind",
        "form",
        "label_element_index",
        "element_index",
        "unit",
        "kept",
        "digest",
        "placement",
        "position_id",
        "role",
        "stem_element_index",
        "solves",
        "solves_other_words",
        "lines",
    }
    with pytest.raises(ValidationError):
        CachedAnalyticTexts.model_validate({**reading("a").model_dump(), "text": "an invented counterplan"})
