# Session report: v1-e31-t29-card-matching-recall

| | |
|---|---|
| Task | `v1-e31-t29-card-matching-recall` — Card matching recovers two kinds of pair it now keeps apart |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t29-card-matching-recall` |
| Session status | WAITING FOR THE PM'S RULING: counts and sample done (ac1, ac3); no rule has changed; ac2 waits on the ruling <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM's order is count, sample, ruling, rule. The counts and the sample are done and recorded in
[the parse report](../data/caselist-parse-report.md#pairs-card-matching-keeps-apart-counted-and-sampled-v1-e31-t29).
**No matching rule has changed**, and the relay below asks the PM to rule.

* **(1) Nine-tenths inside a body holding neither end:** 67 bodies on the store. The operator
  judged **8 of 20 different cards**, at least 3 of them from different articles or sources (two
  articles quoting a third, one author's two articles). A rule on the bodies alone would join cards
  a coach checked as different.
* **(2) Trims sharing no text:** 17,758 pairs. Only **2** have a card of each with the same tag and
  cite; the operator judged 1 one card, 1 two cards. 950 share the cite under other tags, not yet
  sampled.
* **The amendment, holders under 300 words:** 280 by t22's tool (was 216). The operator judged **4
  of 20 two cards**, where t22's sample of all lengths found 0 of 20.
* **Found in the code:** for (2) and the amendment, lifting the witness refusal alone recovers
  nothing. Two trims sharing no text that both propose joining their holder in one round are both
  refused, because they do not overlap each other (`_accepted_joins`, `v1-e31-t20`'s Decision 3).
  Recovering either means relaxing "every two bodies in a cluster overlap", the card ruling itself.

My recommendation is no rule for any of the three (relay, Q1 to Q3). If the PM agrees, ac2 has no
recovered shape to build, and the task closes with tests pinning that each shape stays apart.

### For the PM (paste-ready)

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
| `matching-recall`: Card matching recall | Counted and sampled; the rule waits on the PM | Tools built and tested (`41bf65f`, `bcac62f`, `b05fe2a`); the operator's counts and sample recorded (`8866d53`) |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts for (1) and (2) per caselist, and a sample through t21's sampler, before any rule changes | PASS | The operator's `scripts/count_matching_recall.py` (527 s, `exit 0`) and `scripts/sample_matching_recall.py --seed 20261103` (42 items) on 2026-11-03, recorded in `caselist-parse-report.md`. The sample shows items with t21's `render_pair` and t22's `_between`. (2)'s same-tag-and-cite stratum is the whole population, 2 pairs; the 950 same-cite pairs are not sampled (relay Q2). No rule has changed |
| ac2: precision 1.000 on every labelled set, Brannock's rows apart, each recovered shape with fixtures shown failing first | NOT RUN | Waits on the PM's ruling. No matching rule has changed, so the labelled sets are as `v1-e31-t20` left them |
| ac3 (PM amendment 2026-10-20): the holders under 300 words sampled and tallied before the refusal changes; any change keeps t11's false join apart | PASS (the tally); the change waits on the ruling | 20 of 280 holders drawn: 16 one card cut twice, 4 two cards. The refusal is unchanged |
| Node: `uv run pytest packages/debate_core/tests/evidence -k "cluster or fingerprint"` | PASS | `182 passed` (with the new `test_recall_shapes.py`), 2026-11-03 |

## Files changed

- `packages/debate_core/src/debate_core/evidence/recall_shapes.py` (new): the three shapes in a
  finished placement, in counts. `cluster_diagnosis.py`: `diagnose_cuts` takes an index already
  built. Tests: `packages/debate_core/tests/evidence/test_recall_shapes.py`.
- `scripts/count_matching_recall.py`, `scripts/sample_matching_recall.py` (new), with
  `tests/scripts/test_count_matching_recall.py` and `tests/scripts/test_sample_matching_recall.py`.
- `docs/data/caselist-parse-report.md`: the counts and the sample.

## Deviations from the spec

1. **The shape (2) sample includes trims with the same cite under other tags.** The spec names "an
   identical cite and tag" as the kind of evidence a recovery might use. The operator's count
   (2026-11-03) found 2 such pairs among 17,758 pairs of trims sharing no text, and 950 with the
   same cite under other tags. A rule needing both would recover at most 2 pairs, and a sample of 2
   says nothing, so the sample also draws 10 same-cite pairs end to end (Brannock's shape) and 10
   with words between. The spec says "such as", so this stays within it, but it is the PM's call
   whether the cite alone is evidence a rule may use.

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

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
