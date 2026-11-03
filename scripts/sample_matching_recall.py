#!/usr/bin/env python3
"""Sample the pairs card matching keeps apart, for a person to judge in `less` (`v1-e31-t29`).

Draws from the positions two counts saved, and shows each item through `v1-e31-t21`'s sampler's
display (`compare_card_clusters.render_pair`, the text both hold underlined and each side's own in
bold) or `v1-e31-t22`'s (`sample_card_boundaries._between`, where A ends and B begins):

* **neither end** (20): a body nine-tenths inside another that holds neither of its ends, beside
  that body, from `scripts/count_matching_recall.py`'s candidates. Same card, or different?
* **trims with the same tag and cite** (10 end to end, 10 with words between): two passages of one
  holder that share no text and whose cards carry the same tag and cite, with the holder, from the
  same candidates. One card cut twice, or two cards? The end-to-end ones are Brannock's shape.
* **holders under 300 words** (20): `v1-e31-t22`'s bodies holding two bodies whole that share no
  text, from its count's candidates (`scripts/count_card_boundaries.py --save-candidates`), the
  holder under 300 words. One card cut twice, or two cards? The PM's amendment of 2026-10-20.

**Nothing is asked in the terminal.** The items, numbered and in an order that does not say which
stratum each is from, go to `less -R` and nowhere else: the script refuses to run unless its output
is a terminal, and the text leaves the screen when `less` closes. The answers go on a tally sheet,
a new file outside the repository and the data directory, which holds counts and a row per item to
fill in: no card text, tag, cite, path or digest. The operator fills it in, and the session reads it.

    uv run python scripts/sample_matching_recall.py --seed 20261103 \\
        --tally-sheet ~/t29-matching-recall-tally-sheet.txt
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compare_card_clusters import (  # noqa: E402
    CardKey,
    _marked_words,
    _stored_cards,
    classify_pair,
    current_version,
    read_cards,
    render_pair,
)
from count_card_boundaries import CASELISTS, outside_the_repository_and_the_store  # noqa: E402
from count_matching_recall import CANDIDATES_SHOWN  # noqa: E402
from sample_card_boundaries import _between, _wrap  # noqa: E402

from debate_core.domain.debate_files import ParsedCard  # noqa: E402
from debate_core.evidence.near_duplicates import matching_words, shingles  # noqa: E402
from debate_core.evidence.recall_shapes import HOLDER_UNDER_WORDS, Beside  # noqa: E402
from debate_core.integrations.local.parsed_store import LocalParsedStore  # noqa: E402

__all__ = [
    "HOLDERS_SHOWN",
    "STRATA",
    "Drawn",
    "Stratum",
    "arguments_parser",
    "draw",
    "main",
    "population_of",
    "render_item",
    "run",
    "tally_sheet",
]

HOLDERS_SHOWN = "~/t29-card-boundary-candidates.jsonl"

SAME_QUESTION = "Are A and B the same card?"
SAME_ANSWERS = {"s": "same card", "d": "different card", "u": "unsure"}
CUT_TWICE_QUESTION = "A and B share no text. Are they one card cut twice, or two cards?"
CUT_TWICE_ANSWERS = {"o": "one card cut twice", "t": "two cards", "u": "unsure"}

WHOLE_HOLDER_WORDS = 400
"""A holder of up to this many words is shown whole, A and B marked; a longer one around where A
ends and B begins."""

_UNDERLINE, _REVERSE, _BOLD, _DIM, _RESET = "\x1b[4m", "\x1b[7m", "\x1b[1m", "\x1b[2m", "\x1b[0m"


@dataclass(frozen=True, slots=True)
class Stratum:
    label: str
    question: str
    answers: Mapping[str, str]
    planned: int


NEITHER_END, TRIMS_END_TO_END, TRIMS_WITH_WORDS_BETWEEN, HOLDERS_UNDER_300 = range(4)
STRATA: tuple[Stratum, ...] = (
    Stratum(
        "neither end: nine-tenths inside a body holding neither of its ends", SAME_QUESTION, SAME_ANSWERS, 20
    ),
    Stratum(
        "trims with the same tag and cite, end to end in their holder",
        CUT_TWICE_QUESTION,
        CUT_TWICE_ANSWERS,
        10,
    ),
    Stratum(
        "trims with the same tag and cite, words of the holder between or around them",
        CUT_TWICE_QUESTION,
        CUT_TWICE_ANSWERS,
        10,
    ),
    Stratum(
        "holders under 300 words of two bodies sharing no text", CUT_TWICE_QUESTION, CUT_TWICE_ANSWERS, 20
    ),
)


@dataclass(frozen=True, slots=True)
class Drawn:
    """One item: its stratum, its caselist, and the store positions it shows. For neither end, the
    body and the one holding it; otherwise the holder, then A and B."""

    stratum: int
    caselist: str
    positions: tuple[CardKey, ...]


def _key(position: Sequence[Any]) -> CardKey:
    return (str(position[0]), int(position[1]))


def population_of(
    counted: Iterable[Mapping[str, Any]],
    held: Iterable[Mapping[str, Any]],
    holder_words: Callable[[str, CardKey], int],
) -> dict[int, list[Drawn]]:
    """Each stratum's items: from `count_matching_recall`'s rows (`counted`) and `count_card_boundaries`'
    (`held`), whose holders `holder_words` measures in the clusterer's words."""
    found: dict[int, list[Drawn]] = {number: [] for number in range(len(STRATA))}
    for row in counted:
        caselist = row["caselist"]
        if row["shape"] == "neither-end":
            found[NEITHER_END].append(
                Drawn(NEITHER_END, caselist, (_key(row["cut"]), _key(row["container"])))
            )
        elif row["shape"] == "trims" and row["group"] == Beside.SAME_TAG_AND_CITE.value:
            stratum = TRIMS_END_TO_END if row["words_in_neither"] == "0" else TRIMS_WITH_WORDS_BETWEEN
            found[stratum].append(
                Drawn(stratum, caselist, tuple(_key(p) for p in (row["holder"], *row["pieces"])))
            )
    for row in held:
        if row["count"] != "two-cards-in-one" or row["group"] != "sharing nothing":
            continue
        holder = _key(row["card"])
        if holder_words(row["caselist"], holder) < HOLDER_UNDER_WORDS:
            found[HOLDERS_UNDER_300].append(
                Drawn(HOLDERS_UNDER_300, row["caselist"], (holder, *(_key(p) for p in row["pieces"])))
            )
    return found


def draw(population: Mapping[int, Sequence[Drawn]], seed: int) -> list[Drawn]:
    """Each stratum's planned number at random by `seed` (all of them when fewer), in one shuffled
    order that does not say which stratum an item is from."""
    chooser = random.Random(seed)
    drawn: list[Drawn] = []
    for number, stratum in enumerate(STRATA):
        candidates = population[number]
        drawn += chooser.sample(list(candidates), min(stratum.planned, len(candidates)))
    chooser.shuffle(drawn)
    return drawn


def _tag_and_cite(named: Sequence[tuple[str, ParsedCard]], columns: int) -> list[str]:
    """Each card's tag and its whole cite, wrapped to `columns`, never cut short: the cite is what
    tells one article from another."""
    lines: list[str] = []
    width = max(40, columns)
    for name, card in named:
        for field, text in (("tag", card.tag), ("cite", card.full_cite)):
            opening = f"{name} {field}: " if field == "tag" else f"{' ' * len(name)} {field}: "
            lines += textwrap.wrap(
                " ".join((text or "(none)").split()),
                width=width,
                initial_indent=opening,
                subsequent_indent=" " * len(opening),
                break_long_words=False,
                break_on_hyphens=False,
            )
    return lines


def _marked_holder(text: str, pieces: tuple[frozenset[str], frozenset[str]], columns: int) -> list[str]:
    """The holder with A underlined, B reversed and the words in neither in bold: whole when short,
    else around where A ends and B begins."""
    if len(text.split()) > WHOLE_HOLDER_WORDS:
        return _between(text, pieces, columns)
    in_a, in_b = (_marked_words(text, piece) for piece in pieces)
    tokens = [
        (word, _UNDERLINE if a else _REVERSE if b else _BOLD)
        for (word, a), (_, b) in zip(in_a, in_b, strict=True)
    ]
    legend = (
        f"The whole body: {_UNDERLINE}A underlined{_RESET}, {_REVERSE}B reversed{_RESET}, "
        f"{_BOLD}words in neither in bold{_RESET}."
    )
    return [legend, *_wrap(tokens, max(20, columns))]


def render_item(item: Drawn, cards: Mapping[CardKey, ParsedCard], columns: int) -> str:
    """The item for a person to judge. Shown only through `less`."""
    stratum = STRATA[item.stratum]
    if item.stratum == NEITHER_END:
        cut, container = (cards[position] for position in item.positions)
        shape, _ = classify_pair(cut, container)
        lines = [
            f"{item.caselist}. A is nine-tenths inside B, but B holds neither A's first five words nor its "
            "last five, so the matching never compares them.",
            *_tag_and_cite((("A", cut), ("B", container)), columns),
            "",
            render_pair(cut, container, shape, columns),
        ]
    else:
        holder, first, second = (cards[position] for position in item.positions)
        words = [len(card.evidence_text.split()) for card in (holder, first, second)]
        lines = [
            f"{item.caselist}. A body of {words[0]:,} words holding A, {words[1]:,} words, and B, "
            f"{words[2]:,} words, which share no text.",
        ]
        lines += _tag_and_cite((("The body", holder), ("A", first), ("B", second)), columns)
        pieces = (shingles(first.evidence_text), shingles(second.evidence_text))
        lines += ["", *_marked_holder(holder.evidence_text, pieces, columns)]
    keys = ", ".join(f"{key} {answer}" for key, answer in stratum.answers.items())
    lines += ["", f"{stratum.question} ({keys})"]
    return "\n".join(lines) + "\n"


def tally_sheet(
    items: Sequence[Drawn],
    population: Mapping[int, Sequence[Drawn]],
    *,
    seed: int,
    versions: Mapping[str, str],
) -> list[str]:
    """The sheet the operator fills in: the counts, and a row per item. No text."""
    lines = [
        f"Matching-recall sample (v1-e31-t29), seed {seed}: {len(items)} items.",
        "Store: "
        + ", ".join(f"{caselist} {version}" for caselist, version in sorted(versions.items()))
        + ".",
        "",
        "In the corpus, and drawn:",
    ]
    for number, stratum in enumerate(STRATA):
        drawn = sum(item.stratum == number for item in items)
        lines.append(f"  {stratum.label}: {len(population[number]):,} (drew {drawn} of {stratum.planned})")
    lines += [
        "",
        "For each item, under Answer, write the key it asks for: s same card, d different card, u unsure;",
        "or o one card cut twice, t two cards, u unsure. Under Notes, if anything, say what you went by,",
        "in formatting or editing terms only. No card text, no names, no tags or cites, no titles.",
        "",
        "Examples (made up):",
        "  An item asking 'same card?': A is B's middle paragraph, with a bracketed insertion where B's",
        "    first word was and a footnote number after its last; the cites name one author, year and",
        "    article.                    -> s | bracket at the start, footnote mark at the end",
        "  The same, but the cites name two different articles that quote one passage.",
        "                                -> d | one quotation in two articles; cites differ",
        "  An item asking 'one card cut twice?': A is the body's opening paragraphs, B its last two;",
        "    the words between are one argument, and nothing between looks like a cite or a tag.",
        "                                -> o | A the opening, B the close; one argument between",
        "  The same, but between A and B is a line with an author and a year, and B argues something",
        "    else.                       -> t | a second cite line between A and B",
        "  Two parts that could be either, or a cite too thin to tell articles apart.",
        "                                -> u | cite gives an author and year only",
        "",
        "Then say done in the session; nothing needs pasting.",
        "",
        "Item | Answer | Notes",
    ]
    lines += [f"{number:>4} |  |" for number in range(1, len(items) + 1)]
    lines += ["", "Strata, by item (read after answering):"]
    for number, stratum in enumerate(STRATA):
        drawn = [str(position) for position, item in enumerate(items, start=1) if item.stratum == number]
        lines.append(f"  {stratum.label}: {', '.join(drawn) or 'none'}")
    return lines


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"{path.name} does not exist: run the count that saves it first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _page(text: str) -> None:
    subprocess.run(["less", "-R"], input=text, text=True, check=False)  # noqa: S607 - the operator's pager


def run(arguments: argparse.Namespace, page: Callable[[str], None]) -> int:
    """Draw, write the sheet, then show the items through `page`."""
    sheet = outside_the_repository_and_the_store(arguments.tally_sheet, arguments.data_dir, "--tally-sheet")
    if sheet.exists():
        raise SystemExit(f"{sheet.name} exists: the tally sheet is written new, so name another file")
    store = LocalParsedStore(arguments.data_dir)
    caselists = arguments.caselist or list(CASELISTS)
    versions = {caselist: current_version(store, caselist) for caselist in caselists}
    counted = [row for row in _read_rows(arguments.candidates.expanduser()) if row["caselist"] in versions]
    held = [row for row in _read_rows(arguments.holders.expanduser()) if row["caselist"] in versions]

    holders: dict[str, set[CardKey]] = {caselist: set() for caselist in caselists}
    for row in held:
        if row["count"] == "two-cards-in-one" and row["group"] == "sharing nothing":
            holders[row["caselist"]].add(_key(row["card"]))
    words: dict[tuple[str, CardKey], int] = {}
    for caselist, keys in holders.items():
        for key, card in _stored_cards(store, caselist, versions[caselist], keys).items():
            words[(caselist, key)] = len(matching_words(card["evidence_text"]))
    population = population_of(counted, held, lambda caselist, key: words[(caselist, key)])

    seed = arguments.seed if arguments.seed is not None else random.SystemRandom().randrange(10**9)
    items = draw(population, seed)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(
        "\n".join(tally_sheet(items, population, seed=seed, versions=versions)) + "\n", encoding="utf-8"
    )

    columns = shutil.get_terminal_size().columns
    shown: list[str] = []
    for number, item in enumerate(items, start=1):
        cards = read_cards(store, item.caselist, versions[item.caselist], item.positions)
        shown.append(f"{'-' * 72}\nItem {number} of {len(items)}.\n\n{render_item(item, cards, columns)}")
    page("\n".join(shown) + f"{'-' * 72}\nThe end: fill in the tally sheet.\n")
    print(f"The tally sheet is {sheet.name}: fill in its Answer and Notes columns, then say done.")
    return 0


def arguments_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".debate-research" / "dev",
        help="The data directory whose parsed store is read. Default: the dev data directory.",
    )
    parser.add_argument(
        "--caselist", action="append", help=f"Repeat for several. Default: {', '.join(CASELISTS)}."
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path(CANDIDATES_SHOWN),
        help=f"scripts/count_matching_recall.py's saved positions. Default: {CANDIDATES_SHOWN}.",
    )
    parser.add_argument(
        "--holders",
        type=Path,
        default=Path(HOLDERS_SHOWN),
        help=f"scripts/count_card_boundaries.py's saved positions. Default: {HOLDERS_SHOWN}.",
    )
    parser.add_argument(
        "--seed", type=int, help="Draws the same items again. Default: a new one, on the sheet."
    )
    parser.add_argument(
        "--tally-sheet",
        type=Path,
        required=True,
        help="A new file outside the repository and the data directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = arguments_parser().parse_args(argv)
    if not sys.stdout.isatty():
        print(
            "The items hold card text, so they are shown only in a terminal, through less.", file=sys.stderr
        )
        return 2
    return run(arguments, _page)


if __name__ == "__main__":
    raise SystemExit(main())
