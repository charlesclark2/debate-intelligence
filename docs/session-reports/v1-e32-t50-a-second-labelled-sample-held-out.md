# Session report: v1-e32-t50-a-second-labelled-sample-held-out

| | |
|---|---|
| Task | `v1-e32-t50-a-second-labelled-sample-held-out` — A second labelled sample, held out from tuning, before the bar is read as met |
| Spec | [`plan_specs/v1/e32-argument-landscape/t50-a-second-labelled-sample-held-out.yaml`](../../plan_specs/v1/e32-argument-landscape/t50-a-second-labelled-sample-held-out.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t50-a-second-labelled-sample-held-out` |
| Session status | PARTIAL, ready for the PM's review: built and tested as ruled, the holdout's scan-hit listing included (the PM's third ruling); ac3, the ruled record run and step 7 are done by the operator, ac3 for the PM to record; the holdout's 44 `high_volume` scan hits were judged ordinary words <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM ruled the proposal on 2026-11-14 ([the ruling](#the-pms-ruling-2026-11-14)), and the build follows it:

* **The draw.** `compare_local_classifier.py holdout-sample` draws 120 cards by the first sample's rule (strata
  60/40/20, seed 20261114) from the 2026-11-03 snapshot of this Mac's store. It keeps out every card that shares
  a cluster, an exact fingerprint, a reading or a document with any of the first sample's 60, and takes one
  card per cluster. It prints each exclusion's count and stops, by count, on a first-sample card with no
  occurrence row. It writes its own files under its own names, and refuses to write over any file.
* **The sitting.** `label_holdout_sample.py` takes the two sittings of 60. Rows 16, 33 and 57 of the first
  sample come at the end of the second, each answered `at:<id>`, `also <label>` or `side`.
* **The evaluation.** `landscape evaluate --holdout-*` reads the holdout beside the first sample, as counts and
  scores only; `--breakdown` refuses a holdout; `--check-sample` reads it.
* **The holdout's own scan hits** (the PM's third ruling). `landscape evaluate --holdout-scan-hits` lists, for a
  terminal only, the hits of the holdout's own cassettes: numbered, with no row, outcome or answer.

The tests are on invented cards and stores. They were run red against a refuse-nothing skeleton (39 of 52
failing, each at an assertion) and catch all 13 mutants, the PM's included: a holdout card sharing a cluster
with a first-sample card in another team's file. The node's criterion passes (35 tests).

**The held-out score: the bar is not met on either route.**

| Route | Holdout, pipeline (95%) | First sample, pipeline |
|---|---|---|
| `deep_audit`, Claude Sonnet 4.6 | 44 of 77, 0.571 (0.46 to 0.68) | 14 of 21, 0.667 (a batch of 20 refused) |
| `high_volume`, Claude Haiku 4.5 | 39 of 82, 0.476 (0.37 to 0.58) | 23 of 35, 0.657 |

Prompt 1.3.1 and taxonomy 1.5.1 on both routes. The holdout was drawn at snapshot 2026-11-03, parser
`2026.10.27-docx-7`. The operator ran the ruled record run on 2026-11-14 for about $0.78, and the replay side
by side on each route. Both exit 1 with `EVALUATION_BELOW_BAR`, and the bar reads the holdout. The hold on
live model runs stands. The details, and the three findings the PM ruled on, are under
[Operator follow-ups](#operator-follow-ups).

**The Goal stays `InProgress` until the PM records ac3.** Where things stand:

* ac3 (the draw on 2026-11-13, the coach's two sittings and `--check-sample` on 2026-11-14) passed in the
  operator's run, for the PM to record.
* The holdout's `high_volume` scan hits were judged with the listing the PM ruled for (step 7 of the runbook's
  [held-out section](../runbooks/landscape-model-evaluation-record.md#the-held-out-sample-the-draw-and-the-coachs-two-sittings-v1-e32-t50)).
  All 44 are ordinary words, including hit 12, the one no mark sets aside, so its cassettes are kept.

No further live call is authorized, and none is needed. The affected set is left to the pull request's CI, as
ruled. This report is ready for the PM's review.

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

## The PM's ruling (2026-11-14)

Recorded as given, in short:

1. **Size:** 120, strata 60/40/20, two sittings of 60; the table and the Wilson method as given.
2. **Seed** 20261114. **Snapshot (b):** 2026-11-03 from this Mac's own store, parsed at `2026.10.27-docx-7`,
   recorded beside the holdout's scores in `landscape-model-evaluation.md`. The new file names as proposed;
   the draw keeps refusing to overwrite the first sample's files.
3. **Exclusions:** all of section 3, against all 60 drawn: a first-sample card's cluster (exact fingerprint
   checked too), the same `MatchItem` fingerprint, any first-sample document, and at most one card per
   cluster inside the holdout. A first-sample card with no occurrence row stops the draw, printing a count
   only. Each exclusion's count is printed. The mutant as proposed.
4. **LD:** a separate task, filed by the PM in the next batch, sat only once the Policy holdout has its score.
   The PM amends `v1-e32-t07` ac4's "Policy and LD" in the same batch.
5. **Rows 16, 33 and 57:** `at:<id>`, `also <label>` or `side`, after the holdout's cards at the end of the
   second sitting. `side` writes nothing and names the row on the last line.
6. **Confirmed:** the holdout header; counts and scores only (no row numbers, per-card outcomes or answer ids);
   `--breakdown` refuses it; `first_sample` and `holdout` side by side in the JSON; `--check-sample` reads it;
   the sitting shows no model, score, stratum or mark. The record run is not authorized: the report gives the
   record commands per route measured so far, with a token and cost estimate from the 1.3.1 re-record, and the
   PM rules on them after both sittings.
7. **Labels copy:** the zsh block as given, before and after each sitting.

FYI accepted: `debate_cli`'s `landscape.py` (thin `--holdout-*` options) is a Deviation citing this ruling.

## The build

Every name below is an invented test's or a code identifier; no card, tag, heading or label of the store was
read by the session.

### The draw (`debate_core/arguments/landscape/holdout_sample.py`, `application/holdout_sample_draw.py`)

* **`coach_sample()` gains two keyword arguments, both off by default**, so the first sample's draw is
  unchanged:
  * `strata`, other shares of the same three strata;
  * `cluster_of`, which with the one-card-per-document rule keeps one card per cluster.
* **`holdout_sample()` applies the ruling's rules to every candidate**, against every first-sample card
  drawn:
  * a first-sample card's `cluster_id`;
  * its `exact_fingerprint`;
  * its `MatchItem.fingerprint`;
  * its document.

  A candidate with no occurrence row is also kept out, and counted. Each rule's count is kept: the rules
  overlap, so a card is counted under each rule it meets and once in `excluded`. The draw then runs
  `coach_sample()` on the eligible cards, at 60/40/20 and seed 20261114, one per cluster. A first-sample card
  with no identity, or one with no occurrence row, raises `FirstSampleCardsMissing(missing, of)`, whose
  message gives the counts and never an id.
* **`card_identities()`** names every card of one reading by item id. The read fingerprint comes from
  `read_items`, and the exact fingerprint and cluster from that reading's own `occurrences.jsonl`, joined on
  source and first paragraph, as `landscape_cards` joins them.
* **`holdout_sample_lines()`** writes the rows file. Its header adds `"holdout": true`, the seed, the
  shares, every exclusion count, and `drawn_from`: the caselist, topic, snapshot, version directory, parser
  version and fingerprint versions.
* **The mark** (`HOLDOUT_KEY`, `holdout_header`, `is_holdout`) is in `holdout_mark.py`, a module of its own.
  The evaluation and the CLI read only the mark, and importing the draw would load scikit-learn:
  `test_container_factories` caught that during this session.

### The draw's command (`scripts/compare_local_classifier.py holdout-sample`)

* `--snapshot`, `--labels-out` and `--dry-run`, with seed 20261114 by default.
* It reads the store at the snapshot and refuses a version directory with no occurrence table. It builds the
  feature table, trains both models on the seed, reads the first sample's rows file and draws.
* It prints every count, then writes three new files, each opened for exclusive creation:
  * `<topic>-holdout-<snapshot>-features.jsonl`;
  * `<topic>-holdout-<snapshot>-sample.jsonl`;
  * the coach's CSV at `--labels-out`, with an empty `also` column, and its sidecar through
    `record_first_digest`.
* It refuses an existing target, and a target that is one of the first sample's files, before reading the
  store (`--dry-run` included for the latter).
* The first sample's commands (`compare`, `sample`, `score-sample`, `train-queue-order`) still find their one
  feature table: files with `-holdout-` in the name are left out of their glob.

### The sitting (`application/holdout_sitting.py`, `scripts/label_holdout_sample.py`)

* `--rows 1-60`, then `61-120`, shown in the sample's own order. Each card shows its tag, its headings and the
  side its file was disclosed on (from `sides_by_row`), and its current label if it has one.
* The coach types a label and stance, `at:<id>`, `none` or `unsure`, with an optional `, <second label>`.
  `row_labels` validates it. A refusal is asked again and is never echoed, and an `unsure` card takes no
  second label.
* `--side-rows 16,33,57`, with the first sample's files and `--first-snapshot`, adds the separate part. Each
  card shows its tag, headings, side and labels, and takes `at:<id>`, `also <label>` or `side`. `side` writes
  nothing, and the sitting's last line names its rows.
* Both files are read through the t58 guard before anything is shown. Each changed file is written once, at
  the end, with `write_sitting` (a dated copy, the file, then the sidecar). Ctrl-C writes nothing.
  `rewritten_cells` generalizes t46's `relabelled_sample` to the `position` and `also` columns.
* The end prints counts only: labelled, unsure, blank and second labels, then the first sample's rows written
  and the side line.

### The evaluation (`application/landscape_model_evaluation.py`, `debate_cli/commands/landscape.py`)

* `break_down` refuses a rows file marked a holdout (`EVALUATION_REFUSED`, "never broken down card by card").
* `check_sample` reads a holdout and sets `holdout`. `--check-sample`'s JSON adds `"holdout": true` only for
  one, so the first sample's JSON is unchanged.
* `evaluate_beside` evaluates the first sample and the holdout, each at its own snapshot, and returns both
  with the holdout's `drawn_from`. Before any model is asked, it refuses a holdout whose rows file is not
  marked, a first sample whose rows file is, and a pair that shares a card or a document (counts only).
* `landscape evaluate --holdout-sample/--holdout-sample-rows/--holdout-snapshot` replays both. `data` is
  `bar_reads_sample` (`holdout`), `first_sample` and `holdout`; the last holds the same summary keys plus
  `drawn_from`. It exits 0 when both stages ran, every scan of both is clean, and the holdout meets the bar.
  The options are refused:
  * with `--breakdown` (`HOLDOUT_COUNTS_ONLY`);
  * with `--model-mode record` (`HOLDOUT_RECORDS_ALONE`: the holdout is recorded alone, as `--sample`);
  * with `--check-sample` (`CHECK_SAMPLE_ASKS_NO_MODEL`);
  * when given without all three (`HOLDOUT_NEEDS_ITS_FILES`).

  The command's handler stays at the 25-statement budget: its closing lines moved into `_finish`.
* `sides_by_row` gives every row's disclosed sides, whether or not the row is labelled. The sitting needs it,
  because t46's `sample_sides` reads labelled rows only.

### Tests, run red first

The tests are in five new files, and one test is added to the smoke suite:

* `packages/debate_core/tests/arguments/landscape/test_holdout_sample.py` (13 tests): the draw by hand, each
  rule's count, the mutant's card, the strata and seed, one per cluster, the stop by count, and the rows
  file's header.
* `packages/debate_core/tests/application/test_holdout_sitting.py` (13): ranges, labels with a stance and a
  second label, refusals, nothing of a model shown, the three choices, `side`'s last line, and the cells
  written.
* `packages/debate_core/tests/application/test_holdout_sample_reading.py` (12), on `synthetic26`:
  identities, side by side, the refusals before any model call, `--breakdown` refused, `--check-sample`, and
  sides.
* `packages/debate_cli/tests/test_landscape_evaluate_holdout.py` (7), through the container: recorded alone,
  replayed beside, and each refusal's code.
* `tests/scripts/test_holdout_sample_script.py` (7), on a planted store with an occurrence table: no shared
  document or cluster, the files written and the first sample's unchanged, no overwrite, a dry run, the stop,
  and the first sample's commands.
* `tests/smoke/test_landscape_evaluate_smoke.py::test_landscape_evaluate_reads_a_holdout_as_counts_only`.

**The red run** was against commit `4f8c81e`, a skeleton with every signature in place and no rule applied:
no exclusion, no mark, no refusal, no overwrite check. **39 of 52 failed.** Three of them failed on a missing
key, not an assertion; they were made to fail at their assertions (`1007d8c`) and were run red
again. Three were corrected after the red run, because they picked `aff-two`'s copy of a card where
`aff-one`'s was meant; on the skeleton they still fail, since the skeleton refuses no shared card.

The 13 that passed on the skeleton test code it kept whole: the range parser, the cell rewriter, the
displays, `drawn_from`, the seed's determinism, the first sample's breakdown, and the dry run writing
nothing. The smoke check failed on the skeleton's sources at its assertion
(`assert (None, 4) == (True, 4)`) and passes on HEAD.

**The mutants**, each applied to the committed code, run against the five files, and restored from HEAD:

| Mutant | Tests failing |
|---|---|
| **The PM's: a candidate in a first-sample card's cluster is not kept out** | **5**, among them `test_a_card_sharing_a_cluster_with_a_first_sample_card_in_another_teams_file_is_never_drawn` and the script's no-shared-cluster test |
| The exact-fingerprint rule off | 4 |
| The reading (`MatchItem` fingerprint) rule off | 3 |
| The document rule off | 5 |
| The no-occurrence-row stop off | 3. The `f2` case fails on an `AttributeError`, not an assertion. The `f1` case and the script's stop test fail at their assertions. |
| The first sample measured short of one card (as if against the labelled only) | 9 |
| One card per cluster off | 3 |
| The holdout's `--breakdown` refusal off (service) | 2 |
| The holdout's `--breakdown` refusal off (CLI) | 1 |
| The shared-document check off | 1 |
| The overwrite refusal off | 1 |
| The first sample's feature-table glob takes the holdout's too | 1 |
| The side line names no row | 1 |

All 13 are caught.

## The PM's second ruling (2026-11-14)

Recorded as given, in short:

1. **The record run:** both routes, `deep_audit` and `high_volume`, at prompt 1.3.1 and taxonomy 1.5.1, in the
   order proposed: the holdout recorded alone; the first sample's 47 recorded again, since 1.5.1 moved the
   cassette keys; then the replay side by side, with no call. About $0.95 in all, inside one day's $2.00
   guard. A narrow exception to the hold on live model runs, for these recordings only. The operator runs them
   on one day after both sittings, not on a Wednesday, and sends the PM the evaluation's counts and scores.
   No other live run is authorized.
2. **Decisions confirmed:**
   * (a) the exclusions come before the strata, with a note in `landscape-model-evaluation.md` that the
     holdout's stratum weights are its own and not pooled;
   * (b) with both samples evaluated, the exit code reads the bar on the holdout, while the first sample's
     scans and stops still count;
   * (c) the draw writes the holdout CSV's sidecar.
3. **Deviations accepted:** `debate_cli` src, `tests/scripts` and `tests/smoke`; the PM adds them to the spec's
   packages in the next batch. The smoke test is welcome.
4. **The affected set** is left to the pull request's CI under working agreement 10.

What this session did with it:

* **The record run is now step 6 of the runbook's held-out section**, as four blocks: a recording on each route
  and a side-by-side replay on each. Each recording block refuses a Wednesday (`date +%u` is 3), a set
  `DEBATE_` variable, a running pull, a holdout check without `"holdout": true`, a failed first-sample check
  and a logged-out Bedrock profile, before any call. All eleven blocks of the section pass `zsh -n`.
* **The weights note** is in `landscape-model-evaluation.md`'s held-out section, with the ruling on when the
  scores are recorded and that the bar reads the holdout.

The estimate behind the $0.95 is linear in the cards asked, from the 1.3.1 re-record: 43,165 input and 5,235
output tokens for 47 cards in 5 calls (2 of them repairs), at `config/model_pricing.yaml`'s prices. The holdout
asks only its labelled cards: about 94 at the first sample's rate (47 of 60), at most 120.

| Route | First sample (47) | Holdout (94 / 120) | In all |
|---|---|---|---|
| `deep_audit`, $0.003 / $0.015 per 1,000 | 43,165 in, 5,235 out: $0.208 | 86,330 in, 10,470 out: $0.416 / 110,209 in, 13,366 out: $0.531 | $0.62 / $0.74 |
| `high_volume`, $0.001 / $0.005 per 1,000 | same tokens: $0.069 | $0.139 / $0.177 | $0.21 / $0.25 |

The batches run one after another, so the guard holds the day's spend plus one call's ceiling (about $0.37 on
`deep_audit`, from t55's $1.106 for three calls).

## The PM's third ruling (2026-11-14)

On the record run's findings, as relayed:

1. **(a) Leave the first sample's 20 refused `deep_audit` cards.** The bar reads the holdout, which lost no
   batch, and the first sample's score is context only. No further live call is authorized.
2. **(a) A terminal-only listing of the holdout's scan hits.** Hit numbers and the words around each, for the
   operator's eyes only, with no row, outcome or answer id, tested offline in this task. The operator judges
   each hit by number, as on 2026-11-05, and only the verdicts come back. The runbook's step 5 is not run on
   the first sample until the listing exists.

It also recorded the finding on rows 16, 33 and 57: only row 33's `side` goes to the follow-up on t46's
other-side rule.

### The listing (`arguments/landscape/holdout_scan.py`, `landscape evaluate --holdout-scan-hits`)

* **Which texts.** The scan reads every cassette of the route's classify prompt at its version, and every
  repair of it filed under the caselist, so the listing keeps the holdout's own:
  * a classify cassette whose request's `items` are a card list the holdout's replay sent, compared as
    parsed JSON, so spacing does not matter;
  * a repair whose failed prompt holds such a list.

  The service replays the holdout as `evaluate` asks it, with no model call, and lists the hits of its input
  batches, then its cassettes, then its repairs. The scan's own functions read them (`input_batch_hits`,
  `cassette_hits`, `repair_cassette_hits`), and each hit keeps its marks.
* **What it shows.** One line per hit: its number, the text (`cassette 1`, renumbered among the holdout's
  own), the field, the kind, the marks, `(no mark sets it aside)` where none does, and the words around it.
  A head line gives the counts.
* **What it refuses.**
  * A rows file not marked a holdout. The first sample's hits are the breakdown's.
  * A batch the replay sent with no cassette among those the scan reads, so the filter can never leave the
    holdout's texts out silently.
  * `--json`, `--breakdown`, `--check-sample`, `--model-mode record` and `--holdout-*`
    (`HOLDOUT_HITS_TERMINAL_ONLY`).

  When stdout is not a terminal, it prints the head line and a `withheld` count, never a word. The runbook
  uses that output for what is pasted back.
* **The handler stays at 25 statements.** Two pairs of assignments in `evaluate` became one each, and the
  new branch went in their place.
* **Tests, offline:**
  * 5 in `packages/debate_core/tests/arguments/landscape/test_holdout_scan.py`;
  * 9 in `packages/debate_cli/tests/test_landscape_evaluate_holdout.py`, through `synthetic26`. Each sample's
    rationale names an invented school, and the listing shows the holdout's and not the first sample's.
* **Red first.** Against a refuse-nothing skeleton, which kept every text, refused nothing, printed to a pipe
  and dropped the notice and the marks, 12 of the then 13 new tests failed, each at an assertion. The 13th is
  the set-aside control: its expected `left` is 0, which the skeleton returns.
* **Mutants.** 11 were run, one at a time:
  * cassettes kept without the sent list;
  * repairs kept without it;
  * `left` counting every hit;
  * input batches not listed;
  * a first sample's rows file accepted;
  * missing cassettes not refused;
  * `--json` accepted;
  * a recording accepted;
  * hits printed to a pipe;
  * no notice;
  * no `(no mark sets it aside)`.

  10 were caught. "Input batches not listed" survived, because no test put a hit in a card sent. The added
  test `test_a_hit_in_a_card_the_holdout_sent_is_listed_under_its_input_batch` catches it.
* **Checks.** All pass:
  * ruff and ruff format;
  * pyright on the whole project;
  * lint-imports (20 contracts kept);
  * the thin-handler check;
  * the command-block check;
  * the links and the docs index.

  The tests run for the change:
  * `test_container_factories.py`, the holdout files and the evaluate smoke check: 70 passed;
  * `test_landscape_command.py -k "evaluate or breakdown or check_sample"`: 40 passed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-second-labelled-sample-held-out` (Holdout sample) | DONE | Built as ruled; its criterion passes (below) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the second sample's size, from the interval wanted at 0.85 and the coach's time, ruled on by the PM | PASS | The PM's ruling of 2026-11-14: 120 drawn, 60/40/20, Wilson ([above](#the-pms-ruling-2026-11-14)) |
| ac2: drawn by the strata and seed rule with no card from the first, by tests on invented cards shown failing first, and the evaluation reads it as a holdout beside the first | PASS (code and tests); the real draw is the operator's | Red against `4f8c81e`: 39 of 52 failed, each at an assertion. Green: 52 of 52, plus the smoke check. 13 mutants caught, the PM's by 5 tests. `evaluate_beside` and `--holdout-*` read it beside the first. |
| ac3: the coach labels it in a sitting and `--check-sample` reads it (operator, recorded by the PM) | PASS (the operator's run; the PM records it) | The draw on 2026-11-13, then two sittings on 2026-11-14: 111 of 120 labelled, 9 unsure. `--check-sample` reads `"holdout": true` and `labelled` 111; the file's SHA-256 is `7d1ada7b…`. The first sample is unchanged at 47 ([Operator follow-ups](#operator-follow-ups)). The ruled record run followed on 2026-11-14 |
| Node: Holdout sample tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape -k sample`) | PASS | `35 passed in 3.59s` |

## Files changed

* `packages/debate_core/src/debate_core/arguments/landscape/holdout_sample.py` (new): the draw and its
  exclusions.
* `packages/debate_core/src/debate_core/arguments/landscape/holdout_mark.py` (new): the rows file's mark.
* `packages/debate_core/src/debate_core/arguments/landscape/local_classifier.py`: `coach_sample(strata=,
  cluster_of=)`, `write_sample_csv(second_label_column=)`, `SECOND_LABEL_COLUMN`.
* `packages/debate_core/src/debate_core/application/holdout_sample_draw.py` (new): `card_identities`,
  `drawn_from`.
* `packages/debate_core/src/debate_core/application/holdout_sitting.py` (new): the sitting's rules.
* `packages/debate_core/src/debate_core/application/coach_sample_relabel.py`: `rewritten_cells`.
* `packages/debate_core/src/debate_core/application/landscape_model_evaluation.py`: `break_down`'s refusal,
  `check_sample`'s flag, `evaluate_beside`, `sides_by_row`, `taxonomy_at`, `SampleFiles`, `SamplesBeside`.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: the `--holdout-*` options and refusals, and
  `--check-sample`'s `holdout`.
* `scripts/compare_local_classifier.py`: `holdout-sample`; the first sample's glob leaves out `-holdout-`.
* `scripts/label_holdout_sample.py` (new): the sitting.
* `packages/debate_core/src/debate_core/arguments/landscape/holdout_scan.py` (new): the holdout's own texts and
  their hits; `LandscapeModelEvaluationService.holdout_scan_hits`; `--holdout-scan-hits` and
  `HOLDOUT_HITS_TERMINAL_ONLY` in `debate_cli/commands/landscape.py` (the third ruling).
* Tests: the five new files above, `test_holdout_scan.py`, and one smoke test.
* `docs/runbooks/landscape-model-evaluation-record.md`: the held-out section (the draw, the copy, the two
  sittings, the ruled record run, and step 7, the holdout's own scan hits).
* `docs/data/landscape-model-evaluation.md`: the held-out sample as ruled, with its own stratum weights, and its
  snapshot and parser beside the scores to come.
* This report.

## Deviations from the spec

All three were accepted in the PM's second ruling of 2026-11-14. The PM adds the paths to the spec's
`constraints.packages` in the next batch:

* **`packages/debate_cli/src`.** The `--holdout-*` options and their refusals are in
  `debate_cli/commands/landscape.py`, a thin adapter over the service.
* **`tests/scripts`.** The draw's command is tested beside the first sample's, in
  `tests/scripts/test_holdout_sample_script.py`.
* **`tests/smoke`.** One smoke test is added for the new evaluate surface. `plan_specs/README.md` asks for one
  for a changed CLI surface, and the spec had no smoke node.

The third ruling's listing is in the same two paths (`packages/debate_cli/src` and `packages/debate_core`), so it
adds no path. No other change of scope.

## Decisions and assumptions

* The interval method is Wilson's, because it reproduces the record's two intervals.
* The forecast counted share (0.633) is 1.3.1's, since the holdout is measured on 1.3.1.
* **The exclusions come before the strata** (confirmed, ruling (a)). Excluded cards are removed first, and `coach_sample()`'s rule, its
  threshold, median cut and populations included, runs on the eligible cards. So the holdout's weights stand
  for the cards it could be drawn from. The alternative was to cut the strata on every unplaced card and draw
  only from the eligible ones. That would weight some cells by cards that could never be drawn.
* **One seed for the split, the solver and the draw**, as `sample` uses one: 20261114 trains the proxy as
  well, so the holdout's threshold is its own.
* **The bar reads the holdout** (confirmed, ruling (b)) when both samples are evaluated (`bar_reads_sample`), since the spec reads the
  bar as met only on a sample held out from tuning. The first sample is reported beside it, and its scans and
  stops count toward the exit code.
* **The draw writes the holdout CSV's sidecar itself** (confirmed, ruling (c)), through the t58 one-time step, since nothing has
  sat on the file yet.
* **A first-sample card counts as missing** when the reading does not hold it, as well as when the occurrence
  table has no row for it. Either way its copies cannot be shown absent.
* **In the sitting, a label typed without a second label clears the card's second label**, so what is typed
  is what is written. In a fresh holdout row there is none to clear.

## Operator follow-ups

In order, every block in [the runbook's held-out section](../runbooks/landscape-model-evaluation-record.md#the-held-out-sample-the-draw-and-the-coachs-two-sittings-v1-e32-t50),
from this worktree until it merges:

1. the draw as a dry run, pasting back its counts;
2. the draw;
3. the labels-file copy, the coach's first sitting (rows 1 to 60) with `--check-sample`, and the copy again;
4. the copy, the second sitting (rows 61 to 120, then the first sample's rows 16, 33 and 57) with both
   `--check-sample`s, and the copy again;
5. on one day after both sittings, not a Wednesday: the ruled record run (step 6), on `deep_audit` then
   `high_volume`, then the replay side by side on each, sending the PM the JSON objects only;
6. step 7: the holdout's own `high_volume` scan hits, first piped (the counts are pasted back), then in the
   terminal for the operator's eyes. Only the verdicts come back, by hit number.

Steps 1 to 7 are done (below).

**Step 1, the dry run (the operator's, 2026-11-13, before the draw), as pasted: counts only.** It passed every condition in
the runbook: version `2026.10.27-docx-7`, 120 drawn, no `STOP`, and no first-sample card without an
occurrence row.

* Read 3,869 source entries, 3,825 parsed, all 3,825 on `policy-2026-27-nhi`.
* Measured against the first sample's 60 cards: 60 documents, 57 clusters. Three first-sample cards share a
  cluster with another first-sample card: the first sample kept one card per document but not one per
  cluster.
* 55,531 candidates. Kept out by rule (the rules overlap):

  | Rule | Cards kept out |
  |---|---|
  | In a first-sample card's cluster | 2,552 |
  | With a first-sample card's exact fingerprint | 1,797 |
  | Read alike to a first-sample card | 636 |
  | From a first-sample document | 1,128 |
  | With no occurrence row | 0 |
  | Kept out by any rule | 3,628 |

  That leaves 51,903 eligible.
* Drew 120 cards from 120 documents, seed 20261114. 3,640 eligible cards share a cluster with a drawn card and
  were not drawn.

  | Stratum | Drawn | Eligible | Drawn by kind |
  |---|---|---|---|
  | At or above the threshold | 60 of 60 | 10,284 | advantage, aff, cp, da, k and t, 10 each |
  | Just below | 40 of 40 | 20,811 | advantage, aff, cp, da and k 6 each; t and theory 5 each |
  | Far below | 20 of 20 | 20,808 | advantage, aff, cp, da, k and t 3 each; theory 2 |

* Runtime 113.5 s.
* One thing for the PM to note, not a stop: the 55,531 candidates at 2026-11-03 are fewer than the 56,661
  unplaced cards the first sample's strata counted at 2026-10-20, though the snapshot is later. The taxonomy
  (now 1.5.1) and the coach's overrides have changed since, and either can place cards that were unplaced.
  The session did not measure which.

**Step 2, the draw (the operator's, 2026-11-13; its files are stamped 23:04 local time), as pasted.** Every count is the dry run's, line for line.
It wrote its three new files and nothing else, in 126.7 s:

* the feature table, `policy-2026-27-nhi-holdout-2026-11-03-features.jsonl`;
* the rows file, marked a holdout, `policy-2026-27-nhi-holdout-2026-11-03-sample.jsonl`;
* the coach's CSV, `policy-2026-27-nhi-holdout-sample-labelled.csv`, with SHA-256
  `45c5e6ff4175b2ac039b208bbd4323e061b14eaeeb5649c5ca37e3ff1b4ab09f` recorded beside it.

`shasum -a 256 -c` read the sidecar as `OK`, and the CSV is read-only.

**Step 4, the coach's first sitting (the operator's, 2026-11-14), as pasted: counts only.** Holdout rows 1
to 60. The sitting wrote once, at the end. It first kept the file it replaced as
`policy-2026-27-nhi-holdout-sample-labelled.before-sitting-2026-11-14-2112.csv`, then wrote the file and its
sidecar. The new SHA-256 is `ea5f586bb88aac2b9b59ffea939485b38049f1663d5b57f7c14ab1446b55fd34`.

* `Done.` line: 60 cards; 56 labelled (10 with a second label), 4 unsure, 0 left blank.
* `--check-sample`: `"holdout": true`, taxonomy 1.5.1, snapshot 2026-11-03, `labelled` 56, the same count as
  the `Done.` line, which is the runbook's success condition.

  | Label kind | Rows |
  |---|---|
  | advantage | 14 |
  | cp | 7 |
  | da | 12 |
  | k | 9 |
  | t | 10 |
  | none | 4 |

  By stance: 44 read and 8 answer, which with the 4 `none` makes 56. The 10 second labels are 8 advantage
  and 2 da.
* No row was labelled `aff` or `theory`. The draw drew 19 `aff` and 7 `theory` cards across all 120 rows by
  the proxy model's kind, but the sample's order mixes the strata, so these 60 rows are not a stratum. The
  session draws no conclusion from it before the second sitting.

**Step 3 after the first sitting (the operator's, 2026-11-14), as pasted.** The copies are stamped
`2026-11-14-212026`, eight minutes after the sitting's write at 21:12. There are four digest lines and no
`STOP`, and each copy's digest equals its file's:

* the first sample's CSV, `553374704519fd29f13a43e279a08537b28c87fbfc58372be845bc0de2b0a922`: the digest of
  the coach's labels of 2026-11-06 that t58 recorded, so the first sitting left the first sample untouched;
* the holdout's CSV, `ea5f586bb88aac2b9b59ffea939485b38049f1663d5b57f7c14ab1446b55fd34`: the digest the
  sitting printed.

**The step 3 copy before the first sitting** was not pasted back, but it was taken: the session read only the
digests of the copies in the operator's folder. They are stamped `2026-11-13-230713`, three minutes after the
draw wrote its files at 23:04. The holdout copy is `45c5e6ff…`, the drawn file, and the first sample's is
`553374704519…`.

**Step 5, the coach's second sitting (the operator's, 2026-11-14), as pasted: counts only.** This covered
holdout rows 61 to 120, then the first sample's rows 16, 33 and 57. Step 3 had run first; the session read
the copies' digests, stamped `2026-11-14-212122`: `ea5f586b…` for the holdout and `553374704519…` for the
first sample.

* `Done.` line: 60 cards; 55 labelled (22 with a second label), 5 unsure, 0 left blank.
* `The first sample's rows: 1 written, 2 answered side.` The side-rule line names rows 33 and 57.
* The holdout's `--check-sample` gives `"holdout": true`, taxonomy 1.5.1 and snapshot 2026-11-03.
  `labelled` is 111, which is 56 plus 55. The other 9 of the 120 rows are unsure (4 and 5). No row is blank.

  | Label kind | Rows |
  |---|---|
  | advantage | 28 |
  | aff | 1 |
  | cp | 19 |
  | da | 17 |
  | k | 22 |
  | t | 20 |
  | none | 4 |

  By stance: 82 read and 25 answer, which with the 4 `none` makes 111. **32 of the 111 rows have a second
  label** (advantage 22, cp 4, da 5, k 1), against 2 of the first sample's 47. A second label lets either
  label count as right, so the holdout's scores and the first sample's are not scored under the same
  leniency. The session reports this and draws no conclusion from it. No row is labelled `theory`.
* The first sample's `--check-sample` gives t58's counts for the 2026-11-06 labels: `labelled` 47,
  advantage 16, aff 1, cp 7, da 5, k 9, none 2 and t 7, with 9 answers and 36 reads. It also shows 2 second
  labels, both advantage. **Its file is byte for byte the same as before the sitting.** Its digest is still
  `553374704519…`, the same as the sitting's dated copy (`before-sitting-2026-11-14-2203`) and the step 3 copy.
* **The holdout's file after both sittings** has SHA-256
  `7d1ada7bc00942e536d05c95766b063b2e5353f87d7cd8e2544b5977992c349e`, the digest its sidecar records. The
  sitting kept the file it replaced as `before-sitting-2026-11-14-2203`, which is `ea5f586b…`.

**Two faults in the side rows, both found in this sitting. Neither changed a label.**

1. **Rows 16 and 57 no longer conflicted with the side rule.** I chose the three rows from t49's report.
   That report read the labels from before the coach's sitting of 2026-11-06, which changed both rows:
   * row 16 became `at:inequality-advantage`, so it answers the position, as a negative file would;
   * row 57 became `kritikal-aff`, an affirmative position in a file disclosed on the affirmative.

   Only row 33, `costs-advantage` in a file disclosed only on the negative, still conflicted.
   `SIDE_RULE_ROWS` names the rows, and the sitting never checks them against the current labels. On row 57
   the prompt offered no way to say "already consistent", so the coach answered `side`, on the session's
   advice. **For the PM's follow-up on t46's other-side rule, count row 33 only.** Row 57's `side` means
   the label already agrees with its file's side.
2. **"1 written" counts an answer that matches the current value.** Row 16 was "written", yet no byte of
   the first sample changed. The coach's answer matched the row's current label. The sitting records a
   cell for every `at:` or `also` answer without comparing it with the cell's current value, so it rewrote
   the file, its dated copy and its sidecar with the same bytes.

Neither fault needs code for this task now: the sittings are done, and the labels are the coach's. Both are
in Follow-up work.

**Step 3 after the second sitting** was not pasted back, but it was taken: the session read only the
digests of the copies, stamped `2026-11-14-224901`. They are `553374704519…` for the first sample and
`7d1ada7b…` for the holdout, the files as the sitting left them.

**Step 6, the ruled record run (the operator's, 2026-11-14, a Saturday, after both sittings), as pasted.**
It ran both routes on the same day, as the ruling's "on one day" allows (its reason: both routes on one day
stay under dev's $2). Each block's checks passed, and the two `--check-sample`s matched step 5's. All four
recordings exit 1 with `EVALUATION_BELOW_BAR`, and none was interrupted. All four were taken at prompt 1.3.1
and taxonomy 1.5.1.

| Route | Sample | Calls | Counted | Correct | Accuracy (95%) | Coverage | Refused | Below threshold | Scans |
|---|---|---|---|---|---|---|---|---|---|
| `deep_audit` | holdout, 111 | 7 | 77 | 44 | 0.571 (0.46 to 0.68) | 0.694 | 7 (`NO_POSITION` 6, `ECHOES_EVIDENCE` 1) | 27 | clean |
| `deep_audit` | first, 47 | 5 | 21 | 14 | 0.667 (0.45 to 0.83) | 0.447 | 20 (`BATCH_REFUSED`) | 6 | clean |
| `high_volume` | holdout, 111 | 6 | 82 | 39 | 0.476 (0.37 to 0.58) | 0.739 | 17 (`NO_POSITION`) | 12 | **not clean** |
| `high_volume` | first, 47 | 3 | 35 | 23 | 0.657 (0.49 to 0.79) | 0.745 | 5 (`NO_POSITION`) | 7 | **not clean** |

The intervals are Wilson intervals, computed by the session from the counts. The pipeline equals the model
alone on the holdout: the headings placed none of its cards. On the first sample, the headings placed 4.
On each route the holdout placed 3 of its 4 cards labelled `none`.

* **The bar is not met on either route.** Even the upper ends of the holdout's intervals, 0.68 and 0.58, are
  below 0.85, so the hold on live model runs stands. The holdout counted 77 cards on `deep_audit`, against
  the "about 76" expected from the first sample's rate.
* **The tokens and cost.** `deep_audit`: 113,390 in and 15,918 out. `high_volume`: 125,910 in and 14,557 out.
  At `config/model_pricing.yaml`'s prices, that is about $0.58 on Claude Sonnet 4.6 ($3 and $15 per million)
  and $0.20 on Claude Haiku 4.5 ($1 and $5), **about $0.78 in all**. That is inside the ruled $0.95 and
  dev's $2.00 for the day.
* **The evidence guard held.** One holdout answer on `deep_audit` was refused as `ECHOES_EVIDENCE`, so no
  quoted text was counted.

**Three things for the PM** (ruled on 2026-11-14: [the third ruling](#the-pms-third-ruling-2026-11-14)):

1. **The first sample on `deep_audit` lost a batch of 20.** The terminal printed "structured output failed
   validation" three times, and the 5 calls fit 3 batches (20, 20 and 7) and 2 repairs. One batch's repair
   succeeded and the other's failed, so its 20 cards were refused as `BATCH_REFUSED`. Coverage is 0.447, and
   its 14 of 21 cannot be compared with t55's 26 of 38 on the same 47. A recording of those 20 again is a
   live call outside the ruling. The session did not ask for it.

   The holdout on `deep_audit` printed the message once and lost no batch: its 7 calls are 6 batches and 1
   repair. Neither `high_volume` recording printed it.
2. **One `high_volume` cassette text is unclean, and it is the holdout's.** The cassette scan does not read
   one sample's cassettes. `scanned_cassettes` reads every cassette of the route's classify prompt at
   1.3.1, and the repair scan reads every repair at 1.3.1 filed under hspolicy26. This is the scan's
   existing scope (`v1-e32-t39`, `v1-e32-t40`), and this task did not change it. The counts show it:

   * **The holdout's recording ran first.** It scanned 6 texts, its own 6 batches; 5 were set aside and 1
     was left.
   * **The first sample's recording ran second.** It scanned 9 texts, those 6 and its own 3; 8 were set
     aside and still only 1 was left.

   So the first sample's three texts are clean, and the one text left is among the holdout's six. On
   `deep_audit`, 9 and then 12 texts were scanned, and 3 and then 5 repairs: the earlier 1.3.1 recording's
   3 batches and 2 repairs, plus this run's. All of those are clean.

   The prompt-input scans are clean on both routes, so the word is most likely in the model's answer, not
   in a card sent. The session has not seen where it is. 1.2.0's `high_volume` cassettes also had hits,
   which the operator judged ordinary words on 2026-11-05. The cassettes stay local in `model-cassettes/`,
   and nothing is published.
   * **The runbook's step 5 is not to be run on `high_volume` before the PM rules.** It is the first
     sample's terminal listing, but it reads the same cassettes, so it would list the holdout's hit with the
     card words around it. That would be a holdout card shown by the back door.
   * **No command lists the holdout's hits as a holdout.** `--breakdown` refuses a holdout, as ruled. This
     gap is the session's, from its build. The PM can choose:
     * a terminal-only listing of the holdout's scan hits, with no outcome, row or answer id, for the
       operator to judge by hit number;
     * to keep the `high_volume` holdout cassettes unjudged;
     * or to delete them. The score is below the bar either way.
   * **In the side-by-side JSON, the two samples' `scan` objects are the same object**, for the same reason.
     The holdout's `scan` there is not the holdout's alone.
3. **The second labels.** 32 of the holdout's 111 rows have one (step 5), so it is scored more leniently
   than the first sample. The bar is not met even with that leniency.

**Step 6's replays side by side (the operator's, 2026-11-14), as pasted.** These make no call. Both exit 1
with `EVALUATION_BELOW_BAR` and `bar_reads_sample: "holdout"`.

* Each sample's counts, scores and tokens equal its recording's, number for number, on both routes.
* `drawn_from` gives the holdout's snapshot 2026-11-03, parser and version `2026.10.27-docx-7`, and
  `card-fingerprint-v4`.
* The `deep_audit` replay printed "structured output failed validation" four times: the three recorded
  failures of the first sample and the one of the holdout, replayed.
* The `high_volume` replay's message is the scan's, as in the recordings.
* Both samples' `scan` objects are the same, as finding 2 explains.

The JSON objects went to the PM with the findings above. The PM ruled on 2026-11-14
([the third ruling](#the-pms-third-ruling-2026-11-14)). The listing is built, and step 7 runs it.

**Step 7, the holdout's own `high_volume` scan hits (the operator's, 2026-11-14).** The piped counts, as
pasted: 6 input batches, 6 cassettes and 0 repair cassettes. That is one cassette per batch, as the
recording's 6 calls predict. There are 44 scan hits, and 1 carries no mark that sets it aside; the other 43
are set aside by a mark. The operator then read the hits in the terminal and reported that none of their
words names a team, a school or a tournament. The one hit with no mark is **hit 12: an ordinary word**, the
operator's verdict by number, with no word given. So all 44 hits are ordinary words, the holdout's
`high_volume` cassettes are kept, and nothing is published. The `high_volume` scan was unclean only by its
marks: no name was in those cassettes. The scores stand as recorded. `EVALUATION_BELOW_BAR` holds on the
accuracy alone, on both routes.

**The affected set did not finish locally.** `uv run scripts/affected_tests.py --run --slow` selects 157 files,
5,298 tests. Within the 115-second cap it reached 65% with two failures:
`test_container_factories.py::test_importing_the_container_or_the_app_loads_no_integration`, for the container
and the app. Both were caused by scikit-learn loading through the evaluation's import of the draw, and both
were fixed by `holdout_mark.py` (`a550a5e`); both pass now. Two bounded halves then ran 1,949 of 1,991 and
3,273 of 3,305 with no other failure. The other 72, and the slow tier, are left to the pull request's CI, as
the PM ruled under working agreement 10.
ruff, ruff format, pyright (whole project), lint-imports, the thin-handler check, the command-block check,
the docs index and the link check pass.

## Follow-up work

* The LD sample pair, as ruled (the PM files it).
* A follow-up on t46's other-side rule for row 33, filed by the PM. The sitting's last line names rows 33
  and 57, but row 57's label already agrees with its file's side ([step 5](#operator-follow-ups)).
* The side rows' two faults, if the sitting is used again: check each side row against its current label
  before showing it, and count an answer as written only when it changes a cell.
* `v1-e32-t61` (the labels-file copy built in), until which the copy block stays manual.
* The scan's scope beside a holdout. In the side-by-side JSON both samples' `scan` objects are the route's
  whole cassette directory at the prompt version, so the holdout's `scan` is not its own. A follow-up could
  scope each sample's scan to its own texts, as `holdout_scan.own_cassettes` does for the listing.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

Accepted. ac1, ac2, ac3 and the node pass, and the Goal is `Succeeded`.

* **ac3 is recorded by the PM here**, from the operator's run as reported. The draw ran on
  2026-11-13, and the two sittings and `--check-sample` on 2026-11-14: 111 of 120 labelled, 9
  unsure. Before `scripts/task pr`, the session sets the spec's phase to `Succeeded` and commits it,
  with no other change.
* **The result is the one the holdout exists to give.** On cards never used for tuning, prompt 1.3.1
  scored 0.571 on deep_audit (44 of 77; 95%: 0.46 to 0.68) and 0.476 on high_volume (39 of 82; 0.37
  to 0.58) against the 0.85 bar. The first sample's 0.75 was flattered by tuning. The product owner
  decided the V1 scope from it the same day: v1-e32-t07 is cancelled, and v1-e32-t64, t65 and t66
  are filed. The record run cost about $0.78, inside the ruled authorization.
* **Built as ruled.**
  * The exclusions are by evidence: cluster, fingerprint and document, measured against all 60
    drawn.
  * The holdout is read beside the first sample and never feeds tuning, and the bar reads the
    holdout.
  * Rulings 1 (a) and 2 (a): the first sample's refused batch is left as it is, and the terminal-only
    scan-hit listing exists. Through it the operator judged all 44 hits ordinary words by number,
    hit 12 included.
  * The high_volume holdout cassettes are kept, and nothing is published.
* **The evidence:**
  * the red runs against refuse-nothing skeletons;
  * for the listing, 12 of 13 new tests failed at an assertion;
  * 11 mutants, of which 10 were caught and the survivor gained its catching test.
* **Deviations accepted** as in the second ruling. The PM's batch of 2026-11-14 adds `debate_cli`,
  `tests/scripts` and `tests/smoke` to the packages. If the two pull requests meet on the spec,
  `scripts/task sync`.
* **The affected set** goes to `ci` under agreement 10.
* **Follow-ups:**
  1. The LD sample pair, row 33's follow-up on t46's other-side rule, the side rows' two faults and
     scoping each sample's scan to its own cassettes go on the PM's V1.x list. Each matters only if
     v1-e32-t66 proceeds.
  2. `v1-e32-t61` stays a ready p3. Until it is built, the copy block stays manual.

`scripts/task pr`
