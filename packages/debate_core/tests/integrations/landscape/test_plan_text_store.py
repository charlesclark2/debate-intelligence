"""The plan-text cache file (`v1-e32-t09-policy-plan-texts`).

`<data_dir>/landscape/plan_texts/<caselist>.jsonl` holds one source's reading per line, sorted, so the
same readings always write the same bytes; a line that is not a reading is an error naming its line.
A reading holds digests, indexes and ids, never a paragraph's text. Every digest here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from debate_core.application.ports.plan_text_store import (
    CachedKritikalMarker,
    CachedPlanText,
    CachedPlanTextParagraph,
    PlanTextKey,
    PlanTextStore,
)
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.landscape.plan_text_store import LocalPlanTextStore


def reading(digit: str, *, readable: bool = True) -> CachedPlanText:
    return CachedPlanText(
        source_sha256=digit * 64,
        parser_version="2026.10.20-docx-6",
        vocabulary_digest="f" * 64,
        readable=readable,
        paragraphs=(
            CachedPlanTextParagraph(
                label_element_index=4,
                element_index=5,
                unit=StructuralUnit.ANALYTIC,
                kept=False,
                shaped=True,
                digest="e" * 64,
                named=("sample-plan-aff",),
            ),
        )
        if readable
        else (),
    )


def test_it_is_a_plan_text_store(tmp_path: Path) -> None:
    assert isinstance(LocalPlanTextStore(tmp_path), PlanTextStore)


@pytest.mark.anyio
async def test_a_caselist_never_written_has_no_readings(tmp_path: Path) -> None:
    assert await LocalPlanTextStore(tmp_path).read("sample") == ()


@pytest.mark.anyio
async def test_readings_round_trip_and_write_the_same_bytes_in_any_order(tmp_path: Path) -> None:
    store = LocalPlanTextStore(tmp_path)
    path = tmp_path / "landscape" / "plan_texts" / "sample.jsonl"
    await store.replace("sample", [reading("b"), reading("a", readable=False)])
    first = path.read_bytes()
    await store.replace("sample", [reading("a", readable=False), reading("b")])
    assert path.read_bytes() == first
    assert sorted(await store.read("sample"), key=lambda one: one.source_sha256) == [
        reading("a", readable=False),
        reading("b"),
    ]


@pytest.mark.anyio
async def test_replace_makes_the_readings_the_whole_cache(tmp_path: Path) -> None:
    store = LocalPlanTextStore(tmp_path)
    await store.replace("sample", [reading("a"), reading("b")])
    await store.replace("sample", [reading("c")])
    assert await store.read("sample") == (reading("c"),)
    assert await store.read("other") == ()


@pytest.mark.anyio
async def test_a_line_that_is_not_a_reading_names_its_line(tmp_path: Path) -> None:
    store = LocalPlanTextStore(tmp_path)
    await store.replace("sample", [reading("a")])
    path = tmp_path / "landscape" / "plan_texts" / "sample.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"source_sha256": "nope"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        await store.read("sample")


def test_a_reading_is_keyed_by_source_parser_and_vocabulary() -> None:
    assert reading("a").key == PlanTextKey("a" * 64, "2026.10.20-docx-6", "f" * 64)


def test_a_reading_has_no_field_for_text() -> None:
    assert set(CachedPlanText.model_fields) == {
        "source_sha256",
        "parser_version",
        "vocabulary_digest",
        "readable",
        "paragraphs",
        "kritikal_markers",
        "heading_families",
        "transition_paragraphs",
    }
    assert set(CachedKritikalMarker.model_fields) == {"kind", "form", "element_index", "unit"}
    assert set(CachedPlanTextParagraph.model_fields) == {
        "label_element_index",
        "element_index",
        "unit",
        "kept",
        "shaped",
        "digest",
        "named",
    }
    with pytest.raises(ValidationError):
        CachedPlanText.model_validate({**reading("a").model_dump(), "text": "an invented plan"})
