# ADR-0006: Exact-source evidence verification — LLMs select spans, they do not author evidence

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§2 Goals and Architectural Principles](../architecture/architecture_proposal.md#2-goals-and-architectural-principles)
  - [§8 Evidence Integrity and Provenance](../architecture/architecture_proposal.md#8-evidence-integrity-and-provenance)

## Context

Debate cards are quotations. A card whose evidence text was paraphrased, invented, or
silently altered by a language model is not just lower quality — it is a fabrication that
can lose rounds, get students accused of clipping, and destroy the platform's credibility.
Foundation models can and do produce plausible-sounding quotes that never appeared in the
underlying source, especially under summarization or "clean-up" prompts.

Any workflow that lets a model return the evidence text as a string ("here is the passage
you should cut") therefore has to be treated as an integrity failure by construction.

## Decision

The card-generation pipeline is:

1. Retrieve the source and persist a versioned `SourceSnapshot` (raw and normalized).
2. Normalize text deterministically and compute SHA-256 hashes.
3. Ask the model for **paragraph IDs or character offsets** plus structured tag/citation
   and markup metadata — never rewritten evidence text.
4. Extract evidence text directly from the saved snapshot at those offsets.
5. Reconstruct the card evidence under the same normalization rules and verify byte- or
   character-equivalence before the card is marked as verified.
6. Persist `snapshot_id`, offsets, hashes, extractor and model versions, and the
   verification status on the `Card`.

If the source is unreachable, if the requested span cannot be reproduced from the
snapshot, or if metadata cannot be verified, the card is marked **UNVERIFIED** and is
never presented as a finished evidence card. This rule is enforced in `debate_core` at
the domain layer; delivery surfaces cannot bypass it.

Model output contracts (`CardSelection`, `MarkupSpan`, etc.) allow only offsets and
metadata for evidence content; there is no free-text `evidence_text` field on any
model-facing schema. Cards may carry model-authored tags and rationales, clearly labeled
as such, alongside the verified quotation.

## Consequences

- The system will refuse to produce a card in cases where a paraphrase-happy pipeline
  would silently succeed. This is a feature, not a bug.
- Retrieval-quality issues (paywalls, JS-rendered content, weird PDFs) surface early as
  verification failures rather than as bad cards.
- Every extractor/normalizer change requires a golden-card regression test because a
  normalization change can invalidate previously verified cards.
- Any future feature that suggests text edits ("clean up this quote for readability") must
  either operate outside the verified evidence region or be gated as a distinct
  provenance mode with explicit labeling.

## Alternatives considered

- **Trust model-returned quotations, verified by fuzzy matching.** Rejected: fuzzy
  matching hides substitutions and paraphrases that materially change meaning, and the
  failure mode is invisible to the user.
- **Post-hoc human review only.** Not scalable; students would silently rely on unverified
  cards between reviews.
- **Verification only for exported cards, not saved cards.** Verification failure needs to
  block card creation, not just export, because saved cards get shared and quoted.

## References

- [§2 Goals and Architectural Principles](../architecture/architecture_proposal.md#2-goals-and-architectural-principles)
- [§8 Evidence Integrity and Provenance](../architecture/architecture_proposal.md#8-evidence-integrity-and-provenance)
- [ADR-0003: S3 source-of-truth](0003-s3-source-of-truth-for-raw-artifacts.md)
- [ADR-0005: Bedrock behind ModelRouter](0005-bedrock-behind-model-router.md)
