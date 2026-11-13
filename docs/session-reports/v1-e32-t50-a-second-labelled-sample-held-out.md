# Session report: v1-e32-t50-a-second-labelled-sample-held-out

| | |
|---|---|
| Task | `v1-e32-t50-a-second-labelled-sample-held-out` — A second labelled sample, held out from tuning, before the bar is read as met |
| Spec | [`plan_specs/v1/e32-argument-landscape/t50-a-second-labelled-sample-held-out.yaml`](../../plan_specs/v1/e32-argument-landscape/t50-a-second-labelled-sample-held-out.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t50-a-second-labelled-sample-held-out` |
| Session status | IN PROGRESS: stopped at the spec's stop for the PM's ruling on the proposal <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped at the spec's stop, as the PM's brief of 2026-11-14 asks. No code has been written. The proposal
below sets out the holdout's size from the interval wanted at 0.85, the draw (strata, seed, snapshot), the
card identity that keeps every copy of the first sample out, LD, rows 16, 33 and 57, and the labels-file
copy. The build waits for the PM's ruling. Prerequisites t46, t53, t55 and t58 are `Succeeded`.

## The proposal (2026-11-13, for the PM's ruling)

Counts, ids, row numbers, dates and file names only. Nothing below came from reading the parsed store. The
snapshot names are manifest file names on this Mac, and the pace is file times from `v1-e32-t55`'s report.

### 1. Size

**The interval wanted at 0.85.** A route that truly scores 0.85 should have a 95% interval that leaves out
today's best, 0.75. A route that truly scores 0.75 should have one that leaves out the bar. On the first
sample neither holds: 0.75 on 32 counted runs from 0.58 to 0.87.

**The method.** Wilson's score interval at 95%. It reproduces both intervals the record gives: 23 of 33 is
0.527 to 0.826 and 24 of 32 is 0.579 to 0.867.

**From drawn to counted.** On the first sample, 47 of 60 drawn cards were labelled (0.783), and 1.3.1 counted
38 of the 47 (0.809). So about 0.633 of the cards drawn are counted. Under 1.3.0 it was 32 of 47, so the
count is a forecast, not a promise.

**The coach's pace.** The t46 sitting's copy was taken after the store read, at 22:44:37 on 2026-11-04, and
the sitting wrote the file at 22:51:26. That is 6 min 49 s for 19 cards, **about 21.5 s a card**. Those were
cards the coach had labelled before, with the label shown and Enter keeping it. A fresh label (a position
and a stance from about 45 ids) is likely slower, so the table also gives twice that pace.

| Drawn (strata) | Counted, about | 95% interval at 0.85 | at 0.75 | Coach, t46 pace | at twice the pace |
|---|---|---|---|---|---|
| 60 (30/20/10) | 38 | 0.71 to 0.93 | 0.59 to 0.86 | 22 min | 43 min |
| 90 (45/30/15) | 57 | 0.74 to 0.92 | 0.62 to 0.84 | 32 min | 65 min |
| **120 (60/40/20)** | **76** | **0.75 to 0.91** | **0.64 to 0.83** | **43 min** | **86 min** |
| 150 (75/50/25) | 95 | 0.76 to 0.91 | 0.65 to 0.83 | 54 min | 108 min |

**Recommendation: 120 drawn**, the first sample's strata doubled (60 at or above the proxy's threshold, 40
just below, 20 far below), in two sittings of 60. It is the smallest size where both conditions hold, if
only just: at 0.85 the interval's lower end is at 0.75, and at 0.75 the upper end is 0.83. Chance figures
(binomial, at 76 counted): a route that truly scores 0.75 shows 0.85 or more 1.9% of the time, against 6.0%
on 38 counted. A route that truly scores 0.85 shows 0.85 or more about half the time at any size, so a
larger sample shrinks false passes, not false fails.

### 2. The draw

* **The same rule as the first sample:** `coach_sample()` in
  `debate_core/arguments/landscape/local_classifier.py`, as `scripts/compare_local_classifier.py sample` ran
  it for `v1-e32-t21`. Only stage one's unplaced cards are drawn, with the proxy model retrained on the
  holdout snapshot's feature table and nine tenths of its documents. The strata are cut at that model's
  threshold (0.9 when none reaches the target) and at the median below it. Kinds take turns inside a
  stratum, cards come in seeded-digest order, at most one card per document, and the rows file's header
  records the populations for the weighted score. Only the shares change, to 60/40/20.
* **The seed.** The first sample used 21. With 21 again, the first sample's cards come first in every cell
  and are excluded, so the holdout is that draw continued. A new seed makes it an independent draw. Either
  is unbiased. Recommended: a new seed, the date of the ruling, as t46's sitting used 20261105. It is
  recorded in the rows file's header.
* **The snapshot.** This Mac's store holds hspolicy26 manifests through **2026-11-03** (written 2026-11-04),
  parsed at `2026.10.27-docx-7`. The cloud run's state very likely holds **2026-11-10**: t51 counted
  hsld26's 2026-11-10 snapshot, and hspolicy26's weeklies are Mondays. Confirming it is a read of dev's
  bucket, so it is the operator's.
  * **Recommended: 2026-11-10 if the PM wants the newest, from a restored copy.** The cost: policy 1.18
    deletes a restored copy at the end of the step that restored it. The draw, the sitting (which reads
    each card's side) and the record run each read the same cards, so each restores the copy again, unless
    the PM amends the policy to keep one copy until the record run. A copy holds the cloud image's parser
    version, and the draw refuses a first-sample card it cannot find there.
  * **The alternative: 2026-11-03 from this Mac's own store.** No restore and no policy question. It is the
    store every first-sample evaluation has read, and it is one week older. The draw's first block prints
    the snapshot, sources and unplaced cards, so it shows whether the parse covers it.
  * **What changes from the first sample's 2026-10-20:** more documents and tournaments. The proxy is
    retrained, so the threshold, the strata cuts and the populations (the weights) are the holdout's own,
    and its score is not pooled with the first sample's. The holdout is evaluated with
    `--snapshot <its snapshot>`, the first sample with 2026-10-20. Both run under taxonomy 1.5.1 (the
    coach's `generic-k` wording, t53) and prompt 1.3.1.
* **Its files** get their own names under `<data dir>/landscape/local-classifier/hspolicy26/`
  (`policy-2026-27-nhi-holdout-<snapshot>-features.jsonl`, `-sample.jsonl`). `sample` writes the first
  sample's rows file and its feature table at fixed names, so running it again would overwrite them. The
  draw refuses to write over either. The coach's CSV goes beside the first sample's, as
  `~/Documents/debate/landscape-review/policy-2026-27-nhi-holdout-sample-labelled.csv`, with its sidecar
  recorded when the draw writes it (the t58 guard).

### 3. "No card shared with the 47": by evidence, not by row

The parser has card identity: `occurrences.jsonl`'s **`exact_fingerprint`** and **`cluster_id`**
(`OccurrenceRecord`, `debate_core/application/ports/parsed_store.py`; the rules are in
`debate_core/evidence/fingerprints.py`, now `card-fingerprint-v4`). The exact fingerprint is the SHA-256 of
the normalized evidence body: copies of the same text, whoever tagged or highlighted them. The cluster id
is the near-duplicate cluster: the same card cut longer or shorter. A first-sample item id is
`<source_sha256>:<first paragraph>`, which joins an occurrence row on `source_sha256` and
`first_element_index`. The seed reading the draw is built from carries neither identity, so the draw reads
the occurrence table of the same version directory, where cluster ids are comparable.

The model reads more than the evidence. Its request carries the card's headings, tag, short cite and an
excerpt of the body (`model_candidate`). So the proposal excludes on every identity a tuned prompt could
have learned from:

1. **Every card whose cluster holds a card of the first sample.** This covers the same evidence in any
   team's file, any cut. The exact fingerprint is a subset of it and is checked as well.
2. **Every card read alike to a first-sample card**: the same `MatchItem.fingerprint`, which is the
   headings with their answer flags and the tag's words (a team's tag on a card re-disclosed).
3. **Every card from a document of the first sample**: the same team's tagging, 60 documents.
4. **All 60 drawn, not only the 47 labelled.** The coach read all 60, and the 13 left unsure belong to the
   same draw.
5. **Inside the holdout, at most one card per cluster**, as there is one per document, so two copies of one
   card are not counted twice.

A first-sample card with no occurrence row (a removal reached it) cannot be proved absent. The draw then
stops and names how many, never which; the PM rules. A candidate with no occurrence row is left out and
counted. The draw prints each exclusion's count. The test's mutant lets one holdout card share a cluster
with a first-sample card in another team's file, and the test fails on it.

### 4. LD: a separate task, recommended

* ac4 of `v1-e32-t07` asks for per-format accuracy, and the 47 are Policy only.
* **Prompt 1.3.1 is written for Policy.** It names advantages, disadvantages, counterplans, the
  affirmative, kritiks and topicality 74 times and LD's value, criterion or contention not once, and it has
  never been asked about an LD card.
* So an LD sample is that route's first LD measure. If it fails, tuning on it spends it, and LD then needs a
  holdout of its own: a pair, not one sample.
* **The de-extinction topic began on 2026-11-06.** The newest snapshot holds about one week of its
  disclosures. On hsld26's 2026-11-10 snapshot, 356 of 1,639 disclosures were still space colonization
  files (`topics.yaml`'s comment, t51), and unplaced de-extinction cards will be few. The topic runs to
  2026-12-31.
* **Recommended:** LD is a separate task, filed by the PM, using this task's draw with
  `--caselist hsld26`, the same exclusions and the same files. Draw it once the topic has three or four
  weeks of disclosures. The coach's time at t46's pace: a first LD sample of 60 is about 22 min (43 min at
  twice the pace), and an LD holdout of 120 about 43 min (86 min).
* **The cost of drawing LD in this sitting:** the sitting doubles to about 86 min (172 min at twice the
  pace), and the LD cards come from about a week of the topic.
* Either way, t07's ac4 wording ("a coach-labeled 60-item set (Policy and LD ...)") needs the PM's
  amendment to name the holdout. The ac4 tasks waiting on it are v1-e05-t14, v1-e05-t20 and v1-e40-t19.

### 5. Rows 16, 33 and 57 in the same sitting

* **They come after the holdout's cards, as a part of their own.** The question they ask (this card's file
  was disclosed only on the side opposite its position) would prime the stance on the holdout cards that
  follow, so they are not mixed in.
* **For each row** the sitting shows the tag and headings from the first sample's CSV, the side its file was
  disclosed on, and the coach's current label. Rows 16 and 57 carry the 2026-11-06 labels; row 33 stays open.
* **The coach makes one of the three choices:**
  * `at:<id>`, which replaces the label;
  * `also <label>`, which adds a second label (the `also` column);
  * `side`, for "the side rule is wrong here", which leaves the label as it is.
* **What gets written:** the first two go into the first sample's CSV through the guard. That file gets its
  own dated copy and new sidecar, and the holdout's CSV is written separately. The third writes nothing.
  The sitting's last line names its rows by number, and the PM files the follow-up on t46's other-side
  rule from that line.
* **t53 is decided** (2026-11-08), so its wording is in the taxonomy the sitting reads.

### 6. The sitting, `--check-sample` and the evaluation

* **The sitting** shows each holdout card's tag and headings (a heading fewer than two teams use stays
  withheld, as t21's CSV withholds it) and the side its file was disclosed on. It shows nothing of the
  model, its answers, the strata or a score, and no card is marked. The coach types a position id,
  `at:<id>`, `none`, `unsure`, or Enter to skip, with an optional `, <second label>`; a label the
  evaluation would refuse is asked again. It covers a range of rows (`--rows 1-60`, then `61-120`). It
  writes once at the end, through the guard, and Ctrl-C writes nothing.
* **`--check-sample` reads the holdout** with its own `--sample`, `--sample-rows` and `--snapshot`, and prints
  the same counts.
* **The evaluation reports the holdout beside the first sample.** `landscape evaluate` takes the holdout's
  files as well, and its JSON puts `first_sample` and `holdout` side by side.
* **It never feeds the holdout to tuning.** A rows file whose header says `"holdout": true` is reported as
  counts and scores only: no row numbers, no per-card outcomes, no answer ids. `--breakdown` refuses it.
  Tuning works from which cards a prompt gets wrong, and the holdout never says that, to the PM or to a
  session.
* **Its first score needs a record run**, because no cassette of its cards exists. That run is the
  operator's, after the PM rules on it. The hold on live runs stands.

### 7. The labels files, copied aside before and after the sitting

t61 is not built, so the operator runs this block twice: just before the sitting and just after it. It keeps
a timestamped, read-only copy of both labels files (never over an existing copy), checks it byte for byte,
and prints the SHA-256 of each file and its copy. It was tested in `zsh -f` on two scratch files: a second
paste in the same second stops instead of overwriting, and a missing file stops by name.

```bash
cd ~/Documents/debate/landscape-review
```

```bash
STAMP=$(date +%Y-%m-%d-%H%M%S); for F in policy-2026-27-nhi-coach-sample-labelled.csv policy-2026-27-nhi-holdout-sample-labelled.csv; do if [ ! -f "$F" ]; then echo "STOP: $F is missing"; elif ! cp -n "$F" "${F%.csv}.kept-${STAMP}.csv" || ! cmp -s "$F" "${F%.csv}.kept-${STAMP}.csv"; then echo "STOP: the copy of $F failed"; else chmod a-w "${F%.csv}.kept-${STAMP}.csv"; shasum -a 256 "$F" "${F%.csv}.kept-${STAMP}.csv"; fi; done
```

Success: four digest lines, each file's digest the same as its copy's, and no `STOP`. The holdout's file
first exists once the draw has written it, so before the draw the block names it missing; that is expected.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-second-labelled-sample-held-out` (Holdout sample) | NOT STARTED | Waits on the PM's ruling on the proposal |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the second sample's size, from the interval wanted at 0.85 and the coach's time, ruled on by the PM | NOT RUN | Proposed above (120 drawn); waits on the PM's ruling |
| ac2: drawn by the strata and seed rule with no card from the first, by tests on invented cards shown failing first, and the evaluation reads it as a holdout beside the first | NOT RUN | Built after the ruling |
| ac3: the coach labels it in a sitting and `--check-sample` reads it (operator, recorded by the PM) | NOT RUN | Operator, after the build |
| Node: Holdout sample tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape -k sample`) | NOT RUN | Built after the ruling |

## Files changed

* `docs/session-reports/v1-e32-t50-a-second-labelled-sample-held-out.md`: this proposal.

## Deviations from the spec

None so far. The constraints already list `debate_cli` tests but not `debate_cli`'s source (the evaluate
command's `--holdout-*` options are in `packages/debate_cli/src/debate_cli/commands/landscape.py`). Unless
the PM says otherwise, that command is edited as a thin adapter and recorded here.

## Decisions and assumptions

* The interval method is Wilson's, because it reproduces the record's two intervals.
* The forecast counted share (0.633) is 1.3.1's, since the holdout is measured on 1.3.1.

## Operator follow-ups

None yet. The labels-file copy block is in [section 7](#7-the-labels-files-copied-aside-before-and-after-the-sitting)
for when the sitting is scheduled.

## Follow-up work

* If the PM agrees LD is separate: an LD sample pair (first and holdout) on hsld26's de-extinction topic, using
  this task's draw (section 4).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
