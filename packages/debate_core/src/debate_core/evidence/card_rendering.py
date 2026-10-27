"""What the DOCX renderer is given for each card, beside the card itself (`v1-e06-t04`).

:func:`~debate_core.evidence.docx_renderer.render_cards_docx` renders the cards of one
:class:`~debate_core.evidence.manifest.CardManifest`. Two things it draws are decided above this
layer, by the application, and are handed to it as plain values in :class:`CardToRender`:

* the cite as text, :class:`CiteText`: the short cite and the full cite line that
  `CitationService`'s `format_cite` writes (`v1-e06-t01`);
* why a card is not VERIFIED, as reason codes: `CardService`'s failure reasons (`v1-e06-t02`), or
  the verifier's codes. Only codes are accepted, upper-case words joined by underscores, so a banner
  can never carry a sentence, and with it a word of the snapshot.

Two texts are decided here, from those values and the card alone:

* :func:`banner_text`, the banner over every card that is not VERIFIED: its status, "not a finished
  card", and its reason codes, as the spec words it ("UNVERIFIED — not a finished card: <reasons>");
* :func:`cite_marks`, one mark per cite field the cite shows without verifying, from the citation's
  own flags: "[author unverified]" for a field shown unverified, or a required field that is not
  verified at all; "[author cleared by student]" for a field the student's last cite edit emptied
  (`Citation.cleared_by_student`), which is the student's decision, not a failure to verify.

This module imports no document library, so the application layer can build these values and
`v1-e06-t07`'s reader can share them without reaching python-docx (the import contract "Document
libraries stay inside debate_core.integrations.docx_parser" holds `debate_core.application` off it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from debate_core.domain import Card, Citation, CitationField, VerificationStatus
from debate_core.domain.citation import CITATION_FIELD_NAMES, REQUIRED_CITATION_FIELDS

__all__ = [
    "CITE_FIELD_LABELS",
    "CardToRender",
    "CiteText",
    "DocumentHeadings",
    "RenderRefused",
    "banner_text",
    "cite_marks",
]

REASON_CODE: Final = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
"""A failure reason as a program reads it: `CITATION_UNVERIFIED`, `TEXT_MISMATCH`."""

CITE_FIELD_LABELS: Final = {
    "authors": "author",
    "author_credentials": "credentials",
    "title": "title",
    "publication": "publication",
    "published_at": "date",
    "canonical_url": "URL",
    "accessed_at": "accessed date",
}
"""How a mark names each cite field, in cite order."""


class RenderRefused(ValueError):
    """The cards cannot be rendered as given. Nothing was written."""


@dataclass(frozen=True, slots=True)
class CiteText:
    """A card's cite as the application formatted it: the short cite, and the full line it begins."""

    short_cite: str
    full_cite: str

    def __post_init__(self) -> None:
        if not self.short_cite.strip():
            raise RenderRefused("a cite has a short cite to read out; this one is empty")
        if not self.full_cite.startswith(self.short_cite):
            raise RenderRefused("the full cite line begins with its short cite, as format_cite writes it")

    @property
    def cite_line(self) -> str:
        """What follows the short cite on the full cite line: the bracketed details, if any."""
        return self.full_cite[len(self.short_cite) :]


@dataclass(frozen=True, slots=True)
class CardToRender:
    """One card of the manifest, with its cite text and, unless it is VERIFIED, why it is not."""

    card: Card
    cite: CiteText
    unverified_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        not_codes = [reason for reason in self.unverified_reasons if not REASON_CODE.match(reason)]
        if not_codes:
            raise RenderRefused(
                f"card {self.card.card_id}: a reason is a code such as CITATION_UNVERIFIED, "
                f"not {len(not_codes)} other string(s)"
            )
        if self.card.verification_status is VerificationStatus.VERIFIED and self.unverified_reasons:
            raise RenderRefused(f"card {self.card.card_id} is VERIFIED, so nothing says why it is not")
        if self.card.verification_status is not VerificationStatus.VERIFIED and not self.unverified_reasons:
            raise RenderRefused(
                f"card {self.card.card_id} is {self.card.verification_status.value}, and its banner must "
                "name why: give at least one reason code"
            )


@dataclass(frozen=True, slots=True)
class DocumentHeadings:
    """The pocket, hat and block the cards are filed under, each optional, written once at the top."""

    pocket: str | None = None
    hat: str | None = None
    block: str | None = None


def banner_text(item: CardToRender) -> str | None:
    """The banner over `item`'s card, or None for a VERIFIED card, which has none."""
    status = item.card.verification_status
    if status is VerificationStatus.VERIFIED:
        return None
    return f"{status.value} — not a finished card: {', '.join(item.unverified_reasons)}"


def cite_marks(citation: Citation) -> tuple[str, ...]:
    """A mark for each cite field shown unverified or cleared by the student, in cite order."""
    marks: list[str] = []
    for name in CITATION_FIELD_NAMES:
        field: CitationField[object] = getattr(citation, name)
        label = CITE_FIELD_LABELS[name]
        if name in citation.cleared_by_student:
            marks.append(f"[{label} cleared by student]")
        elif not field.verified and (field.is_present or name in REQUIRED_CITATION_FIELDS):
            marks.append(f"[{label} unverified]")
    return tuple(marks)
