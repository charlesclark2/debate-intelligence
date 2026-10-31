"""Cassettes name the caselists they answered, outside the replay match (`v1-e32-t31`).

The real router is :class:`~debate_core.testing.fakes.model_router.ScriptedModelRouter`: no model is
called. Every caselist here is a synthetic slug, and every prompt, variable and answer is invented.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.cassette_filing import filed_under
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, TaskClass
from debate_core.integrations.models.errors import FixtureFileError, MissingFixtureError
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.record_replay import CASSETTE_FORMAT, RecordReplayModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter

FIRST = "synthld26"
SECOND = "synthpolicy26"
PROMPT = ModelPrompt(
    prompt_id="example.sort-card", prompt_version="1.0.0", variables={"items": "an invented card excerpt"}
)


class Sorted(BaseModel):
    position: str


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def recording(cassettes: Path, *answers: str) -> RecordReplayModelRouter:
    real = ScriptedModelRouter(model_id="recorded-model")
    for answer in answers:
        real.enqueue({"position": answer})
    return RecordReplayModelRouter(real, mode=ModelMode.RECORD, cassette_dir=cassettes, environ={})


def replaying(cassettes: Path) -> RecordReplayModelRouter:
    return RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=cassettes)


async def ask(router: RecordReplayModelRouter, params: ModelParams | None = None) -> str:
    response = await router.generate_structured(TaskClass.HIGH_VOLUME, PROMPT, Sorted, params)
    return response.output.position


def only_cassette(cassettes: Path) -> Path:
    [path] = sorted(cassettes.glob("*/*.json"))
    return path


def document(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def without_caselists(recorded: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in recorded.items() if key != "caselists"}


async def record_under(cassettes: Path, caselist: str | None, answer: str = "states-cp") -> None:
    router = recording(cassettes, answer)
    if caselist is None:
        await ask(router)
        return
    with filed_under(caselist):
        await ask(router)


def test_a_new_cassette_names_the_caselist_it_was_recorded_for(tmp_path: Path) -> None:
    run(record_under(tmp_path, FIRST))

    assert document(only_cassette(tmp_path))["caselists"] == [FIRST]


def test_a_cassette_recorded_for_no_caselist_names_none(tmp_path: Path) -> None:
    """A recording outside a landscape run (a committed test cassette) is written as before."""
    run(record_under(tmp_path, None))

    assert "caselists" not in document(only_cassette(tmp_path))


def test_a_new_cassette_is_the_format_one_shape_plus_its_caselists(tmp_path: Path) -> None:
    """What an older build reads (format, call, key, request, response) is what it always was."""
    filed = tmp_path / "filed"
    unfiled = tmp_path / "unfiled"
    run(record_under(filed, FIRST))
    run(record_under(unfiled, None))
    named = document(only_cassette(filed))

    assert CASSETTE_FORMAT == 1
    assert sorted(named) == ["call", "caselists", "cassette_format", "key", "request", "response"]
    assert only_cassette(filed).relative_to(filed) == only_cassette(unfiled).relative_to(unfiled)
    assert without_caselists(named) == document(only_cassette(unfiled))


def test_a_replay_for_a_second_caselist_adds_it_and_changes_no_recorded_value(tmp_path: Path) -> None:
    run(record_under(tmp_path, FIRST))
    before = document(only_cassette(tmp_path))

    async def replay() -> str:
        with filed_under(SECOND):
            return await ask(replaying(tmp_path))

    assert run(replay()) == "states-cp"
    after = document(only_cassette(tmp_path))
    assert after["caselists"] == sorted([FIRST, SECOND])
    assert without_caselists(after) == without_caselists(before)


def test_a_replay_for_a_caselist_the_cassette_names_writes_nothing(tmp_path: Path) -> None:
    run(record_under(tmp_path, FIRST))
    path = only_cassette(tmp_path)
    before = (path.read_bytes(), path.stat().st_mtime_ns)

    async def replay() -> str:
        with filed_under(FIRST):
            return await ask(replaying(tmp_path))

    assert run(replay()) == "states-cp"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_a_replay_for_no_caselist_writes_nothing(tmp_path: Path) -> None:
    run(record_under(tmp_path, FIRST))
    path = only_cassette(tmp_path)
    before = path.read_bytes()

    assert run(ask(replaying(tmp_path))) == "states-cp"
    assert path.read_bytes() == before


def test_the_same_call_for_a_second_caselist_is_the_same_cassette(tmp_path: Path) -> None:
    """Recording again for another caselist keeps the first one's name: both hold this card."""
    run(record_under(tmp_path, FIRST))
    run(record_under(tmp_path, SECOND, answer="spending-da"))

    recorded = document(only_cassette(tmp_path))
    assert recorded["caselists"] == sorted([FIRST, SECOND])
    assert recorded["response"]["output"] == {"position": "spending-da"}


def test_a_cassette_recorded_before_caselists_still_replays(tmp_path: Path) -> None:
    """An older cassette, with no `caselists`, replays unchanged, and gains the caselist that replays it."""
    run(record_under(tmp_path, None))
    path = only_cassette(tmp_path)
    old = document(path)

    assert run(ask(replaying(tmp_path))) == "states-cp"
    assert document(path) == old

    async def replay() -> str:
        with filed_under(FIRST):
            return await ask(replaying(tmp_path))

    assert run(replay()) == "states-cp"
    assert document(path) == {**old, "caselists": [FIRST]}


def test_a_call_whose_recorded_values_differ_misses_under_any_caselist(tmp_path: Path) -> None:
    """The caselist adds no near miss: a call with other parameters is still unrecorded, and nothing is written."""
    run(record_under(tmp_path, FIRST))
    path = only_cassette(tmp_path)
    before = path.read_bytes()

    async def replay() -> str:
        with filed_under(FIRST):
            return await ask(replaying(tmp_path), ModelParams(temperature=0.9))

    with pytest.raises(MissingFixtureError):
        run(replay())
    assert path.read_bytes() == before


def test_a_cassette_whose_caselists_are_not_slugs_is_a_fixture_file_error(tmp_path: Path) -> None:
    run(record_under(tmp_path, FIRST))
    path = only_cassette(tmp_path)
    path.write_text(json.dumps({**document(path), "caselists": ["../elsewhere"]}), encoding="utf-8")

    with pytest.raises(FixtureFileError, match="caselists"):
        run(ask(replaying(tmp_path)))


@pytest.mark.parametrize("value", ["../hsld26", "Maple Grove", "hsld26/x", "", "HSLD26"])
def test_a_cassette_is_filed_under_a_caselist_slug_and_nothing_else(value: str) -> None:
    with pytest.raises(ValueError, match="caselist"), filed_under(value):
        pass


def test_embedding_and_rerank_cassettes_name_their_caselist_too(tmp_path: Path) -> None:
    real = ScriptedModelRouter(model_id="recorded-model")
    real.enqueue([[0.1, 0.2]])
    real.enqueue([0.5, 0.25])
    router = RecordReplayModelRouter(real, mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={})

    async def record() -> None:
        with filed_under(FIRST):
            await router.embed(["an invented text"])
            await router.rerank("an invented query", ["one document", "another"])

    run(record())

    assert [document(path)["caselists"] for path in sorted(tmp_path.glob("*/*.json"))] == [[FIRST], [FIRST]]
