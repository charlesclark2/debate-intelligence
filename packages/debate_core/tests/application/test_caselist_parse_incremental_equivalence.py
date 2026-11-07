"""The rebuild from the placement state equals today's full rebuild, byte for byte, after every step.

`v1-e31-t10`, Goal criterion ac2, and the PM's ruling of 2026-11-06, item 6. Hypothesis generates a
caselist as a sequence of steps, and after each one the service rebuilds and its index, failures
file and occurrence table are compared with what the rebuild as the task found it writes for the same
store (:mod:`.rebuild_at_start`, the oracle):

* **a week**: one to three new sources, and perhaps an earlier source listed again;
* **a removal**: a source stopped, its per-source file gone, the placement state deleted, as
  `v1-e30-t33`'s removal leaves the directory under this task's ruling;
* **a source stopped elsewhere**, with the state left in place;
* **the state deleted**;
* **a parser version change**: a new version directory, every live source parsed again.

The cards are drawn from four invented articles, so weeks bring copies, copies with a word or three
changed, cuts, short cuts, longer extents, abbreviated and cite-only cards, one text under two short
cites and full cards with no short cite: what joins, splits and links clusters. Each step is labelled
with `event()` by the way the rebuild placed its cards and by whether a week moved an older row to
another cluster, so `--hypothesis-show-statistics` says what was generated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from debate_core.domain.debate_files import CardCompleteness

from .placement_world import LOGGER, WEEKS, Card, PlacementWorld, passage

ARTICLES: Final = tuple(passage(100 + seed, 160) for seed in range(4))
CITES: Final = ("Quillon 26", "Marrow 25", None)
KINDS: Final = (
    "copy",
    "copy",
    "one word changed",
    "two words changed",
    "three words changed",
    "cut",
    "short cut",
    "longer extent",
    "abbreviated",
    "abbreviated under another cite",
    "cite only",
)


@dataclass(frozen=True, slots=True)
class Drawn:
    kind: str
    article: int
    start: int
    length: int
    cite: int


def card_of(drawn: Drawn, element: int) -> Card:
    words = list(ARTICLES[drawn.article])
    start, length = drawn.start, drawn.length
    passage_words = words[start : start + length]
    cite = CITES[drawn.cite]
    if drawn.kind == "one word changed":
        passage_words[length // 2] = "gallimaufry"
    elif drawn.kind == "two words changed":
        # A copy only the MinHash bands find: Jaccard about 0.8, under 0.9 of either inside the other.
        for offset, word in ((length // 3, "hobbledehoy"), (2 * length // 3, "gallimaufry")):
            passage_words[offset] = word
    elif drawn.kind == "three words changed":
        for offset, word in (
            (length // 4, "hobbledehoy"),
            (length // 2, "gallimaufry"),
            (3 * length // 4, "snickersnee"),
        ):
            passage_words[offset] = word
    elif drawn.kind == "cut":
        passage_words = passage_words[length // 5 : length - length // 5]
    elif drawn.kind == "short cut":
        passage_words = passage_words[: max(12, length // 3)]
    elif drawn.kind == "longer extent":
        passage_words = words[max(0, start - 20) : start + length + 20]
    elif drawn.kind.startswith("abbreviated"):
        other = "Tamber 24" if drawn.kind.endswith("another cite") else (cite or "Quillon 26")
        text = f"{' '.join(passage_words[:6])} … {' '.join(passage_words[-6:])}"
        return Card(element, text, CardCompleteness.ABBREVIATED, other)
    elif drawn.kind == "cite only":
        return Card(element, "", CardCompleteness.CITE_ONLY, cite or "Marrow 25")
    return Card(element, " ".join(passage_words), CardCompleteness.FULL, cite)


drawn_cards = st.builds(
    Drawn,
    kind=st.sampled_from(KINDS),
    article=st.integers(0, len(ARTICLES) - 1),
    start=st.integers(0, 60),
    length=st.integers(20, 100),
    cite=st.integers(0, len(CITES) - 1),
)
sources = st.lists(drawn_cards, min_size=1, max_size=4)
weeks = st.tuples(st.just("week"), st.lists(sources, min_size=1, max_size=3), st.booleans())
steps = st.one_of(
    weeks,
    weeks,
    weeks,
    st.tuples(st.just("remove"), st.integers(0, 50)),
    st.tuples(st.just("stop elsewhere"), st.integers(0, 50)),
    st.tuples(st.just("state deleted")),
    st.tuples(st.just("version change")),
)


class Paths(logging.Handler):
    """The rebuild's own log lines, to say which way each step's cards were placed."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "placement state" in message or "in full" in message:
            self.lines.append(message)


def clusters_of(table: bytes) -> dict[tuple[str, int], str]:
    return {
        (row["source_sha256"], row["first_element_index"]): row["cluster_id"]
        for row in map(json.loads, table.decode().splitlines())
    }


async def walk(world: PlacementWorld, first: list[list[Drawn]], later: list[tuple[object, ...]]) -> None:
    paths = Paths()
    logger = logging.getLogger(LOGGER)
    logger.addHandler(paths)
    level = logger.level
    logger.setLevel(logging.INFO)
    try:
        named = 0
        week = 0
        live: list[str] = []
        version = 1

        def add_week(batch: list[list[Drawn]]) -> None:
            nonlocal named
            for cards in batch:
                name = f"s{named}"
                named += 1
                world.add(
                    name, tuple(card_of(drawn, 3 * element) for element, drawn in enumerate(cards)), week=week
                )
                live.append(name)

        add_week(first)
        await world.run()
        assert world.written() == await world.at_start(), "the first week"
        for step in later:
            kind = step[0]
            before = clusters_of(world.written()["occurrences.jsonl"])
            if kind == "week" and week + 1 < len(WEEKS):
                week += 1
                batch, relist = step[1], step[2]
                if relist and live:
                    world.relist(live[0], week)
                add_week(batch)  # type: ignore[arg-type]
            elif kind == "remove" and len(live) > 1:
                await world.remove(world.names[live.pop(int(step[1]) % len(live))])  # type: ignore[call-overload]
            elif kind == "stop elsewhere" and len(live) > 1:
                await world.stop(world.names[live.pop(int(step[1]) % len(live))])  # type: ignore[call-overload]
            elif kind == "state deleted":
                world.state_path.unlink(missing_ok=True)
            elif kind == "version change":
                version += 1
                world.parser_version = f"2031.01.01-synthetic-{version}"
            else:
                kind = "nothing new"
            paths.lines.clear()
            await world.run()
            (line,) = paths.lines
            way = (
                "from the state" if "placement state" in line else line[line.index("(") : line.index(")") + 1]
            )
            event(f"{kind}: placed {way}")
            after = clusters_of(world.written()["occurrences.jsonl"])
            if kind == "week" and any(
                after[key] != cluster for key, cluster in before.items() if key in after
            ):
                event("a week moved an older card to another cluster")
            assert world.written() == await world.at_start(), (kind, way)
    finally:
        logger.removeHandler(paths)
        logger.setLevel(level)


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
@given(first=st.lists(sources, min_size=2, max_size=5), later=st.lists(steps, min_size=1, max_size=6))
def test_after_every_step_the_table_is_todays_full_rebuilds(
    first: list[list[Drawn]], later: list[tuple[object, ...]]
) -> None:
    with tempfile.TemporaryDirectory(prefix="equivalence-") as scratch:
        asyncio.run(walk(PlacementWorld(Path(scratch)), first, later))
