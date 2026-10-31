"""One caselist's cassettes, listed and deleted alone (`v1-e32-t31`).

The cassettes are recorded by the record-and-replay router over
:class:`~debate_core.testing.fakes.model_router.ScriptedModelRouter`, so they are the files a run writes;
no model is called. Every caselist is a synthetic slug, every prompt variable and answer invented.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.cassette_filing import (
    CaselistCassettes,
    caselist_cassettes,
    delete_caselist_cassettes,
    filed_under,
)
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass
from debate_core.integrations.models.errors import FixtureFileError, MissingFixtureError
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.record_replay import CassetteDirectory, RecordReplayModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter

PURGED = "synthld21"
KEPT = "synthld26"
PROMPT_ID = "example.sort-card"
SOLE = "a card only the purged caselist holds"
SHARED = "a card both caselists hold"
UNATTRIBUTED = "a card recorded before cassettes named caselists"
OTHER = "a card only the kept caselist holds"


class Sorted(BaseModel):
    position: str


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def prompt(card: str) -> ModelPrompt:
    return ModelPrompt(prompt_id=PROMPT_ID, prompt_version="1.0.0", variables={"items": card})


async def record(cassettes: Path, card: str, caselist: str | None) -> None:
    real = ScriptedModelRouter(model_id="recorded-model")
    real.enqueue({"position": "states-cp"})
    router = RecordReplayModelRouter(real, mode=ModelMode.RECORD, cassette_dir=cassettes, environ={})
    if caselist is None:
        await router.generate_structured(TaskClass.HIGH_VOLUME, prompt(card), Sorted)
        return
    with filed_under(caselist):
        await router.generate_structured(TaskClass.HIGH_VOLUME, prompt(card), Sorted)


async def replay(cassettes: Path, card: str, caselist: str) -> str:
    router = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=cassettes)
    with filed_under(caselist):
        response = await router.generate_structured(TaskClass.HIGH_VOLUME, prompt(card), Sorted)
    return response.output.position


def path_of(cassettes: Path, card: str) -> Path:
    return CassetteDirectory(cassettes).structured_path(
        ModelRequest.build(TaskClass.HIGH_VOLUME, prompt(card), Sorted)
    )


def name_of(cassettes: Path, card: str) -> str:
    return path_of(cassettes, card).relative_to(cassettes).as_posix()


def snapshot(cassettes: Path) -> dict[str, bytes]:
    return {path.relative_to(cassettes).as_posix(): path.read_bytes() for path in cassettes.rglob("*.json")}


@pytest.fixture
def cassettes(tmp_path: Path) -> Path:
    """Four cassettes: the purged caselist's alone, both caselists', no caselist's, the kept one's alone."""

    async def build() -> None:
        await record(tmp_path, SOLE, PURGED)
        await record(tmp_path, SHARED, PURGED)
        assert await replay(tmp_path, SHARED, KEPT) == "states-cp"
        await record(tmp_path, UNATTRIBUTED, None)
        await record(tmp_path, OTHER, KEPT)

    run(build())
    return tmp_path


def test_a_caselists_cassettes_are_listed_by_what_its_delete_does_to_each(cassettes: Path) -> None:
    before = snapshot(cassettes)

    listed = caselist_cassettes(CassetteDirectory(cassettes), PURGED)

    assert listed == CaselistCassettes(
        caselist=PURGED,
        sole=(name_of(cassettes, SOLE),),
        shared=(name_of(cassettes, SHARED),),
        unattributed=(name_of(cassettes, UNATTRIBUTED),),
        others=1,
    )
    assert snapshot(cassettes) == before


def test_a_caselists_delete_removes_only_the_cassettes_it_alone_names(cassettes: Path) -> None:
    before = snapshot(cassettes)

    done = delete_caselist_cassettes(CassetteDirectory(cassettes), PURGED)

    assert done.sole == (name_of(cassettes, SOLE),)
    assert not path_of(cassettes, SOLE).exists()
    after = snapshot(cassettes)
    assert sorted(after) == sorted(name_of(cassettes, card) for card in (SHARED, UNATTRIBUTED, OTHER))
    for card in (UNATTRIBUTED, OTHER):
        assert after[name_of(cassettes, card)] == before[name_of(cassettes, card)]


def test_a_shared_cassette_loses_only_the_deleted_caselists_name(cassettes: Path) -> None:
    shared = path_of(cassettes, SHARED)
    before = json.loads(shared.read_text(encoding="utf-8"))

    delete_caselist_cassettes(CassetteDirectory(cassettes), PURGED)

    after = json.loads(shared.read_text(encoding="utf-8"))
    assert before["caselists"] == sorted([KEPT, PURGED])
    assert after == {**before, "caselists": [KEPT]}
    assert run(replay(cassettes, SHARED, KEPT)) == "states-cp"


def test_an_unattributed_cassette_is_reported_and_never_deleted_by_a_caselist(cassettes: Path) -> None:
    for caselist in (PURGED, KEPT):
        done = delete_caselist_cassettes(CassetteDirectory(cassettes), caselist)
        assert done.unattributed == (name_of(cassettes, UNATTRIBUTED),)

    assert path_of(cassettes, UNATTRIBUTED).exists()
    assert "caselists" not in json.loads(path_of(cassettes, UNATTRIBUTED).read_text(encoding="utf-8"))


def test_a_deleted_caselists_sole_cassette_no_longer_replays(cassettes: Path) -> None:
    delete_caselist_cassettes(CassetteDirectory(cassettes), PURGED)

    with pytest.raises(MissingFixtureError):
        run(replay(cassettes, SOLE, PURGED))


def test_a_second_delete_of_the_same_caselist_finds_nothing_of_it(cassettes: Path) -> None:
    delete_caselist_cassettes(CassetteDirectory(cassettes), PURGED)
    before = snapshot(cassettes)

    again = delete_caselist_cassettes(CassetteDirectory(cassettes), PURGED)

    assert (again.sole, again.shared, again.others) == ((), (), 2)
    assert snapshot(cassettes) == before


def test_an_unreadable_cassette_stops_the_delete_before_anything_changes(cassettes: Path) -> None:
    (cassettes / PROMPT_ID / f"{'0' * 64}.json").write_text("not json", encoding="utf-8")
    before = snapshot(cassettes)

    with pytest.raises(FixtureFileError):
        delete_caselist_cassettes(CassetteDirectory(cassettes), PURGED)
    assert snapshot(cassettes) == before


def test_a_directory_with_no_cassettes_lists_nothing(tmp_path: Path) -> None:
    listed = caselist_cassettes(CassetteDirectory(tmp_path / "none-here"), PURGED)

    assert listed == CaselistCassettes(caselist=PURGED, sole=(), shared=(), unattributed=(), others=0)


@pytest.mark.parametrize("value", ["../synthld21", "synthld21/x", "Maple Grove", ""])
def test_a_cassette_delete_takes_a_caselist_slug_and_nothing_else(cassettes: Path, value: str) -> None:
    before = snapshot(cassettes)

    with pytest.raises(ValueError, match="caselist"):
        delete_caselist_cassettes(CassetteDirectory(cassettes), value)
    assert snapshot(cassettes) == before


@pytest.mark.parametrize(
    "name", ["../outside.json", "example.sort-card/../../outside.json", "a/b/c.json", "x.json"]
)
def test_a_cassette_directory_deletes_and_withdraws_only_its_own_cassettes(
    cassettes: Path, name: str
) -> None:
    directory = CassetteDirectory(cassettes)

    with pytest.raises(ValueError, match="cassette"):
        directory.delete(name)
    with pytest.raises(ValueError, match="cassette"):
        directory.withdraw(name, PURGED)


def test_a_cassette_never_loses_its_last_caselist_to_a_withdrawal(cassettes: Path) -> None:
    """Taking the only name off would leave a cassette no caselist's delete reaches: it is deleted instead."""
    before = snapshot(cassettes)

    with pytest.raises(ValueError, match="delete it instead"):
        CassetteDirectory(cassettes).withdraw(name_of(cassettes, SOLE), PURGED)
    assert snapshot(cassettes) == before
