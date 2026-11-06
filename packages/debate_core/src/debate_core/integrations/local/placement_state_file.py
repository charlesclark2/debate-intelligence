"""The placement state as one SQLite file (`v1-e31-t10`): `placement-state.sqlite` in a version directory.

:class:`~debate_core.application.ports.placement_state.PlacementState` written and read whole. SQLite
because the standard library reads it, it is one file the bucket can hold beside the aggregates, and a
body's words and signature are binary.

## The layout (schema version 1)

* `meta(name, value)`: `schema_version`, `parser_version`, `profile_version`, `fingerprint_version`,
  `rules`, and `vocabulary`, every word once, joined by line breaks (a word is a run of letters and
  digits, so it never holds one).
* `sources(sha256, cards)`: one row per source the state was built from; `cards` is a JSON list, a card
  as `[first, last, completeness, fingerprint, short-cite key, anchor]`, the key a list of word numbers
  or `null`, the anchor `[key, opening, closing, from the cite line]` or `null`.
* `bodies(fingerprint, words, signature)`: one row per distinct full body; `words` its word numbers and
  `signature` its 128 MinHash values, each little-endian unsigned 32-bit, `signature` `NULL` for a body
  with no words.

## Written fresh, read whole

A write builds a new database in a temporary file beside the old one and renames it into place, so a
reader never meets half a state and no page of an earlier one survives in it (a database edited in
place keeps deleted rows in its free pages). A read opens the file read-only and immutable, which writes
nothing beside it, and checks it whole before anything is returned: every number is in the vocabulary,
every full card's body is there, every signature is 128 values. Anything else is
:class:`~debate_core.application.ports.placement_state.UnreadablePlacementState`, which never names a
word of it.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from array import array
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, Final, cast

from debate_core.application.ports.placement_state import (
    PLACEMENT_STATE_SCHEMA_VERSION,
    PlacedAnchor,
    PlacedBody,
    PlacedCard,
    PlacementState,
    UnreadablePlacementState,
)
from debate_core.domain.debate_files import CardCompleteness
from debate_core.evidence.near_duplicates import MINHASH_PERMUTATIONS

__all__ = ["read_placement_state_file", "write_placement_state_file"]

_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_COMPLETENESS: Final = {str(completeness): completeness for completeness in CardCompleteness}
_PAGE_SIZE: Final = 65536
_STAMPS: Final = ("parser_version", "profile_version", "fingerprint_version", "rules")


def write_placement_state_file(path: Path, state: PlacementState) -> None:
    """Write `state` as a new SQLite database at `path`, which must not exist yet."""
    if any("\n" in word for word in state.vocabulary):
        raise ValueError("a vocabulary word holds a line break")
    with closing(sqlite3.connect(path)) as database:
        # Rows of a body's words and signature run to a few kilobytes: at the default 4 KiB page two fit
        # a page and a third of the file was page overhead (61.0 MB at 2,000 synthetic sources, 46.3 MB
        # at 64 KiB, `v1-e31-t10`'s report).
        database.execute(f"PRAGMA page_size = {_PAGE_SIZE}")
        database.execute("PRAGMA journal_mode = OFF")
        database.execute("CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.execute("CREATE TABLE sources (sha256 TEXT PRIMARY KEY, cards TEXT NOT NULL)")
        database.execute(
            "CREATE TABLE bodies (fingerprint TEXT PRIMARY KEY, words BLOB NOT NULL, signature BLOB)"
        )
        meta = {
            "schema_version": str(PLACEMENT_STATE_SCHEMA_VERSION),
            "parser_version": state.parser_version,
            "profile_version": state.profile_version,
            "fingerprint_version": state.fingerprint_version,
            "rules": state.rules,
            "vocabulary": "\n".join(state.vocabulary),
        }
        database.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        database.executemany(
            "INSERT INTO sources VALUES (?, ?)",
            (
                (sha256, json.dumps([_card_row(card) for card in cards], separators=(",", ":")))
                for sha256, cards in sorted(state.sources.items())
            ),
        )
        database.executemany(
            "INSERT INTO bodies VALUES (?, ?, ?)",
            (
                (
                    fingerprint,
                    _little_endian(body.words),
                    None if body.signature is None else _little_endian(body.signature),
                )
                for fingerprint, body in sorted(state.bodies.items())
            ),
        )
        database.commit()


def read_placement_state_file(path: Path) -> PlacementState:
    """The state in `path`, checked whole. Raises :class:`UnreadablePlacementState` for anything else."""
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)) as database:
            meta = dict(database.execute("SELECT name, value FROM meta").fetchall())
            if meta.get("schema_version") != str(PLACEMENT_STATE_SCHEMA_VERSION):
                raise UnreadablePlacementState("the placement state is of another layout")
            vocabulary = tuple(meta["vocabulary"].split("\n")) if meta["vocabulary"] else ()
            sources = {
                sha256: tuple(_card(row, len(vocabulary)) for row in json.loads(cards))
                for sha256, cards in database.execute("SELECT sha256, cards FROM sources")
            }
            bodies = {
                fingerprint: _body(words, signature, len(vocabulary))
                for fingerprint, words, signature in database.execute(
                    "SELECT fingerprint, words, signature FROM bodies"
                )
            }
            stamps = {name: meta[name] for name in _STAMPS}
    except UnreadablePlacementState:
        raise
    except (sqlite3.Error, KeyError, ValueError, TypeError, IndexError, AttributeError):
        raise UnreadablePlacementState("the placement state cannot be read") from None
    if not all(isinstance(value, str) and value for value in stamps.values()):
        raise UnreadablePlacementState("the placement state's stamps cannot be read")
    if not all(_SHA256.match(name) for name in (*sources, *bodies)):
        raise UnreadablePlacementState("the placement state names something other than a digest")
    _refuse_a_missing_body(sources, bodies)
    return PlacementState(
        parser_version=stamps["parser_version"],
        profile_version=stamps["profile_version"],
        fingerprint_version=stamps["fingerprint_version"],
        rules=stamps["rules"],
        vocabulary=vocabulary,
        sources=sources,
        bodies=bodies,
    )


def _card_row(card: PlacedCard) -> list[Any]:
    anchor = card.anchor
    return [
        card.first_element,
        card.last_element,
        str(card.completeness),
        card.fingerprint,
        None if card.short_cite_key is None else list(card.short_cite_key),
        None
        if anchor is None
        else [
            list(anchor.short_cite_key),
            list(anchor.opening_words),
            list(anchor.closing_words),
            anchor.from_cite_line,
        ],
    ]


def _card(row: Any, words: int) -> PlacedCard:
    first, last, completeness, fingerprint, key, anchor = row
    if not (isinstance(first, int) and isinstance(last, int) and 0 <= first <= last):
        raise ValueError("a card's range")
    if not (isinstance(fingerprint, str) and _SHA256.match(fingerprint)):
        raise ValueError("a card's fingerprint")
    placed = PlacedCard(
        first_element=first,
        last_element=last,
        completeness=_COMPLETENESS[completeness],
        fingerprint=fingerprint,
        short_cite_key=None if key is None else _numbers(key, words),
        anchor=None
        if anchor is None
        else PlacedAnchor(
            short_cite_key=_numbers(anchor[0], words),
            opening_words=_numbers(anchor[1], words),
            closing_words=_numbers(anchor[2], words),
            from_cite_line=_flag(anchor[3]),
        ),
    )
    full = placed.completeness is CardCompleteness.FULL
    if (full and placed.anchor is not None) or (not full and placed.short_cite_key is not None):
        raise ValueError("a card's keys do not fit its completeness")
    return placed


def _numbers(values: Any, words: int) -> tuple[int, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError("a key's words")
    numbers: list[int] = []
    for value in cast(list[object], values):
        if isinstance(value, bool) or not (isinstance(value, int) and 0 <= value < words):
            raise ValueError("a word outside the vocabulary")
        numbers.append(value)
    return tuple(numbers)


def _flag(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("a flag")
    return value


def _body(words: Any, signature: Any, vocabulary: int) -> PlacedBody:
    numbers = _from_little_endian(words)
    if any(number >= vocabulary for number in set(numbers)):
        raise ValueError("a word outside the vocabulary")
    if signature is None:
        if numbers:
            raise ValueError("a body with words and no signature")
        return PlacedBody(numbers, None)
    values = _from_little_endian(signature)
    if len(values) != MINHASH_PERMUTATIONS:
        raise ValueError("a signature of another length")
    return PlacedBody(numbers, values)


def _refuse_a_missing_body(
    sources: Mapping[str, tuple[PlacedCard, ...]], bodies: Mapping[str, PlacedBody]
) -> None:
    for cards in sources.values():
        for card in cards:
            if card.completeness is CardCompleteness.FULL and card.fingerprint not in bodies:
                raise UnreadablePlacementState("the placement state lacks a full card's body")


def _little_endian(numbers: array[int]) -> bytes:
    if sys.byteorder == "little":
        return numbers.tobytes()
    swapped = array("I", numbers)
    swapped.byteswap()
    return swapped.tobytes()


def _from_little_endian(data: Any) -> array[int]:
    if not isinstance(data, bytes) or len(data) % 4:
        raise ValueError("binary words of another length")
    numbers = array("I")
    numbers.frombytes(data)
    if sys.byteorder != "little":
        numbers.byteswap()
    return numbers
