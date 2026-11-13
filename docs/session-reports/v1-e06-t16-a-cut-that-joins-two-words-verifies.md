# Session report: v1-e06-t16-a-cut-that-joins-two-words-verifies

| | |
|---|---|
| Task | `v1-e06-t16-a-cut-that-joins-two-words-verifies` — An untouched export whose cut joins two words with no space verifies |
| Spec | [`plan_specs/v1/e06-card-cutting/t16-a-cut-that-joins-two-words-verifies.yaml`](../../plan_specs/v1/e06-card-cutting/t16-a-cut-that-joins-two-words-verifies.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t16-a-cut-that-joins-two-words-verifies` |
| Session status | COMPLETE |

## Summary

`verify`'s .docx body diff (`debate_core.evidence.docx_verify`) now splits the card's evidence into
tokens at the card's own omission offsets. `evidence_text` joins its kept pieces with nothing, so a
cut that ends at a word and resumes at a word used to be read as one run of letters ("holdflood")
against the body's "hold … flood". Split at the cut, those letters are the two words the source wrote,
and an untouched export verifies wherever its cuts fall. A changed or added word beside a join is
still MANUAL_EDIT. A whole-word deletion beside a join is still a deletion, and one that removes a
negating word still warns NEGATION_REMOVED. No stored `evidence_text`, hash or existing test
expectation changed: the 87 tests in `test_docx_verify.py` from before this task pass untouched.

The measurement came first. CardService made no such join in any existing fixture or cassette: 105
distinct cards, 23 of them cut, 0 joins. The joins in the test suite come from E03's edit API and the
verifier's omission properties (245 cards). So a student's DeleteRange can already store one.

On t15's follow-up 2: a marker retyped with one space, no space or non-breaking spaces already gave
the right verdict. Two spaces either side brought back t15's tie. That is the same rule, so the
marker unit now takes in all the whitespace either side of the "…" (its own commit, Decisions 4).

The PM may want to look first at Decisions 2: a body that takes the marker out at a join, showing
"holdflood", used to verify and is now MANUAL_EDIT.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-cut-that-joins-two-words-verifies` (Joined words) | Done | 42 tests in the node's `-k join` selection pass. The red runs, the mutants and the spacing measurement are recorded below |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: "Joined words tests pass" (`uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k join`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k join` → `42 passed in 1.95s`. That is every new test: 22 for the join fix and 20 for marker spacing. No test from before this task has "join" in its id |
| ac1: the measured count of such joins is recorded, an untouched export whose cut joins two words verifies, and a changed word beside it is still MANUAL_EDIT, by tests on synthetic exports shown failing first | PASS | Count: [Measurement](#measurement-joins-in-the-existing-fixtures-and-cassettes). Tests use an invented source (`JOIN_SOURCE`), exported by ExportService and edited through python-docx. Each checks `compare_body`'s ranges and `VerifyManifest`'s verdict. Red runs, green runs and mutants are below |

### Measurement: joins in the existing fixtures and cassettes

How it was measured: a scratch pytest plugin, not committed, wrapped `EvidenceVerifier.verify` and
`verify_with_snapshot_text`. For each card they were given, it recorded only counts and a digest, and
it marked whether the card came out of `CardService.cut_card`. A **join** is an omission offset `o`
where `evidence_text[o-1]` and `evidence_text[o]` are both word characters (`[^\W_]`, the diff's own
word class). The plugin ran over the 18 test files that cut, edit, export or verify cards (CLI cut,
daily, search and verify; batch cut; card edit; card service and its e2e; citation; export; verify
docx; docx verify; the three verifier files; the two integration e2e files). Result: `795 passed in
13.45s`, 5,039 verifier calls. Counts are of distinct cards (snapshot, evidence and ranges). The
CardService row counts them across its files, and the other rows count them within each file, so a
card verified in two files counts twice there:

| Where the cards come from | Distinct cards | With a cut | With a join |
|---|---|---|---|
| CardService (scripted selections and the recorded model cut), all 11 test files that reach it | 105 | 23 | **0** |
| `test_card_edit_service.py` (E03's edit API: DeleteRange and friends, Hypothesis included), 32 tests | 203 | 166 | 145 |
| `test_verifier_omissions.py` (the verifier's omission properties), 11 tests | 102 | 102 | 100 |
| Every other card the suite verifies (VerificationWorld cuts, t07/t10/t15 docx cards, adversarial verifier cases) | 817 | 15 | 0 |

* **The recorded model cut** is `card.select`: 2 fixtures in `tests/fixtures/model_outputs/card.select/`
  and 1 cassette in `tests/fixtures/model_cassettes/card.select/`. The cassette has the same key as
  one of the fixtures, so there are 2 distinct selections, each of two passages. In both, the first
  passage ends at the end of its paragraph, on a full stop, so neither joins two words. All 23 cut
  CardService cards join with no space between the pieces, but always at punctuation (a full stop
  then a capital), never word to word.
* **Stored manifests** (`tests/fixtures/verify/*.json`, read directly): 13 readable cards, 4 with a
  cut, 0 joins. One card in `mixed.json` does not validate as a Card, by design.
* So CardService has not made a join in any fixture. The model's offsets *can* make one: two passages
  inside one paragraph, the first ending mid-sentence. The edit API makes them often in its own tests.
  No card text was printed or recorded.

### ac1: red runs (tests before the fix)

* The 22 join tests against the unchanged module (`bcdf873`): `-k join -n 0` → `22 failed`, each at an
  assertion. The five untouched cases fail on the comparison: on the old code, every join is a
  ManualEdit, and the PM's reproduction gives exactly ManualEdit(evidence [19, 28), body [19, 31)).
  The changed-word cases were already MANUAL_EDIT on the old code, so they fail on their exact ranges,
  not their verdict: the card's other joins add edits of their own. That is the most a test of "still
  MANUAL_EDIT" can show failing. The deletion and negation cases fail because the untouched joins are
  manual edits.
* The 20 spacing tests against the join fix alone (`3cfe989`, the module put back with `git show`,
  then restored from a saved copy and checked with `cmp`): `2 failed, 127 passed`. The failures are
  `one-word-after-join-1-two-spaces-each-side` and `one-word-after-join-2-two-spaces-each-side`. The
  other 18 pass there: the measurement for one space, none and non-breaking spaces (Decisions 4).

### ac1: green

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence/test_docx_verify.py -n 0`
→ `129 passed` (87 from before, 42 new). Every expected range was counted by hand from the fixture's
comment block, and all of them held on the first green run. The file has no Hypothesis test, so
agreement 8's fresh database does not apply.

### ac1: mutants (each over the whole file, restored from a saved copy, `git status` clean after)

The boundary rule (`_tokens` with the card's omission offsets), against the 109 tests at `3cfe989`:

| Mutant | Result |
|---|---|
| No boundaries (the pre-task tokenization) | caught, 22 failed (every join test) |
| The first cut's offset only | caught, 18 failed (the three-join card's tests) |
| The last cut's offset only | caught, 18 failed |
| Each offset one character late | caught, 75 failed |
| Each offset one character early | caught, 22 failed |
| The body split at the card's offsets too | caught, 52 failed |
| Each segment's tokens end one character short | caught, 80 failed |
| The last segment dropped | caught, 83 failed |

Simplification: the first version filtered, de-duplicated and sorted the offsets. An omission offset is
always strictly inside the evidence and increasing (`omission_offsets`'s own contract), so no input
could tell the filter from its absence. It was dropped in `3cfe989` (agreement 8).

The marker unit with other spacing (`_marker_width`), against the 129 tests:

| Mutant | Result |
|---|---|
| Spaces before the "…" only | caught, 3 failed: both two-space deletions and t15's `a-marker-then-a-word-where-nothing-was-cut` |
| Spaces after the "…" only | caught, 3 failed (the same three) |
| At most one space either side | caught, 2 failed (both two-space deletions) |
| A line feed not counted as a marker's space | **survived**, so the check was removed (below) |
| Units on the body side only | **survived**: t15's known equivalent mutant (its Decisions 4); the reasoning there holds unchanged |

The first version of the spacing unit stopped at a line feed. No input I could build tells that apart
from taking a line feed in: a hunk already allows added whitespace, line feeds included. So the check
went (agreement 8), in the same commit.

### Before the report

* Affected set: `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`
  chose `122 of 755 test files`. It reached 85% with no failure in its progress lines before
  `hard_stop` stopped it at its 115-second limit. Per agreement 10, it is left to the pull request's
  `ci`, which runs the same set. Within the limit, instead:
  * the changed test directory and the always-run list (`packages/debate_core/tests/evidence
    tests/architecture tests/specs packages/debate_cli/tests/test_app.py
    packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py`,
    `-n auto -m "not slow and not live"`) → `2252 passed in 26.45s`;
  * every other test that reads the body diff (`test_verify_docx.py`, `test_verify_manifest.py`,
    `test_verify_command.py`, `test_cut_command.py`, `tests/cli/test_verify_cli.py`, the two e2e
    files, `tests/smoke/test_cli_smoke.py`, `tests/smoke/test_cut_smoke.py`) → `196 passed in 17.22s`.
* `uv run ruff format --check .` → `2093 files already formatted`; `uv run ruff check .` → `All checks
  passed!`
* `uv run --frozen pyright`, the whole project as CI runs it → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`; `uv run scripts/check_thin_handlers.py` →
  `OK: 74 CLI command and API route handlers within 25 statements`
* `uv run scripts/validate_specs.py` → `OK: 684 files, 41 epics, 621 tasks, 22 releases`
* The spec against the local `origin/dev` ref (not fetched): it differs only in the phase.

## Files changed

* `packages/debate_core/src/debate_core/evidence/docx_verify.py`:
  * `_tokens` takes boundaries, and `compare_body` gives it the card's omission offsets;
  * the marker unit is the marker's sign with the whitespace either side (`_units`, `_marker_width`,
    `_past_spaces`);
  * two paragraphs in the module docstring state both rules.
* `packages/debate_core/tests/evidence/test_docx_verify.py`: the new `test_join_*` section on an
  invented source, with its offsets counted by hand in the section's comment block, and a
  `retyped_marker` helper. No line from before this task changed (`git diff f76ddf6` removes none).
* The task spec: the Goal's phase.

## Deviations from the spec

None. The spacing change (Decisions 4) is step 4 of the PM's brief, which allowed a fix that is the
same rule. It changed no existing test's expectation and no stored data, so I did not stop for the PM.

## Decisions and assumptions

1. **Where the fix belongs: the diff's tokenization, not `evidence_text`.** The card's evidence is
   tokenized with its omission offsets as boundaries, and the body as Word shows it. The alternatives,
   and what each would break:
   * **Join the pieces with a space in `evidence_text`.** This changes the stored text and the hash of
     every card with such a cut. Some 245 test cards show the edit API makes them, so stored ones are
     likely to exist. It also breaks the verifier's EVIDENCE_TEXT_EXACT check: `evidence_text` would
     no longer equal the snapshot at its quoted ranges. It moves every span, interpolation anchor and
     omission offset after the join. And it puts a character the source never wrote inside the
     quotation. The brief made that a stop for the PM, and it is not needed.
   * **Draw the marker differently.** The body already shows the two words apart. The misreading was
     on the card's side.
   * **Diff characters instead of tokens.** That would lose t07's rule that a deletion inside a word is
     a changed word ("un" out of "unlikely"), which the forbidden list depends on.
   * **Split the body at the same offsets.** Body offsets are not evidence offsets. The mutant that
     does it fails 52 tests.

   The chosen split only changes anything where a cut falls inside a token: a word, a word with an
   apostrophe, or a bracketed group in the source. Everywhere else an omission offset is already a
   token boundary. That is why no existing expectation moved.
2. **A body that takes the marker out at a join is a MANUAL_EDIT.** Before, a body showing
   "holdflood" equalled the card's characters and verified. Now the card's tokens are "hold" and
   "flood", and the body's one token is a word the source never wrote. That reads it as t07 reads a
   deleted space between two words (`test_diff_deleting_the_space_between_two_words_is_a_manual_edit`),
   and the forbidden list says a changed word is never verified. It is pinned by
   `the-marker-at-join-2-taken-out`, ManualEdit(evidence [24, 33), body [27, 36)). No existing test
   reached it. Taking a marker out where the cut joins punctuation to a word still verifies; see
   follow-up 2.
3. **Test fixture shape.** The invented card has three cuts, each joining a word to a word. Its first
   piece is one word, the body's first; its last piece is one word, the body's last. Join 2 has "not"
   one word before it and "never" right after it. The untouched cases are parametrized:
   * a single join at the start, in the middle and at the end, each on a two-piece card;
   * the three-join card;
   * the PM's own reproduction sentence and ranges.

   Deletions beside a join follow t15's rule: a space beside a marker that can be the card's own is
   read as the card's. So " hold" before join 2 is the deletion "hold" [24, 28), and "levee " after
   join 1 is "levee" [9, 14). A deletion one word further on keeps its own space: "will " [15, 20),
   "came " [34, 39).
4. **A marker typed with other spacing: measured, then fixed only where it is t15's rule.** Measured on
   all three markers of the join card, t15's card and t07's news card:
   * **One space before or after, no spaces, non-breaking spaces:** an untouched body verifies, and
     every deletion is a deletion, before and after this change. Only the range of a deletion right
     beside such a marker can differ. Where the body has no ordinary space beside the marker, the
     card's space is not read as kept, and the deletion includes it: "never " right after a marker
     with no space after it is [28, 34), not [28, 33). That is right: the body really lost that
     space. A non-breaking space does not stand for the card's ordinary one, because the trim
     compares text. No fix was needed.
   * **Two spaces either side:** t15's tie again. The marker's extra spaces could be paired with the
     card's spaces either side of the word after a cut. "will " one word after join 1 read as
     MANUAL_EDIT(evidence [9, 19)), and t07's "biologists " on the news card as MANUAL_EDIT [108, 131).
     This is t15's rule, a marker's own spaces never pairing with the card's, so the unit now is the
     sign "…" with all the whitespace either side. The profile's " … " is one case of it. All 109
     earlier tests pass unchanged, and both cards now read those deletions as deletions.
   * Three full stops typed instead of "…" are not a marker at all: MANUAL_EDIT (follow-up 3).

   Its tests are in the join section, on the join card, so the node's `-k join` selects them.

## Operator follow-ups

None.

## Follow-up work

1. **An interpolation anchored inside a word reads as a MANUAL_EDIT on an untouched export** (E06,
   the same module). Measured: the join card with a recorded interpolation anchored inside "levee"
   (offset 11) gives ManualEdit(evidence [9, 14), body [12, 20)) on its untouched rendering. Anchors
   at a word's edge or at a join verify. E03's edit API does not appear to refuse a mid-word anchor; I
   did not check that through the API. The same one-line change would fix it: the anchors as token
   boundaries beside the omission offsets. It is outside this task's "cuts", so I left it out.
2. **A body that takes the card's marker out where the cut joins punctuation to a word verifies**
   (E06, edit policy). On t15's card, removing cut 1's marker leaves "fail.The", which equals the card's
   characters, so the comparison is empty and the card stays VERIFIED. The reader cannot see that text
   was cut. At a word join the same edit is now a MANUAL_EDIT (Decisions 2), so the two disagree.
   Whether a hidden cut is a difference the policy refuses is the PM's call.
3. **Three full stops typed in place of "…"** (" ... ") are a MANUAL_EDIT even on an untouched body,
   ManualEdit(evidence [12, 12), body [12, 17)) at t15's cut 1. Students who type the marker by hand
   may write it this way. Whether the profile should accept "..." as its marker's sign is a policy
   question, not this unit rule.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-13

**Notes:**

Accepted. ac1 and the node pass, and the Goal is `Succeeded`.

* **The measurement is the right first step, and it is honest.**
  * CardService made 0 word-to-word joins over 105 distinct cards.
  * E03's edit API made 145, in its own tests, so stored joins are likely and the fix matters.
  * Only counts and digests were recorded, and no card text.
* **Decision 1, the fix in the tokenization and never in `evidence_text`, is right.** The report
  measures or argues each alternative: changing stored text breaks EVIDENCE_TEXT_EXACT and every hash,
  splitting the body fails 52 tests, and diffing characters loses t07's rule. No stored data and no
  existing expectation changed (all 87 earlier tests pass untouched).
* **Decision 2 is accepted.** A body that takes the marker out at a word join reads "holdflood", a word
  the source never wrote, so it is a MANUAL_EDIT, as t07 reads a deleted space.
* **Decision 4 is accepted.** It is t15's own rule, extended to all the whitespace around the "…". It
  was measured first: one space, no space and non-breaking spaces already worked, and two spaces
  brought the tie back.
* **The evidence is enough.**
  * 22 of 22 join tests failed red at assertions. The 2 two-space tests failed against the join fix
    alone.
  * All 8 boundary mutants were caught. Two checks no input could distinguish were removed rather than
    kept untested (agreement 8). The body-side-only mutant is t15's known equivalent.
* **The affected set** goes to `ci` under agreement 10.
* **Follow-ups, into the next PM batch:**
  2. Taking the marker out where a cut joins punctuation to a word ("fail.The") still verifies, so a
     reader cannot see that text was cut. That is an evidence-integrity gap: a new E06 task at p2,
     whose outcome is a refusal named as a hidden cut.
  1. An interpolation anchored inside a word: folded into the same task, since it is the same one-line
     boundary change.
  3. Three full stops typed for the marker: the coach's decision, asked of him first; filed by the
     answer.

`scripts/task pr`
