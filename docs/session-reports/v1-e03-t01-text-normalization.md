# Session report: v1-e03-t01-text-normalization

| | |
|---|---|
| Task | `v1-e03-t01-text-normalization` — Deterministic, versioned text normalization |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t01-text-normalization.yaml`](../../plan_specs/v1/e03-evidence-integrity/t01-text-normalization.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t01-text-normalization` |
| Session status | COMPLETE |

## Summary

This task adds `debate_core.evidence.normalization`, the normalizer whose output every later
evidence comparison, hash and quoted span is taken from. `normalize(text, version)` returns a
`NormalizedText` holding the text, the version, paragraphs `p0001`, `p0002`, ... and an offset map
between raw and normalized text that is built while the rules apply. The rules are written down
first, in [`docs/evidence/normalization.md`](../evidence/normalization.md) (`evidence-normalizer-v1`).
They are NFC pinned to Unicode 15.0.0, explicit whitespace, line-break and paragraph tables, four
removed invisible characters, and nothing else. Quotes, dashes, case, ligatures and hyphenated
words are left alone. Versions are a registry with v1 frozen, the version is a required argument,
and unknown versions and a different Unicode database are both refused rather than defaulted.

**What the PM should look at first:** the Unicode pin (Decisions §1). It fails closed, so moving
the repository to Python 3.13 will make `normalize` raise until someone handles it on purpose.
That is intended, and it is recorded as follow-up work.

The fingerprint normalizer in `fingerprints.py` was not touched, imported or shared from.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `policy-doc`: Normalization policy v1 | Done | Written before any code. It lists every code point the explicit rules transform, plus an appendix of all 1,120 code points NFC replaces and the 111 it can compose into a preceding character (Unicode 15.0.0) |
| `char-rules`: Character-level normalizer | Done | `CharacterRules` table per version, the v1 algorithm in one pass, and `normalize_chars()` with the raw→normalized map built as the rules apply |
| `paragraphs-offsets`: Paragraph segmentation and offset map | Done | `NormalizedText` with `paragraphs`, `paragraph()`, `paragraph_text()`, `to_raw_range()` and `to_normalized_range()`; `OffsetMap` validates that its segments form an alignment |
| `property-golden`: Property-based and golden tests | Done | 11 hypothesis properties over real Unicode, a hash-seed determinism check and a six-case invented golden corpus with hand-written expectations |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `normalize(text, version)` is idempotent and deterministic, proven by hypothesis property tests over arbitrary Unicode | PASS | `uv run pytest packages/debate_core/tests/evidence/test_normalization_props.py`. `test_normalize_is_idempotent` also checks the second pass's offset map is the identity. `test_normalize_is_deterministic` passes, and so does `test_normalize_is_deterministic_across_hash_seeds` (the golden corpus digest agrees under `PYTHONHASHSEED` 0, 1 and 4242 in subprocesses). Result: 20 passed |
| ac2: whitespace-only changes inside a paragraph change no paragraph ID or paragraph count | PASS | The property `test_paragraph_ids_survive_whitespace_edits_inside_paragraphs` rewrites every inter-word gap, splits words with whitespace, pads paragraph edges and swaps each paragraph break for another; IDs, count and paragraph content are unchanged. Example: `test_paragraph_ids_ignore_whitespace_edits_inside_a_paragraph`. See Decisions §4 for what counts as "inside a paragraph" |
| ac3: the offset map converts any normalized `[start, end)` back to the raw range with the same characters, verified by property tests | PASS | `test_offset_map_carries_any_normalized_range_to_raw_text_with_the_same_characters` checks coverage, same characters after dropping whitespace, and tightness at content edges. `test_offset_map_carries_any_raw_range_to_exactly_the_normalized_text_it_became` runs the reverse per character. `test_offset_map_round_trips_exactly_between_segment_boundaries` checks exact round trips, and `test_offset_segments_align_the_same_characters` checks every segment |
| ac4: `docs/evidence/normalization.md` lists every transformed code point, and a golden test pins v1 on news, PDF-extracted and think-tank paragraphs | PASS | Four `test_chars_policy_*` tests parse the doc's tables and check them against the implementation's tables and against Unicode 15.0.0 (1,120 and 111 code points). `test_golden_v1_output` covers 6 cases in `tests/fixtures/normalization/golden-evidence-normalizer-v1.json` (genres news, pdf and think-tank). The expected normalized paragraphs *and* the expected raw text of each paragraph were written by hand |
| Node `policy-doc`: policy document exists and contains `NORMALIZER_VERSION` | PASS | `grep -c NORMALIZER_VERSION docs/evidence/normalization.md` → `2` |
| Node `char-rules`: `uv run pytest packages/debate_core/tests/evidence/test_normalization.py -k chars` | PASS | `86 passed` |
| Node `paragraphs-offsets`: `uv run pytest packages/debate_core/tests/evidence/test_normalization.py -k "paragraph or offset"` | PASS | `33 passed` |
| Node `property-golden`: `uv run pytest packages/debate_core/tests/evidence` | PASS | `364 passed in 7.97s`; `normalization.py` line and branch coverage 100% |
| Node `property-golden`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |
| Epic node: `uv run scripts/validate_specs.py --require-succeeded v1-e03-t01-text-normalization` | PASS | `v1-e03-t01-text-normalization: Succeeded`; `uv run scripts/validate_specs.py` → `OK: 288 files, 38 epics, 230 tasks, 20 releases` |

Other checks run: `uv run pytest -q` → `3039 passed, 1 skipped in 44.22s` (run at 02:28 CDT, before
the 19:00 ledger failures of v1-e34-t06 can appear); `uv run lint-imports` → `Contracts: 10 kept,
0 broken`; `uv run ruff check` and `ruff format --check` on `packages/debate_core` are clean.

**How the tests were checked for teeth.** I made six deliberate mutations to the normalizer, and
each one failed a property test:

| Mutation | Test that failed |
|---|---|
| NFC applied per character instead of per stable run | `test_text_without_policy_characters_is_exactly_nfc` |
| One line break treated as a paragraph break | `test_paragraph_ids_survive_whitespace_edits_inside_paragraphs` |
| CR LF counted as two line breaks | `test_paragraph_ids_survive_whitespace_edits_inside_paragraphs` |
| A replaced segment mapped to the wrong raw end | `test_offset_map_round_trips_exactly_between_segment_boundaries` |
| Content casefolded | `test_normalize_changes_only_whitespace_and_listed_code_points` |
| ZWJ added to the removed table | An offset property; the hand-pinned table test also covers this |

I also made a one-off local run of every property at 5,000 examples each (41 s, not committed; CI
uses 400). Hypothesis falsified two of *my test's* definitions, and neither exposed an
implementation bug. First, an empty raw range was counted as overlapping the gap it sat in.
Second, the covering property was being applied to empty normalized ranges strictly inside an
NFC-replaced unit, which have no finer raw position. Both definitions were corrected, and the
policy now documents the empty-range behaviour. After that, all 20 passed at 5,000 examples.

## Files changed

* `docs/evidence/normalization.md` (new): the v1 policy, which is the contract.
* `packages/debate_core/src/debate_core/evidence/normalization.py` (new): the normalizer, version
  registry, `OffsetMap` and `NormalizedText`. `evidence/__init__.py` re-exports `normalize`,
  `NormalizedText`, `NORMALIZER_VERSION` and `SUPPORTED_NORMALIZER_VERSIONS`.
* `packages/debate_core/tests/evidence/test_normalization.py` (new): example tests for the
  character rules, paragraphs and offsets, plus policy/implementation agreement tests.
* `packages/debate_core/tests/evidence/test_normalization_props.py` (new): hypothesis properties
  and the golden test.
* `tests/fixtures/normalization/golden-evidence-normalizer-v1.json` (new): an invented corpus
  with hand-written expectations.
* `docs/README.md` and `docs/process/working-agreements.md`: one index line each for the new
  `docs/evidence/` folder (see Deviations).
* `plan_specs/v1/e03-evidence-integrity/t01-text-normalization.yaml`: Goal phase set to `Succeeded`.

## Deviations from the spec

* **Two one-line edits outside `constraints.packages`.** Working agreements §3 says a new
  top-level docs folder must be added to its directory table and to `docs/README.md`. The spec
  requires `docs/evidence/`, but its package list does not cover those two files. I added one row
  to each and made no other change. If the PM prefers to land those rows separately, they can be
  reverted without affecting anything else in the task.

## Decisions and assumptions

1. **Unicode is pinned to 15.0.0 and fails closed.** `normalize` raises
   `UnicodeDatabaseMismatchError` if `unicodedata.unidata_version` is not v1's pinned version.
   Every Python 3.12 has 15.0.0, which matches `.python-version` and CI. NFC of characters already
   assigned is stable forever, but characters assigned after 15.0 can decompose under a newer
   database. A silent change to stored offsets and hashes is exactly what this task exists to
   prevent, so refusing to run was chosen over "probably the same".
2. **Version name and shape.** The version is `evidence-normalizer-v1`, a name distinct from
   `card-fingerprint-v1`. The version is a required argument with no default, so re-verification
   has to name the card's version. Each version gets a `CharacterRules` table plus its own
   implementation functions, and v1's are frozen. `SUPPORTED_NORMALIZER_VERSIONS` is derived from
   the registry so the two cannot drift apart.
3. **The rule choices** all follow from "may change only whitespace and listed code points":
   * NBSP, NNBSP and the other Zs spaces fold into gaps.
   * Soft hyphen, ZWSP, word joiner and BOM are removed.
   * ZWJ and ZWNJ are kept, because they are orthographic in Persian and Indic scripts and emoji.
   * Bidi controls are kept, because removing them can reorder displayed RTL text.
   * Form feed is a line break, not a paragraph break: PDF page breaks usually fall mid-paragraph.
   * A hard hyphen at a line end is not rejoined (`eco- nomic`), because telling it apart from
     `well-known` would need a dictionary.
   * Ligatures are kept, since only NFKC expands them. Matching and search should fold them, and
     quoted text should not.

   Each choice has a row with its reason in the policy's "deliberately not changed" table.
4. **"Inside a paragraph" for ac2** means whitespace that does not create a blank line. By
   definition a blank line is a paragraph break, so adding one changes the count. The property
   test generates edits under exactly that constraint, including splitting words, padding edges
   and swapping each paragraph break for a different one.
5. **Offset granularity.** Content is NFC'd run by run between `NFC_Quick_Check=Yes` starters
   (UAX #15). An unchanged character therefore maps one to one, and only a run that NFC changed is
   a unit. That boundary rule is conservative: `"0" + U+F900` becomes one two-character unit even
   though `0` itself is unchanged. It is correct, and at most slightly coarse.
6. **Lone surrogates are rejected** with `InvalidTextError`. They cannot be UTF-8 encoded, so
   `v1-e03-t02` could not hash them anyway.
7. **Doc appendix tables are generated from Unicode data, while the expectations are
   hand-written.** The appendix is Unicode's data, not an expected output of this code. A test
   holds it equal to `unicodedata`, and v1's own tables are also pinned by hand in
   `test_chars_policy_tables_match_the_hand_written_v1_classes`. Every example and golden
   expectation was written by hand from the policy (§6). While writing them, I caught and fixed
   one of my own arithmetic slips (a raw range of `(6, 11)` that should have been `(6, 10)`)
   before the first run.
8. **Plain frozen dataclasses** are used for `NormalizedText`, `OffsetMap` and `Paragraph`, not
   Pydantic models. `NormalizedText` does not carry the raw text. How they are persisted is
   `v1-e03-t02`'s decision. `OffsetMap(segments, ...)` validates its input so a deserialized map
   cannot be malformed.

## Operator follow-ups

None.

## Follow-up work

* **Python upgrade past 3.12 (whoever bumps `.python-version`).** Python 3.13 ships Unicode 15.1,
  and `normalize` will raise under it. Before upgrading, check that no code point assigned in 15.1
  or later has a canonical decomposition or composes. Then either add that database to v1's
  accepted set with a written justification, or cut `evidence-normalizer-v2`. The policy's
  Determinism section describes this.
* **`v1-e03-t03-span-extraction`: grapheme boundaries.** The offset map is code-point exact, so a
  normalized range can split a base letter from its combining mark, or split a ZWJ emoji sequence.
  Whether card spans should snap to grapheme clusters is span extraction's decision, not the
  normalizer's.
* **`v1-e03-t02-hashing-provenance`: persistence.** The snapshot's "normalized text and its
  paragraph map" needs a serialized form of `NormalizedText.paragraphs` and
  `OffsetMap.segments`. Both are plain tuples of ints, strings and booleans.
* **Search/matching (E04/E05): ligature and quote folding** belongs to retrieval-side matching
  (compare `fingerprints.normalize_for_matching`), never to this normalizer.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
