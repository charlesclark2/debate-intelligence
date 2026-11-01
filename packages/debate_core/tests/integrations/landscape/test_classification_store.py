"""The classification cache and review queue files (`v1-e32-t02-position-classification`).

`<data_dir>/landscape/classifications/<caselist>.jsonl` holds one cached result per line, sorted, so
the same entries always write the same bytes; a line that is not a cached result is an error naming
its line, never a silent miss. The review queue's CSV goes beside it, under `landscape/review/`.

Every digest, position and heading here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.ports.classification_store import CachedClassification, ClassificationStore
from debate_core.arguments.landscape.review_queue import ReviewRow
from debate_core.domain.landscape_classification import ClassificationResult
from debate_core.integrations.landscape.classification_store import (
    LocalClassificationStore,
    LocalQueueOrderModelStore,
    queue_order_model_path,
    review_queue_path,
)


def entry(fingerprint: str, position_id: str | None = "spending-da") -> CachedClassification:
    placed = position_id is not None
    return CachedClassification(
        topic_id="policy-sample-topic",
        taxonomy_version="1.0.0",
        override_digest="none",
        prompt_version="none",
        item_fingerprint=fingerprint * 64,
        result=ClassificationResult.model_validate(
            {
                "position_id": position_id,
                "role": "READS" if placed else None,
                "confidence": 1.0 if placed else 0.0,
                "rationale": "an invented rule for the test",
                "method": "ALIAS" if placed else None,
                "taxonomy_version": "1.0.0",
            }
        ),
    )


def test_it_is_a_classification_store(tmp_path: Path) -> None:
    assert isinstance(LocalClassificationStore(tmp_path), ClassificationStore)


@pytest.mark.anyio
async def test_a_caselist_never_written_has_no_entries(tmp_path: Path) -> None:
    assert await LocalClassificationStore(tmp_path).read("hspolicy99") == ()


@pytest.mark.anyio
async def test_entries_round_trip_and_write_the_same_bytes_in_any_order(tmp_path: Path) -> None:
    one, two = LocalClassificationStore(tmp_path / "one"), LocalClassificationStore(tmp_path / "two")
    entries = [entry("a"), entry("b", None), entry("c", "states-cp")]
    await one.replace("hspolicy99", entries)
    await two.replace("hspolicy99", list(reversed(entries)))
    path = Path("landscape") / "classifications" / "hspolicy99.jsonl"
    assert (tmp_path / "one" / path).read_bytes() == (tmp_path / "two" / path).read_bytes()
    assert sorted(await one.read("hspolicy99"), key=lambda found: found.item_fingerprint) == entries
    assert await one.read("hspolicy98") == ()


@pytest.mark.anyio
async def test_replace_makes_the_entries_the_whole_cache(tmp_path: Path) -> None:
    store = LocalClassificationStore(tmp_path)
    await store.replace("hspolicy99", [entry("a"), entry("b")])
    await store.replace("hspolicy99", [entry("c")])
    assert await store.read("hspolicy99") == (entry("c"),)


@pytest.mark.anyio
async def test_a_line_that_is_not_a_cached_result_names_its_line(tmp_path: Path) -> None:
    store = LocalClassificationStore(tmp_path)
    await store.replace("hspolicy99", [entry("a")])
    path = tmp_path / "landscape" / "classifications" / "hspolicy99.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"topic_id": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        await store.read("hspolicy99")


def test_a_cached_result_is_kept_under_its_own_versions() -> None:
    found = entry("a")
    with pytest.raises(ValueError, match="taxonomy version"):
        CachedClassification.model_validate({**found.model_dump(), "taxonomy_version": "1.1.0"})
    with pytest.raises(ValueError, match="prompt version"):
        CachedClassification.model_validate({**found.model_dump(), "prompt_version": "1.0.0"})


@pytest.mark.anyio
async def test_the_review_queue_is_written_under_the_data_directory(tmp_path: Path) -> None:
    row = ReviewRow("fed key", False, 2, 2, 1, 1, 3, ("states-cp", "spending-da"))
    location = await LocalClassificationStore(tmp_path).write_review_queue(
        "hspolicy99", "policy-sample-topic", [row]
    )
    assert location == str(review_queue_path(tmp_path, "hspolicy99", "policy-sample-topic"))
    assert Path(location).is_relative_to(tmp_path / "landscape" / "review")
    assert Path(location).read_text(encoding="utf-8").splitlines() == [
        "normalized_heading,answer,documents,teams,aff_teams,neg_teams,cards,candidate_positions,decision",
        "fed key,false,2,2,1,1,3,states-cp;spending-da,",
    ]


@pytest.mark.anyio
async def test_a_queue_the_proxy_ordered_has_its_suggestion_column_before_the_decision(
    tmp_path: Path,
) -> None:
    """`v1-e32-t26`: the suggestion is its own column, blank below the threshold; `decision` stays empty."""
    rows = [
        ReviewRow(
            "debt group", False, 2, 2, 0, 2, 2, (), proxy_confidence=0.8, suggested_position="spending-da"
        ),
        ReviewRow("fed key", False, 6, 6, 0, 6, 6, ("states-cp",), proxy_confidence=0.3),
    ]
    location = await LocalClassificationStore(tmp_path).write_review_queue(
        "hspolicy99", "policy-sample-topic", rows, suggestions=True
    )
    assert Path(location).read_text(encoding="utf-8").splitlines() == [
        "normalized_heading,answer,documents,teams,aff_teams,neg_teams,cards,candidate_positions,"
        "suggested_position,decision",
        "debt group,false,2,2,0,2,2,,spending-da,",
        "fed key,false,6,6,0,6,6,states-cp,,",
    ]


@pytest.mark.anyio
async def test_the_review_order_model_is_kept_beside_t21s_feature_table(tmp_path: Path) -> None:
    store = LocalQueueOrderModelStore(tmp_path)
    assert await store.read("hspolicy99", "policy-sample-topic") is None
    location = await store.write("hspolicy99", "policy-sample-topic", "{}\n")
    assert location == store.location("hspolicy99", "policy-sample-topic")
    assert Path(location) == queue_order_model_path(tmp_path, "hspolicy99", "policy-sample-topic")
    assert Path(location).parent == tmp_path / "landscape" / "local-classifier" / "hspolicy99"
    assert await store.read("hspolicy99", "policy-sample-topic") == "{}\n"
