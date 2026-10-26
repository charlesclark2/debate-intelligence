# Session report: v1-e32-t21-local-classifier-comparison

| | |
|---|---|
| Task | `v1-e32-t21-local-classifier-comparison` — A local text classifier for the cards headings cannot place, compared before anything is wired |
| Spec | [`plan_specs/v1/e32-argument-landscape/t21-local-classifier-comparison.yaml`](../../plan_specs/v1/e32-argument-landscape/t21-local-classifier-comparison.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t21-local-classifier-comparison` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task built the local classifier the PM specified, measured it on hspolicy26 through 2026-10-20, and
stops here for review, as asked. The model is TF-IDF over word 1- and 2-grams of a card's tag and normalized
headings, with scikit-learn's logistic regression. Nothing is wired: the report, the matcher and the review
queue are unchanged.

**The model as specified cannot be judged on its held-out tenth.** Its labels come from the
headings it reads. It learns the alias table and scores 97.1% held-out precision. On that measure 90% is
reached at confidence 0, so it would "place" 99.5% of the 56,928 unplaced cards. That number says
nothing, because no heading over an unplaced card is an alias.

So I also measured a **proxy**, which I propose here and the PM may discard. It is the same model,
trained and scored without the headings that place a card on their own, which is how every unplaced
card looks:

* **Held out:** 68.4% precision overall, and 90.2% at confidence 0.5 or above. At 0.5 it would place
  12,752 unplaced cards (22.4%).
* **Weighed to the unplaced cards' mix:** held-out precision is 82.7% at 0.5 on cards unlike any training
  card, and the unplaced cards are mostly of that sort. Weighed to their mix, the estimate is 85.2% at
  0.5. It first reaches 90% at 0.6, where the proxy would place **9,749 unplaced cards (17.1%)**.

**Recommendation: use it now only to order the review queue, and decide on wiring from the coach's
labels.** The coach-labelled sample is the one real test, and it is an operator step that has not run.
So the Goal stays **InProgress**, with ac2's coach-sample accuracy NOT RUN. The sample is ready: 60
unplaced cards, 30 of them at or above the proxy's threshold ([the block](#operator-follow-ups)).

What the PM should look at first:

* [the two models side by side](#the-numbers-hspolicy26-through-2026-10-20);
* [the recommendation and the bar for wiring](#recommendation);
* [the questions](#questions-for-the-pm).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `local-classifier`: Local classifier comparison | Built, measured; the coach's labels outstanding | Node criterion passes. Goal ac1 passes; ac2 passes but for the coach-labelled sample (operator) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on synthetic fixtures, training and scoring are deterministic for a fixed seed | PASS | `test_training_and_scoring_are_the_same_for_a_seed_whatever_order_the_cards_arrive_in`: two runs, the second on shuffled cards, give equal comparisons, vocabularies and every prediction to the last bit. `test_the_coach_sample_is_the_same_for_a_seed` does the same with fresh comparisons and reversed cards. Also on the real store: two `compare` runs printed identical counts ([below](#how-it-was-read)) |
| ac1: no school, team code or name is a feature | PASS | `test_no_school_team_code_or_name_is_a_feature`, `test_no_school_team_code_tournament_or_cite_reaches_a_cards_features`, `test_another_teams_code_alone_in_a_tag_is_taken_out`, `test_a_cards_tag_loses_its_teams_names_and_the_caselists_schools`. A debater's name planted in one team's tags is in its tokens and never in the vocabulary. With a one-team rule it would be (`test_only_the_team_rule_keeps_one_teams_words_out`) |
| ac1: writes nothing outside the data directory | PASS | `test_the_four_commands_write_only_under_the_data_directory`: it runs `features`, `compare`, `sample` and `score-sample` from another working directory with `HOME` moved, snapshots every file under the test's root before and after, and names the five files written under `<data dir>/landscape/local-classifier/<caselist>/` |
| ac1: tests shown failing first | PASS | [Red runs](#checks-shown-failing-for-their-reason): 23 of 27 failed against a refuse-nothing skeleton, each at its own assertion, and the 4 that passed are controls. The script tests failed on their first run for a real leak. Each later addition was shown failing against a mutant |
| ac2: on hspolicy26 (read-only), held-out precision by position and confidence | PASS | `compare` on the real store, for both models: precision and recall by kind and by position, precision by confidence band and at or above each grid point ([below](#the-numbers-hspolicy26-through-2026-10-20)) |
| ac2: the coach-labelled sample's accuracy | NOT RUN | No session can close it: it needs the coach's labels. v1-e32-t07's 60 items do not exist, so the sample is proposed here ([the proposal](#the-coach-sample-proposed)). The operator writes it with the first block and scores it with the second ([Operator follow-ups](#operator-follow-ups)) |
| ac2: the unplaced cards it would place at 90% held-out precision | PASS | Specified model: 56,661 of 56,928 at confidence 0. Proxy: 12,752 at 0.5, or 9,749 at 0.6 by the mix-weighed estimate. Both by kind ([below](#what-it-would-place)) |
| ac2: sent to the PM with a recommendation | PASS | [Recommendation](#recommendation), in this report |
| Node `local-classifier`: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape -q` → **772 passed** in 4.70 s (27 of them this task's) |

## The numbers (hspolicy26, through 2026-10-20)

### How it was read

* **Guards.** Every run was read-only for the stores and started from the script's own checks: no
  `DEBATE_*` variable set and no `caselist pull` running. Both were clear on every run.
* **Time limits.** The interpreter ran under `perl -e 'alarm 115'`. No pool and no worker process is
  started: after each run, `pgrep -fl compare_local_classifier` found nothing.
* **Load.** The load average was 5 to 11 on 11 cores.
* **Runtimes.** `features` took 47.5 s, and 40.6 s to rebuild. `compare` trains both models and took 45
  to 53 s over four runs. The last two printed identical counts.
* **Output.** The script prints counts and position ids only. Its files live under
  `~/.debate-research/dev/landscape/local-classifier/hspolicy26/`:
  * the feature table, which holds normalized tags and headings, keyed team digests and no team;
  * the counts as JSON.
* **The table, rebuilt once.** The first build, a timing probe, held the teams' identities, school and
  code. The rebuild replaced it, and none of its lines holds a `/`, which an identity has.
* **The reading** is t02's (`read_seed_sources`) and t02's matcher, with no cache and no write: 3,825
  on-topic sources, of which 3,806 have a card.

| Cards (taxonomy 1.2.0, review threshold 0.6) | Count | Share |
|---|---|---|
| All | 126,681 | |
| **Labelled** (ALIAS, INHERITED, OVERRIDE, TAG_KEYWORD at or above 0.6) | **63,494** | 50.1% |
| ALIAS | 39,302 | 31.0% |
| INHERITED | 21,303 | 16.8% |
| OVERRIDE | 2,803 | 2.2% |
| TAG_KEYWORD | 86 | 0.1% |
| BELOW_THRESHOLD (tag keyword alone, 0.5) | 1,371 | 1.1% |
| OVERRIDE_NO_POSITION | 4,888 | 3.9% |
| **UNPLACED** | **56,928** | **44.9%** |

63,494 is the count t05, t10 and t14 counted, to the card.

### The split and the two models

* **Split:** 3,806 documents, ordered by a seeded digest. The first 381 are held out, holding 6,369
  labelled cards, and no document is on both sides.
* **Specified:** a card's tag and every heading over it. It is trained on 57,125 labelled cards, with 84
  positions and 30,493 features.
* **Proxy:** a card's tag and the headings that place nothing on their own (`solvency`, `link`,
  `framing`). It is trained on 56,922 cards (203 have no feature left), with 84 positions and 30,303
  features.
* **Features:** a token is one only when cards of three or more teams carry it.

| Held out | Specified | Proxy |
|---|---|---|
| Labelled cards; predicted | 6,369; 6,369 | 6,369; 6,348 |
| Correct (precision; recall) | 6,186 (97.1%; 97.1%) | 4,341 (68.4%; 68.2%) |
| Of those predicted, exactly like a training card: correct | 2,945: 2,921 (99.2%) | 3,547: 2,889 (81.4%) |
| The rest: correct | 3,424: 3,265 (95.4%) | 2,801: 1,452 (51.8%) |

**By kind** (held out, predicted, correct, precision, recall; "right kind" is the share of predictions
whose label is a position of the same kind):

| Kind | Specified | Proxy | Proxy, right kind |
|---|---|---|---|
| advantage | 3,528, 3,546, 3,440, 97.0%, 97.5% | 3,528, 3,519, 2,282, **64.8%**, 64.7% | 90.3% |
| aff | 271, 268, 257, 95.9%, 94.8% | 271, 267, 218, 81.6%, 80.4% | 82.4% |
| cp | 443, 446, 438, 98.2%, 98.9% | 443, 367, 293, 79.8%, 66.1% | 88.0% |
| da | 1,708, 1,697, 1,652, 97.3%, 96.7% | 1,708, 1,896, 1,322, 69.7%, 77.4% | 79.8% |
| k | 301, 299, 289, 96.7%, 96.0% | 301, 223, 174, 78.0%, 57.8% | 87.4% |
| t | 83, 82, 80, 97.6%, 96.4% | 83, 54, 33, 61.1%, 39.8% | 88.9% |
| theory | 35, 31, 30, 96.8%, 85.7% | 35, 22, 19, 86.4%, 54.3% | 86.4% |

**By position**, the proxy's largest and its outliers (held out, predicted, correct, precision, recall).
The 74 positions with held-out cards are in the JSON; `compare` prints the 35 with 20 or more.

| Position | Proxy |
|---|---|
| midterms-da | 897, **1,157**, 862, 74.5%, 96.1% |
| costs-advantage | 642, **1,083**, 535, **49.4%**, 83.3% |
| economy-advantage | 582, 392, 319, 81.4%, 54.8% |
| disease-advantage | 360, 390, 263, 67.4%, 73.1% |
| growth-advantage | 360, 291, 218, 74.9%, 60.6% |
| inequality-advantage | 332, 372, 247, 66.4%, 74.4% |
| coverage-advantage | 283, 299, 174, 58.2%, 61.5% |
| states-cp | 270, 278, 218, 78.4%, 80.7% |
| single-payer-aff | 260, 259, 210, 81.1%, 80.8% |
| access-advantage | 238, 199, 179, 89.9%, 75.2% |
| cap-k | 198, 194, 149, 76.8%, 75.3% |
| pharma-da | 159, **247**, 123, **49.8%**, 77.4% |
| economy-da | 128, 165, 70, **42.4%**, 54.7% |
| irs-da | 65, 55, 52, 94.5%, 80.0% |
| smokers-pic | 49, 28, 28, 100.0%, 57.1% |
| pharma-advantage | 24, 1, 0, 0.0%, 0.0% |
| biotech-advantage | 20, 0, 0, n/a, 0.0% |

The proxy pulls toward the largest positions. A tag alone says "midterms" or "costs" more often than
the headings did.

**By confidence band** (cards, correct, precision):

| Band | Specified | Proxy |
|---|---|---|
| 0.00 to 0.30 | 135, 91, 67.4% | 1,718, 546, 31.8% |
| 0.30 to 0.50 | 294, 237, 80.6% | 1,390, 873, 62.8% |
| 0.50 to 0.60 | 271, 240, 88.6% | 611, 448, 73.3% |
| 0.60 to 0.70 | 374, 348, 93.0% | 591, 513, 86.8% |
| 0.70 to 0.80 | 632, 619, 97.9% | 610, 560, 91.8% |
| 0.80 to 0.90 | 1,158, 1,149, 99.2% | 804, 781, 97.1% |
| 0.90 to 0.95 | 1,030, 1,029, 99.9% | 412, 409, 99.3% |
| 0.95 to 1.00 | 2,475, 2,473, 99.9% | 212, 211, 99.5% |

**At or above a confidence**, the proxy (cards, correct, precision). The second column is the same
over the held-out cards unlike any training card:

| Confidence | All held-out | Unlike any training card |
|---|---|---|
| 0.40 | 3,908, 3,385, 86.6% | 1,294, 1,003, 77.5% |
| 0.45 | 3,551, 3,147, 88.6% | 1,135, 913, 80.4% |
| **0.50** | 3,240, 2,922, **90.2%** | 1,009, 834, **82.7%** |
| 0.55 | 2,925, 2,701, 92.3% | 881, 759, 86.2% |
| **0.60** | 2,629, 2,474, 94.1% | 755, 677, **89.7%** |
| 0.65 | 2,335, 2,228, 95.4% | 646, 596, 92.3% |
| 0.70 | 2,038, 1,961, 96.2% | 553, 520, 94.0% |
| 0.80 | 1,428, 1,401, 98.1% | 372, 363, 97.6% |
| 0.90 | 624, 620, 99.4% | 172, 170, 98.8% |

**The confidence at 90% held-out precision**, the lowest grid point from which precision stays at 90%
or more (a point with under 50 cards above it is passed over):

* specified: **0.0**;
* proxy: **0.5**.

### What it would place

| Model and confidence | UNPLACED (56,928) | OVERRIDE_NO_POSITION (4,888) | BELOW_THRESHOLD (1,371) |
|---|---|---|---|
| Specified, at 0.0 | 56,661 (99.5%) | 4,888 (100%) | 1,371 (100%) |
| Proxy, at 0.5 | **12,752 (22.4%)** | 965 (19.7%) | 156 (11.4%) |
| Proxy, at 0.6 (the estimate's 90%) | **9,749 (17.1%)** | n/a | n/a |

By kind:

| Kind | Specified, 0.0 | Proxy, 0.5 | Proxy, 0.6 |
|---|---|---|---|
| advantage | 27,492 | 2,433 | 1,426 |
| aff | 4,150 | 1,185 | 881 |
| cp | 3,185 | 1,220 | 937 |
| da | 18,388 | 6,768 | 5,777 |
| k | 2,834 | 907 | 661 |
| t | 422 | 238 | 67 |
| theory | 190 | 1 | 0 |

* 267 unplaced cards have no feature either model knows, and neither places them.
* Only 156 unplaced cards have exactly the features of a training card under the specified model: no
  training card lacks an alias heading. Under the proxy 6,099 do, and 2,958 of them are at 0.5.

**The estimate.** Held-out precision differs sharply between the cards a training card matches and the
rest: for the proxy at 0.5, 93.6% against 82.7%. The unplaced cards it would place at 0.5 hold 2,958
of the first kind and 9,794 of the second, a different mix from the held-out set. At each confidence, the estimate weighs the
two held-out precisions by that mix (`estimate_precision`):

| Proxy, confidence | Unplaced cards placed | Of them like a training card | Estimated precision |
|---|---|---|---|
| 0.40 | 16,941 | 3,540 | 80.4% |
| 0.50 | 12,752 | 2,958 | 85.2% |
| 0.55 | 11,182 | 2,689 | 88.3% |
| **0.60** | **9,749** | 2,446 | **91.2%** |
| 0.70 | 7,386 | 2,056 | 94.9% |
| 0.80 | 5,476 | 1,635 | 97.8% |
| 0.90 | 3,244 | 1,012 | 99.1% |

The same estimate for the specified model is 95.4% at 0.0, and it is no better than its held-out
number. Its unmatched held-out cards still carry an alias heading, so neither measure can see what it
does without one.

It is an estimate, not a measure. It assumes an unplaced card is like a held-out card of the same
sort. Unplaced cards also include many that belong to no position (framing, theory blocks, overviews),
which every held-out card has by construction. The coach's labels are the measure.

### Why the specified model's held-out numbers say nothing about unplaced cards

* Every labelled card is labelled from the alias or override heading over it, and the specified
  model reads that heading. `h:states cp` is the label, and the model learns the alias table.
* No heading over an unplaced card places anything, so that heading is never there.
* The proxy reads exactly what the specified model reads on an unplaced card, and is trained to place
  cards from it.
* The two agree on 35 of the 60 sampled cards. On every other card at least one of them is wrong.

## The coach sample (proposed)

* **The 60 cards:**
  * drawn from the 56,661 unplaced cards the proxy predicts, at most one per document;
  * stratified by the proxy's confidence, since the specified model's threshold of 0 would put every
    card in one stratum.
* **The strata:**

  | Stratum | Share | Unplaced cards in it |
  |---|---|---|
  | at or above its held-out threshold (0.5): what wiring would place | 30 | 12,752 |
  | below 0.5, the upper half by confidence | 20 | 22,089 |
  | the lower half | 10 | 21,820 |

* **Kinds:** inside a stratum, the predicted kinds take turns, largest first, so each kind is measured.
  Drawn in memory on the real table, writing nothing:
  * top stratum: 5 each of advantage, aff, cp, da and k, 4 t and 1 theory (the only one there);
  * middle: 3 of each kind and 2 theory;
  * bottom: 2, 1, 1, 2, 2, 1 and 1.

  One stratum short of cards passes its share to the next, and what the last cannot take goes back.
* **Deterministic:** seed 21, the same 60 on every run.
* **The coach's file:** `<data dir>/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.csv`.
  * Its columns are `sample_row, tag, headings, position, note`.
  * The tag and headings are what the model read. The tag has the team's names, the caselist's schools
    and every team code taken out. A heading fewer than two teams use is shown as
    `[a heading one team used]`, as the review queue leaves one out.
  * There is no prediction, confidence, stratum, school, team code or path.
  * The rows are in a seeded order that hides the strata.
* **Beside it,** `…-coach-sample.jsonl` keeps each row's item id and both models' predictions, and
  each stratum's and cell's population: no text.
* **The coach fills `position`** with a position id (the ids the review queue's decisions use),
  `none` for a card that belongs to no position, or `unsure`. `none` counts as a wrong placement
  for both models. `unsure` and blank rows are not scored.
* **The score** gives, for each model:
  * accuracy overall, by stratum and by predicted kind;
  * accuracy on the cards at or above its own threshold;
  * the same two weighted over every unplaced card. Each labelled card stands for its cell: the
    stratum, and the kind the proxy predicts.

  A source a removal reaches after the sample is drawn is left out of the score, and the score names
  its rows.

## Recommendation

**Keep it for the review queue's ordering only, now, and decide on wiring from the coach's labels.**

* **The specified model should not be wired.** Its held-out precision measures the alias table. On
  unplaced cards it reads only what the proxy reads, but was fitted mostly to headings that are never
  there.
* **The proxy is promising but unproven.**
  * Held out, it places half the labelled cards at 90%, but those are mostly cards it has seen before.
  * Weighed to the unplaced cards' mix, it reaches 90% only from 0.6, for 9,749 cards (17.1%), mostly
    DAs (5,777).
  * Its errors cluster in the largest positions: midterms-da is predicted 1,157 times for 897 held-out
    cards, and costs-advantage reaches 49.4% precision.
  * Unplaced cards include cards that belong to no position, which no held-out card can show.
* **Ordering the review queue costs nothing and risks nothing.** A row whose cards the proxy places
  surely, under one position, is the coach's quickest decision.
* **The bar for wiring it later**, as `LOCAL_MODEL` behind review-queue rules, as the spec's later task
  describes:
  * at least **27 of the 30** top-stratum cards right;
  * a weighted precision at the chosen threshold of at least **90%**;
  * no kind under 4 of 5 in the top stratum.

  Below that bar, drop it as a placer and keep the ordering.
* **What I would not do:** add evidence text before the coach's labels say tags and headings fall
  short. It was not counted ([Decisions 10](#decisions-and-assumptions)).

## Checks shown failing for their reason

* **The red run** (working agreement 6, ac1). The 27 tests of `test_local_classifier.py` ran
  against a refuse-nothing skeleton. `make_skeleton.py`, a scratch script, swapped 11 bodies for the
  naive version:
  * tags keep their names;
  * no team rule;
  * an unseeded split by `random.random`;
  * every placement a label, the BELOW_THRESHOLD and coach-ruled ones included;
  * one token stream with no `h:`/`t:` fields;
  * the threshold at the first grid point;
  * one stratum, and the first 60 cards with no one-per-document rule;
  * the prediction written into the coach's file, and the tag into the sidecar;
  * any label accepted;
  * an unweighted score;
  * the mix ignored in the estimate, and the by-kind count at the held-out threshold.

  Result, `-n 0 -p no:randomly`: **23 failed, 4 passed**, each failure at its own assertion. Examples:
  * `local_classifier.py imports ['random']`;
  * `'maple grove …' == 's evidence proves deficit'`;
  * `('t:a', 't:b', 't:c') == ('t:a', 't:c')`;
  * `assert 0.0 == 0.6`;
  * `Counter({'at-…': 60}) == {…: 55}`.

  The 4 that pass are not checks of a protection:
  * the fixture's own counts;
  * the positive control that a debater's name is in one team's tags;
  * the characterization that the specified model scores perfectly on its own headings;
  * `__all__`.

  The real module was restored from a copy and its sha1 checked (`6eb59cc…`) before the green run.
* **The script's planted-store test failed on its first run, for a real leak.** The feature table held
  each team's identity, its school and code, which `SeedTeam` says is never written. It now holds a
  digest keyed by a salt the build draws and never stores (`cba001d`).
* **Each later addition was shown failing against a mutant, then restored by copy and sha1:**
  * the coach's file written to the working directory: the test failed at its read;
  * a second, stray file in the working directory: `assert after == before` failed, naming it;
  * the estimate ignoring the mix;
  * the by-kind count at the wrong confidence. It **survived** at first: the synthetic tags separated
    the positions perfectly, so both confidences were 0. A third of the placed cards' tags now speak
    for another position, as real tags often do, and the test uses a seed whose two confidences
    differ. It then failed.
  * the score weighted by stratum alone.
* **No Hypothesis property** is in this task, so working agreement 8 does not apply.

## Files changed

* **`packages/debate_core/src/debate_core/arguments/landscape/local_classifier.py` (new):**
  * features and tokens, the team rule, training and prediction;
  * the held-out measure, the threshold, the estimate and the comparison;
  * the coach sample, its file and its score.

  It is pure: rows in, values out.
* **`packages/debate_core/src/debate_core/application/local_classifier_comparison.py` (new):**
  * the feature table, built from a seed reading with t02's matcher, and its line format;
  * the check that a removal has reached a table's sources.
* **`scripts/compare_local_classifier.py` (new):** the four commands, with the guards built in.
* **Tests (new):**
  * `packages/debate_core/tests/arguments/landscape/test_local_classifier.py`: 27 tests on a
    synthetic caselist of 36 documents by 12 invented teams;
  * `tests/scripts/test_compare_local_classifier.py`: 9 tests on a planted store.
* **`pyproject.toml`, `packages/debate_core/pyproject.toml`, `uv.lock`:** scikit-learn as debate-core's
  `local-classifier` extra and a dev dependency.
  * Locked **offline** from uv's cache: scikit-learn 1.8.0, numpy 2.4.4, scipy 1.17.1, joblib 1.5.3,
    threadpoolctl 3.6.0.
  * No `debate-cli` extra asks for it, so an installed build does not get it, and
    `declared_extras` is unchanged.
* **This report.**

Nothing in `config/`, `render.py`, the matcher, the review queue or any landscape module changed.

## Deviations from the spec

1. **Measurements beyond the specified model, made before the PM saw them.** The PM asked for anything
   else to be proposed before it is used. I used three things only to measure, and none is wired:
   * **The proxy model.** The specified model's held-out measure could not answer the question, so I
     measured the proxy too.
   * **The mix-weighed estimate.**
   * **Stratifying the coach sample on the proxy.** The specified model's threshold of 0 would leave
     one stratum.

   The specified model's numbers are all reported as asked, and the sample scores both models. The
   PM may discard any of the three ([question 1](#questions-for-the-pm)).
2. **The coach's file is written under the data directory**, not at a path the operator chooses. The
   PM asked for "a local CSV outside the repository". The data directory is outside it, and keeping
   every derived file in one directory keeps them under one retention and one deletion. The coach's
   returned file is read from any path outside the repository.
3. **Removal and retention reach the files only by refusal.**
   * `compare` and `sample` refuse a table whose sources a removal has since reached: no longer
     parsed, suppressed whole, or a newly suppressed disclosure.
   * `score-sample` leaves such a source out and names its rows.
   * Nothing deletes `<data dir>/landscape/local-classifier/` on a removal or at the annual purge.
     The runbooks are outside this task's packages ([question 3](#questions-for-the-pm)).
4. **`sample` was not run by the session.** The PM asked for a block that writes it. I drew the sample
   in memory on the real table, writing nothing, to check the block and count its strata.

## Decisions and assumptions

1. **Field-prefixed tokens.** A heading's words are `h:` tokens and the tag's are `t:`. A 2-gram never
   runs from one heading into the next, or into the tag. It is still TF-IDF over word 1- and 2-grams.
2. **A token is a feature only when three teams carry it** in the training cards. Three, not seeding's
   two: a debater who changes partners is two teams. This is what keeps a debater's name out, since
   no list of names exists to strip.
3. **Tags lose every team code of the caselist**, not only the team's own. A tag is free text, and a
   code alone in it is not stripped as a heading's would be. A code that is also a word costs a tag
   that word.
4. **Teams are kept as keyed digests**, under a salt drawn for each build and never stored. The table
   can count a word's teams but cannot name one, even by trying the caselist's public school names.
5. **Labels are position ids only.** The role (READS or ANSWERS) comes from the answer flags, as
   the matcher sets it.
6. **Training settings:**
   * scikit-learn's defaults for logistic regression (L2, C = 1, lbfgs, multinomial), with
     `max_iter` 1,000 and `random_state` the seed;
   * `sublinear_tf`;
   * identical (features, label) cards fitted once, weighted by their count.

   Nothing was tuned on the held-out tenth.
7. **The split.** The documents are ordered by `sha256(seed:sha256)`, and the first round(n / 10) are
   held out. The model is trained on the other nine tenths, and the threshold and what it would place
   come from that model, so the threshold applies to it.
8. **The threshold rule.** It is the lowest point of a 0.05 grid (plus 0.975 and 0.99) from which
   precision stays at 90% or more. A point with under 50 held-out cards above it is passed over.
9. **"Exactly like a training card"** means the same known features as some labelled training card,
   whatever its label. It is the count behind the estimate.
10. **Evidence text was not counted.** It needs every source parsed again from its blob, as t09 and t11
    do, which is over two minutes and an operator run. Tags and headings come first, and the coach's
    labels say whether they fall short.
11. **The sample's draw.**
    * At most one card per document.
    * Within a stratum, the kinds take turns, so the score weighs each card by its (stratum, kind)
      cell's population.
    * Only cards the proxy predicts are drawn: 267 unplaced cards have no known feature.

## Questions for the PM

Paste-ready:

> **v1-e32-t21: four rulings needed before the coach labels the sample**
>
> 1. **Which model is judged?** The specified model (tag and every heading) scores 97.1% held-out
>    because its labels come from the headings it reads, so its 90% threshold is 0 and says nothing
>    about unplaced cards. The proxy (the same model without the headings that place on their own)
>    scores 68.4% held-out, 90.2% from 0.5, and an estimated 90% on the unplaced cards' mix from 0.6
>    (9,749 cards). Options:
>    * (a) judge the proxy, the sample stratified on it, both models scored *(recommended: it is the
>      only one whose held-out numbers bear on unplaced cards)*;
>    * (b) judge the specified model only and restratify the sample on it, though its threshold puts
>      all 60 cards in one stratum;
>    * (c) discard the proxy.
> 2. **The decision and its bar.** I recommend using the proxy only to order the review queue now,
>    and wiring it later, as `LOCAL_MODEL` behind review-queue rules, only if the coach's labels give:
>    * at least 27 of 30 right in the top stratum;
>    * a weighted precision of at least 90% at the chosen threshold;
>    * no kind under 4 of 5.
>
>    Otherwise drop it as a placer. Accept, or set another bar?
> 3. **Retention.** `<data dir>/landscape/local-classifier/` holds tags and headings derived from the
>    corpus. The script refuses a table a removal has reached, but nothing deletes the directory. I
>    propose one line in `docs/runbooks/caselist-removal.md` and in the annual purge, "delete
>    `<data dir>/landscape/local-classifier/<caselist>/`", and deleting it after your ruling on this
>    comparison. Both are outside this task's packages. Add them here, or in a follow-up?
> 4. **The coach's file.** Its tags lose the team's names, the caselist's schools and every team
>    code, and a heading one team used is withheld. A debater's name inside a tag would still show,
>    as it does in the report's top cards. Accept, or withhold words that only one team writes (which
>    also blanks rare technical words)?

## Operator follow-ups

**1. Write the coach sample** (expected runtime about 1 minute)

Where: your Mac, in this task's worktree. The block refuses to start if a `DEBATE_*` variable is set or
a `caselist pull` is running, and the script checks both again. It reads the feature table this session
built, trains both models with seed 21, and writes two files under
`~/.debate-research/dev/landscape/local-classifier/hspolicy26/`: the coach's CSV, and beside it the
cards' ids and predictions. It deletes and publishes nothing.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t21-local-classifier-comparison
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/compare_local_classifier.py sample --caselist hspolicy26; fi
```

Success looks like:

* `Sampled 60 unplaced cards from 60 documents, stratified by the proxy model's confidence; thresholds
  specified 0.000, proxy 0.500.`
* Three stratum lines: `at-or-above-threshold: 30 of 12752`, `just-below-threshold: 20 of 22089` and
  `far-below-threshold: 10 of 21820`. Each count must be above zero.
* The two `Wrote …` lines.

A `Refused: a removal has reached …` means the store changed since this session's run. Run
`features --caselist hspolicy26 --snapshot 2026-10-20` the same way, then this block again. Paste the
output back.

**2. The coach labels the file** (no command)

Give the coach a copy of
`~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.csv`.
They fill `position` on each row:

* a position id, as for the review queue's decisions;
* `none` when the card belongs to no position;
* `unsure` when they cannot tell.

Save the returned file outside the repository, for example as
`~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv`.

**3. Score it** (expected runtime a few seconds)

Where: the same worktree, after step 2. Change the path if the file was saved elsewhere.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t21-local-classifier-comparison
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/compare_local_classifier.py score-sample --caselist hspolicy26 --labels ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv; fi
```

Success looks like:

* `Labels: N of 60 sampled cards`, with N above zero;
* then a `Model specified` and a `Model proxy` paragraph, each with its accuracy at its threshold,
  its weighted accuracy and precision, and its lines by stratum and kind.

Paste the whole output back. A `Refused: row K of the labelled sample names no active position`
names a row whose `position` is not a position id. Correct that row and run the block again.

**No whole-selection run is handed over.** `pyproject.toml` and `uv.lock` changed, so
`scripts/affected_tests.py` reports the whole selection affected. The PM ruled for this task to run what
it touches plus the always-run list and leave the rest to the pull request's `ci`.

## What was run before this report

* `uv run scripts/affected_tests.py` → "The whole selection is affected: packages/debate_core/pyproject.toml
  is shared test ground", so nothing more was selected.
* **The node's criterion:** `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape -q`
  under `alarm 115` → **772 passed** in 4.70 s.
* **The always-run list, and the suites that read debate-core's extras or this task's script:**
  * the files: `tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`,
    `test_help_rendering.py`, `test_installation.py`,
    `packages/debate_core/tests/integrations/bedrock/test_aws_extra.py` and
    `tests/scripts/test_compare_local_classifier.py`;
  * run with `-n auto -m "not slow and not live"` under `alarm 115` → **363 passed** in 26.68 s;
  * no worker left.
* **Repo-wide checks:**
  * `ruff format --check .`: 1,340 files already formatted;
  * `ruff check .`: all checks passed;
  * `pyright packages/debate_core`: 0 errors (17.7 s);
  * `lint-imports`: 16 contracts kept, 0 broken;
  * `scripts/check_thin_handlers.py`: OK, 54 handlers;
  * `uv run scripts/validate_specs.py`: OK, 457 files.
* **The docs checks on this report:**
  * `scripts/check_command_blocks.py --base origin/dev`: OK, no `#` comments in 431 shell blocks
    (1 session report changed);
  * `scripts/docs_index.py --check-descriptions`: all 47 indexed documents have a description;
  * `scripts/check_links.py`: OK, 2,422 links and anchors;
  * `tests/docs`, `test_check_command_blocks.py` and `test_docs_index.py`: 162 passed.

## Follow-up work

* **Removal and the annual purge delete `<data dir>/landscape/local-classifier/`**: a runbook line in
  E30/E39's removal runbook, or this task's amendment ([question 3](#questions-for-the-pm)).
* **An import-linter contract keeping scikit-learn inside
  `debate_core.arguments.landscape.local_classifier`**, like the library contracts. It needs a case in
  `tests/architecture/test_import_contracts.py`, which is outside this task's packages. It belongs with
  whichever task wires the model, if one does.
* **Review-queue ordering by the proxy's confidence** (the recommendation): a small task in E32,
  touching `review_queue.py`, that orders rows and adds no placement.
* **If the coach's labels clear the bar:** a `LOCAL_MODEL` stage, as the spec's later task describes,
  with the threshold the coach's labels support. It would also need a model file under the data
  directory, which this task never writes.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

The most useful finding of this task is the one the spec didn't ask for: the specified model's
held-out score measures the alias table, not the cards that need placing.
1. **ac1 passes.**
   * Determinism holds for a seed whatever the card order.
   * No school, team code or name is a feature, with a positive control showing the three-team rule
     is what keeps a debater's name out.
   * Writes stay under the data directory.
   * Red against a refuse-nothing skeleton: 23 failed, and the 4 that passed are controls.
   * The real leak the planted-store test caught on its first run (teams' identities in the feature
     table) was fixed with keyed digests and an unstored salt. That's the right fix.
2. **ac2's measurements pass; the coach-labelled sample is an operator step** and not yet run, so
   the PR merges `--partial`.
3. **Rulings on the four questions:**
   1. **(a): the proxy is judged,** the sample is stratified on it, and both models are scored. The
      deviation (the proxy, the mix-weighed estimate, and the stratification) is accepted: each was
      needed to answer the question honestly, and none is wired.
   2. **The decision and its bar are accepted.** Use the proxy only to order the review queue for
      now. Wire it as `LOCAL_MODEL` only if the coach's labels give at least 27 of 30 right in the
      top stratum, a weighted precision of at least 90% at the chosen threshold, and no kind under
      4 of 5. Otherwise drop it as a placer and keep the ordering. The ordering is a small E32 task
      the PM files.
   3. **Retention: a follow-up.** The PM amends `v1-e30-t28` (the annual purge) and files the
      removal runbook's line, to delete `<data dir>/landscape/local-classifier/<caselist>/`. The
      directory stays until the coach's sample is scored, then follows the decision. Meanwhile the
      script's refusal of a table a removal has reached is the guard.
   4. **The coach's file: accepted as built.** It stays on the operator's machine for the coach,
      who is the operator, under the same rules as the review queue. Withholding one-team words
      would blank the rare technical words the coach needs to judge a card.
4. **Accepted as made:**
   * decisions 1 to 11: field-prefixed tokens, the three-team rule, every team code out of tags, no
     tuning on the held-out tenth, the threshold rule and the one-card-per-document draw;
   * deviations 2 and 4;
   * scikit-learn as an extra only, so an installed build doesn't get it.
5. **The affected set** is the whole selection (`uv.lock`), so it is left to the PR's `ci` under
   agreement 10. What it touches and the always-run list passed.

No re-review is needed. The coach's sample and its score are recorded by the PM when the operator
runs them.

## PM record, 2026-10-25

Added by the PM. Nothing above is changed, and this section is not a review.

* **The coach sample is written** (operator follow-up 1, 2026-10-25, from `origin/dev` at
  `e229387`): 60 unplaced cards from 60 documents, thresholds specified 0.000 and proxy 0.500;
  `at-or-above-threshold` 30 of 12,752, `just-below-threshold` 20 of 22,089, `far-below-threshold` 10
  of 21,820, every kind drawn as this report proposed; both files written under the data
  directory, in 54.4 s.
* **Still open, so the Goal stays `InProgress`:** the coach's labels (after 2026-11-01) and the
  score. The proxy's review-queue ordering is filed as `v1-e32-t26`. Removal and the annual purge
  now delete `<data dir>/landscape/local-classifier/<caselist>/` (the removal runbook, and
  `v1-e30-t28`'s amendment).
