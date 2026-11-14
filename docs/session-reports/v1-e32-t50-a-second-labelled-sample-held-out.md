# Session report: v1-e32-t50-a-second-labelled-sample-held-out

| | |
|---|---|
| Task | `v1-e32-t50-a-second-labelled-sample-held-out` — A second labelled sample, held out from tuning, before the bar is read as met |
| Spec | [`plan_specs/v1/e32-argument-landscape/t50-a-second-labelled-sample-held-out.yaml`](../../plan_specs/v1/e32-argument-landscape/t50-a-second-labelled-sample-held-out.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t50-a-second-labelled-sample-held-out` |
| Session status | PARTIAL, ready for the PM's verdict on a partial merge: built and tested as ruled; ac3 (the draw, both sittings, `--check-sample`) and the ruled record run are the operator's <!-- COMPLETE / PARTIAL / BLOCKED --> |

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

The tests are on invented cards and stores. They were run red against a refuse-nothing skeleton (39 of 52
failing, each at an assertion) and catch all 13 mutants, the PM's included: a holdout card sharing a cluster
with a first-sample card in another team's file. The node's criterion passes (35 tests).

**What is left is the operator's, so the Goal stays `InProgress`.** ac3 (the draw, the coach's two sittings
and `--check-sample` on the real store) and the record run are both run from the runbook's
[held-out section](../runbooks/landscape-model-evaluation-record.md#the-held-out-sample-the-draw-and-the-coachs-two-sittings-v1-e32-t50).
The PM's second ruling of 2026-11-14 ([below](#the-pms-second-ruling-2026-11-14)) allows the record run as a
narrow exception to the hold on live runs. It runs both routes on one day after both sittings, not on a
Wednesday, for about $0.95. It also confirms the three decisions and accepts the deviations, and leaves the
affected set to the pull request's CI. This report is ready for the PM's verdict on a partial merge.

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

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-second-labelled-sample-held-out` (Holdout sample) | DONE | Built as ruled; its criterion passes (below) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the second sample's size, from the interval wanted at 0.85 and the coach's time, ruled on by the PM | PASS | The PM's ruling of 2026-11-14: 120 drawn, 60/40/20, Wilson ([above](#the-pms-ruling-2026-11-14)) |
| ac2: drawn by the strata and seed rule with no card from the first, by tests on invented cards shown failing first, and the evaluation reads it as a holdout beside the first | PASS (code and tests); the real draw is the operator's | Red against `4f8c81e`: 39 of 52 failed, each at an assertion. Green: 52 of 52, plus the smoke check. 13 mutants caught, the PM's by 5 tests. `evaluate_beside` and `--holdout-*` read it beside the first. |
| ac3: the coach labels it in a sitting and `--check-sample` reads it (operator, recorded by the PM) | NOT RUN | Operator: the runbook's held-out section, steps 1 to 5; then the ruled record run, step 6 |
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
* Tests: the five new files above and one smoke test.
* `docs/runbooks/landscape-model-evaluation-record.md`: the held-out section (the draw, the copy, the two
  sittings, and the ruled record run).
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

No other change of scope.

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
   `high_volume`, then the replay side by side on each, sending the PM the JSON objects only.

**Step 1, the dry run (the operator's, 2026-11-14), as pasted: counts only.** It passed every condition in
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
* After the second sitting: a follow-up on t46's other-side rule for the rows answered `side`, filed by the PM
  from the sitting's last line.
* `v1-e32-t61` (the labels-file copy built in), until which the copy block stays manual.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
