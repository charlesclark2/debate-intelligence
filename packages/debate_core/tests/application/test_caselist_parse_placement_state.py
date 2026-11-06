"""When the rebuild places from the placement state, and when it rebuilds in full (`v1-e31-t10`).

The PM's ruling of 2026-11-06, item 2: the rebuild uses the state only when it is readable, its
versions are the directory's, and its sources are exactly the ones placed less the ones the run
added. Anything else is a full rebuild, which writes a new state. Each condition is a test here, and
in every one the index, failures file and occurrence table are compared, byte for byte, with what the
rebuild as the task found it writes for the same store (:mod:`.rebuild_at_start`, the oracle).

Which way a run placed its cards is read from two things: the documents its rebuild read
(:class:`~.placement_world.CountingStore`) and its log line, which names the reason for a full
rebuild. Every word, path, school and team here is invented.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import sqlite3
import tempfile
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Final

import pytest

import debate_core.evidence.near_duplicates as near_duplicates
from debate_core.application.caselist_parse import FullRebuildReason
from debate_core.application.ports.parsed_store import PLACEMENT_STATE_NAME
from debate_core.application.ports.placement_state import PlacementState, UnreadablePlacementState
from debate_core.domain.debate_files import CardCompleteness
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, fingerprint_text

from .placement_world import (
    CASELIST,
    PARSER_VERSION,
    PROFILE_VERSION,
    SCHOOL,
    TAG,
    Card,
    PlacementWorld,
    passage,
    rebuild_lines,
)

X: Final = passage(1, 100)


def changed(words: list[str], replacements: dict[int, str]) -> str:
    """`words` with the word at each position replaced by an invented word outside the vocabulary."""
    return " ".join(replacements.get(position, word) for position, word in enumerate(words))


#: Three words apart from X: a copy of neither (Jaccard 81/111 = 0.73, worked by hand: 96 shingles
#: each, 15 of them changed), and not inside it (81/96 = 0.84 of its shingles, under 0.9).
Y: Final = changed(X, {20: "gallimaufry", 50: "hobbledehoy", 80: "snickersnee"})
#: Two words apart from X (Jaccard 86/106 = 0.81) and one from Y (91/101 = 0.90): a copy of each.
Z: Final = changed(X, {50: "hobbledehoy", 80: "snickersnee"})
#: A cut of X, thirty words that Y holds but for its first change: both are its containers.
CUT: Final = " ".join(X[10:40])


def abbreviated(words: list[str], element: int, short_cite: str = "Quillon 26") -> Card:
    return Card(
        element, f"{' '.join(words[:6])} … {' '.join(words[-6:])}", CardCompleteness.ABBREVIATED, short_cite
    )


def week_one(world: PlacementWorld) -> None:
    other = passage(2, 90)
    world.add(
        "first",
        (Card(0, " ".join(X)), Card(3, CUT), abbreviated(X, 6)),
        week=0,
        again=1,
    )
    world.add(
        "second",
        (Card(0, Y), Card(3, " ".join(other)), Card(6, "", CardCompleteness.CITE_ONLY, "Marrow 25")),
        week=0,
    )
    world.add(
        "third",
        (Card(0, " ".join(other)), Card(3, " ".join(passage(3, 40))), abbreviated(other, 6, "Tamber 24")),
        week=0,
    )


def in_a_world(
    test: Callable[[PlacementWorld], Coroutine[object, object, None]], *, incremental: bool = True
) -> None:
    with tempfile.TemporaryDirectory(prefix="placement-") as scratch:
        asyncio.run(test(PlacementWorld(Path(scratch), incremental=incremental)))


async def placed_digests(world: PlacementWorld) -> set[str]:
    stored = await world.store.read_placement_state(CASELIST, PARSER_VERSION)
    assert stored is not None
    return set(stored.sources)


def test_the_first_rebuild_writes_a_state_of_the_sources_it_placed(caplog: pytest.LogCaptureFixture) -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        caplog.set_level(logging.INFO)
        await world.run()

        assert world.written() == await world.at_start()
        stored = await world.store.read_placement_state(CASELIST, PARSER_VERSION)
        assert stored is not None
        assert (stored.parser_version, stored.profile_version, stored.fingerprint_version) == (
            PARSER_VERSION,
            PROFILE_VERSION,
            FINGERPRINT_VERSION,
        )
        assert set(stored.sources) == set(world.names.values())
        # Full bodies by hand: X, its cut, Y, the other passage (in two sources), the third's 40 words.
        assert len(stored.bodies) == 5
        assert [len(cards) for _, cards in sorted(stored.sources.items())] == [3, 3, 3]
        assert rebuild_lines(caplog.records) == [
            f"caselist parse {CASELIST} {PARSER_VERSION}: rebuilt in full (NO_STATE), 3 placed sources read"
        ]

    in_a_world(test)


def test_a_week_is_placed_from_the_state_reading_only_its_new_documents(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        new = world.add("fourth", (Card(0, " ".join(passage(4, 70))), abbreviated(X, 3)), week=1)
        caplog.set_level(logging.INFO)

        await world.run()

        assert world.store.documents_read == [new]
        assert rebuild_lines(caplog.records) == [
            f"caselist parse {CASELIST} {PARSER_VERSION}: placed from the placement state, 1 of 4 placed "
            "sources read"
        ]
        assert world.written() == await world.at_start()
        assert await placed_digests(world) == set(world.names.values())

    in_a_world(test)


def test_a_rebuild_with_nothing_new_reads_no_document() -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        before = world.written()

        await world.run()

        assert world.store.documents_read == []
        assert world.written() == before == await world.at_start()

    in_a_world(test)


def test_a_week_that_merges_two_existing_clusters_is_placed_as_a_full_rebuild_places_it() -> None:
    """X and Y, three words apart, are two clusters, and the cut of X that both hold stays out of
    each, its witnesses being two clusters. Z, a copy of each, joins X and Y, and then the cut's
    witnesses are one cluster, so it joins too. Every row of the four takes the smallest of their
    fingerprints (worked by hand from the figures beside X, Y and Z)."""

    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        first, second = world.names["first"], world.names["second"]
        x, y, z, cut = (fingerprint_text(text) for text in (" ".join(X), Y, Z, CUT))

        def clusters() -> dict[tuple[str, int], str]:
            return {
                (row["source_sha256"], row["first_element_index"]): row["cluster_id"]
                for row in map(json.loads, world.written()["occurrences.jsonl"].decode().splitlines())
            }

        before = clusters()
        assert before[(first, 0)] == x
        assert before[(second, 0)] == y
        assert before[(first, 3)] == cut
        new = world.add("merging", (Card(0, Z),), week=2)

        await world.run()

        after = clusters()
        assert world.store.documents_read == [new]
        assert (
            after[(first, 0)]
            == after[(second, 0)]
            == after[(new, 0)]
            == after[(first, 3)]
            == min(x, y, z, cut)
        )
        assert world.written() == await world.at_start()

    in_a_world(test)


def test_a_week_a_removal_shrank_is_rebuilt_in_full_and_its_state_holds_none_of_the_removed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        removed = world.names["second"]
        await world.remove(removed)
        caplog.set_level(logging.INFO)

        await world.run()

        assert "rebuilt in full (NO_STATE)" in rebuild_lines(caplog.records)[0]
        assert sorted(world.store.documents_read) == sorted({world.names["first"], world.names["third"]})
        assert world.written() == await world.at_start()
        assert await placed_digests(world) == {world.names["first"], world.names["third"]}

    in_a_world(test)


async def _missing(world: PlacementWorld) -> None:
    world.state_path.unlink()


async def _unreadable(world: PlacementWorld) -> None:
    world.state_path.write_bytes(b"not a database of any kind")


def _replaced(**changes: object) -> Callable[[PlacementWorld], Awaitable[None]]:
    async def tamper(world: PlacementWorld) -> None:
        stored = await world.store.read_placement_state(CASELIST, PARSER_VERSION)
        assert stored is not None
        world.state_path.unlink()
        await world.store.write_placement_state(
            CASELIST, PARSER_VERSION, dataclasses.replace(stored, **changes)
        )

    return tamper


def _sources(
    change: Callable[[PlacementState, PlacementWorld], dict[str, object]],
) -> Callable[[PlacementWorld], Awaitable[None]]:
    async def tamper(world: PlacementWorld) -> None:
        stored = await world.store.read_placement_state(CASELIST, PARSER_VERSION)
        assert stored is not None
        world.state_path.unlink()
        sources = change(stored, world)
        await world.store.write_placement_state(
            CASELIST, PARSER_VERSION, dataclasses.replace(stored, sources=sources)
        )

    return tamper


async def _stopped_elsewhere(world: PlacementWorld) -> None:
    await world.stop(world.names["third"])


@pytest.mark.parametrize(
    ("condition", "tamper", "reason"),
    [
        ("missing", _missing, FullRebuildReason.NO_STATE),
        ("unreadable", _unreadable, FullRebuildReason.UNREADABLE),
        (
            "another parser version",
            _replaced(parser_version="2031.01.01-synthetic-0"),
            FullRebuildReason.VERSIONS_DIFFER,
        ),
        (
            "another profile version",
            _replaced(profile_version="synthetic-profile-0"),
            FullRebuildReason.VERSIONS_DIFFER,
        ),
        (
            "another fingerprint version",
            _replaced(fingerprint_version="card-fingerprint-v0"),
            FullRebuildReason.VERSIONS_DIFFER,
        ),
        ("other rules", _replaced(rules="0" * 64), FullRebuildReason.RULES_DIFFER),
        (
            "a digest the directory lacks",
            _sources(
                lambda stored, world: {**stored.sources, "f" * 64: stored.sources[world.names["first"]]}
            ),
            FullRebuildReason.SOURCES_DIFFER,
        ),
        (
            "a digest the directory holds beyond the state",
            _sources(
                lambda stored, world: {
                    sha: cards for sha, cards in stored.sources.items() if sha != world.names["third"]
                }
            ),
            FullRebuildReason.SOURCES_DIFFER,
        ),
        ("a source stopped elsewhere, the state left", _stopped_elsewhere, FullRebuildReason.SOURCES_DIFFER),
    ],
)
def test_anything_but_a_matching_readable_state_is_a_full_rebuild_that_writes_a_new_one(
    condition: str,
    tamper: Callable[[PlacementWorld], Awaitable[None]],
    reason: FullRebuildReason,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        await tamper(world)
        new = world.add("fourth", (Card(0, " ".join(passage(4, 70))),), week=1)
        caplog.set_level(logging.INFO)

        await world.run()

        placed = {
            sha
            for name, sha in world.names.items()
            if not (condition.startswith("a source stopped") and name == "third")
        }
        assert set(world.store.documents_read) == placed, condition
        assert len(world.store.documents_read) == len(placed), condition
        (line,) = rebuild_lines(caplog.records)
        assert f"rebuilt in full ({reason})" in line, condition
        assert world.written() == await world.at_start(), condition
        stored = await world.store.read_placement_state(CASELIST, PARSER_VERSION)
        assert stored is not None
        assert set(stored.sources) == placed and new in placed
        assert (stored.parser_version, stored.profile_version, stored.fingerprint_version) == (
            PARSER_VERSION,
            PROFILE_VERSION,
            FINGERPRINT_VERSION,
        )

    in_a_world(test)


def test_the_setting_off_rebuilds_in_full_and_still_writes_a_new_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        world.state_path.unlink()
        world.incremental = False
        world.add("fourth", (Card(0, " ".join(passage(4, 70))),), week=1)
        caplog.set_level(logging.INFO)

        await world.run()

        assert len(world.store.documents_read) == 4
        (line,) = rebuild_lines(caplog.records)
        assert "rebuilt in full (TURNED_OFF)" in line
        assert world.written() == await world.at_start()
        assert await placed_digests(world) == set(world.names.values())

        caplog.clear()
        await world.run()
        assert len(world.store.documents_read) == 4, "off, a state that matches is not used either"

    in_a_world(test, incremental=False)


def test_the_state_holds_no_path_school_team_tag_or_cite_beyond_its_short_cite() -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()

        held = world.state_path.read_bytes()
        for forbidden in (SCHOOL, "Team ", "round-", ".docx", TAG, "Invented Author", "Fictional Quarterly"):
            assert forbidden.encode() not in held, forbidden
        assert sorted(path.name for path in world.directory.iterdir() if path.is_file()) == sorted(
            ["index.jsonl", "failures.jsonl", "occurrences.jsonl", PLACEMENT_STATE_NAME]
        ), "a read or a write leaves no journal beside the state"

    in_a_world(test)


def _inconsistent(
    change: Callable[[PlacementState], PlacementState],
) -> Callable[[PlacementWorld], Awaitable[None]]:
    async def tamper(world: PlacementWorld) -> None:
        stored = await world.store.read_placement_state(CASELIST, PARSER_VERSION)
        assert stored is not None
        world.state_path.unlink()
        await world.store.write_placement_state(CASELIST, PARSER_VERSION, change(stored))

    return tamper


def _without_a_body(stored: PlacementState) -> PlacementState:
    gone = min(stored.bodies)
    return dataclasses.replace(
        stored, bodies={key: body for key, body in stored.bodies.items() if key != gone}
    )


def _a_word_outside_the_vocabulary(stored: PlacementState) -> PlacementState:
    return dataclasses.replace(stored, vocabulary=stored.vocabulary[:-1])


def _a_short_signature(stored: PlacementState) -> PlacementState:
    fingerprint, body = next((key, body) for key, body in sorted(stored.bodies.items()) if body.signature)
    assert body.signature is not None
    short = dataclasses.replace(body, signature=body.signature[:100])
    return dataclasses.replace(stored, bodies={**stored.bodies, fingerprint: short})


@pytest.mark.parametrize(
    "change",
    [_without_a_body, _a_word_outside_the_vocabulary, _a_short_signature],
    ids=lambda one: one.__name__,
)
def test_a_state_that_does_not_hold_together_is_unreadable_and_rebuilt_in_full(
    change: Callable[[PlacementState], PlacementState], caplog: pytest.LogCaptureFixture
) -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        await _inconsistent(change)(world)
        caplog.set_level(logging.INFO)

        await world.run()

        (line,) = rebuild_lines(caplog.records)
        assert "rebuilt in full (UNREADABLE)" in line
        assert len(world.store.documents_read) == 3
        assert world.written() == await world.at_start()

    in_a_world(test)


def test_a_state_of_another_layout_is_unreadable() -> None:
    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        with sqlite3.connect(world.state_path) as database:
            database.execute("UPDATE meta SET value = '2' WHERE name = 'schema_version'")
        database.close()

        with pytest.raises(UnreadablePlacementState):
            await world.store.read_placement_state(CASELIST, PARSER_VERSION)

    in_a_world(test)


def test_a_full_card_sharing_its_text_with_an_abbreviated_card_seen_first_is_placed_as_before() -> None:
    """A body written as first and last words around an ellipsis is a full card in one file and an
    abbreviated one in another: one fingerprint, the abbreviated card first. The full card's words are
    still taken, from the state as from the document."""
    text = f"{' '.join(X[:6])} … {' '.join(X[-6:])}"

    async def test(world: PlacementWorld) -> None:
        world.add(
            "both",
            (Card(0, text, CardCompleteness.ABBREVIATED), Card(3, text), Card(6, " ".join(X))),
            week=0,
        )
        await world.run()
        assert world.written() == await world.at_start()
        world.add("later", (Card(0, text),), week=1)

        await world.run()

        assert world.store.documents_read == [world.names["later"]]
        assert world.written() == await world.at_start()

    in_a_world(test)


def test_a_week_signs_only_its_new_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of the state: a stored body's MinHash signature is read, not taken again. The week
    adds one new body and one copy of a stored one, so one body is signed."""
    signed: list[int] = []
    original = near_duplicates.minhash_signature

    def counting(*args: object, **kwargs: object) -> tuple[int, ...]:
        signed.append(1)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    async def test(world: PlacementWorld) -> None:
        week_one(world)
        await world.run()
        world.add("fourth", (Card(0, " ".join(passage(4, 70))), Card(3, " ".join(X))), week=1)
        monkeypatch.setattr(near_duplicates, "minhash_signature", counting)

        await world.run()

        assert len(signed) == 1
        assert world.written() == await world.at_start()

    in_a_world(test)
