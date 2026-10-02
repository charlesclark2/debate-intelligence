# ADR-0018: A card quotes one passage and records what it omitted

- Status: Accepted
- Date: 2026-10-01
- Deciders: Charlie Clark (coach, operator), PM

## Context

Debaters cut cards. A cut card is one passage with pieces removed from the middle of it, and the
removal is the ordinary case rather than the exception.

The domain cannot express one. `Card` holds a single `evidence_text`, a single
`evidence_start_offset` and `evidence_end_offset` naming one contiguous range of the snapshot, and
`CardSpan` offsets measured into `evidence_text`. There is nowhere to say that something inside the
quotation was left out.

Two tasks ran into this from opposite sides. `v1-e03-t05` requires that a student edit may
"delete ranges (shrink or split selections, adding omitted ranges)", which is exactly the
unrepresentable case. `v1-e03-t03` needed snapshot-relative markup offsets for its own criterion
and could not return a domain `CardSpan`, whose offsets are relative to `evidence_text`, so it
returned an evidence-layer `EvidenceMarkupSpan` instead and flagged the gap.

The gap was ours. E03's epic node for t03 says the task covers "ellipsis/omitted-range
representation", and the t03 task spec that was written from it carries no criterion for any such
thing. The work fell between the epic node and the spec, and nothing failed when it did.

The question this record settles is how a card represents evidence with cuts in it, and whether
`CardSpan` moves to snapshot offsets. It binds verification (`v1-e03-t04`), edit policy
(`v1-e03-t05`), the verify command (`v1-e03-t06`) and export (E06), which is why no one task should
decide it while passing through.

## Decision

**A card names one envelope in the snapshot and lists what it removed from inside that envelope.
`CardSpan` offsets stay relative to `evidence_text`.**

1. `evidence_start_offset` and `evidence_end_offset` are the **envelope**: the first and last
   character of the passage the card quotes from. The fields do not change shape.
2. `Card` gains `omitted_ranges`, snapshot-relative half-open ranges in **canonical form**: sorted,
   non-overlapping, non-adjacent (two touching omissions are one omission), strictly inside the
   envelope and touching neither boundary. An omission at an edge is a smaller envelope instead.
   One card therefore has exactly one representation.
3. `evidence_text` is the envelope with the omissions removed, concatenated with **no joiner**. It
   stays verbatim, which is the property the whole platform rests on.
4. The ellipsis is a **rendering** decision, made by the exporter from `omitted_ranges`. It is never
   stored in `evidence_text`, because a stored "..." is text no snapshot contains.
5. `CardSpan` offsets stay relative to `evidence_text`, as today.
6. A single named function in `debate_core.evidence` converts a `v1-e03-t03` selection and its
   `EvidenceMarkupSpan`s into an envelope, omissions, `evidence_text` and `CardSpan`s. The offset
   arithmetic exists once, in one tested place.

## Consequences

**Reordering quoted text becomes inexpressible rather than forbidden.** `v1-e03-t05` must reject
insertions, substitutions and reordering. A list of segments can express a reordering, so it would
need a validator to refuse one. An envelope is read left to right and cannot. This repository has
turned up four checks in a month that reported success without doing their work, so where a rule can
be carried by a structure instead of a check, it should be.

**An omission is a claim, and the representation keeps it visible.** Cutting the word "not" out of a
sentence is the evidence-integrity failure this platform exists to prevent, and it is invisible in
the result. The envelope keeps two separate inspectable facts: the passage quoted from, and what was
taken out of it. That makes it possible to render the removed text, measure how much of the envelope
survived, or flag an omission that deletes a negation. A list of surviving segments records only
what is left and discards the evidence of the act.

**A span can never cover omitted text.** Because spans index `evidence_text`, and omitted text is
not in it. Under snapshot-relative spans, a span crossing a seam would silently mark text the card
removed, and nothing in the type would stop it.

**The domain gains an invariant it can actually check.** `(end - start)` minus the total length of
the omissions must equal `len(evidence_text)`. That is enforceable at construction without the
snapshot, which keeps the existing rule that the domain does not compare a card against its source
(that is the verifier's job, so a tampered card stays constructible and reportable).

**Costs accepted.** Two genuinely distant passages in one card become a wide envelope with a wide
omission, which is rare and arguably the more honest rendering. The verifier does one extra
slice-and-join. Migration is free: `omitted_ranges` defaults to empty, every existing card remains
valid, and nothing already stored changes meaning.

**`v1-e03-t03` is unaffected.** `EvidenceMarkupSpan` stays an evidence-layer type describing a
selection, which is a different thing from a card's markup. `v1-e03-t04` may proceed on
single-segment cards. `v1-e03-t05` depends on this landing, and is edged to it.

## Alternatives considered

**A list of segments, replacing the single range.** Isomorphic to this for a single envelope, and
the shape most people reach for first. Rejected on the two grounds above: it can express a
reordering, and it discards the omission as a fact.

**Moving `CardSpan` to snapshot offsets.** Would let t03's output be stored unchanged. Rejected
because it lets a span cover omitted text, and because the renderer marks up the quotation it is
handed, so spans that are correct no matter where the quotation came from is the right property.

**Leaving the domain contiguous and forbidding cut cards in V1.** Rejected: cutting is not an
advanced feature, it is what the word "card" means.

## References

- [`v1-e03-t03` session report](../session-reports/v1-e03-t03-span-extraction.md), Deviation 2 and
  its follow-up, which raised this.
- `packages/debate_core/src/debate_core/domain/card.py`, the three construction rules in its module
  docstring.
- [ADR-0006](0006-exact-source-evidence-verification.md), the evidence-integrity rule this serves.
- `plan_specs/v1/e03-evidence-integrity/t05-edit-constraints.yaml`, clause (a).
