# Session report: v1-e31-t23-in-round-markers

| | |
|---|---|
| Task | `v1-e31-t23-in-round-markers` — In-round markers kept in a card's evidence text |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t23-in-round-markers.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t23-in-round-markers.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t23-in-round-markers` |
| Session status | COMPLETE: every criterion a session can close has passed. ac3's re-parse of the store can only follow the merge, so the Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The counts came first, as the PM asked. `scripts/count_in_round_markers.py`, with its logic in
`debate_core.evidence.in_round_markers`, counted marker lines by form, reading and place, and the
lines read as nothing between body paragraphs by the same form ids. The operator ran it over 13,518
sources. Markers turned out rare: 96 lines of the three clear forms in 287,545 cards, splitting one
cluster. The counts also found a third reading: a capitalised marker with a two-digit hour,
`Marked 10:42`, was read as a cite that cut its card in two.

The PM ruled M1, M3 and L-D. M1 leaves markers as they are. M3 (no marker is ever a cite) was built
red first; over the same sources it takes the 4 marker cites to 0, rejoins the divided card and
removes the stray `CITE_ONLY` card, and it leaves the labelled evaluation exactly as it was. L-D
sampled the short lines first, and the coach's sample of 66 items led to the ruling N1. N1 was built
red first, with the ruled cite guard and one guard more, a Deviation below.

Over the store, N1 makes 13,905 lines body, in 5,831 cards, and changes no other card. On the
labelled evaluation it reads 25 more body lines right (recall 0.882 → 0.906). It also read one
paragraph labelled OTHER as body (paragraph 16 of file `a8afd234…`), so EVIDENCE precision first
fell 0.9708 → 0.9705 and the session stopped at the PM's gate.

The PM ruled Option A. The coach, shown the paragraph blind, answered **s**, the source's own text.
Its label went from OTHER to EVIDENCE in the guide's own label pull request, **#814**, counted against
the file's pre-label restored from git: 75 of 255 rows. On the shipped `2026.11.03-docx-9`
(`v1-e31-t32` merged first with `docx-8`), **EVIDENCE precision is 0.9715 against N1-off's 0.9708**, and
no card boundary moved. Everything else a session can close has passed. ac3's re-parse of the store
follows the merge, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `markers`: In-round markers | DONE (Goal `InProgress` for ac3's re-parse after the merge) | Counts; M3 and N1 built red first; every measurement on the shipped `docx-9`; ac4's gate passed after #814 |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: operator-run counts of marker lines by form and position per caselist, and the clusters they split | PASS | `uv run python scripts/count_in_round_markers.py` (operator, 2026-11-02, 661 s, 13,518 sources) → 96 lines of the three clear marker forms (34 body, 58 nothing, 4 a cite), 1 cluster split; recorded per caselist in [the parse report](../data/caselist-parse-report.md#in-round-markers-and-the-short-lines-between-body-paragraphs-v1-e31-t23) |
| ac2: the PM's ruling written into this spec, built with synthetic fixtures shown failing first | PASS | Rulings in the spec (2026-11-03: M1, M3, L-D, N1, the version note). M3: `c782278` red, **9 failed, 7 passed**, every failure by assertion; green at `5720a62`, 16 passed. One expectation was corrected after the red run, the bold marker (Decisions). |
| ac3: if the parser or fingerprint changes, the version is bumped and the operator's re-parse records the counts before and after | NOT RUN | Parser bumped to `2026.11.03-docx-9` (`68cd671`); fingerprints unchanged. Before and after over the same 13,518 sources, read-only, from the branch: M3 (`count_in_round_markers.py` again, 902 s) and N1 on `docx-9` (`diff_lines_between_body_paragraphs.py`, 841 s), both in the parse report. The store's re-parse can only follow the merge (Operator follow-ups), so this stays open and the Goal `InProgress` |
| ac4: the short-lines ruling written into the spec beside the marker ruling, built with fixtures shown failing first; the labelled evaluation's evidence precision does not fall | PASS | Ruling and fixtures: `0a2a945` red, **4 failed, 20 passed**, the 4 by assertion; green at `b461889`. The evaluation, by the operator, both gates PASSED every time: N1 off and on (`docx-8`), then `docx-9` with the old label, then `docx-9` after #814 (`uv run pytest tests/evals/parser -m "eval and slow"` → `1 passed in 4.19s`; `run_parser_eval.py --tier both`). Full-tier EVIDENCE precision: **0.9708 (N1 off) → 0.9705 (N1 on) → 0.9715 (`docx-9`, after #814)**, 956 right / 28 wrong, recall 0.8824 → 0.9062. PR subset 0.9433 → 0.9442. No group below its N1-off figure; card boundaries unchanged. The one paragraph first counted against it: file `a8afd234413032f4723e0dc5b38ea90f332f738e3c8e21fcd84189664fd382dc`, paragraph 16, labelled OTHER until #814, the coach's blind answer s. M3 alone changed nothing in either report |
| Node `markers`: `uv run pytest packages/debate_core/tests -k "docx or parser or fingerprint"` | PASS (as part of a wider run) | Run inside the changed directories below: `packages/debate_core/tests/integrations/docx_parser`, `docx_file_writer` and `evidence` among 3,827 passed, 2 xfailed |

### Red then green

| Fixtures | Red commit, result | Green commit, result |
|---|---|---|
| M3, `test_in_round_marker_cites.py` | `c782278`: 9 failed, 7 passed. Every failure by assertion; the passes are five real cites, a marker in the tag style and every card's version | `5720a62`: 16 passed |
| N1, `test_lines_between_body_paragraphs.py` | `0a2a945`: 4 failed, 20 passed. The two strata fail by assertion; the left-alone strata, the ruled cite guard, a real cite and the places N1 does not reach pass before and after | `b461889`: 26 passed. The cite-shape guard's two cases were written and shown failing with N1 in place before the guard |

### Planted breaks

Each was planted on a committed tree and restored with `git checkout HEAD --`. All failed by
assertion. A break that crashed was not counted and was replaced (agreement 8).

| Where | Break | Result |
|---|---|---|
| Counting module and script | No join across a marker cite; no between-body place; any cite below a body joined; a split counted at one cluster; no copy held today | 2, 2, 3, 1 and 1 failed |
| Sampler's short-lines plan | Markers drawn by length; capitals not told apart; every place drawn | 2, 2 and 2 failed |
| N1 in the parser | No link/DOI/"accessed" guard; no cite-shape guard; no form guard; short sentences read; no sentence end asked; any place | 6, 4, 2, 1, 1 and 7 failed. The form guard first survived: every short form is left by length, and a capitalised marker is cite-shaped. Fixed by two lines that only their form keeps out |
| N1's diff script | An evidence change counted as another; only the ruled guard counted | 1 and 1 failed. The first attempt at the second break crashed (`TypeError`), so it was not counted and was replaced |

## Checks before the report

The affected set (`uv run scripts/affected_tests.py`) is **293 test files**: the parser is a hub
module. That is well over two minutes, so it was not run and is left to the pull request's `ci`
(working agreement 10). Run instead, on the final tree:

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest` over the changed test dirs (`docx_parser`, `docx_file_writer`, `evidence`, `tests/evals/parser`), this task's three script tests, t32's and t24's script tests, `test_landscape_restored_copy.py` and the always-run list, `-n auto -m "not slow and not live"` | 3,827 passed, 2 xfailed, 26.6 s |
| `uv run ruff format --check .` | 1,911 files already formatted |
| `uv run ruff check .` | All checks passed |
| `uv run pyright packages/debate_core` and the changed scripts and their tests | 0 errors |
| `uv run lint-imports` | 20 kept, 0 broken |
| `uv run scripts/validate_specs.py` | OK: 608 files, 41 epics, 545 tasks, 22 releases |
| `scripts/check_command_blocks.py`, `scripts/check_thin_handlers.py` | OK |

Relative to `origin/dev` at `9343ad0` (#814), after `scripts/task sync` three times: before t32
merged, after it, and after #814.

## Files changed

- `packages/debate_core/src/debate_core/evidence/`. `marker_lines.py` (new) holds the marker forms
  and `is_an_in_round_marker`. `in_round_markers.py` (new) describes lines by form, reading and
  place, and gives marker-free bodies for matching only. `style_classifier.py`: no cite heuristic
  reads a marker (M3).
- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`. M3 in the
  where-a-cite-stands and by-place rules. N1 (`read_between_body_paragraphs`, and the step after the
  place-based cite rules). `2026.11.03-docx-9`, with both bumps named.
- `scripts/`. `count_in_round_markers.py` and `diff_lines_between_body_paragraphs.py` are new, both
  read-only counts. `sample_cite_shapes.py` gains the `short-lines` plan, merged beside t32's
  `bold-in-part` plan, with its strata numbered after t32's.
- Tests: `packages/debate_core/tests/evidence/test_in_round_markers.py`,
  `.../docx_parser/test_in_round_marker_cites.py` and `.../test_lines_between_body_paragraphs.py`,
  `tests/scripts/test_count_in_round_markers.py` and `test_diff_lines_between_body_paragraphs.py`,
  and the sampler's tests.
- Version pins t32 updated, now `docx-9`: the ten structural expectations, the four provenance
  fixtures, `test_fidelity.py`, `test_writer.py`, and the later-bump notes in t31's and t24's version
  tests.
- `docs/data/caselist-parse-report.md`: the counts, the sample, the rulings, the before-and-afters on
  `docx-8` and `docx-9`, every evaluation, the coach's answer on paragraph 16 and #814. The spec holds
  the rulings.
- Not on this branch: the label change itself, in its own pull request **#814** (`labels/a8afd234413032f4`,
  merged into `dev`): the label file and its pre-label, restored from `7a9c4ff` under `labels/prelabels/`.

## Deviations from the spec

1. **N1's cite guard holds one shape more than the ruling names**, as the PM confirmed on 2026-11-03.
   The ruling holds a line carrying a URL, a DOI or "accessed". As first built, N1 also read as body
   two lines that earlier tests pin as nothing:
   - `v1-e31-t12`'s bracketed reference inside a body;
   - `v1-e31-t21`'s cite-shaped line.

   Both are a long line naming its source at its head, which is a citation's line. The guard adds
   `v1-e31-t21`'s own test, `is_cite_shaped`: a name and a year within 40 characters of the start. It
   holds back 197 lines over the store (133 sentences, 64 long lines), counted apart from the ruled
   guard's 595.
2. **ac4 failed as first measured, by one reading, and passed after a label change.** N1 read
   paragraph 16 of `a8afd234…fd382dc`, then labelled OTHER, as body: full-tier EVIDENCE precision
   0.9708 → 0.9705. The session stopped at the gate, and the PM ruled Option A, then B. The coach,
   shown the paragraph blind with the one above and below and no label, reading or rule, answered
   **s**. So the label changed OTHER → EVIDENCE in card 1, through the guide's coach-reviewed route,
   as its own pull request (#814).
   - The file had been corrected before 2026-11-02 and had no kept pre-label. As the PM ruled, the
     pre-label was restored from git (`7a9c4ff`, `PRELABELED`, the plan and rows the coach corrected,
     byte for byte), and `import --replace` counted against it: **75 of 255 rows**, the coach's 74 and
     this one.
   - The worksheet was written from the corrected labels. A scratch helper set row 16 and marked every
     row checked, without printing a cell: every other row carries the coach's correction unchanged.
   - The evaluation baseline did not change.
   - Option B, the PM's acceptance of the fall, was not needed: on `docx-9` precision is 0.9715.
3. **Every figure the report records is the shipped `2026.11.03-docx-9`'s**, as the PM ruled. Earlier
   measurements were taken on the branch's `docx-8`, before t32 merged. On `docx-9` the evaluation
   reports and N1's store counts equal `docx-8`'s exactly, but for 5 fewer cards, which are t32's
   rule's own.

## Decisions and assumptions

- **Forms are patterns, never text.** Marker words are `mark`, `marked`, `marking`, `stop` and
  `stopped`, and a marker form is a line of 60 characters or fewer. The PM ruled the three clear forms
  markers.
- **M3 asks for the line's form, not the word alone.** A real cite by an author named `Mark`, `Mark 19,
  …`, is no marker form and stays a cite (pinned).
- **A bold marker at reading size reads as a tag under M3.** That is how the classifier's bold-heading
  rule reads any bold short line. The red fixture had expected the card whole, which went beyond "reads
  as it would otherwise", so it was corrected to pin the tag. The PM accepted this as FYI.
- **N1 reuses the counts' definitions.** "Between two body paragraphs of one card" is
  `lines_read_as_nothing`, and its strata use t19's length bands, so the rule reads exactly the
  population sampled. Made body plus held back equals the sample's two populations: 10,863 and 3,834.
- **The coach was told before answering how to read the PM's question:** a citation line, page
  furniture or anything he could not tell is "something else"; a marker or an omission note is a
  cutter's note. He kept no count of which "something else" answers were citation lines.
- **Tests for the counting tools read their fixtures as the counts were taken.** The marker rule or
  N1 is switched off in-process, and a test beside each reads the fixture as `docx-9` does (the t24
  idiom).

## Operator follow-ups

**After the merge, the re-parse to `docx-9`** (ac3). It rides the first cloud run on an image
carrying `docx-9`, which parses every caselist in full (`v1-e40-t08`), as t32's re-parse does. Restore
a copy of the dev data directory after that run, at `~/debate-research-restored-after-docx-9`
with t32's guarded restore block (`docs/session-reports/v1-e31-t32-bold-in-part-tags.md`, Operator
follow-ups) and that path in place of its own, then count again. This runs past two
minutes:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t23-in-round-markers
uv run python scripts/count_in_round_markers.py --data-dir ~/debate-research-restored-after-docx-9 --expect-version 2026.11.03-docx-9 > /tmp/in-round-marker-counts-after-reparse.json
```

Success looks like exit 0 and every caselist's `store_version` `2026.11.03-docx-9` with
`sources_whose_cards_differ_from_the_store` 0. The before figures are the parse report's 2026-11-02
and 2026-11-03 tables.

## Follow-up work

- **The two strata N1 leaves (the PM, 2026-11-03):** lines of 40 characters or fewer not in capitals
  (15,611; 6 of 8 the source's) and lines of 41 to 200 that end no sentence (7,803; 5 of 8). Each needs
  a larger sample before any rule. The PM files the task.
- **A bold marker at reading size reads as a tag** under M3, through the classifier's bold-heading
  rule, so its card still divides there. Pinned in `test_in_round_marker_cites.py`; not built.
- **The baseline in `tests/evals/baselines/parser.json` is `docx-5`'s.** Every eval run here notes it;
  refreshing it needs a coach-reviewed report (E31).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

Counted before any rule, sampled before the larger one, stopped at the gate when it moved by a single
reading, and finished by a blind check rather than an argument. That is the order this work should
always take.

1. **ac1 passes.** 96 marker lines of the three clear forms in 287,545 cards, one cluster split, and the
   third reading (`Marked 10:42` read as a cite that cut its card) found by the count, not assumed.
2. **ac2 passes.** M3 red first at `c782278` (9 failed by assertion), green at `5720a62`. The bold-marker
   expectation corrected after the red run is the "reads as it would otherwise" the ruling meant;
   accepted, as said on 2026-11-03.
3. **ac4 passes, and the PM checked the arithmetic.** Full tier: 930/958 = 0.9708 with N1 off, 955/984 =
   0.9705 with N1 on and the old label, 956/984 = 0.9715 on `docx-9` after #814. N1-off reads paragraph
   16 as nothing, so its precision is unchanged by the label and the comparison is like for like. Recall
   0.8824 to 0.9062, the PR subset up, no group below its N1-off figure, no card boundary moved.
4. **The label change was done the right way.** The coach answered **s** blind, with no label, reading
   or rule shown. The pre-label was restored from git (`7a9c4ff`), so the count landed at 75 of 255, the
   coach's 74 and this one, one of the two values the PM said would prove the right version; the file
   stays in the blind comparison. It went in as its own pull request (#814), holding the label file and
   its pre-label only, and the baseline did not change.
5. **Deviations accepted.** (1) The cite-shape guard (t21's `is_cite_shaped`), confirmed on 2026-11-03:
   197 lines kept as today, counted apart from the ruled guard's 595. (2) The gate's fall and the label
   change, recorded in full; Option B, the PM's acceptance of the fall, was not needed and is void. (3)
   Every recorded figure is `docx-9`'s, equal to `docx-8`'s but for t32's 5 cards.
6. **The store:** 13,905 lines made body (10,692 sentences, 3,213 long lines) in 5,831 cards, 0 other
   cards changed. These are the author's words coming back into cards, at about 1 foreign line in 26 by
   the labelled check.
7. **Planted breaks:** every one caught by assertion, the form guard's survivor closed with the two
   lines only it keeps out, and the crashed break replaced rather than counted (agreement 8).
8. **ac3, the re-parse, is re-timed by the PM.** It rides the same image as v1-e31-t32's step 4, so one
   full re-parse carries `docx-9`, and one restored copy after that run serves both tasks' "after"
   counts (t32's step 5 and this task's block, with `--expect-version 2026.11.03-docx-9`). The before
   figures are the parse report's (the Mac's store, which lacks the cloud's weeks); the record says the
   two populations differ. The copy is deleted after both counts (data-use policy 1.18), which the block
   above leaves out.
9. **Follow-ups the PM files in the next batch:** a larger sample of the two strata N1 leaves (15,611 and
   7,803 lines); the bold marker that reads as a tag; and a refreshed parser-evaluation baseline (still
   `docx-5`'s), through a coach-reviewed report.
10. **Closing checks:** the affected set (293 files) is left to `ci` (agreement 10); the bounded run of
    the changed directories, the always-run list and the script tests (3,827 passed), ruff, pyright,
    lint-imports, thin handlers, command blocks and the specs are clean, after syncing onto #814.
11. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the
    re-parse's counts are recorded.

## Operator records (recorded by the PM, 2026-11-12)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3: the operator's re-parse records the counts before and after | NOT RUN | PASS (PM ruling) | The re-parse happened: the run of 2026-11-11 (`20261111T120101Z`) parsed all four current caselists in full at `2026.11.03-docx-9` (20,746 sources, 392,919 cards), and a restored copy of 2026-11-12 holds every store at docx-9. The before and after counts are the session's, over the same 13,518 sources on the shipped docx-9, in the parse report. `count_in_round_markers.py --expect-version 2026.11.03-docx-9` over that copy found every store at docx-9 but no source blob (a run-state restore brings back the parsed store, not the sources), so it re-parsed nothing; its check, a re-parse matching the store, holds by construction for a store the same parser wrote from the same sources. The PM ruled on 2026-11-12 that this closes ac3 without a restore that carries the blobs |

Every criterion passes, so the Goal is `Succeeded`.
