"""Property: a card made by place_evidence_on_card reproduces from its snapshot, and its spans never
land on omitted text (`v1-e03-t07` ac4).

Over random snapshots, random envelopes with random omissions, and random markup, the card's fields
are compared with an oracle written here from the rules, not from the code: the kept ranges are the
selection itself, ``evidence_text`` is their text joined with nothing, and each evidence_text index
has the snapshot position the oracle lists for it. The verifier then reconstructs the card from the
snapshot and must find nothing wrong.

Example count comes from ``CARD_MAPPING_PROPERTY_EXAMPLES`` (default 200). The generators record
``event``s so ``--hypothesis-show-statistics`` shows how often cards with omissions, with spans, and
with spans at a cut are actually produced (see the `v1-e03-t07` session report).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from debate_core.domain import Card, ProvenanceMode, SourceSnapshot, SpanStyle
from debate_core.evidence.card_mapping import place_evidence_on_card
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan
from debate_core.evidence.normalization import NORMALIZER_VERSION, normalize
from debate_core.evidence.selection import EvidenceSelection
from debate_core.evidence.snapshot_text import SnapshotText
from debate_core.evidence.verifier import (
    VerificationFindings,
    check_against_snapshot,
    evidence_text_of,
    reconstruct_card_evidence,
)
from debate_core.testing.builders import DEFAULT_OWNER_ID, build_citation, build_source_snapshot

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("CARD_MAPPING_PROPERTY_EXAMPLES", "200")),
    deadline=None,  # the first normalize() call builds cached Unicode tables
    suppress_health_check=[HealthCheck.too_slow],
)

_WORD = st.text(
    alphabet=st.one_of(st.characters(categories=("L", "N", "P")), st.sampled_from(list("aéß—\"'"))),
    min_size=1,
    max_size=8,
)


@st.composite
def snapshots(draw: st.DrawFn) -> tuple[SourceSnapshot, SnapshotText]:
    """A record and its normalized text, from one to five paragraphs of one to ten words."""
    paragraphs = draw(st.lists(st.lists(_WORD, min_size=1, max_size=10), min_size=1, max_size=5))
    raw = "\n\n".join(" ".join(words) for words in paragraphs)
    text = SnapshotText.from_normalized(normalize(raw, NORMALIZER_VERSION))
    assume(len(text.text) >= 2)
    return build_source_snapshot(normalized_text=text.text, normalizer_version=NORMALIZER_VERSION), text


@st.composite
def kept_ranges(draw: st.DrawFn, length: int) -> tuple[tuple[int, int], ...]:
    """One to four non-empty ranges of ``[0, length]`` with at least one character between each pair:
    the envelope's kept pieces, so the gaps between them are canonical omissions by construction."""
    pieces = draw(st.integers(1, min(4, (length + 1) // 2)), label="kept pieces")
    points = sorted(
        draw(st.lists(st.integers(0, length), min_size=2 * pieces, max_size=2 * pieces, unique=True))
    )
    return tuple((points[index], points[index + 1]) for index in range(0, len(points), 2))


@st.composite
def markup_spans(draw: st.DrawFn, kept: tuple[tuple[int, int], ...]) -> tuple[EvidenceMarkupSpan, ...]:
    """Underlines inside each kept piece, none, the whole piece (so underlines touch across a cut), or
    disjoint pieces of it, each optionally with a highlight inside it."""
    spans: list[EvidenceMarkupSpan] = []
    for start, end in kept:
        mode = draw(st.sampled_from(["none", "whole", "pieces"]))
        underlines: list[tuple[int, int]] = []
        if mode == "whole":
            underlines.append((start, end))
        elif mode == "pieces" and end - start >= 1:
            count = draw(st.integers(1, max(1, min(3, (end - start + 1) // 2))))
            points = sorted(
                draw(st.lists(st.integers(start, end), min_size=2 * count, max_size=2 * count, unique=True))
            )
            underlines.extend((points[index], points[index + 1]) for index in range(0, len(points), 2))
        for left, right in underlines:
            spans.append(EvidenceMarkupSpan.underline(left, right))
            if draw(st.booleans()):
                inner_left = draw(st.integers(left, right - 1))
                spans.append(
                    EvidenceMarkupSpan.highlight(inner_left, draw(st.integers(inner_left + 1, right)))
                )
    return tuple(draw(st.permutations(spans)))


def _record_events(kept: tuple[tuple[int, int], ...], spans: tuple[EvidenceMarkupSpan, ...]) -> None:
    omissions = len(kept) - 1
    event("with omissions" if omissions else "without omissions")
    event(f"omissions: {omissions}")
    event("with spans" if spans else "without spans")
    if omissions and spans:
        event("with omissions and spans")
    starts = {start for start, _ in kept[1:]}
    ends = {end for _, end in kept[:-1]}
    if any(span.start in starts for span in spans):
        event("a span starts just after a cut")
    if any(span.end in ends for span in spans):
        event("a span ends just before a cut")
    underlines = [span for span in spans if span.style is SpanStyle.UNDERLINE]
    if any(a.end in ends and b.start in starts and a.end < b.start for a in underlines for b in underlines):
        event("underlines either side of a cut")


@PROPERTY_SETTINGS
@given(data=st.data())
def test_card_mapping_reproduces_from_the_snapshot_and_no_span_lands_on_an_omission(
    data: st.DataObject,
) -> None:
    snapshot, text = data.draw(snapshots())
    kept = data.draw(kept_ranges(len(text.text)))
    spans = data.draw(markup_spans(kept))
    _record_events(kept, spans)
    selection = EvidenceSelection.of_offsets(*data.draw(st.permutations(kept)))
    evidence = EvidenceExtractor().extract(snapshot, text, selection)
    blank = Card(
        owner_id=DEFAULT_OWNER_ID,
        article_id=snapshot.article_id,
        tag="A generated card",
        citation=build_citation(),
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
    )

    card = place_evidence_on_card(blank, CardMarkup(evidence, spans))

    # The oracle: the kept ranges as drawn, the gaps between them, and each evidence_text index's
    # position in the snapshot.
    omitted = [
        (left_end, right_start) for (_, left_end), (right_start, _) in zip(kept, kept[1:], strict=False)
    ]
    positions = [position for start, end in kept for position in range(start, end)]
    assert (card.evidence_start_offset, card.evidence_end_offset) == (kept[0][0], kept[-1][1])
    assert [(omission.start_offset, omission.end_offset) for omission in card.omitted_ranges] == omitted
    assert card.evidence_text == "".join(text.text[position] for position in positions)

    # Reconstructing from the snapshot reproduces evidence_text exactly, and the verifier's checks
    # against the snapshot find nothing.
    assert evidence_text_of(reconstruct_card_evidence(card, snapshot, text)) == card.evidence_text
    findings = VerificationFindings()
    check_against_snapshot(card, snapshot, text, findings)
    assert findings.reasons == ()

    # Every card span maps back onto exactly the snapshot characters its markup span marked, none of
    # them omitted.
    assert len(card.spans) == len(spans)
    for card_span, markup_span in zip(card.spans, spans, strict=True):
        marked = positions[card_span.start_offset : card_span.end_offset]
        assert marked == list(range(markup_span.start, markup_span.end))
        assert not any(start <= position < end for position in marked for start, end in omitted)
        assert (card_span.style, card_span.purpose) == (markup_span.style, markup_span.purpose)
