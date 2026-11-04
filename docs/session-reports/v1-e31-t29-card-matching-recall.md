# Session report: v1-e31-t29-card-matching-recall

| | |
|---|---|
| Task | `v1-e31-t29-card-matching-recall` — Card matching recovers two kinds of pair it now keeps apart |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t29-card-matching-recall` |
| Session status | COMPLETE: counted, sampled and ruled; by the PM's ruling of 2026-11-03 no shape is recovered, and tests pin that each stays apart. Goal `Succeeded` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM's order was count, sample, ruling, rule. The operator counted and sampled all three shapes on
the Mac's dev store on 2026-11-03 ([the parse report](../data/caselist-parse-report.md#pairs-card-matching-keeps-apart-counted-and-sampled-v1-e31-t29)),
and **the PM ruled the same day that no shape is recovered**: each sample found the shape would join
different cards. **No matching rule changed, no placement changes, and there is no fingerprint
version bump**: `card-fingerprint-v4` stays, and no stored cluster needs a rebuild by anyone.

* **(1) Nine-tenths inside a body holding neither end:** 67 bodies. The operator judged **8 of 20
  different cards**, at least 3 from different articles or sources quoting one passage.
* **(2) Trims sharing no text:** 17,758 pairs. Only **2** carry the same tag and cite, judged 1 one
  card and 1 two cards. 950 share the cite under other tags; the PM ruled them not sampled.
* **The amendment, holders under 300 words:** 280 by t22's tool (was 216). **4 of 20 two cards.**
  The witness refusal stays unchanged.
* **Found in the code, and shown by a mutant:** lifting the witness refusal alone recovers nothing,
  because two trims that do not overlap each other are both refused as joiners. Recovering (2)
  means relaxing "every two bodies in a cluster overlap", which the PM kept.

What the task leaves: `debate_core.evidence.recall_shapes` and two operator tools
(`scripts/count_matching_recall.py`, `scripts/sample_matching_recall.py`), the figures in the parse
report, ac2 amended by the PM's ruling, and five tests pinning that the sampled shapes stay apart,
each shown failing under a mutant.

### The PM's ruling (2026-11-03)

* **Q1 (a):** shape (1) stays apart.
* **Q2 (a):** no rule, and no sample of the 950 same-cite pairs; the overlap rule is the card
  ruling and is not relaxed in this task.
* **Q3 (a):** the witness refusal stays unchanged, for short holders and long.
* **Q4:** agreed, with the specifics built here: ac2 amended and dated; five pinning tests on
  invented text; no version bump, stated; the record keeps every count, tally, the code finding and
  the caveats; one Follow-up line on where recall could come from.

### The relay that was sent to the PM

```text
v1-e31-t29: counts and sample are in; no rule has changed. Ruling needed before any rule (ac2).
Record: docs/data/caselist-parse-report.md, "Pairs card matching keeps apart, counted and sampled".
Store: the Mac's dev store as it stands (hsld26/hspf26/openev docx-6, hspolicy26 docx-7, all
card-fingerprint-v4), without the cloud's weeks since the cutover.

Found in the code first: for (2) and the amendment, lifting the witness refusal alone recovers
nothing. Both trims would propose joining their holder in one round, and two joiners that do not
overlap each other are both refused (t20's Decision 3). Recovering either needs "every two bodies
in a cluster overlap" relaxed for that case: the card ruling itself, not a limit.

Q1. Shape (1), nine-tenths inside a body holding neither of its ends: 67 bodies (20/27/18/2).
    Sample 20: 12 same card, 8 different (22%-61%); at least 3 of the 8 are different articles or
    sources quoting one passage, 2 are the same article making a different claim, 3 have no note.
    Options: (a) no rule; the shape stays apart. (b) a rule on the bodies plus a further
    condition, counted and sampled again.
    Recommend (a): any body-only join would join pairs the operator checked as different
    (forbidden), and 36 of the 67 holders also hold a passage the body does not overlap, so they
    would be refused as witnesses anyway.

Q2. Shape (2), two passages of one holder sharing no text: 17,758 pairs (1,996 holders).
    Same tag and cite: 2 pairs in the whole store, judged 1 one card and 1 two cards. Same cite
    under other tags: 950 (not sampled). End to end in the holder (Brannock's shape): 679.
    Options: (a) no rule. (b) first sample 20 of the 950 same-cite pairs (about 10 minutes of the
    operator's time), then rule. (c) relax the overlap rule for same tag and cite.
    Recommend (a). Same tag and cite would recover at most 2 pairs, one judged two cards.
    Brannock's rows carry the same tag and cite, so a cite rule must also tell them apart by
    shape. (b) only helps if you are ready to relax the overlap rule at all.

Q3. The amendment, holders under 300 words: 280 by t22's tool (was 216; 61/72/140/7).
    Sample 20: 16 one card cut twice, 4 two cards (8%-42%); t22's 20 of all lengths were 0 two
    cards. The refusal keeps 4,240 bodies out of every cluster holding them, 264 of them with a
    smallest container under 300 words.
    Options: (a) keep the refusal unchanged. (b) lift it for holders of 300 words or more.
    Recommend (a): short holders are two cards about one time in five, t11's false join is that
    shape, and (b) recovers nothing until the overlap rule changes.

Q4. If Q1-Q3 are all (a): amend ac2 to "no shape is recovered; precision and Brannock's rows as
    t20 left them", add tests pinning that each sampled shape stays apart (two articles quoting
    one passage, a short holder of two cards, Brannock, t11's false join), no fingerprint-version
    bump since no placement changes, and set the Goal Succeeded. Agree?

Caveats: the sample ran before two display fixes, so the items showed short cites for a pair and a
holder's cite cut at the screen edge (the operator's notes show the cites were read). A few
"same card?" items were answered with the other question's keys and are read by their meaning.
```

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `matching-recall`: Card matching recall | Done | Tools built and tested (`41bf65f`, `bcac62f`, `b05fe2a`); the operator's counts and sample recorded (`8866d53`); by the PM's ruling, no rule, and the shapes pinned apart (`d18066b`, `276bbd7`). `uv run pytest packages/debate_core/tests/evidence -k "cluster or fingerprint"` → `182 passed in 6.48s` |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts for (1) and (2) per caselist, and a sample through t21's sampler, before any rule changes | PASS | The operator's `scripts/count_matching_recall.py` (527 s, `exit 0`) and `scripts/sample_matching_recall.py --seed 20261103` (42 items) on 2026-11-03, recorded in `caselist-parse-report.md`. The sample shows items with t21's `render_pair` and t22's `_between`. (2)'s same-tag-and-cite stratum is the whole population, 2 pairs; the 950 same-cite pairs are not sampled (relay Q2). No rule has changed |
| ac2 (PM amendment 2026-11-03): no shape is recovered; precision and Brannock's rows stay as `v1-e31-t20` left them, and the shapes sampled stay apart, by test | PASS | `uv run pytest packages/debate_core/tests/evidence/test_short_card_recall.py -n0` → `64 passed`; its table, row for row as t20's: precision 1.000 on all 13 rows, the same 11 and 30 misses. The five tests of "The shapes the samples kept apart" in `test_near_duplicates.py` pass, and each fails under a mutant ([Pinning tests](#pinning-tests-and-the-mutants-that-break-them)) |
| ac3 (PM amendment 2026-10-20): the holders under 300 words sampled and tallied before the refusal changes; any change keeps t11's false join apart | PASS | 20 of 280 holders drawn: 16 one card cut twice, 4 two cards, tallied before the ruling. By the ruling the refusal is unchanged; `test_a_short_holder_of_two_cards_stays_refused_as_a_witness_for_either` and `test_t11s_false_join_stays_apart` pin it |
| Node: `uv run pytest packages/debate_core/tests/evidence -k "cluster or fingerprint"` | PASS | `182 passed in 6.48s` on the final tree |
| `uv run scripts/validate_specs.py` | PASS | `OK: 599 files, 41 epics, 536 tasks, 22 releases`, with the Goal `Succeeded` |

## Pinning tests and the mutants that break them

`packages/debate_core/tests/evidence/test_near_duplicates.py`, section "The shapes the samples kept
apart (`v1-e31-t29`)", on invented words. All five pass on the code as it stands, which is what the
PM asked; each was then run against hand-written mutants of `near_duplicates.py`, one at a time,
each with a new empty `HYPOTHESIS_STORAGE_DIRECTORY`, the file restored with `git checkout HEAD --`
and `git status --porcelain` empty after:

| Mutant | Fails |
|---|---|
| Containers found from a body's middle run, not its ends (shape (1) recovered) | two articles quoting one passage (the shape is no longer reported, and the pair joins: checked apart, `joined`); Brannock's rows |
| The witness refusal lifted | the short holder of two cards, and only it: every partition stays apart, which is the code finding |
| The refusal lifted and joiners that do not overlap accepted | the short holder; Brannock's rows; t11's false join; two trims of one holder |

So each of the five fails under at least one. The second line is the finding the relay reported:
lifting the refusal alone joins nothing.

## The checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run`, under `scripts/hard_stop.py 115` | 61 files; stopped at its 115-second limit at about 96%, under a load near 14, no failure printed. Over two minutes, so by working agreement 10 it is left to the pull request's `ci` |
| The test directories of what changed: `packages/debate_core/tests/evidence`, and `tests/scripts/test_{compare_card_clusters,count_matching_recall,sample_matching_recall,count_card_boundaries,sample_card_boundaries}.py`, `-m "not slow and not live"` | `1854 passed, 2 warnings in 15.90s` |
| The always-run list: `tests/architecture tests/specs` and the CLI's wiring tests (`test_app`, `test_container_factories`, `test_help_rendering`, `test_installation`) | `406 passed in 24.63s` |
| `uv run --frozen ruff format --check .`; `ruff check .` | `1908 files already formatted`; `All checks passed!` |
| `uv run --frozen pyright packages/debate_core` and the four new script and test files | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports`; `check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.`; `OK: 72 ... within 25 statements` |
| `check_command_blocks.py --base origin/dev`; `docs_index.py --check-descriptions`; `check_links.py` | all OK |

## Files changed

- `packages/debate_core/src/debate_core/evidence/recall_shapes.py` (new): the three shapes in a
  finished placement, in counts. `cluster_diagnosis.py`: `diagnose_cuts` takes an index already
  built. Tests: `packages/debate_core/tests/evidence/test_recall_shapes.py`.
- `scripts/count_matching_recall.py`, `scripts/sample_matching_recall.py` (new), with
  `tests/scripts/test_count_matching_recall.py` and `tests/scripts/test_sample_matching_recall.py`.
- `packages/debate_core/tests/evidence/test_near_duplicates.py`: the five pinning tests.
- `docs/data/caselist-parse-report.md`: the counts, the sample, the code finding and the ruling.
- `plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml`: ac2 amended by the PM's
  ruling, dated, its earlier wording kept; the Goal `Succeeded`.

## Deviations from the spec

1. **The shape (2) sample includes trims with the same cite under other tags.** The spec names "an
   identical cite and tag" as the kind of evidence a recovery might use. The operator's count
   (2026-11-03) found 2 such pairs among 17,758 pairs of trims sharing no text, and 950 with the
   same cite under other tags. A rule needing both would recover at most 2 pairs, and a sample of 2
   says nothing, so the sample also draws 10 same-cite pairs end to end (Brannock's shape) and 10
   with words between. The spec says "such as", so this stays within it, but it is the PM's call
   whether the cite alone is evidence a rule may use. In the event, the operator answered the first
   run's sheet, drawn before this change, so no same-cite pair was asked, and the PM then ruled that
   none be.
2. **ac2 is amended by the PM's ruling of 2026-11-03,** written into the spec by this session at the
   PM's direction, dated, with its earlier wording kept after "Was:". `plan_specs/` is outside
   `constraints.packages`; the edit is the PM's text.
3. **The counts ran on a mixed store** (three caselists in `docx-6`, hspolicy26 in `docx-7`), as
   the PM said they would, so t22's count ran without `--expect-version`, and its long-body half,
   which re-parses with this checkout's `docx-8` parser, is not used.

## Decisions and assumptions

1. **The store's own tables are counted, not a new placement.** Every table on the Mac is
   `card-fingerprint-v4`, the rules the shapes are about, so no placement is made in memory.
2. **Shape (1) is counted as the shape, not as divided pairs.** `v1-e31-t20`'s 13 were the pairs
   `v3` joined and `v4` divided; no store holds a `v3` table of these cards, and re-placing them
   under `v3` would take a rebuild's time for a figure that only says how many were once joined.
3. **Shape (2) is two passages of one holder** (each at least a tenth of it): the bodies the
   witness refusal works on. A pair two holders hold is counted once.
4. **"The same tag and cite" compares the fingerprint normalization of the tag and the full cite**,
   over every card of each body; an absent tag or cite matches nothing.
5. **The answers are read by their meaning.** On a few "same card?" items the operator used the
   other question's keys (`o`, `t`); one card cut twice is read as the same card and two cards as
   different. On "cut twice?" items, `s` and `d` are read the same way.
6. **The sample was answered under the first display** (short cites for a pair; a holder's cite cut
   at the screen's edge). The operator's notes show the cites were read. A re-run under the
   whole-cite display would draw the same 20 items of (1) again by the seed, but other holders.

## The old candidates

`~/t22-card-boundary-candidates.jsonl` (2026-10-19, `2026.10.18-docx-5`, 11,154 sources) was read
against the Mac's dev store as it stands on 2026-11-03: hsld26, hspf26 and openev in
`2026.10.20-docx-6`, hspolicy26 in `2026.10.27-docx-7`, 13,518 parsed sources. The store lacks the
weeks the cloud has run since the cutover; nothing was fetched. A scratch script, counts only, read
each candidate's three bodies at their positions and asked the clusterer's own `CutIndex` whether
the holder still holds both and whether they still share nothing:

| Two cards in one | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Still the same shape | 1,426 | 1,221 | 2,247 | 142 | 5,036 |
| A position holds no full card now | 4 | 124 | 8 | 0 | 136 |
| The holder no longer holds both | 0 | 1 | 0 | 0 | 1 |

97% resolve. But the store holds about 2,400 more sources than the count did, so the file is not
the population any more, and the PM asked for the 216 to be recounted. It is regenerated with
t22's own tool to a new file (Operator follow-ups, step 2); the old one stays.

## Operator follow-ups

### Before the PM's ruling: the counts and the sample

*Run on 2026-11-03:* steps 2 to 4 ran, both counts `exit 0` (558 s and 527 s). The sample was
answered on the sheet of the first run of step 4, before the display changes, so the blank-sheet
step below was not needed. The figures are in the parse report.

Every step reads the Mac's dev store in place and writes only to your home folder. The count
files hold counts, the candidates files hold digests and paragraph indices, and the tally sheet
holds your answers. Don't start while a `caselist pull` is running. The sample's items are real
disclosures. They appear only inside `less`: nothing from that screen goes into a message, a
screenshot or a file, and the sheet's Notes column takes formatting or editing terms only.

**Step 1. Check the worktree** (seconds).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t29-card-matching-recall
git status --short
git log --oneline -1
ls ~/t29-card-boundary-candidates.jsonl ~/t29-matching-recall-candidates.jsonl ~/t29-matching-recall-tally-sheet.txt
```

Expected: `git status` prints nothing; the last commit is this report's; `ls` says "No such file"
three times.

**Step 2. t22's count, regenerating its candidates** (about 7 to 12 minutes; t22's took 6.3 on a
smaller store). Its long-body half parses sources again with this checkout's parser
(`2026.11.03-docx-8`), which did not write the store, so that half reports cards as not
reproduced. Only the two-cards-in-one half is used here.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t29-card-matching-recall
uv run python scripts/count_card_boundaries.py --save-candidates ~/t29-card-boundary-candidates.jsonl > ~/t29-card-boundary-counts.json; echo "exit $?"
jq -c '.caselists | to_entries[] | {caselist: .key, version: .value.version, sources: .value.sources, sharing_nothing: .value.two_cards_in_one.holding_two_sharing_nothing_texts, not_overlapping: .value.two_cards_in_one.holding_two_not_overlapping_texts, by_holder_words: .value.two_cards_in_one.by_holder_words}' ~/t29-card-boundary-counts.json
```

Expected: `exit 0`; four lines, hspolicy26 at `2026.10.27-docx-7` and the others at
`2026.10.20-docx-6`, `sources` above zero on each.

**Step 3. This task's count** (about 5 to 15 minutes: openev took 10 seconds in the session and
hspolicy26 has 18 times its cards).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t29-card-matching-recall
uv run python scripts/count_matching_recall.py --save-candidates ~/t29-matching-recall-candidates.jsonl > ~/t29-matching-recall-counts.json; echo "exit $?"
jq -c '.caselists | to_entries[] | {caselist: .key, version: .value.version_directory, tables: .value.fingerprint_version, cards: .value.cards, neither_end: .value.neither_end.bodies, trims: .value.trims_sharing_nothing.pairs, refusing: .value.witness_refusal.holders, seconds: .value.seconds}' ~/t29-matching-recall-counts.json
```

Expected: `exit 0`; four lines, the same versions as step 2, `tables` `card-fingerprint-v4`, `cards`
above zero on each.

**Step 4 first: clear the blank sheet.** The first run of step 4 (01:52, under the earlier
display) wrote `~/t29-matching-recall-tally-sheet.txt` before showing anything. The session read
it: every Answer row is blank, so nothing is lost. The script refuses to overwrite a sheet, so
remove it first:

```zsh
rm ~/t29-matching-recall-tally-sheet.txt
```

**Step 4. The sample** (under a minute to draw, then your time: about 60 items, about 20 seconds each
in t22's sample).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t29-card-matching-recall
uv run python scripts/sample_matching_recall.py --seed 20261103 --tally-sheet ~/t29-matching-recall-tally-sheet.txt
```

The items open in `less`: space pages, `b` goes back, `q` closes it. Each item gives every card's
tag and its whole cite, wrapped and never cut short (the operator asked for the whole cite, which
is what tells one article from another), and says which keys answer it. The sheet opens with
made-up examples of each answer. Fill in the Answer column of `~/t29-matching-recall-tally-sheet.txt` in any editor, and
the Notes column only where something is worth saying, in formatting or editing terms. Then say
"done" in the session: it reads the two counts files and the sheet from your home folder, so
nothing needs pasting.

### After the merge

Nothing. No placement changes, so no rebuild, re-parse or publish follows this task. The files in
your home folder (`~/t29-card-boundary-*`, `~/t29-matching-recall-*`) hold counts, positions and
answers only; delete them when the PM has read this report.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

- If recall here is ever wanted, it could only come from the 950 trims sharing a cite under other
  tags, and only by relaxing the overlap rule for an exact cite match with a shape check that keeps
  Brannock's rows apart (E31). The PM files nothing now.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

A task that recovers nothing and is still worth merging: it shows from counts, samples and the code
why each recovery would have joined different cards, and pins that they stay apart.

1. **ac1 passes.** Both counts ran on the Mac's store (`exit 0`), and the sample went through t21's
   sampler with the operator's tallies, before any rule. The old candidates file was checked against the
   current store (97% resolve) and regenerated as the PM asked, rather than reused.
2. **The code finding is the most useful result,** and a mutant shows it: lifting the witness refusal
   alone joins nothing, because two trims that don't overlap are both refused as joiners. So any
   recovery of shape (2) or the amendment is a change to the card ruling itself, not a limit, and the
   PM kept it.
3. **ac2 (amended by the PM, 2026-11-03) passes.** The short-card table is row for row t20's, precision
   1.000 on all 13 rows. The five pinning tests pass on the code as it stands, and each fails under at
   least one hand-written mutant.
4. **ac3 passes.** 20 of 280 short holders tallied before the ruling (4 two cards); the refusal is
   unchanged, and t11's false join is pinned.
5. **No fingerprint-version bump and no rebuild,** as ruled: no placement changes.
6. **Deviations accepted.** (1) The same-cite strata drawn into the sample design are moot: the sheet
   answered predates them and the PM ruled no sample. (2) ac2's wording is the PM's. (3) The mixed store,
   and t22's long-body half not used.
7. **The caveats are recorded** (the truncated cites, the answers given with the other question's keys).
   Every ruling keeps today's behaviour, so a misread answer can't let a wrong join in.
8. **The spec check in the criteria table** (599 files, 536 tasks) predates the branch's last sync with
   `dev`, which has since gained the PM's batch of 2026-11-03 (608 files). `scripts/task pr` runs on the
   synced branch, and `ci`'s spec check decides.
9. **Closing checks:** the affected set (61 files) reached 96% under the limit with no failure and is
   left to `ci` (agreement 10); the changed areas (1,854 passed), the always-run list (406), ruff,
   pyright, lint-imports, thin handlers, command blocks, the docs index and links are clean.
10. **Operator:** the files in the home folder hold counts, positions and answers only; delete them now
    that the PM has read the report.
11. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
