"""Exact card fingerprints, and the matching-only normalization they are computed under.

Two teams that disclose the same card almost never disclose the same *bytes*. One pasted it from a
PDF with curly quotes, the other retyped the quotation marks; one re-flowed the paragraph, the
other kept the publisher's line breaks; both wrote their own tag and highlighted different words.
The exact fingerprint is the SHA-256 of the card body after a normalization that erases exactly
those differences and no others, so any change to the *words* of the evidence still changes it.

## The fingerprint normalization (version :data:`FINGERPRINT_VERSION`)

Applied in this order, by :func:`normalize_for_matching`:

1. **Unicode NFKC.** Compatibility forms fold to their plain equivalents: the `ﬁ` ligature becomes
   `fi`, a non-breaking space becomes a space, full-width letters become ASCII.
2. **Casefold.** `Growth`, `GROWTH` and `growth` are one word.
3. **Quotes unified.** Every single quotation mark, apostrophe and prime becomes `'`; every double
   quotation mark and double prime becomes `"`.
4. **Dashes unified.** Hyphen, non-breaking hyphen, figure dash, en dash, em dash, horizontal bar,
   minus sign and their small and full-width forms all become `-`.
5. **Invisible characters removed.** Soft hyphen, zero-width space, zero-width joiner and
   non-joiner, word joiner and the byte-order mark: characters a reader cannot see.
6. **Whitespace collapsed.** Every run of whitespace, line breaks included, becomes one space, and
   the ends are trimmed.

What is *not* normalized is as deliberate: punctuation other than quotes and dashes, digits, and
every letter. `the plan fails` and `the plan fail` have different fingerprints, which is ac1's
"differ when a word of evidence changes".

**Tags and cites are excluded.** A card's identity is its evidence body, because teams re-tag and
re-cite the same card constantly. The one exception is a `CITE_ONLY` card, which has no body; its
fingerprint is taken over its normalized cite line and says so in
:attr:`~debate_core.domain.card_occurrence.CardFingerprint.basis`, under a distinct prefix so it can
never collide with a body's digest.

**Highlighting and formatting are not text.** A :class:`~debate_core.domain.debate_files.ParsedCard`
keeps emphasis as offsets beside its `evidence_text`, so a re-highlighted copy has the same text and
therefore the same fingerprint without anything here having to know about highlighting.

## Matching only

Nothing this module returns is evidence text. :func:`normalize_for_matching` exists to be hashed
and shingled, and its output is never stored, displayed or written back over a card (the task's
forbidden list; architecture proposal §8). Stored and displayed evidence is always the parser's
exact copy.

## Changing the rules

Any change to the normalization changes digests, so it bumps :data:`FINGERPRINT_VERSION`, and every
fingerprint carries the version it was computed under. A consumer that compares fingerprints of two
versions is comparing two different functions.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Final

from debate_core.domain.card_occurrence import (
    CUTTER_MARK_MAX_LENGTH,
    CardFingerprint,
    FingerprintBasis,
)
from debate_core.domain.debate_files import CardCompleteness, ParsedCard

__all__ = [
    "FINGERPRINT_VERSION",
    "card_fingerprint",
    "extract_cutter_mark",
    "fingerprint_text",
    "normalize_for_matching",
]

FINGERPRINT_VERSION: Final = "card-fingerprint-v1"
"""Version of the normalization rules above. Bumped by any change that can change a digest."""

_SINGLE_QUOTES: Final = "\u2018\u2019\u201a\u201b\u2032\u2035`\u00b4\u02bc\uff07"
_DOUBLE_QUOTES: Final = "\u201c\u201d\u201e\u201f\u2033\u2036\u00ab\u00bb\uff02"
_DASHES: Final = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
_INVISIBLE: Final = "\u00ad\u200b\u200c\u200d\u2060\ufeff"

_TRANSLATION: Final = str.maketrans(
    {
        **dict.fromkeys(_SINGLE_QUOTES, "'"),
        **dict.fromkeys(_DOUBLE_QUOTES, '"'),
        **dict.fromkeys(_DASHES, "-"),
        **dict.fromkeys(_INVISIBLE, None),
    }
)

_WHITESPACE_RUN: Final = re.compile(r"\s+")

#: Prefix on the hashed input of a CITE_ONLY card, so a cite line can never share a body's digest.
_CITE_LINE_DOMAIN: Final = "cite-line\x00"


def normalize_for_matching(text: str) -> str:
    """Apply the fingerprint normalization to `text`. For hashing and shingling only.

    The result is never evidence: it is lowercased, its quotes and dashes are rewritten and its
    line breaks are gone. Callers hash it or split it into words; they do not keep it.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    # NFKC can itself produce a character the translation table maps (a full-width dash, say),
    # and casefold never produces one, so one translation after both is enough.
    unified = folded.translate(_TRANSLATION)
    return _WHITESPACE_RUN.sub(" ", unified).strip()


def fingerprint_text(text: str) -> str:
    """SHA-256 hex digest of `text` under the fingerprint normalization."""
    return hashlib.sha256(normalize_for_matching(text).encode("utf-8")).hexdigest()


def card_fingerprint(card: ParsedCard) -> CardFingerprint:
    """The exact fingerprint of one parsed card.

    The evidence body for a FULL or ABBREVIATED card; the cite line, under its own prefix, for a
    CITE_ONLY card. Tag, undertag and formatting never contribute.
    """
    if card.completeness is CardCompleteness.CITE_ONLY:
        payload = _CITE_LINE_DOMAIN + normalize_for_matching(card.full_cite)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return CardFingerprint(
            exact_fingerprint=digest,
            fingerprint_version=FINGERPRINT_VERSION,
            basis=FingerprintBasis.CITE_LINE,
        )
    return CardFingerprint(
        exact_fingerprint=fingerprint_text(card.evidence_text),
        fingerprint_version=FINGERPRINT_VERSION,
        basis=FingerprintBasis.EVIDENCE_BODY,
    )


# ------------------------------------------------------------------------------------------------
# Cutter marks
# ------------------------------------------------------------------------------------------------

#: `// JD` or `//ab/cd` closing the cite: the convention debaters use to sign what they cut.
_CUTTER_MARK_TAIL: Final = re.compile(r"//\s*(?P<mark>[^\s/][^\s]*)\s*$")


def extract_cutter_mark(full_cite: str) -> str | None:
    """The cutter mark closing a cite line, verbatim, or `None` when there is not one.

    Only the explicit convention is recognised: a `//` followed by one token at the very end of
    the cite (`… accessed 9-3-2026 //QX`). A bare trailing word is not taken for a mark, because
    it is as likely to be the end of a title or a URL; a mark that is not recognised is simply not
    recorded, which is the safe failure for something that identifies a student.

    The mark is returned exactly as written and nothing is done with it here or anywhere else:
    no expansion, no lookup, no normalization. A token longer than
    :data:`~debate_core.domain.card_occurrence.CUTTER_MARK_MAX_LENGTH` is not a mark and is
    dropped rather than truncated.
    """
    lines = [line for line in full_cite.splitlines() if line.strip()]
    if not lines:
        return None
    match = _CUTTER_MARK_TAIL.search(lines[-1])
    if match is None:
        return None
    mark = match.group("mark")
    # A URL ends a cite far more often than a signature does: `https://example.org/a` has a `//`.
    if match.start() > 0 and lines[-1][match.start() - 1] == ":":
        return None
    if len(mark) > CUTTER_MARK_MAX_LENGTH:
        return None
    return mark
