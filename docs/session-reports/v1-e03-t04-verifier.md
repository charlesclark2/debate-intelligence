# Session report: v1-e03-t04-verifier

| | |
|---|---|
| Task | `v1-e03-t04-verifier` — EvidenceVerifier and verification statuses |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t04-verifier.yaml`](../../plan_specs/v1/e03-evidence-integrity/t04-verifier.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t04-verifier` |
| Session status | COMPLETE |

## Summary

`EvidenceVerifier` decides whether a card is finished evidence. It checks the card, loads its
snapshot through `SnapshotService.load` (every t02 integrity check), cuts the evidence again from the
stored normalized text at the card's offsets with t03's extractor, compares it exactly, and checks
spans and citation flags. It returns a `VerificationResult` with every reason found and the checks
that ran. Every Goal criterion and node criterion passes; the phase is `Succeeded`.

What the PM should look at first:

- **The verifier is split across two layers** (Deviation 1). `EvidenceVerifier` is in
  `debate_core.application`, because the layer contract forbids `evidence` from importing
  `SnapshotService`. The pure checks are in `evidence/verifier.py`, the path the spec names.
- **`ensure_finished` re-verifies** and never reads the card's status field (Decisions §1). A
  hand-built card claiming `VERIFIED` with altered text is refused (test below).
- **One reason code beyond the spec and t02's suggestion: `CARD_INCOMPLETE`** (Deviation 2).
- **The verifier does not build t03 `CardMarkup`.** So the PM's `InvalidMarkup → SPAN_OUT_OF_RANGE`
  mapping has nothing to map (Deviation 3).
- **Mutation: 27 of 27 mutants caught.** One check was removed because mutation could not tell it
  apart from its absence (Mutation testing).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `result-types`: VerificationResult and reason codes | Done | `evidence/verification_types.py`: `ReasonCode`, `VerificationCheck`, `REQUIRED_CHECKS`, `VerificationReason`, `VerificationResult`, `UnverifiedEvidenceError`, `VERIFIER_VERSION` |
| `verifier-core`: EvidenceVerifier.verify | Done | Pure checks in `evidence/verifier.py`; `EvidenceVerifier` in `application/evidence_verifier.py` (Deviation 1) |
| `finished-guard`: ensure_finished guard | Done | `EvidenceVerifier.ensure_finished`, async, re-verifies (Decisions §1) |
| `adversarial-fixtures`: Fabrication and paraphrase fixtures | Done | `tests/fixtures/verification/fabricated_evidence.json` (28 hand-written fabrications) and `verification_world.py`; `test_verifier_adversarial.py` |

## Acceptance criteria

All commands were run from the task worktree, using the repository's default pytest options (xdist and
coverage) unless noted.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a card built by EvidenceExtractor from an intact snapshot verifies as VERIFIED with no reasons | PASS | `test_a_card_cut_from_an_intact_snapshot_is_verified_with_no_reasons` asserts `VERIFIED`, `reasons == ()` and `checks_run` = every check. The card is cut by the extractor from a snapshot made by `SnapshotService.create` and loaded by `load`, then mapped to a `Card` by hand in a test fixture (`card_from_extraction`), as the PM asked. Also covered: a card crossing a paragraph break, and a card quoting the whole text. |
| ac2: a single changed, inserted or deleted character → UNVERIFIED, TEXT_MISMATCH and the first differing offset | PASS | 8 hand-written cases (`test_one_edited_character_is_a_text_mismatch_at_the_first_differing_offset`), the run-of-equal-characters case (`Tessaly` → `Tesaly` reports 22), and an exhaustive enumeration of all 169 single-character edits of a 56-character card (`test_every_single_character_edit_is_a_text_mismatch_at_its_own_offset`). The offset is in **evidence-text coordinates** (see Decisions §4). |
| ac3: missing snapshot, tampered blob or unknown normalizer_version → UNVERIFIED with the matching code, never an exception | PASS | Missing record and missing blobs → `SNAPSHOT_MISSING`. Tampered raw blob, tampered normalized blob, and a tampered blob behind a store that skips its own read check → `HASH_MISMATCH`. Unknown version on the card, and on the snapshot → `UNKNOWN_NORMALIZER_VERSION`. Every call returns a result. Tests also show what still propagates: `StoreUnavailable`, a bug inside `load`, and a repository returning another snapshot's record. |
| ac4: ensure_finished(card) raises UnverifiedEvidenceError for any card whose latest result is not VERIFIED; covered by tests later exporters use | PASS | `uv run pytest packages/debate_core/tests/evidence/test_verifier.py -k finished` → `9 passed`. Covers: one unverified card per reason code; a hand-built card claiming VERIFIED with altered text (refused, `TEXT_MISMATCH` at 23); a card recorded VERIFIED whose snapshot was then tampered with (refused); and a never-promoted card that verifies now (passes). Exporters' tests can import `tests/fixtures/verification/verification_world.py` for a verifier, a card that verifies and a card that does not. |
| ac5: a mutation-style suite of fabricated and paraphrased fixtures has a 0% pass rate | PASS | `uv run pytest packages/debate_core/tests/evidence/test_verifier_adversarial.py` → `33 passed`. None of the 28 hand-written fabrications verifies, and each fails with `TEXT_MISMATCH` at its hand-counted offset. None of the 1,743 single-character mutations of the 6 honest fixture cards verifies (579 look-alike or `X` replacements, 579 deletions, 585 insertions). Each honest card verifies, so a verifier that refused everything would fail this file. |
| Node `result-types`: artifact `verification_types.py` exists, contains `TEXT_MISMATCH` | PASS | `grep -c TEXT_MISMATCH packages/debate_core/src/debate_core/evidence/verification_types.py` → `6` |
| Node `verifier-core`: `uv run pytest packages/debate_core/tests/evidence/test_verifier.py` | PASS | `78 passed in 6.00s` |
| Node `finished-guard`: `uv run pytest packages/debate_core/tests/evidence/test_verifier.py -k finished` | PASS | `9 passed in 4.95s` |
| Node `adversarial-fixtures`: `uv run pytest packages/debate_core/tests/evidence/test_verifier_adversarial.py` | PASS | `33 passed in 5.61s` |
| Node `adversarial-fixtures`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |
| Forbidden: fuzzy or similarity matching | PASS | The comparison is `first_difference(card.evidence_text, reconstructed)` on raw strings. Mutants that compared case-folded, NFKC or whitespace-collapsed text were each caught by the adversarial suite (Mutation testing). |
| Forbidden: setting VERIFIED anywhere except EvidenceVerifier | PASS | `test_verified_is_set_only_by_the_evidence_verifier`, an AST scan of every `packages/*/src` module (Decisions §5). It asserts it saw the verifier's own three writes, and fails on a stale allow-list entry. |
| Forbidden: any model/LLM call in the verification path | PASS | The verifier, its checks, the extractor and `SnapshotService` import nothing from `ports.providers` or `ModelRouter` (grep: none). |

Other checks run: `uv run pytest packages/debate_core/tests/evidence packages/debate_core/tests/application packages/debate_core/tests/domain packages/debate_core/tests/testing tests/architecture tests/docs --no-cov -q` → `2009 passed in 17.84s`, including t03's free-text signature scans, which now also see `reconstruct_card_evidence`. Also: `uv run ruff check .` → all passed; `uv run ruff format --check .` → 453 files formatted; `uv run lint-imports` → 10 kept, 0 broken; `uv run python scripts/check_links.py` → OK; `uv run scripts/validate_specs.py` → `OK: 296 files, 38 epics, 238 tasks, 20 releases`.

## Mutation testing

Runner: a scratchpad script. For each mutant it applies one exact-string replacement (refusing if the
pattern does not occur exactly once), runs both verifier test files with `-n0 --no-cov`, and restores
the original bytes in a `finally`. **Every run used a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`**
(a new temporary directory per run, per working agreement 8). Neither test file uses Hypothesis:
the single-character edits are enumerated instead, so no property statistics apply. A pytest exit
other than 0 or 1 is reported as ERROR and not counted as a catch; none occurred. After the run the
worktree held only the edits it held before.

Final run, against the committed code: **27 of 27 caught**, each in 0.7-2.8 s, about 31 s in all.

| Mutant | Failed / run | One test that caught it |
|---|---|---|
| Exact comparison disabled (`differs_at = None`) | 46 / 111 | `test_one_edited_character_is_a_text_mismatch_at_the_first_differing_offset[changed-u-of-pump]` |
| Card text compared with itself instead of the reconstruction | 46 / 111 | same |
| Case-insensitive comparison | 2 / 33 | `test_a_fabrication_is_unverified_with_a_text_mismatch_where_it_departs[case changed]` |
| NFKC comparison | 5 / 33 | `...[accent decomposed (NFD a + combining grave)]`, `...[full-width digits]` |
| Whitespace-collapsing comparison | 7 / 33 | `...[no-break space kept from the raw text]` |
| A prefix is not a difference | 5 / 33 | `...[truncated before the comparison]` |
| First differing offset off by one | 12 / 78 | `test_one_edited_character_is_a_text_mismatch_at_the_first_differing_offset[...]` |
| `InvalidSelection` not converted | 2 / 78 | `test_offsets_past_the_end_of_the_text_are_span_out_of_range` |
| `SnapshotTextMismatch` not converted | 1 / 78 | `test_text_that_is_not_the_records_is_a_hash_mismatch_even_past_a_broken_load` |
| `NotFound` reported as `HASH_MISMATCH` | 3 / 78 | `test_a_card_whose_snapshot_record_does_not_exist_is_snapshot_missing` |
| Unknown snapshot version reported as `HASH_MISMATCH` | 1 / 78 | `test_a_snapshot_under_an_unknown_normalizer_version_is_unverified_with_that_code` |
| Blanket `except Exception` around the load | 7 / 78 | `test_a_tampered_raw_blob_is_a_hash_mismatch`, and the propagation tests |
| Unknown card normalizer version accepted | 1 / 78 | `test_a_card_under_an_unknown_normalizer_version_is_unverified_with_that_code` |
| Card/snapshot text-hash binding dropped | 1 / 78 | `test_a_card_cut_from_other_text_is_a_hash_mismatch_and_is_not_compared` |
| Card/snapshot version binding dropped | 1 / 78 | `test_a_card_under_an_unknown_normalizer_version_is_unverified_with_that_code` |
| Span containment dropped | 2 / 78 | `test_a_span_past_the_end_of_the_evidence_is_span_out_of_range` |
| Citation check dropped | 3 / 78 | `test_an_unverified_citation_is_citation_unverified` |
| Spans no longer required | 3 / 78 | `test_a_card_with_no_spans_is_incomplete` |
| Text hash no longer required | 1 / 78 | `test_a_card_with_no_text_hash_is_incomplete` |
| Span check forgotten (returns early, records nothing) | 11 / 111 | `test_a_card_cut_from_an_intact_snapshot_is_verified_with_no_reasons` (the result refuses to be VERIFIED with a check missing) |
| Result invariant: VERIFIED with a skipped check allowed | 1 / 111 | `test_a_verified_result_that_skipped_a_check_cannot_be_constructed` |
| Span check forgotten and the result invariant dropped together | 5 / 111 | ac1 tests asserting `checks_run` is every check |
| `ensure_finished` trusts a card claiming VERIFIED | 2 / 78 | `test_ensure_finished_rejects_a_hand_built_card_claiming_verified_with_altered_text` |
| `ensure_finished` never raises | 7 / 78 | `test_ensure_finished_raises_for_every_unverified_card[...]` |
| A status write added to `snapshot_service.py` | 1 / 78 | `test_verified_is_set_only_by_the_evidence_verifier` |
| An `evolve(verification_status=VERIFIED)` added to the evidence layer | 1 / 78 | same |
| The scan reads no files (its own glob broken) | 1 / 78 | same: "did not see the verifier's own assignments" |

**A check removed because mutation could not tell it apart from its absence.** The first version
enforced "every check ran" twice: in `VerificationFindings.passed`, and in `VerificationResult`'s
constructor. Combined mutants showed each was a backstop for the other. With a forgotten span check,
dropping either rule failed the same 11 tests, and the 12th failure was only that rule's own unit
test. So I removed the one in `VerificationFindings` (commit `7b7a2e5`) and kept the rule on the
result type, which also guards any future constructor. The final rows above show the remaining rule
still catches a forgotten check, and that the ac1 assertions on `checks_run` catch it when both
are gone.

## Files changed

- `packages/debate_core/src/debate_core/evidence/verification_types.py` (new): result type, reason
  codes, the checks a verification records, `UnverifiedEvidenceError`, verifier version.
- `packages/debate_core/src/debate_core/evidence/verifier.py` (new): `reconstruct_card_evidence`
  (the one reconstruction function), `evidence_text_of`, `first_difference`, `check_card`,
  `check_against_snapshot`, `VerificationFindings`. No I/O, and it sets no status.
- `packages/debate_core/src/debate_core/application/evidence_verifier.py` (new): `EvidenceVerifier`
  with `verify`, `verify_and_record` and `ensure_finished`; maps load failures to reasons. The only
  module that writes a verification status.
- `packages/debate_core/tests/evidence/test_verifier.py` (new): ac1-ac4, reason mapping and
  propagation, result invariants, the VERIFIED scan and its self-test.
- `packages/debate_core/tests/evidence/test_verifier_adversarial.py` (new): ac5.
- `tests/fixtures/verification/fabricated_evidence.json` (new): two invented sources, 6 honest cards,
  28 fabrications, all hand-written with hand-counted offsets.
- `tests/fixtures/verification/verification_world.py` (new): verifier wired to in-memory stores, and
  the test-only `card_from_extraction` mapping that t07 will replace.
- `docs/evidence/snapshot-text-format.md`: new section "Verifying a card against its snapshot",
  covering the steps, the reason-code mapping, offset coordinates, what VERIFIED guarantees and what
  it does not yet. Six rows added to the guarantees table.
- `plan_specs/v1/e03-evidence-integrity/t04-verifier.yaml`: phase `Succeeded` only.

## Deviations from the spec

1. **`EvidenceVerifier` lives in `debate_core.application.evidence_verifier`, not
   `evidence/verifier.py`.** The node says `EvidenceVerifier.verify` should "load snapshot with
   integrity check". The only integrity-checked load is `SnapshotService.load`, which is in the
   application layer. The layers contract (`integrations | testing` > `application` > `evidence` >
   `domain`) forbids `evidence` from importing it. Finding the snapshot record from a card's
   `snapshot_id` also needs the `ArticleRepository` port. So the class that loads, and sets the
   status, is in the application layer. Everything that needs no I/O is in
   `evidence/verifier.py`, the spec's output path. Both packages are in `constraints.packages`.
2. **One reason code added: `CARD_INCOMPLETE`.** The PM's mapping adds `UNKNOWN_NORMALIZER_VERSION`
   (from t02) and nothing else. Some cards cannot be re-verified at all: no evidence text or offsets,
   no spans, no text hash, no normalizer version. They need a reason, and every existing code would
   send a reader looking for the wrong problem. `TEXT_MISMATCH` and `HASH_MISMATCH` suggest
   tampering, and `SPAN_OUT_OF_RANGE` suggests bad offsets. Without some refusal, a card with
   nothing cut would compare `""` with `""`. The list mirrors the domain's own preconditions for
   VERIFIED, plus the text hash (Decisions §3). A card with no `snapshot_id` reports
   `SNAPSHOT_MISSING`, not this code.
3. **`InvalidMarkup → SPAN_OUT_OF_RANGE` is not implemented, because nothing produces it.** The
   verifier checks `CardSpan`s directly against the reconstructed evidence. It does not convert
   them to t03 `EvidenceMarkupSpan`s inside a `CardMarkup`, for two reasons. Under ADR-0018,
   `CardSpan`s index `evidence_text`, so a span may run across a cut, while `CardMarkup` refuses
   that (`CROSSES_OMITTED_TEXT`). And `CardMarkup` enforces the highlight-within-underline
   convention, which is formatting, not fidelity to the source. `InvalidSelection` and
   `SnapshotTextMismatch` are mapped as decided.
4. **`ensure_finished` is `await verifier.ensure_finished(card)`, not a free function.** It
   re-verifies, so it needs the verifier's ports (Decisions §1). It is still called with the card
   alone.
5. **Added `EvidenceVerifier.verify_and_record(card)`.** It returns the card with
   `verification_status` set from the result, and demotes a card that no longer verifies. The spec
   only asks for a result. But t05 must re-verify on every edit and persist the status, and the
   forbidden list says only `EvidenceVerifier` may set VERIFIED. Without this method, t05 would have
   to write a status itself, and the scan would fail it.

## Decisions and assumptions

1. **`ensure_finished` re-verifies instead of checking a bound result.** Two reasons. First,
   `VerificationResult`s are not stored anywhere. A saved card carries only its status field, so an
   exporter of saved cards would have no result to check a binding against. Second, a result is a
   plain frozen dataclass: anyone can construct one or `dataclasses.replace` the binding onto
   another card. Binding proves only that someone computed it. Re-verifying trusts nothing the card
   says. The cost is one `load` per card: 0.3 ms for a 150 KB web article, 166 ms for a 50 MB PDF
   (t02's measurements). A card whose stored status is UNVERIFIED but which verifies now passes the
   guard. The guard judges the evidence, not the stored claim (test
   `test_ensure_finished_judges_the_evidence_not_the_stored_status`).
2. **What "re-normalizes" means (PM decision, implemented as written).** The verifier loads with
   t02's checks, requires a known `normalizer_version`, reconstructs from the stored normalized text
   at the card's offsets, and compares exactly. `checks_run` lists the eight checks, and none of
   them is a raw-bytes reproduction, so a VERIFIED result cannot be read as claiming one.
   Re-extraction from the raw bytes is follow-up work for E04.
   **Normalizer idempotence: left out.** A scratchpad probe wrote a record and blobs together,
   outside `SnapshotService.create`, with consistent hashes. With un-normalized text
   (`"Wells  will run dry.\n"`), `load` passed, `verify` gave VERIFIED, and an idempotence check
   would have refused it. With invented, already-normalized text (`"Wells will never run dry."`),
   `load` passed, `verify` gave VERIFIED, and an idempotence check would have passed it too. So the
   check catches one thing the hashes miss: a consistent record around un-normalized text. No code
   path writes one, because `create` is the only encoder of snapshot text and it stores
   `normalize()` output. A forger defeats the check by normalizing first. It would also make every
   verification depend on the pinned Unicode database, which loading and offset reconstruction do
   not. Recorded in the verifier module and the format doc.
3. **The card's `normalized_text_hash` is required and compared.** The domain does not require it
   for VERIFIED. It is the only thing that binds a card to the exact text it was cut from,
   independently of the record store. Without it, a snapshot record replaced under the same id with
   consistent blobs would verify the card against different text. Requiring it is stricter than the
   domain, and an UNVERIFIED card is the safe side of that. The extractor's output always carries
   it.
4. **Offset coordinates.** `first_differing_offset` is an index into the card's `evidence_text`. For
   a single-range card the snapshot offset is `evidence_start_offset` plus it. Evidence-text
   coordinates stay meaningful once t07 adds omissions, where a snapshot offset would need mapping.
   When one text is a prefix of the other, the offset is the shorter one's length. Deleting one
   character from a run of equal characters is reported where the texts diverge, which is the end of
   the run's common prefix. Hand-written cases cover both.
5. **The VERIFIED scan.** An AST walk over every `packages/*/src/**/*.py`. It flags
   `VerificationStatus.VERIFIED` used as anything but a comparison operand, a `verification_status=`
   keyword with any value but `UNVERIFIED`, an attribute assignment to `.verification_status`, a
   non-docstring string `"VERIFIED"` or `"verification_status"` (which catches
   `model_copy(update=...)`, `setattr` and `VerificationStatus("VERIFIED")`), and any
   `VerificationResult(...)` call. The allow-list has two entries: the verifier, and
   `debate_core/testing/builders.py`, whose `build_card` passes its caller's status through for
   tests (default UNVERIFIED; the application layer cannot import `testing`). The scan asserts it
   saw all three of the verifier's own kinds of write. It fails if an allow-list entry matches
   nothing. A parametrized self-test shows what it flags and what it leaves alone. It cannot see a
   status computed indirectly, such as `list(VerificationStatus)[1]`. Review has to catch that.
6. **Only expected failures become reasons.** `NotFound` and `SnapshotIntegrityError` from the load,
   and `InvalidSelection` and `SnapshotTextMismatch` from reconstruction, are converted. Everything
   else propagates. That includes `StoreError`, which means verification could not run, not that
   the card failed it. It also includes a record for a different snapshot than the card names, which
   raises `ValueError` as a caller bug. Tests show each.
7. **Every reason is reported, not only the first.** A card that fails several checks lists them in
   check order. `reason_codes` gives the codes without repeats. Reason details never quote evidence
   text. A `TEXT_MISMATCH` detail gives code points (for example `U+0430 ... where the snapshot has
   U+0061`), which is also the only way a homoglyph is visible.
8. **Reconstruction is skipped when it would compare nothing.** That is when the card has no offsets,
   or when its text hash or normalizer version contradicts the snapshot's, because the offsets then
   point into other text. `checks_run` shows the skip, and a reason has already been recorded.
9. **Adversarial fixtures survive t07.** Some fabrications have text whose length differs from the
   range they claim (for example a dropped "not"). They are constructible today. Under t07's length
   invariant they will be refused at construction instead. The test counts that as a refusal, and
   requires every same-length fabrication and all 579 same-length mutations to reach the verifier,
   so it cannot pass vacuously after t07.

## Operator follow-ups

None. Every command in this task finished in under 20 seconds and was run in the session.

## Follow-up work

- **E04 content extractor: raw-bytes re-extraction as a verification check.** Re-run the extractor
  on the stored raw bytes and compare with the stored normalized text, if the extractor is
  deterministic for its `extractor_version`. It would be a new `VerificationCheck` and a new
  `VERIFIER_VERSION`.
- **`v1-e03-t07-card-omissions`:** extend `reconstruct_card_evidence` to select the envelope minus
  `omitted_ranges`. `evidence_text_of` already joins segments with no joiner. Switch
  `tests/fixtures/verification/verification_world.py`'s `card_from_extraction` to t07's function.
  The fabrications that change length will start being refused by the domain, and the adversarial
  test already allows for that (Decisions §9). If t07 adds a field that matters to verification, it
  belongs in `check_card`'s completeness list.
- **`v1-e03-t05-edit-constraints`:** use `EvidenceVerifier.verify_and_record` after each accepted
  edit. Any other write of `verification_status` fails `test_verified_is_set_only_by_the_evidence_verifier`.
- **`v1-e03-t06-verify-command`:** call `EvidenceVerifier.verify` per card. Decide the exit code for
  a `StoreError`, which propagates by design: it is neither "UNVERIFIED" (1) nor a manifest error
  (2). Reason details are safe to print, because they never quote evidence. Verification loads the
  snapshot per card; a batch use case could cache, but only through `SnapshotService.load`, never a
  hand-built `LoadedSnapshot`.
- **E06 exporters:** call `await verifier.ensure_finished(card)` before rendering a finished card.
  Tests can use `VerificationWorld` for one card that verifies and one that does not.
- **For the PM: the card's `article_id` is not compared with its snapshot's.** A card citing one
  article while quoting another's snapshot verifies today. That is a provenance check, outside this
  spec's list, and no reason code fits it cleanly. Listed under "What it does not guarantee yet" in
  the format doc.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
