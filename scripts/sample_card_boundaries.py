#!/usr/bin/env python3
"""Ask a person what the long bodies and the bodies holding two cards are (`v1-e31-t22`). Counts only.

`scripts/count_card_boundaries.py` counts two kinds of card boundary the parser may miss and saves
the store positions it counted (`--save-candidates`). Counts say how many and of what shape, not
what they are. This draws from those positions and asks one question with one key per item:

* **A body too long to be one card** (over 3,000 words), ten distinct texts of each kind the count
  names (`debate_core.evidence.card_boundaries.LongBodyKind`): *what is this body?* One card,
  several cards stored as one, or no cards at all (a case, a speech, notes, an article not cut).
* **A body holding two cards' bodies that share no text**, ten whose body is under 1,000 words and
  ten of 1,000 or more: *are the two marked parts two cards, a boundary the parser missed, or one
  card two teams cut differently?*

Each item is the card's range as the parser reads it from the source's blob: one line a paragraph,
with what the parser read it as (a line read as NOTHING is where a tag typed in body style hides),
its words, how much is underlined or highlighted, the marks the count used, and its opening and
end. A body holding two cards also shows, for each paragraph, how much of it is in each of the two.
The paragraph that ended the card closes the item.

**Through `v1-e31-t21`'s sampler** (`scripts/compare_card_clusters.py`): its key reader (one key,
no Enter, keys pressed early discarded), its refusal to show card text anywhere but a terminal, the
screen cleared between items and at the end, and the closing tally lines appended to a file.

**Read-only, and nothing but tallies leaves it.** It reads the parsed store and the blobs in place.
The tallies file must be outside the repository and outside the data directory: the seed, the
population and the items drawn and asked of each stratum, the seconds spent answering, and the
answers counted by stratum. No paragraph, tag, cite, file name, path or digest.

    uv run python scripts/sample_card_boundaries.py --seed 20261019 \\
        --save-tallies ~/t22-card-boundary-sample-tallies.txt

Keys: as each question says, with no Enter; `q` stops and keeps the tallies so far.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compare_card_clusters import CLEAR_TERMINAL, STOP_KEY, read_key  # noqa: E402
from count_card_boundaries import (  # noqa: E402
    CANDIDATES,
    outside_the_repository_and_the_store,
    version_directory,
)

from debate_core.application.ports.parsed_store import source_object_key  # noqa: E402
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin  # noqa: E402
from debate_core.domain.debate_files import ParsedCard, ParsedDocument  # noqa: E402
from debate_core.domain.style_profile import StructuralUnit, StyleProfile  # noqa: E402
from debate_core.evidence.card_boundaries import (  # noqa: E402
    Ending,
    InsideParagraph,
    LongBodyKind,
    ending_of,
    marked_up_share,
    paragraphs_inside,
    word_count,
)
from debate_core.evidence.fingerprints import fingerprint_text  # noqa: E402
from debate_core.evidence.near_duplicates import shingles  # noqa: E402
from debate_core.integrations.docx_parser import DebateDocxParser  # noqa: E402
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY  # noqa: E402

__all__ = [
    "LONG_BODY",
    "STRATA",
    "TWO_CARDS",
    "Drawn",
    "Item",
    "Stratum",
    "Tallies",
    "ask_about",
    "draw",
    "holder_band",
    "main",
    "population_of",
    "prepare",
    "render_item",
]

LONG_BODY, TWO_CARDS = "long-body", "two-cards-in-one"

LONG_QUESTION = "What is this body?"
LONG_ANSWERS = {
    "o": "one card",
    "s": "several cards stored as one",
    "n": "no cards: a case, a speech, notes or an article not cut",
    "u": "unsure",
}
TWO_QUESTION = "The two marked parts, A and B, share no text. Are they two cards, or one card cut twice?"
TWO_ANSWERS = {"t": "two cards: a boundary the parser missed", "o": "one card cut twice", "u": "unsure"}

#: A body holding two cards is drawn in two bands of its own length.
HOLDER_UNDER, HOLDER_OVER = "body under 1,000 words", "body of 1,000 words or more"
HOLDER_BAND_WORDS = 1_000


def holder_band(words: int) -> str:
    """The band a body holding two cards is drawn in: 999 words is under 1,000, 1,000 is not."""
    return HOLDER_UNDER if words < HOLDER_BAND_WORDS else HOLDER_OVER


@dataclass(frozen=True, slots=True)
class Stratum:
    """One cell of the plan: which count, which group of it, and how many to draw."""

    count: str
    group: str
    planned: int

    @property
    def label(self) -> str:
        return f"{self.count} | {self.group}"

    @property
    def answers(self) -> dict[str, str]:
        return LONG_ANSWERS if self.count == LONG_BODY else TWO_ANSWERS

    @property
    def question(self) -> str:
        return LONG_QUESTION if self.count == LONG_BODY else TWO_QUESTION


STRATA: tuple[Stratum, ...] = (
    *(Stratum(LONG_BODY, kind.value, 10) for kind in LongBodyKind),
    Stratum(TWO_CARDS, HOLDER_UNDER, 10),
    Stratum(TWO_CARDS, HOLDER_OVER, 10),
)

type CardKey = tuple[str, int]


# ------------------------------------------------------------------------------------------------
# Drawing
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Drawn:
    """One item drawn: its stratum, its caselist, and the store positions it shows."""

    stratum: int
    caselist: str
    card: CardKey
    pieces: tuple[CardKey, CardKey] | None = None


@dataclass(frozen=True, slots=True)
class _Candidate:
    caselist: str
    card: CardKey
    fingerprint: str
    pieces: tuple[CardKey, CardKey] | None


def draw(
    population: Mapping[int, Sequence[_Candidate]], seed: int, strata: Sequence[Stratum] = STRATA
) -> list[Drawn]:
    """The items of the plan, in an order that does not say which stratum each is from.

    Each stratum's candidates are shuffled by the seed and taken in turn, a text already drawn
    passed over, so a text disclosed by many teams is drawn once and as likely as any other.
    """
    rng = random.Random(seed)
    drawn: list[Drawn] = []
    seen: set[str] = set()
    for number, stratum in enumerate(strata):
        candidates = sorted(population.get(number, ()), key=lambda c: (c.caselist, c.card))
        rng.shuffle(candidates)
        taken = 0
        for candidate in candidates:
            if taken == stratum.planned:
                break
            if candidate.fingerprint in seen:
                continue
            seen.add(candidate.fingerprint)
            drawn.append(Drawn(number, candidate.caselist, candidate.card, candidate.pieces))
            taken += 1
    rng.shuffle(drawn)
    return drawn


def _read_cards(
    store_root: Path, caselist: str, version: str, keys: Iterable[CardKey]
) -> dict[CardKey, dict[str, Any]]:
    wanted: defaultdict[str, set[int]] = defaultdict(set)
    for sha256, first in keys:
        wanted[sha256].add(first)
    cards: dict[CardKey, dict[str, Any]] = {}
    for sha256, firsts in sorted(wanted.items()):
        with (store_root / source_object_key(caselist, version, sha256)).open(encoding="utf-8") as stream:
            stream.readline()
            document = json.loads(stream.readline())["document"]
        for card in document["cards"]:
            first = card["provenance"]["first_element_index"]
            if first in firsts:
                cards[(sha256, first)] = card
    return cards


def population_of(
    rows: Sequence[Mapping[str, Any]],
    data_dir: Path,
    expected: str | None,
    strata: Sequence[Stratum] = STRATA,
) -> tuple[dict[int, list[_Candidate]], dict[str, str]]:
    """Each stratum's candidates, one a distinct text, from the counted positions; and the version
    directory each caselist was read from."""
    number_of = {(stratum.count, stratum.group): number for number, stratum in enumerate(strata)}
    by_caselist: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["count"] == LONG_BODY or row["group"] == "sharing nothing":
            by_caselist[row["caselist"]].append(row)
    population: defaultdict[int, dict[tuple[str, str], _Candidate]] = defaultdict(dict)
    versions: dict[str, str] = {}
    store_root = data_dir / "parsed"
    for caselist, found in sorted(by_caselist.items()):
        version = version_directory(store_root, caselist, expected).name
        versions[caselist] = version
        cards = _read_cards(store_root, caselist, version, (tuple(row["card"]) for row in found))
        for row in found:
            key: CardKey = (row["card"][0], row["card"][1])
            body = cards[key]["evidence_text"]
            if row["count"] == LONG_BODY:
                number, pieces = number_of[(LONG_BODY, row["group"])], None
            else:
                number = number_of[(TWO_CARDS, holder_band(word_count(body)))]
                first, second = row["pieces"]
                pieces = ((first[0], first[1]), (second[0], second[1]))
            candidate = _Candidate(caselist, key, fingerprint_text(body), pieces)
            known = population[number].get((caselist, candidate.fingerprint))
            if known is None or candidate.card < known.card:
                population[number][(caselist, candidate.fingerprint)] = candidate
    return {number: list(found.values()) for number, found in population.items()}, versions


# ------------------------------------------------------------------------------------------------
# Showing an item
# ------------------------------------------------------------------------------------------------

_BOLD, _UNDERLINE, _REVERSE, _DIM, _RESET = "\x1b[1m", "\x1b[4m", "\x1b[7m", "\x1b[2m", "\x1b[0m"

_READING = {
    StructuralUnit.TAG: "tag",
    StructuralUnit.CITE: "cite",
    StructuralUnit.UNDERTAG: "undertag",
    StructuralUnit.EVIDENCE: "body",
    StructuralUnit.OTHER: "NOTHING",
    StructuralUnit.ANALYTIC: "analytic",
}

#: A paragraph of up to this many words is shown whole; a longer one by its opening and its end.
SHOWN_WHOLE_WORDS = 30
OPENING_WORDS, END_WORDS = 10, 6
#: Paragraphs always shown at the start and the end of a card.
FIRST_ROWS, LAST_ROWS = 4, 3


@dataclass(frozen=True, slots=True)
class Item:
    """One drawn item, read and ready to show."""

    drawn: Drawn
    card: ParsedCard
    inside: tuple[InsideParagraph, ...]
    ending: Ending
    closer: str | None
    pieces: tuple[frozenset[str], frozenset[str]] | None = None
    """For a body holding two cards, the five-word runs of A and of B, A the earlier in the body."""
    piece_words: tuple[int, int] = (0, 0)


def _shortened(text: str, width: int) -> str:
    text = " ".join(text.split())
    words = text.split()
    if len(words) > SHOWN_WHOLE_WORDS:
        text = " ".join(words[:OPENING_WORDS]) + " … " + " ".join(words[-END_WORDS:])
    return text if len(text) <= width else text[: max(1, width - 1)] + "…"


def _shares(text: str, pieces: tuple[frozenset[str], frozenset[str]]) -> tuple[float, float]:
    own = shingles(text)
    if not own:
        return 0.0, 0.0
    return len(own & pieces[0]) / len(own), len(own & pieces[1]) / len(own)


def _kept(item: Item) -> list[bool]:
    """Which rows are shown: the first and last few, every line read as nothing or short, every
    marked line and the lines beside it, and for a body holding two cards every line where the
    part changes, and the lines beside it."""
    rows = item.inside
    count = len(rows)
    kept = [index < FIRST_ROWS or index >= count - LAST_ROWS for index in range(count)]

    def part(index: int) -> str:
        if item.pieces is None:
            return ""
        a, b = _shares(rows[index].section.text, item.pieces)
        return "A" if a >= 0.5 else "B" if b >= 0.5 else ""

    for index, row in enumerate(rows):
        unit = row.section.match.unit
        marked = row.cite_shaped or row.where_a_tag_would_be
        changes = index > 0 and item.pieces is not None and part(index) != part(index - 1)
        short = unit is not StructuralUnit.EVIDENCE or word_count(row.section.text) <= SHOWN_WHOLE_WORDS
        if marked or changes or short:
            for near in (index - 1, index, index + 1):
                if 0 <= near < count:
                    kept[near] = True
    return kept


def render_item(item: Item, columns: int) -> str:
    """The item for a person to judge: a heading, then its paragraphs one a line, then what ended it.

    Shown only on a terminal, by :func:`ask_about`.
    """
    stratum = STRATA[item.drawn.stratum]
    card = item.card
    words = word_count(card.evidence_text)
    if item.pieces is None:
        heading = f"{item.drawn.caselist}. A body of {words:,} words."
    else:
        heading = (
            f"{item.drawn.caselist}. A body of {words:,} words holding two cards' bodies that share no "
            f"text: A, {item.piece_words[0]:,} words, and B, {item.piece_words[1]:,} words."
        )
    lines = [
        heading,
        f"Tag: {_shortened(card.tag or '(none)', columns - 6)}",
        f"Cite: {_shortened(card.full_cite or '(none)', columns - 7)}",
        "",
        f"{_DIM}One line a paragraph: what the parser read it as, words, share underlined or highlighted"
        + (", share in A and in B" if item.pieces else "")
        + ". ◆ names a source at its head; ▸ is a short line above one, where a tag would be."
        + f"{_RESET}",
    ]
    kept = _kept(item)
    hidden_rows = hidden_words = 0
    for index, row in enumerate(item.inside):
        if not kept[index]:
            hidden_rows += 1
            hidden_words += word_count(row.section.text)
            continue
        if hidden_rows:
            lines.append(
                f"{_DIM}      … {hidden_rows} body paragraphs, {hidden_words:,} words, not shown …{_RESET}"
            )
            hidden_rows = hidden_words = 0
        section = row.section
        reading = _READING.get(section.match.unit, section.match.unit.value.lower())
        mark = "◆" if row.cite_shaped else "▸" if row.where_a_tag_would_be else " "
        share = marked_up_share(section.text, section.formatting_spans)
        columns_text = f"{index + 1:>4} {reading:<8} {word_count(section.text):>5}w {share:>4.0%}"
        if item.pieces is not None:
            a, b = _shares(section.text, item.pieces)
            columns_text += f" A{a:>5.0%} B{b:>5.0%}"
        prefix = f"{columns_text} {mark} "
        text = _shortened(section.text, max(20, columns - len(prefix)))
        style = _BOLD if reading == "NOTHING" or row.cite_shaped or row.where_a_tag_would_be else ""
        lines.append(f"{prefix}{style}{text}{_RESET if style else ''}")
    if hidden_rows:
        lines.append(
            f"{_DIM}      … {hidden_rows} body paragraphs, {hidden_words:,} words, not shown …{_RESET}"
        )
    closer = f": {_shortened(item.closer, columns - 30)}" if item.closer else ""
    lines += ["", f"Ended by {item.ending.value}{closer}", "", stratum.question]
    return "\n".join(lines) + "\n"


def _prompt(stratum: Stratum) -> str:
    keys = "   ".join(f"{key} {answer}" for key, answer in stratum.answers.items())
    return f"  {keys}   {STOP_KEY} stop and keep the tallies > "


def ask_about(
    items: Sequence[Item],
    *,
    ask: Callable[[str], str],
    show: Callable[[str], None],
    columns: int,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[Counter[tuple[int, str]], bool, float]:
    """Show each item and read one key for it. The answers by stratum, whether stopped, seconds."""
    answered: Counter[tuple[int, str]] = Counter()
    stopped = False
    started = clock()
    for number, item in enumerate(items, start=1):
        stratum = STRATA[item.drawn.stratum]
        show(CLEAR_TERMINAL)
        show(f"Item {number} of {len(items)}.\n")
        show(render_item(item, columns))
        key = ""
        while key not in stratum.answers and key != STOP_KEY:
            key = ask(_prompt(stratum)).strip().lower()[:1]
        if key == STOP_KEY:
            stopped = True
            break
        answered[(item.drawn.stratum, stratum.answers[key])] += 1
    seconds = clock() - started if items else 0.0
    show(CLEAR_TERMINAL)
    return answered, stopped, seconds


# ------------------------------------------------------------------------------------------------
# Reading the drawn items
# ------------------------------------------------------------------------------------------------


def _parse(content: bytes, sha256: str, caselist: str) -> ParsedDocument | None:
    snapshot = date(2026, 10, 19)
    record = SourceDocument(
        sha256=sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV if caselist == "openev" else SourceOrigin.CASELIST_ARCHIVE,
        caselist=None if caselist == "openev" else caselist,
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    document = DebateDocxParser().parse(content, record, source_path="sampled.docx")
    return document if isinstance(document, ParsedDocument) else None


def prepare(
    drawn: Sequence[Drawn], data_dir: Path, versions: Mapping[str, str], profile: StyleProfile
) -> tuple[list[Item], int]:
    """Each drawn item read from its source's blob; and how many were not reproduced, and skipped."""
    items: list[Item] = []
    skipped = 0
    for entry in drawn:
        sha256, first = entry.card
        blob = data_dir / BLOB_DIRECTORY / sha256[:2] / sha256[2:4] / sha256
        stored = _read_cards(data_dir / "parsed", entry.caselist, versions[entry.caselist], [entry.card])[
            entry.card
        ]
        document = _parse(blob.read_bytes(), sha256, entry.caselist) if blob.is_file() else None
        card = next(
            (c for c in (document.cards if document else ()) if c.provenance.first_element_index == first),
            None,
        )
        if (
            document is None
            or card is None
            or card.provenance.last_element_index != stored["provenance"]["last_element_index"]
            or card.evidence_text != stored["evidence_text"]
        ):
            skipped += 1
            continue
        ending, closer = ending_of(document, card)
        pieces: tuple[frozenset[str], frozenset[str]] | None = None
        piece_words = (0, 0)
        if entry.pieces is not None:
            bodies = _read_cards(data_dir / "parsed", entry.caselist, versions[entry.caselist], entry.pieces)
            texts = [bodies[key]["evidence_text"] for key in entry.pieces]
            texts.sort(key=lambda text: _first_shared(card.evidence_text, shingles(text)))
            pieces = (shingles(texts[0]), shingles(texts[1]))
            piece_words = (word_count(texts[0]), word_count(texts[1]))
        items.append(
            Item(
                drawn=entry,
                card=card,
                inside=tuple(paragraphs_inside(document, card, profile)),
                ending=ending,
                closer=closer.text if closer is not None else None,
                pieces=pieces,
                piece_words=piece_words,
            )
        )
    return items, skipped


def _first_shared(body: str, piece: frozenset[str]) -> int:
    """Which paragraph of `body` first holds a run of `piece`: how A is told from B."""
    for number, paragraph in enumerate(body.split("\n")):
        if shingles(paragraph) & piece:
            return number
    return len(body)


# ------------------------------------------------------------------------------------------------
# Tallies
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tallies:
    """What was drawn and answered, by stratum. Counts only."""

    seed: int
    population: Mapping[int, int]
    drawn: Counter[int]
    answered: Counter[tuple[int, str]]
    asked: int
    skipped: int
    stopped: bool
    seconds_answering: float

    def lines(self) -> list[str]:
        answered = sum(self.answered.values())
        summary = (
            f"Card-boundary sample, seed {self.seed}: drew {sum(self.drawn.values())} of "
            f"{sum(stratum.planned for stratum in STRATA)} planned, asked {self.asked}, answered {answered} "
            f"in {round(self.seconds_answering)} seconds"
        )
        summary += f", stopped with {self.asked - answered} not answered." if self.stopped else "."
        lines = [summary]
        if self.skipped:
            lines.append(f"  not reproduced by this checkout's parser, and skipped: {self.skipped}")
        for number, stratum in enumerate(STRATA):
            lines.append(
                f"  {stratum.label}: distinct texts {self.population.get(number, 0)}, "
                f"planned {stratum.planned}, drawn {self.drawn[number]}"
            )
            for answer in stratum.answers.values():
                if self.answered[(number, answer)]:
                    lines.append(f"    {answer}: {self.answered[(number, answer)]}")
        return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".debate-research" / "dev",
        help="The data directory whose parsed store and blobs are read. Default: the dev data directory.",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=CANDIDATES,
        help="The positions count_card_boundaries.py saved. Default: ~/t22-card-boundary-candidates.jsonl.",
    )
    parser.add_argument(
        "--expect-version", help="Stop unless each caselist's store is of this parser version."
    )
    parser.add_argument("--seed", type=int, help="Draws the same items again. Default: a new one, recorded.")
    parser.add_argument(
        "--save-tallies",
        type=Path,
        required=True,
        help="A file outside the repository and the data directory.",
    )
    arguments = parser.parse_args(argv)
    saved = outside_the_repository_and_the_store(arguments.save_tallies, arguments.data_dir, "--save-tallies")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "The sample shows card text, so it runs only with a terminal for input and output.",
            file=sys.stderr,
        )
        return 2
    seed = arguments.seed if arguments.seed is not None else random.SystemRandom().randrange(10**9)

    rows = [
        json.loads(line) for line in arguments.candidates.read_text(encoding="utf-8").splitlines() if line
    ]
    print(f"Reading {len(rows):,} counted positions …", flush=True)
    population, versions = population_of(rows, arguments.data_dir, arguments.expect_version)
    drawn = draw(population, seed)
    profile = DebateDocxParser().profile
    items, skipped = prepare(drawn, arguments.data_dir, versions, profile)
    columns = shutil.get_terminal_size((120, 40)).columns
    answered, stopped, seconds = ask_about(
        items, ask=read_key, show=lambda text: print(text, end="", flush=True), columns=columns
    )
    tallies = Tallies(
        seed=seed,
        population={number: len(found) for number, found in population.items()},
        drawn=Counter(item.drawn.stratum for item in items),
        answered=answered,
        asked=len(items),
        skipped=skipped,
        stopped=stopped,
        seconds_answering=seconds,
    )
    lines = tallies.lines()
    print("\n".join(lines))
    saved.parent.mkdir(parents=True, exist_ok=True)
    with saved.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    print(f"Tallies appended to {saved.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
