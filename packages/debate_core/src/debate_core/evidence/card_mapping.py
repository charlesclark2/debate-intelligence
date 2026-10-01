"""From an extracted selection and its markup to a card: the one place that offset arithmetic lives.

`v1-e03-t03` describes a selection in snapshot coordinates: an
:class:`~debate_core.evidence.extractor.ExtractedEvidence` of segments with cuts between them, and a
:class:`~debate_core.evidence.markup.CardMarkup` of spans over those segments. A
:class:`~debate_core.domain.Card` records the same evidence the way ADR-0018 settles it: an
envelope in the snapshot, the omissions inside it, ``evidence_text`` (the envelope minus the
omissions, joined with nothing) and :class:`~debate_core.domain.CardSpan` offsets into that text.
:func:`place_evidence_on_card` converts one into the other, and nothing else in the tree does
(`v1-e03-t07` ac3; ``tests/evidence/test_card_mapping.py`` scans for a second copy).

## The calculation

A snapshot offset ``s`` inside a kept segment is, in ``evidence_text``,
``s - start - (total length of the omissions that end at or before s)``, where ``start`` is where
the envelope begins. :func:`_evidence_offset` is that sentence and is the only code that applies it.

It is only asked about offsets a :class:`CardMarkup` has already checked: every markup span lies
inside a single segment, so its start and end are each inside, or at the edge of, one segment and
never inside an omission. An end equal to a segment's end counts only the omissions before that
segment, because the omission after it starts there and has not ended.

## Touching spans on either side of a cut are not merged

An underline that ends where a segment ends and another that starts where the next one begins
become two spans that touch in ``evidence_text``. The domain allows that (two spans of one style may
touch; they may not share a character), and they stay two spans, one per markup span, because:

* each keeps its own ``purpose``; two spans that touch may do different argumentative work, and a
  merged span would have to drop one;
* each card span then lies inside the text of one segment, so it maps back onto exactly the snapshot
  characters it was made from and never across a cut. An edit (`v1-e03-t05`) that recomputes a
  card from the snapshot can carry each span over without splitting it;
* the exporter has to break a mark at a cut anyway to place the ellipsis, so a merged span would be
  split again at render time.

## What is not decided here

Nothing is compared with the snapshot here beyond what :class:`ExtractedEvidence` already proved
when it was built. Verification is :mod:`debate_core.evidence.verifier`'s job, and the card this
returns is ``UNVERIFIED`` until the verifier says otherwise. How a cut is rendered is the
exporter's (E06).
"""

from __future__ import annotations

from debate_core.domain import Card, CardOmission, CardSpan, VerificationStatus
from debate_core.evidence.extractor import ExtractedEvidence
from debate_core.evidence.markup import CardMarkup
from debate_core.evidence.verifier import evidence_text_of

__all__ = ["place_evidence_on_card"]


def place_evidence_on_card(card: Card, markup: CardMarkup) -> Card:
    """Return ``card`` holding the evidence and markup of ``markup``, and nothing it held before.

    Sets the envelope, ``omitted_ranges``, ``evidence_text``, the spans, and the snapshot id, text hash
    and normalizer version the offsets refer to, all from ``markup.evidence``. The card's identity,
    tag, citation and provenance are kept. Its verification status is reset to ``UNVERIFIED``: new
    evidence has not been verified, whatever the card held before.

    Raises :class:`ValueError` if the card cites a different article from the one the snapshot was
    taken of, rather than producing a misattributed card.
    """
    evidence = markup.evidence
    if card.article_id != evidence.snapshot.article_id:
        raise ValueError(
            f"card {card.card_id} cites article {card.article_id}, but the evidence was cut from a snapshot "
            f"of article {evidence.snapshot.article_id}"
        )
    return card.evolve(
        snapshot_id=evidence.snapshot_id,
        normalized_text_hash=evidence.normalized_text_hash,
        normalizer_version=evidence.normalizer_version,
        evidence_start_offset=evidence.start,
        evidence_end_offset=evidence.end,
        omitted_ranges=tuple(
            CardOmission(start_offset=omitted.start, end_offset=omitted.end)
            for omitted in evidence.omitted_ranges
        ),
        evidence_text=evidence_text_of(evidence),
        spans=tuple(
            CardSpan(
                start_offset=_evidence_offset(evidence, span.start),
                end_offset=_evidence_offset(evidence, span.end),
                style=span.style,
                purpose=span.purpose,
            )
            for span in markup.spans
        ),
        verification_status=VerificationStatus.UNVERIFIED,
    )


def _evidence_offset(evidence: ExtractedEvidence, snapshot_offset: int) -> int:
    """Where ``snapshot_offset``, at or inside a kept segment, falls in the card's ``evidence_text``."""
    omitted_before = sum(
        omitted.end - omitted.start for omitted in evidence.omitted_ranges if omitted.end <= snapshot_offset
    )
    return snapshot_offset - evidence.start - omitted_before
