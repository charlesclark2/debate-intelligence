#!/usr/bin/env python3
"""The tags a landscape report's tables quote that hold a caselist word, counted (`v1-e32-t28`).

Three tables quote a tag per row: the impact table's Tag column (and impact_cards.csv's `tag`, the same
rows), the link-chain table and top_cards.csv. This counts, per table, the tags as parsed holding a word
of a caselist school, team code or tournament, by the kind of word matched:

* **school word**: a word of a school's name over three characters;
* **team-code shape**: a word of a team code, at any length;
* **tournament word**: a word of a tournament's name over three characters.

Since the PM's ruling (b) of 2026-10-27, the report withholds a tag holding a school word or a team code
(`caselist_words`) and leaves its cell empty, and withholds no tournament's word. Each line also says how
many tags the report withheld; a report that withheld other tags than those is refused. A tag may hold
words of two kinds, so the kinds may add up to more than the tags. It also prints how many tags the
most-matched word holds, since the PM's question was whether a few ordinary words are most of it.

By default it prints counts only: no word, tag, school or team code. `--show-words` adds each matched word,
its kind and how many tags of each table hold it, for the operator's screen and the coach's eyes only:
never paste them into a report, a log or a commit.

It reads the working copy as `v1-e32-t25`'s counts did, wired by hand: the parsed store, the
classification cache through the run's read-only view, no container, no worker pool, no aff
assignments and no analytic texts. It writes nothing and calls no model.

    uv run python scripts/landscape_table_tag_words.py --data-dir ~/.debate-research/dev \
        --caselist hspolicy26 --through 2026-10-20
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

from debate_core.application.errors import DomainError
from debate_core.arguments.landscape.link_chains import MINIMUM_WITHHELD_WORD, caselist_words, is_withheld
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape_report import LandscapeCard, LandscapeReport, TopCard

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"
KINDS: tuple[str, ...] = ("school word", "team-code shape", "tournament word")


def _plain_words(text: str) -> list[str]:
    """A text's words as `is_withheld` reads them: letters and digits, without case."""
    return re.findall(r"[0-9a-z]+", text.casefold())


def words_by_kind(disclosures: Iterable[Disclosure]) -> dict[str, frozenset[str]]:
    """The caselist's withholding words, split by where each came from; together, `caselist_words`'."""
    found: dict[str, set[str]] = {kind: set() for kind in KINDS}
    for one in disclosures:
        found["school word"] |= {w for w in _plain_words(one.school) if len(w) >= MINIMUM_WITHHELD_WORD}
        found["team-code shape"] |= set(_plain_words(one.team_code))
        found["tournament word"] |= {
            w for w in _plain_words(one.tournament or "") if len(w) >= MINIMUM_WITHHELD_WORD
        }
    return {kind: frozenset(words) for kind, words in found.items()}


def tables(report: LandscapeReport) -> dict[str, Sequence[TopCard]]:
    """Each table's rows, as the report holds them."""
    return {
        "Impact table (report.md's Tag column, impact_cards.csv's tag)": report.impact_cards,
        "Link-chain table": report.chain_cards,
        "top_cards.csv": report.top_cards,
    }


def parsed_tags(rows: Sequence[TopCard], cards: Iterable[LandscapeCard]) -> list[tuple[str | None, bool]]:
    """Each row's tag as parsed, from the card it shows, and whether the report left it out.

    A row names its card by its file's content-addressed key, which ends in the file's digest, and the
    card's first paragraph.
    """
    by_key = {(card.source_sha256, card.element_index): card for card in cards}
    found: list[tuple[str | None, bool]] = []
    for row in rows:
        card = by_key.get((row.source_object_key.rsplit("/", 1)[-1], row.element_index))
        if card is None:
            raise ValueError(f"no card for {row.position_id} rank {row.rank}")
        found.append((card.tag, row.tag is None and card.tag is not None))
    return found


def _matched(tags: Sequence[str | None], words: frozenset[str]) -> tuple[list[str], Counter[str]]:
    """The tags holding a word of `words`, and how many of them hold each word."""
    held = [tag for tag in tags if tag and tag.strip() and is_withheld(tag, words)]
    by_word: Counter[str] = Counter()
    for tag in held:
        by_word.update(set(_plain_words(tag)) & words)
    return held, by_word


def _share(part: int, whole: int) -> str:
    return f" ({100 * part / whole:.1f}%)" if whole else ""


def report_lines(
    report: LandscapeReport,
    disclosures: Sequence[Disclosure],
    cards: Iterable[LandscapeCard],
    *,
    show_words: bool = False,
) -> list[str]:
    """Counts per table, and with `show_words` each matched word under its table."""
    withheld_words = caselist_words(disclosures)
    kinds = words_by_kind(disclosures)
    if kinds["school word"] | kinds["team-code shape"] != withheld_words:
        raise ValueError("the school words and team codes are not the words the report withholds")
    words = frozenset().union(*kinds.values())
    header = report.header
    lines = [
        f"Tags the tables quote that hold a caselist word: {header.caselist} through "
        f"{header.snapshot.isoformat()}, taxonomy {header.taxonomy_version}.",
        f"Caselist words: {len(words)}; "
        + ", ".join(f"{kind} {len(kinds[kind])}" for kind in KINDS)
        + f"; in two kinds or more {sum(sum(w in kinds[k] for k in KINDS) > 1 for w in words)}; "
        f"withheld, the school words and team codes: {len(withheld_words)}.",
    ]
    if show_words:
        lines.append(
            "The words below are for this screen only: never paste them into a report, a log or a commit."
        )
    cards = tuple(cards)
    for name, rows in tables(report).items():
        found = parsed_tags(rows, cards)
        tags = [tag for tag, _ in found]
        quoted = [tag for tag in tags if tag and tag.strip()]
        held, by_word = _matched(tags, words)
        withheld = [tag for tag in held if is_withheld(tag, withheld_words)]
        if sorted(withheld) != sorted(tag for tag, left_out in found if left_out and tag):
            raise ValueError(f"{name}: the report withheld other tags than those holding a withheld word")
        by_kind = Counter(kind for tag in held for kind in KINDS if set(_plain_words(tag)) & kinds[kind])
        top = by_word.most_common(1)
        lines.append(
            f"{name}: {len(rows)} rows, {len(quoted)} with a tag, {len(held)} holding a word of a caselist "
            f"school, team code or tournament{_share(len(held), len(quoted))}, {len(withheld)} of them "
            f"withheld{_share(len(withheld), len(quoted))}; by kind of word: "
            + ", ".join(f"{kind} {by_kind[kind]}" for kind in KINDS)
            + f"; the most-matched word is in {top[0][1] if top else 0}."
        )
        if show_words:
            lines += [
                f"  {word} ({', '.join(kind for kind in KINDS if word in kinds[kind])}): {count}"
                for word, count in sorted(by_word.items(), key=lambda one: (-one[1], one[0]))
            ]
    return lines


async def _run(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    # Imported here: wired by hand over the working copy, as `v1-e32-t25`'s counts were.
    from debate_core.application.caselist.evidence_listing import LocalEvidence
    from debate_core.application.caselist.suppression import RecordedSuppressionList
    from debate_core.application.landscape_report import (
        LandscapeReportInputs,
        LandscapeReportService,
        landscape_cards,
    )
    from debate_core.application.landscape_run import (
        _ReadOnlyClassifications,  # pyright: ignore[reportPrivateUsage]
    )
    from debate_core.application.landscape_seeding import read_seed_sources
    from debate_core.application.landscape_staleness import LandscapeStaleness
    from debate_core.application.position_classification import PositionClassificationService
    from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD
    from debate_core.integrations.landscape.classification_store import LocalClassificationStore
    from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
    from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
    from debate_core.integrations.local.parsed_store import LocalParsedStore
    from debate_core.integrations.local.suppression_list import local_suppression_list_file

    data_dir: Path = arguments.data_dir.expanduser()
    caselist: str = arguments.caselist
    through: date = arguments.through
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    taxonomies = YamlTaxonomyRepository.load(arguments.config_dir)
    resolved = taxonomies.resolve(caselist, through)
    if resolved is None or resolved.taxonomy is None:
        print(
            f"Refused: no topic with a taxonomy covers {caselist} on {through.isoformat()}.", file=sys.stderr
        )
        return 2
    store = LocalParsedStore(data_dir)
    reading = await read_seed_sources(
        store=store,
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic=resolved.topic,
        caselist=caselist,
        through=through,
    )
    run = await PositionClassificationService(
        taxonomies=taxonomies,
        store=_ReadOnlyClassifications(LocalClassificationStore(data_dir)),
        review_threshold=DEFAULT_REVIEW_THRESHOLD,
    ).classify(reading)
    occurrences = await store.read_occurrences(caselist, reading.version) or ()
    inputs = LandscapeReportInputs(
        caselist=caselist,
        through=through,
        taxonomy=resolved.taxonomy,
        overrides=taxonomies.overrides(resolved.topic.id),
        parser_version="-",
        classifications=run.classifications,
        disclosures=reading.disclosures,
        cards=landscape_cards(reading.sources, occurrences, reading.caselist_names),
    )
    staleness = LandscapeStaleness(caselist=caselist, report_date=through, newest_snapshot=through)
    report = LandscapeReportService().build(inputs, staleness)
    for line in report_lines(report, reading.disclosures, inputs.cards, show_words=arguments.show_words):
        print(line)
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir", type=Path, required=True, help="The working copy, e.g. ~/.debate-research/dev."
    )
    parser.add_argument("--caselist", required=True, help="The caselist slug.")
    parser.add_argument("--through", type=date.fromisoformat, required=True, help="YYYY-MM-DD.")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml. Default: config/landscape.",
    )
    parser.add_argument(
        "--show-words",
        action="store_true",
        help="Also print each matched word, for the operator's screen only.",
    )
    arguments = parser.parse_args(argv)
    try:
        return asyncio.run(_run(arguments))
    except (DomainError, ValueError, OSError) as error:
        print(f"Refused: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
