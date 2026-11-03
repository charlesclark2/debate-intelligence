# Session report: v1-e31-t29-card-matching-recall

| | |
|---|---|
| Task | `v1-e31-t29-card-matching-recall` — Card matching recovers two kinds of pair it now keeps apart |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t29-card-matching-recall` |
| Session status | IN PROGRESS: the counting and sampling tools are built and tested; the operator's counts and sample are next, then the PM's ruling, and only then any rule <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM's order is count, sample, ruling, rule. This first part builds the counting and the
sampling and hands both to the operator; no matching rule has changed.

* `debate_core.evidence.recall_shapes` finds the three shapes in a finished placement, in digests
  and counts: (1) a body nine-tenths inside a body that holds neither of its ends; (2) two passages
  of one holder sharing no text, with what their cards carry beside them (the same tag and cite or
  not) and how many of the holder's words are in neither; (3) the holders `v1-e31-t20`'s witness
  refusal sets aside, by length.
* `scripts/count_matching_recall.py` counts them over each caselist's own `v4` table and saves
  positions. `scripts/sample_matching_recall.py` draws 60 items, shows them only through `less -R`,
  and writes a tally sheet with no text.
* **t22's candidates mostly resolve, but the store has moved on** ([The old candidates](#the-old-candidates)):
  so the operator regenerates them with t22's own tool, which also recounts the 216.

**For the PM, found in the code:** for shape (2) and the amendment, lifting the witness refusal on
its own recovers nothing. Two trims sharing no text that both propose joining their holder in one
round are both refused, because they do not overlap each other (`_accepted_joins`, `v1-e31-t20`'s
Decision 3, which the PM agreed). Recovering either shape means relaxing "every two bodies in a
cluster overlap" for the case the evidence picks out. That is a change to the card ruling itself,
not to a limit.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

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

**Step 4. The sample** (under a minute to draw, then your time: 60 items, about 20 seconds each in
t22's sample).

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
