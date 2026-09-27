"""Linking abbreviated and cite-only disclosures to the full card they stand for.

Open-source disclosure rules require a team to post its cites and the first and last few words of
each card, not the card. A wiki-converted disclosure therefore arrives as a tag, a cite and
`Cities that pave … an aesthetic one.` — which the parser keeps as an `ABBREVIATED` card, or, when
even that is folded into the cite line, as `CITE_ONLY` (`v1-e31-t03`). That is still evidence that
the team read the card, and the landscape should count it. It cannot be clustered by its text,
because it has almost none; it is *linked* instead, by what it does carry.

## The link key

An abbreviated card is keyed by its **short cite** and its **opening and closing words**:

* The short cite through :func:`short_cite_key`: the fingerprint normalization, punctuation and
  apostrophes dropped, and a four-digit year reduced to its last two digits, so `Pellam 26`,
  `Pellam '26` and `PELLAM 2026` are one key. A card with no readable short cite has no key.
* The words either side of the first wiki ellipsis marker (the style profile's
  `wiki_ellipsis_markers`), read with the clusterer's word rules. When the marker is in the body,
  the words before it are the card's first words and the words after it its last. When the marker
  is only in the cite line, the words before it are the cite followed by the card's first words,
  with no telling where one ends; there, the link needs at least :data:`MIN_ANCHOR_WORDS` of them
  to line up with the start of a full card, and the same at the end.

## When it links, and when it does not

A full card *matches* when its short-cite key is equal and its body begins with the opening words
and ends with the closing words. The abbreviated card joins a cluster only when every matching full
card is in that **one** cluster. No match, or matches in two clusters, and it stays
:attr:`~debate_core.domain.card_occurrence.ClusterMembership.UNLINKED`: two cards from the same
article can share an author, a year and a stock opening, and choosing between them would be a
guess about what a team read.

Linking changes which cluster an occurrence is counted in. It never changes a cluster id (those
come from full cards only), and it never merges an abbreviated card's text into anything.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from debate_core.domain.debate_files import CardCompleteness, ParsedCard
from debate_core.evidence.fingerprints import normalize_for_matching
from debate_core.evidence.near_duplicates import matching_words
from debate_core.evidence.style_profile_loader import load_style_profile

__all__ = [
    "MIN_ANCHOR_WORDS",
    "AbbreviationAnchor",
    "FullCardWords",
    "abbreviation_anchor",
    "default_ellipsis_markers",
    "link_abbreviated",
    "short_cite_key",
]

MIN_ANCHOR_WORDS: Final = 3
"""Fewest opening words, and fewest closing words, an abbreviated card must carry to be linked."""

_FOUR_DIGIT_YEAR: Final = re.compile(r"^(?:19|20)(\d{2})$")


def default_ellipsis_markers() -> tuple[str, ...]:
    """The wiki ellipsis markers of the default style profile, which the parser also uses."""
    return load_style_profile().cite.wiki_ellipsis_markers


def short_cite_key(short_cite: str | None) -> str | None:
    """A short cite reduced to what identifies it: `Pellam '26` and `pellam 2026` are `pellam 26`."""
    if short_cite is None:
        return None
    words = [
        (year.group(1) if (year := _FOUR_DIGIT_YEAR.match(word)) else word)
        for word in re.findall(r"\w+", normalize_for_matching(short_cite).replace("'", ""))
    ]
    return " ".join(words) or None


@dataclass(frozen=True, slots=True)
class AbbreviationAnchor:
    """What an abbreviated or cite-only card can be linked by."""

    short_cite_key: str
    opening_words: tuple[str, ...]
    closing_words: tuple[str, ...]
    from_cite_line: bool
    """True when the marker was found only in the cite line, so the opening words start with cite."""


@dataclass(frozen=True, slots=True)
class FullCardWords:
    """A full card as the linker compares it: its cluster, short-cite key and body words."""

    cluster_id: str
    short_cite_key: str | None
    words: tuple[str, ...]


def abbreviation_anchor(card: ParsedCard, markers: Sequence[str] | None = None) -> AbbreviationAnchor | None:
    """The link key of an ABBREVIATED or CITE_ONLY card, or `None` when it cannot be linked."""
    if card.completeness is CardCompleteness.FULL:
        return None
    key = short_cite_key(card.short_cite)
    if key is None:
        return None
    ellipses = tuple(markers) if markers is not None else default_ellipsis_markers()
    split = _split_at_marker(card.evidence_text, ellipses)
    from_cite_line = split is None
    if split is None:
        split = _split_at_marker(card.full_cite, ellipses)
    if split is None:
        return None
    head, tail = split
    opening = tuple(matching_words(head))
    closing = tuple(matching_words(tail))
    if len(opening) < MIN_ANCHOR_WORDS or len(closing) < MIN_ANCHOR_WORDS:
        return None
    return AbbreviationAnchor(
        short_cite_key=key, opening_words=opening, closing_words=closing, from_cite_line=from_cite_line
    )


def link_abbreviated(anchor: AbbreviationAnchor, full_cards: Iterable[FullCardWords]) -> str | None:
    """The one cluster every matching full card is in, or `None` when there is not exactly one."""
    clusters = {
        full.cluster_id
        for full in full_cards
        if full.short_cite_key == anchor.short_cite_key and _matches(anchor, full.words)
    }
    if len(clusters) != 1:
        return None
    return next(iter(clusters))


def _matches(anchor: AbbreviationAnchor, body: tuple[str, ...]) -> bool:
    if anchor.from_cite_line:
        return (
            _overlap(anchor.opening_words, body, at_start=True) >= MIN_ANCHOR_WORDS
            and _overlap(anchor.closing_words, body, at_start=False) >= MIN_ANCHOR_WORDS
        )
    opening, closing = anchor.opening_words, anchor.closing_words
    if len(opening) + len(closing) > len(body):
        return False
    return body[: len(opening)] == opening and body[len(body) - len(closing) :] == closing


def _overlap(fragment: tuple[str, ...], body: tuple[str, ...], *, at_start: bool) -> int:
    """How many words of `fragment` line up with the start (or end) of `body`.

    At the start, the longest suffix of the opening fragment that is a prefix of the body: the cite
    text in front of it is skipped. At the end, the longest prefix of the closing fragment that is a
    suffix of the body: anything the cite line added after the card's last word is skipped.
    """
    for length in range(min(len(fragment), len(body)), 0, -1):
        if at_start and fragment[len(fragment) - length :] == body[:length]:
            return length
        if not at_start and fragment[:length] == body[len(body) - length :]:
            return length
    return 0


def _split_at_marker(text: str, markers: Sequence[str]) -> tuple[str, str] | None:
    """Split `text` at its first ellipsis marker, preferring the longest marker at that position."""
    best: tuple[int, int] | None = None
    for marker in markers:
        position = text.find(marker)
        if position < 0:
            continue
        candidate = (position, -len(marker))
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    position, negative_length = best
    return text[:position], text[position - negative_length :]
