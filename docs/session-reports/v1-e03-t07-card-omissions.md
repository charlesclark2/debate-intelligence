# Session report: v1-e03-t07-card-omissions

| | |
|---|---|
| Task | `v1-e03-t07-card-omissions` — Card omissions and the selection-to-card mapping |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t07-card-omissions.yaml`](../../plan_specs/v1/e03-evidence-integrity/t07-card-omissions.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t07-card-omissions` |
| Session status | COMPLETE |

## Summary

`Card` now records a cut card the way ADR-0018 settles it. The evidence offsets are the
**envelope**. A new `omitted_ranges` field (`CardOmission`, snapshot offsets) lists what was removed
from inside it, in canonical form. `evidence_text` is the envelope minus the omissions, joined with
nothing. Construction refuses any non-canonical omission set, and any card whose envelope minus its
omissions is not exactly as long as `evidence_text`. `place_evidence_on_card(card, markup)` in
`debate_core.evidence.card_mapping` is the one function that turns t03's `CardMarkup` into a card's
envelope, omissions, text and `CardSpan`s. The verifier's `reconstruct_card_evidence` now
reconstructs the envelope minus the omissions. t04's test fixture builds its cards through the new
function. Every criterion passed, and the Goal is `Succeeded`.

**What the PM should look at first:**

- **ac7 as literally worded cannot be met, so I tested what it means (Deviation 3).** Widening,
  narrowing, removing or adding an omission always changes how much is omitted. On the card's
  original envelope, the length invariant therefore refuses every such card at construction. To
  reach the verifier, a change has to move the envelope's end as well. With that, 96 of the 97
  single-omission changes are `TEXT_MISMATCH`. One verifies, and should: moving the first cut one
  character right leaves the same text, because the cut text begins and ends with a space.
- **The length invariant broke 26 of t04's tests, as t04 predicted, and I changed them (Deviation
  2).** Each changed test now either moves the envelope to fit the text or counts the domain's
  refusal. One hand-written ac2 case could not survive: deleting the final period, with an envelope
  fitted to the text, is an honest card. I replaced that case, and a separate test now asserts that
  card verifies.
- **The verifier gained one refusal (Decisions §5).** If the evidence comes back cut anywhere other
  than where the card says, the verifier reports `SPAN_OUT_OF_RANGE`. Without this, an unvalidated
  card claiming an omission of zero characters would verify, while claiming a cut that never
  happened. Mutation shows the check is load-bearing.
- **Mutation: 20 of 20 mutants caught**, including the spec's four, with a fresh Hypothesis
  database for every run. No check had to be removed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `domain-shape`: omitted_ranges, canonical form and the length invariant | Done | `domain/card.py`: `CardOmission`, `Card.omitted_ranges`, `_check_omissions`, `Card.quoted_ranges`. The schema was regenerated. `build_card` takes `omitted_ranges`. Commit `94b6ede`. |
| `mapping`: one function from selection to card | Done | `evidence/card_mapping.py`: `place_evidence_on_card` and the private `_evidence_offset`. Commit `d2c2a0e`. It also extends `reconstruct_card_evidence` (ac7) and switches t04's fixture to the new function. |
| `mutation`: prove the invariants by mutation | Done | 20 mutants, all caught (table below). |
| `docs`: record the model where someone will look for it | Done | New section in `docs/evidence/snapshot-text-format.md`, plus updated verification steps, guarantees and limits. Card module docstring has four rules. Commit `b622d68`. |

The plan has no node for ac7. I did the ac7 work in the `mapping` node, because it needs the
mapping, and its tests run under that node's criterion (`-k "omission or card_mapping"` selects
`test_verifier_omissions.py`).

## Acceptance criteria

All commands were run from the task worktree. Unless noted, they used the repository's default
pytest options (xdist, coverage).

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Card carries `omitted_ranges`, default empty; construction rejects out of order, overlapping, adjacent, zero-length, outside or touching the envelope; every existing card still valid with the same meaning | PASS | `test_card.py`. `test_a_non_canonical_omission_set_is_refused` has 11 cases: out of order, overlapping, one inside another, identical, adjacent, touching the start, touching the end, across the start, across the end, before the envelope, after the envelope. Every case removes 20 characters in all, so the length invariant holds and only the rule under test can refuse it. Also: zero-length and reversed omissions, a negative offset, and omissions with no envelope. The default is `()`, and an existing card's `quoted_ranges` is its whole envelope. The whole default suite passes with no change to any card fixture outside t04's length-changing ones (Deviation 2). The round-trip property now generates cards with omissions. |
| ac2: the domain enforces the length invariant at construction, without the snapshot; a tampered card stays constructible | PASS | `test_the_envelope_minus_the_omissions_must_be_as_long_as_the_text` has 6 hand-counted cases, each checking the exact message: omission forgotten, one short, one long, text one long, text one short, omission added. `test_the_length_invariant_holds_for_a_card_without_omissions`. `test_a_card_altered_without_changing_its_length_is_still_constructible_despite_its_omissions`. The validator reads only the card's own fields. |
| ac3: one named public function in `debate_core.evidence`; a repository-wide scan finds no other copy and asserts it saw its call sites | PASS | `place_evidence_on_card` (`evidence/card_mapping.py`). `test_card_mapping_arithmetic_exists_once_in_the_whole_tree` reads every `.py` file under `packages/*/src`, `packages/*/tests`, `tests/` and `scripts/`. It flags any offset shift outside the mapping module. It asserts it saw the mapping's own arithmetic, and the calls in `tests/fixtures/verification/verification_world.py` and in the mapping tests. 12 parametrized cases show what the shape detector flags and what it ignores. It went red when a second copy was added to t04's fixture, and when the scan was limited to production code (mutation table). |
| ac4: property over generated snapshots, envelopes, omissions and markup: reconstruction reproduces `evidence_text`, and no CardSpan maps onto an omission; generators shown to reach the cases | PASS | `test_card_mapping_reproduces_from_the_snapshot_and_no_span_lands_on_an_omission` checks against an oracle written in the test. Each `evidence_text` index has a snapshot position listed by the oracle. Every card span must map back onto exactly its markup span's snapshot characters, none of them omitted. `reconstruct_card_evidence` plus `check_against_snapshot` must find nothing wrong. At 10,000 examples with a fresh database: `1 passed in 26.87s`. Statistics are below. |
| ac5: mutation proves the invariants; at minimum adjacency, ordering, length invariant and a CardSpan shifted by a preceding omission; fresh `HYPOTHESIS_STORAGE_DIRECTORY` per run | PASS | 20 of 20 caught, including all four named, each with a fresh, empty database. See "Mutation testing". |
| ac6: the format doc and the card docstring record the envelope and omission model, the no-joiner rule and that the ellipsis belongs to rendering; three rules become four | PASS | `docs/evidence/snapshot-text-format.md`, new section "How a card records what it quotes: envelope and omissions". `domain/card.py` module docstring: sections "Envelope and omissions (ADR-0018)" and "Construction rules", with four numbered rules. `uv run python scripts/check_links.py` → `OK: 1158 relative links and anchors in 156 Markdown files`. |
| ac7: the verifier honours omissions; t04's reconstruction function extended, not copied; a mapped card with omissions is VERIFIED; any omission widened, narrowed, removed or added is UNVERIFIED with TEXT_MISMATCH; t04's fixtures switched to the mapping | PASS, as interpreted in Deviation 3 | `reconstruct_card_evidence` is extended in place and still the only reconstruction. `test_verifier_omissions.py` → `17 passed`. The mapped card verifies with every check run. Five hand-written changes with fitted envelopes give `TEXT_MISMATCH` at hand-counted offsets: widened 7, narrowed 18, removed 8, added 24, shifted 17. The same changes on the original envelope are refused at construction. The exhaustive test runs all 97 single-omission changes: 85 change the amount omitted, and all 85 are refused on the original envelope. With fitted envelopes, 96 are `TEXT_MISMATCH` at the oracle's offset. The 97th quotes the same text and verifies (explained in its own test). `card_from_extraction` is gone: `VerificationWorld.cut_card` and `cut_card_from_ranges` call `place_evidence_on_card`. |
| Node `domain-shape`: `uv run pytest packages/debate_core/tests/domain -k omission` | PASS | `30 passed in 4.41s`; `domain/card.py` is 100% line and branch covered by the domain and evidence tests together. |
| Node `mapping`: `uv run pytest packages/debate_core/tests/evidence -k "omission or card_mapping"` | PASS | `42 passed in 6.94s`; `card_mapping.py` 100%. |
| Node `mutation`: four mutations each turn the suite red under a fresh Hypothesis database | PASS | See the mutation table. |
| Node `docs`: artifact `docs/evidence/snapshot-text-format.md` exists | PASS | Exists, with the new section. |
| Forbidden: a joiner stored inside `evidence_text` | PASS | The mapping uses t04's `evidence_text_of` (`"".join`). `test_card_mapping_stores_no_joiner_where_text_was_omitted`. Mutant "pieces joined with a space" is caught: the length invariant refuses the longer text. |
| Forbidden: non-canonical `omitted_ranges` | PASS | ac1 above. The verifier also refuses unvalidated non-canonical sets (`test_omissions_that_are_not_canonical_are_span_out_of_range`, 4 cases). |
| Forbidden: CardSpan offsets measured against the snapshot | PASS | Hand-counted spans in `test_card_mapping_puts_the_envelope_omissions_text_and_spans_on_the_card`. The property maps every span back through the oracle. |
| Forbidden: a second copy of the arithmetic anywhere in the tree | PASS | ac3's scan. |
| Forbidden: comparing `evidence_text` against the snapshot in the domain | PASS | `_check_omissions` reads only the card. ac2's tampered-card test. |

Wider checks:

- `uv run pytest -q --no-cov` (whole repository, default markers) → `3656 passed, 1 skipped in
  35.62s`. The skip is the existing `tests/evals/parser/test_parser_eval.py:279`.
- `uv run ruff check .` → clean. `uv run ruff format --check .` → clean.
- `uv run pyright packages/debate_core tests/fixtures` → `0 errors, 0 warnings, 0 informations`.
- `uv run lint-imports` → `Contracts: 11 kept, 0 broken.`
- `uv run scripts/validate_specs.py` → `OK: 298 files, 38 epics, 240 tasks, 20 releases`.
- t03's free-text signature scans and t04's VERIFIED scan still pass. The mapping sets status only
  to `UNVERIFIED`, which that scan allows.
- Coverage over the domain and evidence tests: `card.py` 100%, `card_mapping.py` 100%,
  `verifier.py` 99%. The one missed line is the no-offsets guard in `reconstruct_card_evidence`,
  which t04 already had. `check_against_snapshot` returns before calling it.

### Property statistics (ac4)

10,000 examples, a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, `--hypothesis-show-statistics`.
Percentages are of all generated cases, including Hypothesis's 959 invalid ones, so complementary
pairs do not sum to 100:

- **With omissions: 52.49%.** One cut 16.96%, two 17.99%, three 17.53%. Without: 41.11%.
- **With spans: 56.86%.** Without: 36.74%.
- **With omissions and spans together: 45.07%.**
- **Spans at a cut:** a span starts just after a cut in 32.88%, and one ends just before a cut in
  32.19%. Underlines sit either side of a cut in 20.32%. These are the cases where an off-by-one in
  the shift would show.
- **Gave up on `assume`:** 0.41%.

A 2,000-example run, also on a fresh database, gave the same distribution within two points.

## Mutation testing

The runner is a scratchpad script and is not committed. For each mutant it:

- applies one exact-string replacement, and refuses if the pattern does not occur exactly once;
- runs the seven affected test files with `-n0 --no-cov`: `test_card.py`, `test_roundtrip.py`,
  `test_card_mapping.py`, `test_card_mapping_properties.py` (200 examples),
  `test_verifier_omissions.py`, `test_verifier.py` and `test_verifier_adversarial.py`;
- separately runs the property alone at 2,000 examples;
- restores the original bytes in a `finally`.

**Every run, suite and property alike, set `HYPOTHESIS_STORAGE_DIRECTORY` to a new, empty
directory** (working agreement 8). A pytest exit code other than 0 or 1 would have been reported as
ERROR rather than counted as a catch. None occurred. The runs took 5-10 s each, about four minutes
in all, split into batches of under two minutes. After every batch, `git status` was clean.

| # | Mutant | Suite | One test that caught it | Property @ 2,000 |
|---|---|---|---|---|
| 1 | **Adjacency rule dropped** (`<=` → `<` in the gap rule) | 1 failed / 230 | `test_a_non_canonical_omission_set_is_refused[adjacent]` | passes |
| 2 | **Ordering rule dropped** (omissions sorted before the gap rule) | 1 / 230 | `...[out-of-order]` | passes |
| 3 | **Length invariant dropped** | 28 / 230 | the six length cases, the 15 length-changing fabrications, the four unfitted ac7 changes and the exhaustive ac7 test, among others | passes |
| 4 | Whole order/overlap/adjacency rule dropped | 5 / 230 | `...[overlapping]`, `[identical]`, `[one-inside-another]` | passes |
| 5 | Inside-the-envelope rule dropped | 6 / 230 | `...[before-the-envelope]` and five others | passes |
| 6 | Omissions may touch the envelope's ends (`<` → `<=`) | 2 / 230 | `...[touching-the-start]`, `[touching-the-end]` | passes |
| 7 | Zero-length omission accepted (`>=` → `>`) | 1 / 230 | `test_an_omission_must_remove_at_least_one_character[1873-1873]` | passes |
| 8 | Omissions without an envelope accepted | 1 / 230 | `test_omissions_without_an_envelope_are_refused` | passes |
| 9 | `quoted_ranges` ignores the omissions | 17 / 230 | `test_a_cut_card_records_its_omission_and_quotes_the_envelope_around_it` | caught |
| 10 | **CardSpan shifted by a preceding omission** (a cut ending exactly at `s` not counted: `omitted.end < s`) | 9 failed, 16 errors / 230 | `test_card_mapping_counts_an_omission_only_once_a_span_is_past_it` | caught |
| 11 | Span shift ignores omissions entirely | 9 + 16 errors | same | caught |
| 12 | Span end shifted by the following omission (`omitted.start <= s`) | 9 + 16 errors | same | caught |
| 13 | Mapping records each omission one character narrower | 9 + 16 errors | `test_card_mapping_puts_the_envelope_omissions_text_and_spans_on_the_card` | caught |
| 14 | Mapping does not refuse another article's card | 1 / 230 | `test_card_mapping_refuses_a_card_for_another_article` | passes |
| 15 | Mapping keeps the card's old verification status | 1 / 230 | `test_card_mapping_keeps_the_card_and_replaces_its_evidence` | passes |
| 16 | Pieces joined with a space (mapping and verifier alike) | 9 + 16 errors | `test_card_mapping_stores_no_joiner_where_text_was_omitted` (the length invariant refuses the card) | caught |
| 17 | Verifier reconstructs the whole envelope, ignoring omissions | 13 / 230 | `test_a_card_cut_with_omissions_by_the_mapping_is_verified` | caught |
| 18 | Verifier's cut-where-the-card-says check dropped | 1 / 230 | `test_omissions_that_are_not_canonical_are_span_out_of_range[removes-nothing]` | passes |
| 19 | A second copy of the span shift added to t04's fixture | 1 / 230 | `test_card_mapping_arithmetic_exists_once_in_the_whole_tree` | passes |
| 20 | The scan reads production code only | 1 / 230 | same ("did not see the mapping's call sites") | passes |

Notes on the table:

- **"Errors" in rows 10-13 and 16 are fixture setups, not collection errors.** Those mutants make the
  mapping produce a card the domain refuses. Module fixtures that cut cards with omissions (t04's
  adversarial world, the ac7 `honest` card) then fail during setup. The catch is the 9 tests that
  ran and failed. I did not count the setup errors.
- **The property catches the span shift by its own assertion, not only through the domain.** For
  row 10, I ran the property alone, once more and on a fresh database. Its output shows both
  `assert marked == list(range(markup_span.start, markup_span.end))` failing (`[3] == [2, 3]`) and a
  `CardSpan` `ValidationError`. A span shifted but still valid is caught by the oracle comparison.
- **Rows 1 and 2 have one catching test each, by design.** Order, overlap and adjacency are one
  rule: each omission starts after the previous one ends, with a kept character between. The
  message only labels which way a refused pair breaks it. Row 1 is the rule's `<=` relaxed.
  Row 2 sorts the omissions before checking, which is what dropping the ordering rule means when
  it shares a comparison with the others. A separate ordering check would have been masked by the
  overlap check (an out-of-order pair also starts before the previous one ends), and mutation could
  not have told it apart from its absence.
- **The property passes the domain-only mutants, as expected.** It generates only canonical cards.
  The domain's refusals are held by the hand-written example tests, each with its own message.
- **No check was removed.** Each one has a mutant that some test catches, and each catching test is
  about that check.

## Files changed

- `packages/debate_core/src/debate_core/domain/card.py`: `CardOmission`, `Card.omitted_ranges`, the
  omission validator (canonical form, length invariant), `Card.quoted_ranges`. The module docstring
  gains the envelope/omission model and four construction rules.
- `packages/debate_core/src/debate_core/domain/__init__.py`: exports `CardOmission`.
- `packages/debate_core/schemas/card.schema.json`: regenerated with `uv run
  scripts/export_schemas.py` (0.14 s). `test_schemas.py` fails without it.
- `packages/debate_core/src/debate_core/evidence/card_mapping.py` (new): `place_evidence_on_card`.
- `packages/debate_core/src/debate_core/evidence/verifier.py`: `reconstruct_card_evidence` selects
  `card.quoted_ranges` and refuses a reconstruction cut elsewhere. The `SPAN_OUT_OF_RANGE` detail
  counts omitted ranges. Docstring updated.
- `packages/debate_core/src/debate_core/evidence/markup.py`: docstring now points at the mapping
  instead of "the card service's step (`v1-e06-t02`)".
- `packages/debate_core/src/debate_core/testing/builders.py`: `build_card(omitted_ranges=())`.
- `tests/fixtures/verification/verification_world.py`: `card_from_extraction` replaced by
  `card_from_markup`, which builds a tag-only card and calls `place_evidence_on_card`. New method
  `cut_card_from_ranges` for multi-range cards.
- Tests, new: `tests/evidence/test_card_mapping.py` (examples, and ac3's scan with its self-test),
  `test_card_mapping_properties.py` (ac4), `test_verifier_omissions.py` (ac7).
- Tests, changed: `tests/domain/test_card.py` (omission section), `tests/domain/test_roundtrip.py`
  (cards with omissions), and t04's `tests/evidence/test_verifier.py` and
  `test_verifier_adversarial.py` (Deviation 2).
- `docs/evidence/snapshot-text-format.md`: new section, updated verification steps and guarantees,
  two new limits of VERIFIED, five guarantee rows.
- `plan_specs/v1/e03-evidence-integrity/t07-card-omissions.yaml`: phase only.

## Deviations from the spec

1. **Edits outside `constraints.packages`**, all needed by the spec's own criteria:
   - `tests/fixtures/verification/` and `debate_core/testing/builders.py`: authorised by the PM in
     the task prompt.
   - `packages/debate_core/schemas/card.schema.json`: the committed contract for the domain, which
     `test_schemas.py` requires to match the model.
   - `tests/domain/test_roundtrip.py`: the domain's round-trip property, which should cover the new
     field.
2. **t04's tests changed where the length invariant refuses their cards.** 26 t04 tests failed after
   the domain change (15 adversarial cases and 11 in `test_verifier.py`). None failed for a verifier
   reason: each built a card whose text length differed from its envelope.
   - `test_verifier_adversarial.py`: the 28 fabrications are split by hand into 13 of the claimed
     length, which must reach the verifier and give `TEXT_MISMATCH` at their hand-counted offsets as
     before, and 15 that change the length. The 15 kinds are listed by name in the test, and each
     must be refused at construction for the length invariant (t04 Decision 9).
     `test_no_fabrication_passes` and the 1,743-mutation test pass unchanged.
   - `test_verifier.py`, ac2 (one changed, inserted or deleted character): an insertion or deletion
     is now given an envelope one character longer or shorter (`_with_text`), so the verifier still
     judges it. The first differing offset is unchanged in every case but one. Deleting the final
     period with a fitted envelope is the honest card for 61-116, so I replaced the hand-written
     `deleted-final-period` case with `deleted-final-s` (offset 54). The exhaustive 169-edit test
     skips that one edit. A new test asserts it verifies. Another new test asserts all 113
     length-changing edits are refused on the original envelope.
   - `test_text_appended_and_marked_is_a_text_mismatch_and_a_span_out_of_range` uses `model_copy`
     (unvalidated) to keep its scenario: the verifier must not rely on domain validation. The
     `ensure_finished` "text" case and the forged-VERIFIED card get fitted envelopes; their
     expected results are unchanged.
3. **ac7's wording, "the same card with any omission widened, narrowed, removed or added yields
   UNVERIFIED with TEXT_MISMATCH", cannot hold literally once ac2 is in force.** Each of those
   changes alters the total omitted, so on the same envelope ac2 refuses the card at construction.
   The PM anticipated this in the task prompt. I tested both halves:
   - unfitted: refused, all 85 such changes in the exhaustive test;
   - fitted envelope: `TEXT_MISMATCH` at the oracle's offset.

   I also tested shifts, which keep the length and so reach the verifier unchanged. One fitted
   change verifies, correctly: moving the first cut one right (" there now" → "there now ") leaves
   the same 37 characters. An omission's position is determined by the text only up to repeated
   characters at its edges. The format doc now lists this under "What it does not guarantee yet".
   If the PM wants the criterion reworded, I suggest: "any single-omission change is refused at
   construction or, with the envelope refitted, is `TEXT_MISMATCH` unless it quotes the same text".
4. **The mapping returns a `Card`, not loose fields** (Decisions §1).

## Decisions and assumptions

1. **`place_evidence_on_card(card, markup) -> Card`.** It takes a card (normally tag-only) and t03's
   `CardMarkup`, and returns the card with all the evidence fields set.
   - Why not return a bundle of `evidence_text`, offsets and spans: that would be a public
     evidence-layer constructor taking free text, which t03 worked to rule out.
   - The function sets the snapshot id, text hash and normalizer version from the extraction. It
     keeps identity, tag, citation and provenance.
   - It resets `verification_status` to `UNVERIFIED`: new evidence is unverified, whatever the card
     said before.
   - It raises `ValueError` if the card cites another article than the snapshot's, instead of
     producing a card the verifier would report as `ARTICLE_MISMATCH`.
   - The t03 runtime type guards are not repeated. Its inputs are typed objects built by code, not
     deserialized model output, and guards nothing could test would be decoration.
2. **Touching same-style spans either side of a cut are not merged.** One markup span becomes one
   card span. Reasons:
   - each keeps its own `purpose`, which a merge would have to drop;
   - each card span stays inside one kept piece, so it maps back onto exactly the snapshot
     characters it came from and never across a cut. t05 can carry spans over an edit without
     splitting them;
   - the exporter has to break a mark at a cut to place the ellipsis anyway.

   The domain's overlap rule already allows touching spans. Tests:
   `test_card_mapping_keeps_touching_spans_either_side_of_a_cut_as_separate_spans`, and the property
   (20% of examples have underlines either side of a cut).
3. **The calculation is written once.** `_evidence_offset(evidence, s) = s - evidence.start -
   (total length of the omissions ending at or before s)`. "At or before" is the edge that matters.
   A span starting where a cut ends is past that cut. A span ending where a cut starts is not past
   it. Both are hand-tested, and mutants 10 and 12 break each edge.
4. **`CardOmission` is its own type, in snapshot offsets, named apart from t03's `OmittedRange`.**
   - It uses the domain's `start_offset`/`end_offset` naming, and its docstring says it indexes the
     snapshot, unlike `CardSpan`.
   - It is not given its own schema file. It appears in `card.schema.json`'s `$defs`.
   - `Card.quoted_ranges` gives the envelope minus the omissions in snapshot pairs, for the verifier
     and, later, the exporter.
5. **The verifier refuses a reconstruction cut anywhere other than where the card says.** The
   domain refuses non-canonical omissions, but a card can arrive unvalidated (`model_construct`,
   `model_copy`). Most non-canonical forms leave an empty or reversed range, which the selection
   refuses. An omission of zero characters inside a kept piece does not. The extractor joins the
   two touching ranges, the text comes back intact, and the card would verify while claiming a cut
   that never happened. `reconstruct_card_evidence` therefore compares the segments it got with
   `card.quoted_ranges` and raises `InvalidSelection(SEGMENTS_TOUCH)`, reported as
   `SPAN_OUT_OF_RANGE`. Mutant 18 shows this check is load-bearing.
6. **Nothing added to `check_card`'s completeness list.** An empty `omitted_ranges` is a complete
   statement ("nothing omitted"), not a missing field. Omissions are checked as part of the text
   reconstruction instead.
7. **`VERIFIER_VERSION` stays `evidence-verifier-v1`.** A card with no omissions reconstructs exactly
   as before. A card with omissions could not exist before this task, so no stored result was
   reached under different rules.
8. **The ac3 scan matches shapes, not meaning.** It flags `x - <obj>.start` (or `.start_offset`,
   `.evidence_start_offset`) unless `x` is the same object's end, which is a length. It also flags
   `<envelope start> + <span offset>` (the inverse) and `-=` by a start. It cannot see the
   arithmetic through an alias (`base = evidence.start; s - base`). Review has to catch that, as
   with t03's scans.

## Operator follow-ups

None. Every command finished in under two minutes and ran in the session. The longest were the
mutation batches (85 s, 92 s and 55 s) and the 10,000-example property (27 s).

What remains is the usual step after review: `scripts/task pr v1-e03-t07-card-omissions`, run from
the task worktree.

## Follow-up work

- **`v1-e03-t05-edit-constraints`:** an edit that deletes a range produces a new selection. Re-cut it
  with `place_evidence_on_card`, then call `EvidenceVerifier.verify_and_record`. If t05 needs the
  inverse mapping (card span → snapshot offsets) to carry spans across an edit, it belongs in
  `card_mapping.py`. The ac3 scan flags that arithmetic anywhere else.
- **E06 exporters:** render cuts from `omitted_ranges`. Decide how to render a cut that removes only
  a paragraph break, and break marks at a cut, since touching spans either side of a cut stay
  separate.
- **ADR-0018's "flag an omission that deletes a negation" is not implemented anywhere.** Today
  VERIFIED says nothing about whether a cut is fair (format doc, "What it does not guarantee yet").
  Owner: PM (t05 or E06).
- **The adversarial fixture now refuses 15 of its 28 fabrications in the domain.** If the PM wants
  every fabrication to reach the verifier, those 15 need claimed ranges fitted to their length.
  Their hand-counted offsets would then need re-deriving.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
