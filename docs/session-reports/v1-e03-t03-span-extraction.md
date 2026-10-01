# Session report: v1-e03-t03-span-extraction

| | |
|---|---|
| Task | `v1-e03-t03-span-extraction` — Span-addressed evidence extraction |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t03-span-extraction.yaml`](../../plan_specs/v1/e03-evidence-integrity/t03-span-extraction.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t03-span-extraction` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task adds `EvidenceExtractor` (`debate_core.evidence.extractor`). It takes a snapshot record,
the snapshot's normalized text and an `EvidenceSelection` of paragraph runs and offset ranges. It
returns `ExtractedEvidence`: ordered segments sliced from that text, and the cuts between them as
`OmittedRange` offsets that carry no text. `CardMarkup` (`debate_core.evidence.markup`) checks
underline and highlight spans against that evidence, in snapshot offsets. Every criterion passed,
and the Goal is `Succeeded`.

**What the PM should look at first:**

* **No public constructor in these modules takes evidence text.** A segment holds the
  `SnapshotText` and its offsets, and its `text` is a slice taken on every read. The signature test
  went red for all seven ways I tried to add a text parameter. Its second half also catches a
  text-taking helper added anywhere else in `debate_core` (ac4 table below).
- **The extractor checks the paragraph map at the point of use.** Before it resolves a paragraph
  ID, it compares the map with the one the text's normalizer version gives that text. A boundary
  moved the way t02 found is refused, whichever route the `SnapshotText` took (Decisions §2).
- **Two deviations, both choices the spec left open and t04 will inherit:**
  - The signature is `extract(snapshot, snapshot_text, selection)`.
  - Markup is an evidence-layer type, not the domain `CardSpan`, because the domain `CardSpan` is
    relative to `evidence_text` while ac3 asks for snapshot-relative offsets.
- **Mutation testing found four gaps, and all four are closed.** One check was redundant, one
  check was load-bearing yet no example test exercised it, and two were property-generator blind
  spots. Re-run with a fresh Hypothesis database per run, every one of 26 mutants is caught.
- **The 50,000-example deep run passed.** The operator ran it on 2026-10-01: `5 passed in 194.01s`.
  I ran 10,000 examples per property myself.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `selection-types` — EvidenceSelection and segment types | Done | `selection.py`: `EvidenceSelection` (parts are `OffsetRange` or `ParagraphRun`), `ParagraphId` (a `NewType`), `EvidenceSegment`, `OmittedRange`, `InvalidSelection` with a `SelectionProblem` code. |
| `extractor` — EvidenceExtractor | Done | `extractor.py`: resolves paragraph runs, sorts parts into source order and joins touching ones. Overlaps, reversed ranges and out-of-range offsets are refused, never clamped. Checks the text against the record and the map against the text. |
| `markup-spans` — CardSpan construction | Done | `markup.py`: `EvidenceMarkupSpan` and `CardMarkup`. Each span must be non-empty and inside a single segment, never across a cut. Spans of one style may not overlap, and every highlighted character must be underlined. See Deviations for why this is not the domain `CardSpan`. |
| `property-tests` — Property tests and type check | Done | Five Hypothesis properties against oracles written from the rules, plus the signature test. Run deep, then with each guarded check removed (below). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — `extract` returns segments whose text equals the normalized snapshot text at the recorded offsets, for paragraph-ID and offset selections | PASS | `test_extractor.py` compares against expected strings and offsets written by hand from an invented three-paragraph source: one paragraph, a run, offsets inside a paragraph and across a break, and up to the last character. `test_extract_through_a_verified_load` goes `SnapshotService.create` → `load` → `extract`. The property `test_extract_a_valid_selection_yields_exactly_the_selected_characters_in_source_order` checks that the segments hold exactly the selected characters, none added and none dropped. |
| ac2 — non-contiguous selections give ordered segments with explicit `OmittedRange` records; overlapping or reversed ranges raise `InvalidSelection` | PASS | Non-contiguous paragraphs, mixed parts and backwards-given parts each give hand-written segments and cuts. `pieces()` alternates segment and cut, and `OmittedRange` has only `start` and `end`. Overlaps are refused: partial, contained, identical, backwards, and overlaps that appear only after paragraphs resolve. Reversed offset ranges and reversed paragraph runs are refused, including a reversed run that touches another part (Decisions §4). The property `test_extract_an_arbitrary_selection_is_either_exact_or_refused_never_repaired` covers random selections. |
| ac3 — CardSpan builders reject empty, out-of-bounds and same-style-overlapping spans, and record snapshot-relative offsets | PASS (see Deviations: the builders are `EvidenceMarkupSpan`/`CardMarkup`) | `test_markup.py` → `35 passed`. Empty, reversed, negative, `bool`, `float` and string-typed spans are refused. So are spans before or past the evidence, spans over a cut (five positions), and six same-style overlap shapes. `test_markup_records_snapshot_offsets_not_offsets_into_the_evidence` checks "twice" is recorded at 82, not 17 or 48. The property `test_markup_is_accepted_exactly_when_…` agrees with the oracle in both directions. |
| ac4 — the extractor API has no parameter that accepts free text, enforced by a signature test | PASS | `test_no_public_extraction_api_has_a_parameter_that_accepts_free_text` and `test_nothing_in_debate_core_produces_extracted_evidence_from_free_text`, plus 15 cases of the annotation check itself → `17 passed`. Each scan asserts it saw the entry points it exists for, so it cannot pass by seeing nothing. It went red for every mutation in the ac4 table below. |
| `selection-types` node: selection module exists with `class EvidenceSelection` | PASS | `grep -c "class EvidenceSelection" packages/debate_core/src/debate_core/evidence/selection.py` → `1` |
| `extractor` node: extraction tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence/test_extractor.py` → `87 passed in 6.92s` |
| `markup-spans` node: markup span tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence/test_markup.py` → `35 passed in 4.56s` |
| `property-tests` node: property tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence -k "extract or markup"` → `130 passed in 7.73s`. `selection.py`, `extractor.py`, `markup.py` and `_runtime_checks.py` are each 100% line and branch covered. |
| `property-tests` node: pyright strict passes | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |

Wider checks: `uv run pytest` (whole repository, default markers) → `3349 passed, 1 skipped in
52.55s`. The skip is the existing `tests/evals/parser/test_parser_eval.py:279`. `uv run ruff check .`
→ clean. `ruff format --check .` → `428 files already formatted`. `uv run lint-imports` →
`Contracts: 10 kept, 0 broken`, with no new `ignore_imports` entry. `uv run scripts/validate_specs.py`
→ `OK: 292 files, 38 epics, 234 tasks, 20 releases`. t02's
`test_nothing_in_debate_core_turns_serialized_text_into_a_snapshot_text_without_a_key` still passes:
nothing here turns bytes into a `SnapshotText`.

### ac4, proved by mutation

Each row adds one text-carrying parameter, runs `-k free_text`, and restores the file. All seven
went red.

| Mutation | Caught by |
|---|---|
| `extract(..., text: str = "")` | the public-API scan |
| `extract(..., **overrides)` with no annotation | the public-API scan (an unannotated parameter counts as text) |
| `EvidenceSegment` gains a `quote: str \| None` field | the public-API scan |
| `OffsetRange` gains `expected: Quote \| None`, with `Quote = NewType("Quote", str)` | the public-API scan (only `ParagraphId` is an allowed string alias) |
| `EvidenceSelection.from_quote(cls, quote: str)` classmethod | the public-API scan |
| `evidence_from_text(snapshot, text: str) -> ExtractedEvidence` added to `application/snapshot_service.py` | the debate_core-wide scan |
| A `QuotedEvidence(ExtractedEvidence)` subclass in the application layer whose `__init__` takes `quote: str` | the debate_core-wide scan |

My first attempt at the `NewType` row errored at collection: `Quote` was used before it was
defined. That error proves nothing, so I did not count it as a catch. I re-ran it with the alias
defined first.

What the signature test cannot see: `SnapshotText(text=...)` and `SourceSnapshot(...)` are ordinary
constructors that take text. The extractor's inputs can therefore be invented together by a caller
that means to. The extractor's module docstring says so plainly: the text must come from
`SnapshotService.load`, and that guarantee is the caller's (Decisions §1).

### Breaking the implementation on purpose

Each row is one deliberate change, applied alone. For each, I ran the example tests
(`test_extractor.py` and `test_markup.py`) and the property that guards the check, alone at 10,000
examples. Every run used a fresh, empty Hypothesis database (see the note after the table). The
runner applies one exact-string replacement and always restores the file's bytes. It is in the
session scratchpad and not committed.

| Break | Examples | Guarding property @ 10,000 |
|---|---|---|
| Touching ranges not joined | caught | caught (valid-selection) |
| …and the `SEGMENTS_TOUCH` backstop also removed | caught | caught |
| Parts not sorted into source order | caught | caught (valid-selection) |
| Segment bounds check removed | caught | caught (arbitrary-selection) |
| Offsets clamped to the text length (`min(end, len)`) | caught | caught (arbitrary-selection) |
| Overlap refusal removed (`ExtractedEvidence`, now the only one) | caught | caught (arbitrary-selection) |
| Reversed paragraph run check removed | caught (by a test added for it) | caught, but late: 36 s into the 10,000 |
| Empty paragraph run check removed | caught | **survived**: unreachable, because v1 never produces an empty paragraph |
| Unknown paragraph falls back to the first paragraph | caught | caught (arbitrary-selection) |
| Paragraph-map check skipped | caught | caught (moved-boundary) |
| Paragraph map compared by count only | caught | caught (moved-boundary) |
| Paragraph map compared by IDs only | caught | caught (moved-boundary) |
| Text-hash check removed | caught | caught (one-character-change) |
| Normalizer-version check removed | caught | none guards it |
| `ExtractedEvidence` does not call the binding check | caught | caught (one-character-change) |
| Segments from different `SnapshotText`s accepted | caught | none guards it |
| Segment text sliced one character long | caught | caught (valid-selection) |
| `bool` accepted as an offset | caught | none guards it |
| Markup: containment check removed | caught | caught (markup) |
| Markup: outside-evidence *label* removed (everything reported as a cut) | caught | **survived**: the property checks refusal, not the problem code |
| Markup: same-style overlap check removed | caught | caught (markup) |
| Markup: spans not sorted before the neighbour check | caught | caught (markup) |
| Markup: highlight-within-underline check removed | caught | caught (markup) |
| Markup: a highlight only needs to start inside an underline | caught | caught (markup) |
| Markup: touching underlines cannot carry a highlight across | caught | caught (markup), after the generator fix below |
| Markup: empty span allowed | caught | none guards it |

**A note on the Hypothesis database.** I ran the reversed-run mutant three times to see how
reliably the property caught it. Run one caught it 28 seconds in. Runs two and three "caught" it in
0.3 seconds, but that was Hypothesis replaying the failing example saved by run one, not finding it
again. Results like that overstate how strong a property is, and fast catches earlier in my first
pass may have been replays too. The table above comes from a second full pass with
`HYPOTHESIS_STORAGE_DIRECTORY` pointed at a new empty directory for every run.

### What breaking it found

The first pass, before the fixes, found four things. Each is now closed.

1. **A redundant check.** The extractor refused overlaps itself, and `ExtractedEvidence` refused
   them again. Removing the extractor's check changed nothing: same exception, same problem code,
   every test and the property at 10,000 still passed. A check that cannot be told apart from its
   absence is decoration, so I deleted it. `ExtractedEvidence` is now the one place overlaps are
   refused, and removing that check is caught by both the examples and the property.
2. **A load-bearing check no example test exercised.** With the reversed-run check removed, every
   example test passed. The arbitrary-selection property failed. Run p0002..p0001 resolves to
   `(33, 31)`. Next to a part ending at 33, the extractor joins the two as touching, and the
   selection silently becomes `[20, 31)`: shortened, not refused. That is the clamping failure
   the spec forbids, arriving by another route. I added
   `test_extract_refuses_a_reversed_run_that_touches_another_part_instead_of_shortening_it`. The
   property then missed it in a fresh run, because the case needs a part ending exactly at a
   paragraph edge, so I made it draw offsets at paragraph edges. It now catches it, at 36 s into
   10,000 examples. The example test is the reliable guard.
3. **A markup property that was decorative for one path.** It never generated two underlines that
   touch, so it could not see a highlight that runs across them being wrongly refused. It now
   splits some underlines into touching pairs and catches that mutant.
4. **Two overlapping containment checks in markup.** Removing the outside-evidence check left the
   property passing, because the cut check refuses the same spans. It is now one decision ("is the
   span inside a single segment?"), and the problem code is a label on the refusal. Removing the
   decision is caught everywhere. Removing only the label is caught by the example tests, which
   assert the code.

Bugs in my own tests, caught before they could hide anything: a three-way `zip(strict=True)` over
lists of different lengths, and a generator asking for more distinct cut points than its range
held.

### Property statistics and the deep run

At 2,000 examples each on the final code, fresh database (`--hypothesis-show-statistics`).
Percentages are of all generated examples, so they do not sum to 100:

- **Valid-selection property:** 47% of examples had one segment and 36% had two or more. 16% used
  paragraph runs, and 21% joined touching parts.
- **Arbitrary-selection property:** 32% of selections were valid and 54% invalid, so both branches
  are exercised.
- **Markup property:** 33% valid with spans, 25% invalid, 20% with no spans. Before I rebalanced the
  generator, only 3.5% of its examples were valid markup with any spans, so the acceptance direction
  was barely tested.

The five properties at 10,000 examples each, `-n 5`: `5 passed in 45.66s`. The default run is 200
examples (`EXTRACTION_PROPERTY_EXAMPLES`), which keeps CI fast.

The five properties at 50,000 examples each, run by the operator on 2026-10-01 in the task worktree
(Python 3.12.7, hypothesis 6.168.0):
`EXTRACTION_PROPERTY_EXAMPLES=50000 uv run pytest packages/debate_core/tests/evidence/test_extraction_properties.py --no-cov -n 5`
→ `5 passed in 194.01s (0:03:14)`. That run used the worktree's own Hypothesis database, so it also
replayed any examples saved during my first mutation pass. A pass is unaffected by that; it only
adds cases.

## Files changed

* `packages/debate_core/src/debate_core/evidence/selection.py`: new. Selection parts,
  `EvidenceSelection`, `EvidenceSegment`, `OmittedRange`, `InvalidSelection`/`SelectionProblem`.
* `packages/debate_core/src/debate_core/evidence/extractor.py`: new. `EvidenceExtractor`,
  `ExtractedEvidence`, `SnapshotTextMismatch`/`SnapshotTextCheck`. Its module docstring states that
  the `SnapshotText` must come from a verified load, and what the extractor checks in its place.
* `packages/debate_core/src/debate_core/evidence/markup.py`: new. `EvidenceMarkupSpan`, `CardMarkup`,
  `InvalidMarkup`/`MarkupProblem`.
* `packages/debate_core/src/debate_core/evidence/_runtime_checks.py`: new, private. `isinstance`
  helpers typed on `object`, so strict pyright allows runtime guards on deserialized input.
* `packages/debate_core/src/debate_core/evidence/normalization.py`: adds the public `paragraph_map(text,
  version)`, which exposes the existing per-version segmentation. No rule or frozen v1 function
  changed (Decisions §2).
* `packages/debate_core/tests/evidence/test_extractor.py`, `test_markup.py`,
  `test_extraction_properties.py`: new tests. All source text is invented in the files, and no
  fixtures were added. `SnapshotText` values come from a normalizer result or from
  `SnapshotService.load`, never from decoding bytes written by hand.
* `plan_specs/…/t03-span-extraction.yaml`: phase only.

## Deviations from the spec

* **The signature takes the record and the text: `extract(snapshot: SourceSnapshot, snapshot_text:
  SnapshotText, selection: EvidenceSelection)`.** The spec writes `extract(snapshot, selection)` and
  says "given a SourceSnapshot". A `SourceSnapshot` holds hashes, versions and blob keys, not text.
  `LoadedSnapshot` pairs the two, but it lives in `application`, above `evidence`, so the extractor
  cannot take it. Taking only the text would lose the snapshot ID, text hash and normalizer version
  a card needs to be re-verified. The caller would then pair them up again later, which is exactly
  where text from one snapshot gets the ID of another. With both, the result carries its own
  provenance (`evidence.snapshot_id`, `.normalized_text_hash`, `.normalizer_version`), and the
  pairing is checked here (Decisions §1). **For t04:** a verifier can rebuild a card's evidence by
  calling `extract(loaded.snapshot, loaded.normalized, EvidenceSelection.of_offsets(...))` with the
  card's stored offsets.
* **ac3's "CardSpan builders" build `EvidenceMarkupSpan` records inside a `CardMarkup`, not
  `debate_core.domain.CardSpan`.** The domain `CardSpan` documents its offsets as "into the card's
  `evidence_text`", while ac3 requires snapshot-relative offsets. A domain `Card` also has a single
  `evidence_text` with one start and end offset, and no place for the cuts in non-contiguous
  evidence. So there is no faithful way to put this task's output onto today's `Card`. The domain is
  outside this task's package list. The builders do everything ac3 asks, on a type of their own in
  `debate_core.evidence`. Mapping them onto a card is the card service's step (`v1-e06-t02`), and
  it needs a decision first (Follow-up work). I named the type `EvidenceMarkupSpan` so it does not
  collide with the `MarkupSpan` model output that `v1-e05-t06` will define in the same package.

## Decisions and assumptions

1. **What the extractor checks, given that it cannot check provenance.** Every `ExtractedEvidence`,
   however it is built, requires the text's SHA-256 to equal the record's `normalized_text_hash` and
   the two normalizer versions to match. Otherwise it raises `SnapshotTextMismatch`. That catches
   text paired with the wrong record, and one changed character anywhere in the text (property, 10,000
   examples). It does not catch a record and a text invented together. The module docstring says
   so, and puts the guarantee on the caller.
2. **The paragraph map is checked against the text whenever a paragraph is selected.** t02 found
   that a boundary moved to another valid offset is invisible to every check but the normalized
   blob's own hash. For v1, the correct map is a pure function of the text, so the extractor
   re-derives it (`normalization.paragraph_map`) and refuses a map that differs. That closes the
   finding at the point of use, even for a `SnapshotText` that skipped `load`. Offset-only
   selections do not depend on the map and skip the check. `paragraph_map` reuses the frozen v1
   segmentation function rather than duplicating it. It deliberately skips the Unicode-database pin,
   because segmentation reads no Unicode data. A version that does not exist still raises
   `UnknownNormalizerVersionError`.

   Measured cost on an Apple M3 Pro, Python 3.12.7 (median of 30–200 runs, synthetic text; script
   in the scratchpad, not committed):

   | Text | Characters | Paragraphs | Extract by offsets | Extract by paragraph | Text hash alone | Map derivation alone |
   |---|---|---|---|---|---|---|
   | News article | 17,810 | 61 | 0.012 ms | 0.067 ms | 0.007 ms | 0.047 ms |
   | Long report | 348,646 | 1,194 | 0.172 ms | 1.263 ms | 0.127 ms | 0.970 ms |
   | Very large | 2,341,838 | 8,020 | 1.237 ms | 8.687 ms | 0.909 ms | 6.637 ms |

   The map check accounts for most of a paragraph extraction. Against t02's measured `load` (166 ms
   at 50 MB raw), it is small, so I kept it always on, like `load`'s own checks.
3. **The extractor never changes what was selected.** Every selected character lands in exactly
   one segment, and no unselected character lands in any. It follows that:
   - Parts that touch become one segment, because nothing lies between them and an ellipsis there
     would announce a cut that never happened.
   - Consecutive paragraphs listed as separate parts keep the paragraph break between them as an
     `OmittedRange`, because the break was not selected. `ParagraphRun(first, last)` selects a run
     including its breaks, as one segment.
   - Parts may be given in any order and come out in source order. A selection therefore cannot
     splice a source's sentences into an order it did not write them in.
   - The overall extent is `[segments[0].start, segments[-1].end)`.
4. **A reversed paragraph run is refused explicitly, not left to the segment's range check.** Left
   to that check, a reversed run touching another part gets joined and shortens the selection
   (mutation finding 2).
5. **Markup may not cross a cut.** A span must lie inside a single segment, so an underline that
   continues past an ellipsis is two spans. Highlights must be covered by the union of underlines,
   so a highlight may run across two underlines that touch. A `CardMarkup` with no spans is
   allowed. Whether a card needs at least one span to be `VERIFIED` is the domain's and t04's rule,
   not this module's.
6. **Runtime type checks as well as annotations.** Selections will come from deserialized model
   output (`v1-e05-t06`), so constructors refuse a `bool` or `float` offset, a string style or
   purpose, and a list where a tuple is expected, at runtime. Refusals carry a problem enum
   (`SelectionProblem`, `MarkupProblem`, `SnapshotTextCheck`) that a caller can map to reason codes
   without parsing messages.

## Operator follow-ups

Done: the deep property run at 50,000 examples per property, `5 passed in 194.01s` (see "Property
statistics and the deep run").

What remains is the usual step after review: `scripts/task pr v1-e03-t03-span-extraction`, run from
the task worktree.

## Follow-up work

* **How a `Card` represents non-contiguous evidence and its markup (owner: PM; touches
  `debate_core.domain`, needed by `v1-e03-t05` and `v1-e06-t02`).** Today a `Card` has one
  `evidence_text` with one start and end offset, and `CardSpan` offsets are relative to that text.
  `ExtractedEvidence` can have several segments with cuts between them. Deletions in t05 ("adding
  omitted ranges") will produce exactly that. Before t04 builds cards, someone must decide whether
  a card stores segments and omitted ranges and whether `CardSpan` moves to snapshot offsets. Until
  then, single-segment evidence maps cleanly: `evidence_text` is the segment's text, and the card
  offset is the snapshot offset minus `evidence.start`.
* **`v1-e03-t04-verifier`: reason codes for these refusals.** Suggested mapping:
  - `InvalidSelection` → `SPAN_OUT_OF_RANGE`.
  - `SnapshotTextMismatch` with `TEXT_HASH`, `NORMALIZER_VERSION` or `PARAGRAPH_MAP` →
    `HASH_MISMATCH`.
  - `InvalidMarkup` → `SPAN_OUT_OF_RANGE`.
* **`v1-e05-t06-card-selection-contract`:** its `CardSelection` can convert to `EvidenceSelection`
  (`OffsetRange`, `ParagraphRun`) and its `MarkupSpan` to `EvidenceMarkupSpan`. Its guard's
  "offset outside the snapshot" check then has a second line of defence here. The signature test
  will fail if that conversion is written as a function taking text.
* **Rendering a cut that holds only a paragraph break (`v1-e06` renderer).** Paragraphs selected as
  separate parts leave an `OmittedRange` over just `"\n\n"`. Whether that renders as an ellipsis or
  a plain paragraph break is a renderer decision. `ParagraphRun` avoids it at the source.
* **`docs/evidence/snapshot-text-format.md`:** its guarantees table could add that span extraction
  now re-checks the paragraph map against the text at the point of use. `docs/` was outside this
  task's package list, so I did not edit it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-01

**Notes:**

Accepted in full, phase `Succeeded`. Both deviations are right, the follow-up that matters is mine
rather than yours, and one finding in here changes how every future task reports property strength.

**The Hypothesis replay finding is the most valuable thing in this report, and it reaches
backwards.** One mutant caught at 28 seconds and then twice at 0.3 seconds is not a property that
got faster; it is Hypothesis replaying the saved failing example instead of rediscovering it. You
noticed a number that was too good, worked out why, and re-ran the entire mutation pass with a
fresh `HYPOTHESIS_STORAGE_DIRECTORY` per run rather than reporting the table you already had.

It reaches backwards because neither `v1-e03-t01` nor `v1-e03-t02` isolated the database, and both
reported mutation tables with catch times. Their conclusions about which checks are load-bearing
probably stand, because a saved example that kills one mutant usually kills a closely related one
for the same reason. What does not stand is reading those timings as evidence of how readily the
properties find a break from scratch. I am not reopening either task for it. I am making the fresh
database per mutation run a standing requirement, and I will say so in the task prompt so no one
has to rediscover this.

**Mutation earned its cost here, which is not something I say by default.** Four gaps, each of a
different kind: a check that could not be told apart from its absence, which you deleted rather
than wrote a test for; a check that was load-bearing with no example exercising it; a property that
never generated the input class it was written to cover; and two overlapping containment checks
collapsed into one decision plus a label. The second of those is the one I would have missed: a
reversed paragraph run touching another part *silently shortened the selection*, which is the
clamping this task's forbidden list prohibits, arriving through a door the forbidden list does not
describe. A forbidden behaviour is only actually forbidden once something fails when it happens by
accident, and until this mutation nothing did.

**The generator statistics are a sibling of a pattern this project keeps hitting.** A markup
property producing valid-with-spans examples 3.5 percent of the time is a green property that
barely tests the direction it exists for. We have now seen an import-linter key that was never
read, a promotion guard whose job never ran, seventy-six export tests passing by skipping, and now
a property passing on inputs that skip its point. Same failure, four surfaces: the check reports
success without having done its work. Measuring the distribution with `--hypothesis-show-statistics`
and rebalancing is the right response, and I want it treated as normal practice rather than as
something you did because this task happened to be about generators.

**ac4's scan asserting that it saw its own entry points is the structural fix for that whole
family.** A scan that fails when it finds nothing cannot silently stop covering the thing it was
written for. Seven mutations, all red, including the two I would have expected to slip past: an
untyped `**overrides` counting as text, and a `NewType` alias caught because only `ParagraphId` is
allowed. And you declined to count the eighth because it errored at collection. An attempt that
never ran proves nothing about the check, and most reports would have counted it.

**Decision 2 is better than the criterion asked for.** I asked `v1-e03-t02` to make unverified
construction impossible inside its own layer. You added a second, independent defence at the point
of use: the extractor re-derives the paragraph map and refuses a mismatch even for a `SnapshotText`
that reached you without going through `load`. That holds whatever another layer does or stops
doing later, which is the only kind of guarantee worth having across a package boundary. Keeping it
always on at 6.6 milliseconds against `load`'s 166 is obviously right, and measuring before
deciding is why the answer is credible.

**Deviation 1 is the resolution I was hoping for.** Taking the text alone and re-pairing it with a
snapshot in the caller is exactly where text from one snapshot acquires the id of another. Passing
both and verifying they agree puts the check at the boundary instead of trusting the caller to do
it.

**Deviation 2 is correct, and the decision behind it is mine.** Domain `CardSpan` offsets are
relative to `evidence_text` while ac3 needs snapshot-relative, and the domain was outside your
package list, so an evidence-layer type was the only honest option. The real question your report
surfaces is how a `Card` represents evidence with cuts in it: whether it stores segments plus
omitted ranges, and whether `CardSpan` moves to snapshot offsets. That is a representation choice
binding on verification, edit policy and export at once, so it is not a decision any one task should
make on the way past. I have recorded it on both `v1-e03-t04` and `v1-e03-t05` and will settle it
before t05 starts. t04 may proceed on single-segment cards.

**The `docs/evidence` omission is mine, and this is the fifth time.** `v1-e03-t01` and
`v1-e03-t02` both carry `docs/evidence` in their package lists and this spec did not, which is a
copying error on my part, not a scoping decision. I have amended the constraint in this branch, so
the format doc's guarantees table is now in scope and the point-of-use recheck should be recorded
there before the pull request. `v1-e01-t16` exists in part to stop me doing this a sixth time.
