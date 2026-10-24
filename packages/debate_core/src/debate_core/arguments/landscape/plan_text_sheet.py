"""The coach's sheet of plan texts, clustered by the mechanism words that tell them apart (`v1-e32-t09` ac2).

The coach names each single-payer mechanism as a child aff with tag keywords he supplies. He needs to
see what plans teams read, grouped by what differs between them, and not one team's file. So
:func:`cluster_plan_texts` takes every affirmative document's plan texts as words and:

1. **drops the frame**: a short list of English joining words, and every word in at least
   `frame_share` of all plan texts, 80% by default (`united`, `states`, `federal`, `government`,
   `should`, and the like). What is left of a plan text is its **mechanism words**;
2. **groups plan texts by their mechanism words**, then merges a group into an earlier, larger one
   whose words it shares at `similarity` or more (Jaccard), largest groups first, so one word's edit
   does not make a new cluster;
3. **counts each cluster** by documents and by distinct teams, with the aff its plan texts name (or
   `none`), the words every plan text in it holds, and the words only some do;
4. **shows each cluster's commonest plan text word for word**, with how many of its documents hold it
   exactly, and lists one-team clusters too (the PM's review ruling 1 of 2026-10-24, under data-use
   policy 1.13). A plan text that names a school of the caselist is never shown, and no school or team
   is named beside a text. With `minimum_teams` above one, a cluster fewer teams read is withheld,
   counted and not shown.

Every school the caselist names, with its codes beside it, is taken out of the words first
(:class:`~debate_core.arguments.landscape.source_headings.CaselistNames`). Teams are opaque identities
and are only ever counted. :func:`render_plan_text_sheet` writes the sheet and :func:`write_answers_csv`
the CSV the coach fills (a mechanism name and tag keywords per cluster). Both go outside the repository:
they hold the teams' own words. A cluster's text is the one most of its documents hold, ties going to the
shorter, then to the first in order. Deterministic and pure.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import reduce
from typing import Final, TextIO

from debate_core.arguments.landscape.plan_text import JOINING_WORDS
from debate_core.arguments.landscape.source_headings import CaselistNames

__all__ = [
    "ANSWERS_FILE",
    "ANSWER_COLUMNS",
    "DEFAULT_FRAME_SHARE",
    "DEFAULT_MINIMUM_TEAMS",
    "DEFAULT_SIMILARITY",
    "PlanTextCluster",
    "PlanTextSheet",
    "PlanTextWords",
    "cluster_plan_texts",
    "render_plan_text_sheet",
    "write_answers_csv",
]

DEFAULT_MINIMUM_TEAMS: Final = 1
"""Every cluster is listed, a single team's too (the PM's review ruling 1, 2026-10-24)."""
DEFAULT_FRAME_SHARE: Final = 0.8
"""Nearly every plan text: a mechanism most teams read (single payer) stays a mechanism word."""
DEFAULT_SIMILARITY: Final = 0.75
ANSWERS_FILE: Final = "plan-text-answers.csv"
ANSWER_COLUMNS: Final = (
    "cluster",
    "teams",
    "documents",
    "aff_named",
    "words_in_every_plan_text",
    "mechanism_name",
    "tag_keywords",
)
_NONE: Final = "none"
_MARKDOWN_SPECIAL: Final = re.compile(r"([\\`*_\[\]<>|#])")


@dataclass(frozen=True, slots=True)
class PlanTextWords:
    """One affirmative document's plan texts as words, with its teams and the aff they name."""

    source_sha256: str
    teams: frozenset[str] = field(repr=False)
    named: str | None
    """The aff the document's plan texts name, or None."""
    words: tuple[str, ...] = field(repr=False)
    """Its plan texts' lowercase words, one plan text after another."""
    texts: tuple[str, ...] = field(default=(), repr=False)
    """Its plan texts word for word, as the file holds them (data-use policy 1.13)."""


@dataclass(frozen=True, slots=True)
class PlanTextCluster:
    label: str
    """`C01`, `C02`, ... in the sheet's order: most teams first."""
    documents: int
    teams: int
    named: tuple[str, ...]
    """The affs its documents' plan texts name, `none` for those naming none, most documents first."""
    shared_words: tuple[str, ...] = field(repr=False)
    """Mechanism words every plan text in the cluster holds."""
    other_words: tuple[str, ...] = field(repr=False)
    """Mechanism words only some hold, most documents first."""
    text: str | None = field(default=None, repr=False)
    """Its commonest plan text naming no school, whitespace made single; None when none can be shown."""
    text_documents: int = 0
    """The cluster's documents that hold :attr:`text` exactly."""


@dataclass(frozen=True, slots=True)
class PlanTextSheet:
    clusters: tuple[PlanTextCluster, ...] = field(repr=False)
    """The clusters at least `minimum_teams` teams read, most teams first."""
    documents: int
    teams: int
    frame_words: tuple[str, ...]
    frame_share: float
    withheld_clusters: int
    withheld_documents: int
    minimum_teams: int
    school_texts: int = 0
    """Documents whose plan text names a school of the caselist, so is never shown."""


def cluster_plan_texts(
    items: Sequence[PlanTextWords],
    names: CaselistNames,
    *,
    minimum_teams: int = DEFAULT_MINIMUM_TEAMS,
    frame_share: float = DEFAULT_FRAME_SHARE,
    similarity: float = DEFAULT_SIMILARITY,
) -> PlanTextSheet:
    """`items`' plan texts grouped by their mechanism words, the clusters fewer teams read withheld."""
    scrubbed = [
        (one, frozenset(names.without_schools(" ".join(one.words)).split()) - JOINING_WORDS) for one in items
    ]
    counts = Counter(word for _, words in scrubbed for word in words)
    frame = frozenset(word for word, count in counts.items() if count >= frame_share * len(scrubbed))
    groups: dict[frozenset[str], list[PlanTextWords]] = defaultdict(list)
    for one, words in scrubbed:
        groups[words - frame].append(one)
    ordered = sorted(groups.items(), key=lambda group: (*_rank(group[1]), sorted(group[0])))
    merged: list[tuple[frozenset[str], list[tuple[frozenset[str], PlanTextWords]]]] = []
    for words, members in ordered:
        home = next((cluster for cluster in merged if _jaccard(cluster[0], words) >= similarity), None)
        if home is None:
            merged.append((words, [(words, one) for one in members]))
        else:
            home[1].extend((words, one) for one in members)
    texts = {id(one): _showable_texts(one, names) for one in items}
    shown: list[PlanTextCluster] = []
    withheld_clusters = withheld_documents = 0
    for _, members in sorted(
        merged, key=lambda cluster: (*_rank([one for _, one in cluster[1]]), sorted(cluster[0]))
    ):
        documents = [one for _, one in members]
        teams = frozenset(team for one in documents for team in one.teams)
        if len(teams) < minimum_teams:
            withheld_clusters += 1
            withheld_documents += len(documents)
            continue
        shared: frozenset[str] = reduce(frozenset[str].__and__, (words for words, _ in members))
        some = Counter(word for words, _ in members for word in words - shared)
        named = Counter(one.named or _NONE for one in documents)
        held = Counter(text for one in documents for text in set(texts[id(one)][0]))
        text = min(held, key=lambda found: (-held[found], len(found), found)) if held else None
        shown.append(
            PlanTextCluster(
                label=f"C{len(shown) + 1:02d}",
                documents=len(documents),
                teams=len(teams),
                named=tuple(sorted(named, key=lambda aff: (-named[aff], aff))),
                shared_words=tuple(sorted(shared)),
                other_words=tuple(sorted(some, key=lambda word: (-some[word], word))),
                text=text,
                text_documents=held[text] if text is not None else 0,
            )
        )
    return PlanTextSheet(
        clusters=tuple(shown),
        documents=len(items),
        teams=len(frozenset(team for one in items for team in one.teams)),
        frame_words=tuple(sorted(frame)),
        frame_share=frame_share,
        withheld_clusters=withheld_clusters,
        withheld_documents=withheld_documents,
        minimum_teams=minimum_teams,
        school_texts=sum(1 for one in items if texts[id(one)][1]),
    )


def render_plan_text_sheet(
    sheet: PlanTextSheet, *, caselist: str, taxonomy_version: str, through: str
) -> str:
    """The coach's sheet as Markdown: counts first, then one row per cluster shown."""
    rows = [
        f"| {one.label} | {one.teams} | {one.documents} | {', '.join(one.named)} | "
        f"{', '.join(one.shared_words)} | {', '.join(one.other_words)} |".replace("|  |", "| |")
        for one in sheet.clusters
    ]
    withheld = sheet.withheld_clusters
    frame = ", ".join(sheet.frame_words) or "none"
    withheld_lines = (
        [
            f"{_plural(withheld, 'cluster')} ({_plural(sheet.withheld_documents, 'document')}) read by "
            f"fewer than {sheet.minimum_teams} teams {'is' if withheld == 1 else 'are'} counted here and not "
            "shown: one team's plan text can point at the team.",
            "",
        ]
        if withheld
        else []
    )
    lines = [
        f"# Plan texts on {caselist}, through {through}",
        "",
        f"Taxonomy {taxonomy_version}. {_plural(sheet.documents, 'affirmative document')} with a plan text, "
        f"disclosed by {_plural(sheet.teams, 'team')}.",
        "",
        f"Words in at least {sheet.frame_share:.0%} of all plan texts are left out as the frame plans "
        f"share: {frame}. What is left of a plan text is its mechanism words, and plan texts are grouped "
        "by them. A cluster's documents all hold its first column of words; some hold the second.",
        "",
        *withheld_lines,
        "| Cluster | Teams | Documents | Aff its plan texts name | Words in every plan text "
        "| Words in some |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        *_text_section(sheet),
        "For each cluster that is a mechanism of its aff, write a short name in sentence case and the "
        f"tag keywords that mark it in `{ANSWERS_FILE}` beside this sheet. Leave a row blank to keep it "
        "under its aff.",
    ]
    return "\n".join(lines) + "\n"


def write_answers_csv(sheet: PlanTextSheet, stream: TextIO) -> None:
    """One row per cluster shown, with a blank mechanism name and blank tag keywords for the coach."""
    writer = csv.writer(stream)
    writer.writerow(ANSWER_COLUMNS)
    for one in sheet.clusters:
        writer.writerow(
            [one.label, one.teams, one.documents, " ".join(one.named), " ".join(one.shared_words), "", ""]
        )


def _text_section(sheet: PlanTextSheet) -> list[str]:
    """Each shown cluster's plan text, word for word, with the documents that hold it exactly."""
    if not sheet.clusters:
        return []
    lines = [
        "## The plan texts",
        "",
        "Each cluster's commonest plan text, word for word as its files hold it, and how many of the "
        "cluster's documents hold it exactly. No team or school is named beside a text, and a plan text "
        f"that names a school of the caselist is not shown ({_plural(sheet.school_texts, 'document')} here).",
        "",
    ]
    for one in sheet.clusters:
        lines += [f"### {one.label}: {_plural(one.teams, 'team')}, {_plural(one.documents, 'document')}", ""]
        if one.text is None:
            lines += ["No plan text of this cluster can be shown: each names a school of the caselist.", ""]
            continue
        quoted = _MARKDOWN_SPECIAL.sub(r"\\\1", one.text)
        lines += [
            f"> {quoted}",
            "",
            f"Held exactly by {one.text_documents} of its {_plural(one.documents, 'document')}.",
            "",
        ]
    return lines


def _showable_texts(one: PlanTextWords, names: CaselistNames) -> tuple[tuple[str, ...], bool]:
    """`one`'s plan texts with single spaces, those naming a school left out; and whether any did."""
    kept: list[str] = []
    named_a_school = False
    for text in one.texts:
        words = " ".join(re.findall(r"[0-9a-z]+", text.casefold()))
        if names.without_schools(words) != words:
            named_a_school = True
        else:
            kept.append(" ".join(text.split()))
    return tuple(kept), named_a_school


def _rank(documents: Sequence[PlanTextWords]) -> tuple[int, int]:
    """Most teams first, then most documents."""
    return (-len(frozenset(team for one in documents for team in one.teams)), -len(documents))


def _jaccard(one: frozenset[str], other: frozenset[str]) -> float:
    union = one | other
    return len(one & other) / len(union) if union else 1.0


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
