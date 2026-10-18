# Session report: v1-e31-t20-long-cuts-and-limits

| | |
|---|---|
| Task | `v1-e31-t20-long-cuts-and-limits` — Long cuts join the one cluster that holds them, and the matching limits are set from samples |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t20-long-cuts-and-limits.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t20-long-cuts-and-limits.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t20-long-cuts-and-limits` |
| Session status | PARTIAL: the rules (`card-fingerprint-v4`), the diagnosis, the preview and the sampler option are built, tested red first, and mutated 39 of 39. Every measurement is the operator's and NOT RUN. One finding needs a PM ruling before merge: the ruling costs two hand-labelled cards their trim pairs, and with them t08's 0.90 recall target on two rows |

## Summary

`card-fingerprint-v4` builds the PM's ruling of 2026-10-16 into near-duplicate clustering. Long cuts
now join the one cluster that holds them by the step short cuts use, found from their ends instead
of left to whether the banding paired them. A body that holds a cut and another passage sharing no
text with it is no witness for the cut. A cut's own cluster counts among its witnesses. And no join,
of copies or of a cut, puts two bodies that share no text in one cluster, so ac5's measure is 0 in
every cluster by construction. t11's false join is the first fixture and stays three clusters under
every order of fingerprints. `MIN_CUT_SHARE` and `MAX_CONTAINER_CLUSTERS` are unchanged, waiting
for the samples that set them. `sample --ask-shape` (item 8) shows a person the pairs of a shape
the rule decides, tallied apart. `counts --save-after` and `--after` let the operator preview all of
ac1, ac2, ac3, ac5 and ac6 from this worktree before the merge, writing nothing to the store.

**Read these first:**

1. **The ruling and t08's labelled set disagree on two cards, and no design satisfies both.** In
   each, a trimmed-start and a trimmed-end copy share no text. One of them, Brannock's (t06's rows),
   is word for word t11's false join at a smaller size: the original is the trimmed end followed by
   the trimmed start. The labels call all of each card's copies one card, and the ruling says the
   two trims are two passages, joined through nothing. Precision stays 1.000 everywhere. Recall
   falls on exactly those two cards' pairs, and the t08 target of 0.90 on "full short cards" fails
   on two rows: 19/24 and 23/37. Those two checks are strict xfails naming the pending ruling. The
   relay prompt for the PM is at the end of this summary. See
   [Labelled sets, before and after](#labelled-sets-before-and-after).
2. **ac5 is 0% by construction, and that is a claim for the operator's preview to confirm.** Every
   join checks that the joiner shares at least one five-word run with every body already in its
   target. On an invented article cut at 600 extents, v3 put 584 of them in one cluster with
   138,081 pairs sharing nothing, and v4 makes 199 clusters, the largest 44, with none.
3. **The cost is the much-read card split into its passages.** A card body that holds two disjoint
   cuts witnesses neither, so the two cuts become two clusters and the body a third. That is the
   ruling ("two passages of one article are two cards"), but it will show in `counts` as divided
   clusters, and the PM should expect many. The join sample (ac1) and the divided-pairs diagnosis
   (step 7) are what to read.
4. **Two places where I chose and the PM may rule otherwise:** two joiners that share nothing are
   both refused rather than one winning by order (Decision 3), and a long cut nine-tenths inside a
   body lacking one of its ends still joins it, as the banding used to (Decision 4). Short ones wait
   for item (4)'s sample.
5. **An installed agent rewrites the table as `v3`.** Every build reads a `v4` table, since no code
   compares the version. But every parse stage rebuilds the table under the running build's version,
   so `v1.1.0-dev.18` would put `v3` back on its next run. Reinstall the agent on the first
   pre-release carrying this task before the dev rebuild (step 9).

**The Goal stays `InProgress`.** ac1's sample, ac2's figures, ac3's sample, ac4's re-cluster, ac5's
shapes and ac6's sample all need the operator's store. Merge with `scripts/task pr --partial` once
the PM has ruled on item 1.

**For the PM** (paste-ready):

```text
v1-e31-t20 needs one ruling before merge, and records three choices for you to confirm.

1. The ruling against t08's labels (needs a ruling).
   Two labelled cards in short_cards.jsonl have a trimmed-start and a trimmed-end copy that share no
   five-word run. In Brannock's (t06's rows) the original is the trimmed-end copy followed by the
   trimmed-start one, word for word: t11's false join at 29 words instead of 150. Under the ruling
   the two trims are two passages; "never transitively" keeps them apart, and the bodies holding
   both witness neither. Labels say one card.
   Measured, before -> after (precision 1.000 throughout):
     short-card set, full short cards: 24/0/0 -> 19/0/5 (t08 target 0.90, now 0.792)
     extended set, full short cards: 35/0/2 -> 23/0/14 (target 0.90, now 0.622)
     short-card set, abbreviated with a full copy: 44 -> 39; abbreviated pairs: 12 -> 11
     every other row unchanged; every lost pair is one of these two cards'.
   Options:
     (a) The ruling stands: the two trims of each card are two cards. Record the new figures as
         expected, and amend t08's ac1 target for the two "full short cards" rows to the measured
         values, with the ruling as the reason. The two strict xfails become plain expectations.
     (b) The labels stand: keep text-disjoint trims of one card in one cluster. No rule on the
         bodies alone tells these two cards from t11's false join, so this undoes ac1's fixture
         and the ruling's "never transitively".
     (c) Relabel the two cards' trims as different cards. Their pairs with the full copies would
         still be lost, because the full copy holding both trims witnesses neither.
   Recommendation: (a). The labels predate the ruling, and Brannock's rows are the false join's
   shape exactly. Keeping them one card means a coach-checked "different card" pair joins again.

2. FYI, proceeding unless told otherwise:
   - Two clusters that would both join a third, and share no text with each other, are both
     refused (symmetric), not one by fingerprint order. That keeps "not a witness for joining any
     of them" literal; it loses more recall than letting one win.
   - A long cut nine-tenths inside a body that lacks one of its ends joins it, as v3's banding did
     when it paired them. Short ones are still not compared until item (4)'s sample.
   - "Shares no text" means no five-word run in common: the shape ac5 counts and the sampler
     decides by rule. Two passages sharing a single run are not refused.

Reply with 1(a), 1(b) or 1(c), and anything on 2 you want changed.
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `long-cuts` — Long cuts and limits | Done in the session; the operator's samples and re-cluster are open | The join, the guards, the diagnosis, the preview, item (8) and the version bump are built and tested. The limits are unchanged pending the samples, and the re-cluster figures are NOT RUN |

## Acceptance criteria

Every command ran from the task worktree on 2026-10-18, against invented fixtures only.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — (1), (5) and (7) built on synthetic fixtures, shown failing first, including two disjoint bodies and a third holding both, which stay apart | PASS | The 13 tests of "Long cuts, and joins only on text two bodies share" in `test_near_duplicates.py`, committed red (`a295999`) against the v3 rules: `14 failed, 4 passed`. Now `uv run pytest packages/debate_core/tests/evidence/test_near_duplicates.py -n0` → `106 passed`. t11's false join stays `[[A], [B], [C]]` under all six orders of fingerprint. See [Shown failing first](#shown-failing-first) |
| **ac1** — the operator's join sample of 20 newly joined pairs, through t21's sampler, has no pair the coach calls different | **NOT RUN** | Needs the store and a person. Operator follow-ups, step 4 (before the merge) and step 14 (after it, same seed) |
| **ac2** — each limit set from the recorded samples, with the figures in the report, and re-measured after (1) | **NOT RUN** | The samples need the store. The tools are built: `--kept-apart-by` now tallies each pair by cut size and share band, and `diagnose --after` re-measures every limit on v4's placement. Steps 5 and 7. `MIN_CUT_SHARE` stays 0.25 and `MAX_CONTAINER_CLUSTERS` 8 until then; both are mutation-tested at their boundaries |
| **ac3** — (4): the sample decides, and the rule follows it, by test | **NOT RUN** (the sample); the rule as it stands is pinned | `test_a_short_body_nine_tenths_inside_a_body_lacking_one_of_its_ends_stays_out` and `test_a_card_lacking_the_end_of_a_short_copy_does_not_hold_it_and_is_a_second_witness` pin today's rule. The mutant that lets short bodies be compared by one end is caught. Step 6 is the sample; if it says "copies", the change is that mutant, with these two tests turned round |
| **ac4** — `fingerprint_version` bumped | PASS | `card-fingerprint-v4` (`14be4c4`). Red first: the test literals raised to `v4` failed with `'card-fingerprint-v3' == 'card-fingerprint-v4'`, twice, then passed. `fingerprints.py` lists what `v4` changed; `parsed-card-store.md` has its row. Mutant "the version not bumped" → 3 failed |
| **ac4** — the operator's re-parse records clusters, merges and divided pairs before and after in `caselist-parse-report.md` | **NOT RUN** | A re-cluster, not a re-parse. The section is written, every figure marked not run: [The re-cluster under `card-fingerprint-v4`](../data/caselist-parse-report.md#the-re-cluster-under-card-fingerprint-v4-v1-e31-t20). Steps 2, 7 and 9 to 16 |
| **ac5** — under 5% of pairs sharing no text in each caselist's three largest clusters, after the rebuild | **NOT RUN** | 0% by construction: no join puts two bodies sharing no shingle in one cluster, and every refusal is mutation-tested (`copies-join-unguarded`, `cut-join-unguarded`, `joiners-not-checked-against-each-other`, all caught). Preview from this worktree: step 3, seconds after step 2. After the rebuild: step 13 |
| **ac6** — `sample` shows the pairs of a decided shape the person names, tallied apart, by test | PASS | `sample --ask-shape SHAPE`, repeatable. `test_a_sample_shows_the_pairs_of_a_decided_shape_it_is_asked_to_and_tallies_them_apart` and `test_a_decided_shape_asked_about_is_shown_and_the_rest_still_decided` (red against the start commit: the option does not exist, and `run_sample` has no `ask_shapes`). With no `--ask-shape` every tallies line is as t21 left it; t21's tests pass unchanged |
| **ac6** — the operator's sample of contained pairs under a third of the larger sets or confirms `MIN_CUT_SHARE` | **NOT RUN** | Step 5 |
| Node `long-cuts`: `uv run pytest packages/debate_core/tests -k "fingerprint or cluster"` | PASS | `179 passed` |

### Also run

| Check | Result |
|---|---|
| Default suite, `uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`, one command each, on the final tree | `2023 passed, 1 xfailed` (51 s); `2031 passed, 1 xfailed` (48 s); `2031 passed, 1 skipped, 1 xfailed, 2 warnings` (45 s); `2023 passed, 3 xfailed, 1 warning` (52 s): 8,108 passed. The skip is the parser eval waiting on corrections; two xfails are t12's; four are this task's pending-ruling xfails |
| `uv run --frozen ruff check .`; `ruff format --check .` | `All checks passed!`; `785 files already formatted` |
| `uv run --frozen pyright` (after the last format) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `check_thin_handlers.py`, `check_links.py`, `docs_index.py --check-descriptions` | all OK |
| Coverage of the changed modules, lines and branches | `cluster_diagnosis.py` 100%, `fingerprints.py` 100%, `near_duplicates.py` 99%: line 540 (`_Clusters.join` given one root twice, which no caller does) and 563 (`v1-e31-t04`'s empty-body exit in the banding loop) |
| `uv run scripts/validate_specs.py` | `OK: 366 files, 38 epics, 308 tasks, 20 releases` (the Goal left `InProgress`) |
| `scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 295 shell code blocks in 123 Markdown files` |

## The rules (`card-fingerprint-v4`)

In [`near_duplicates.py`](../../packages/debate_core/src/debate_core/evidence/near_duplicates.py),
whose docstring now opens with the ruling and maps each sentence of it to a step.

1. **Copies.** Banding candidates with Jaccard at least 0.8, and pairs of bodies of one size that
   each hold the other (a word changed), are joined most similar first, then by fingerprint. A join
   that would put two bodies sharing no shingle in one cluster is refused. A one-word-changed copy
   of a body too common to compare is held back, counted against the Jaccard copies, as `v3`'s
   short step held it back.
2. **Containers, found and not sampled.** `CutIndex` works out, from the bodies alone, which bodies
   hold which: at least as large, holding the cut's first and last shingle (a long cut's first or
   last), and confirmed, nine-tenths or, for a short cut, all but one word. The containment union
   through the banding is gone.
3. **The cut step, in rounds.** Each round, every cluster's join is worked out from the clusters
   the last round left:
   * a container that also holds a passage (a body it holds, at least `MIN_CUT_SHARE` of it)
     sharing nothing with the cut is no witness;
   * the cut's own cluster counts among its witnesses;
   * nested witnesses count once, as in `v3`;
   * the cut must be within the share of its smallest witness;
   * a short cut whose ends more than `MAX_CONTAINER_CLUSTERS` other clusters hold, counted as the
     clusters stand, is left alone.

   A join is refused if the joiner shares nothing with a body already in the target. A cluster
   joining nothing takes in its joiners, except any two that share nothing, which it takes in
   neither of. A cluster whose own join is so refused takes in its joiners in the same round. A
   cluster that is joining another waits a round. Rounds end when one joins nothing.

`CutIndex`, `witnesses`, `too_common` and `joining_target` are public, and
[`cluster_diagnosis.py`](../../packages/debate_core/src/debate_core/evidence/cluster_diagnosis.py)
decides every outcome with them, so the diagnosis cannot drift from the rules.

### What it costs

The rebuild has not been timed on the store (that is a store run). On invented corpora, run
locally under loads of 7 to 52 (other sessions):

| Invented corpus | `v3` | `v4` |
|---|---|---|
| 3,000 cuts of 375 articles, lengths log-normal around 120 words | 29.8 s | 9.4 s |
| 10,000 cuts of 1,250 articles | 39.5 s | 23.1 s |
| 600 extents of one 3,000-word article | 2.3 s: 14 clusters, largest 584, 138,081 pairs sharing nothing | 4.2 s: 199 clusters, largest 44, none |
| 2,000 extents of that article | not run | 39.5 s: 335 clusters, largest 150, none |

A profile of the 1,200-extent case: 17.2 s, of which MinHash, which `v3` does too, is 11.5 s, the
copies' Jaccard 2.3 s and the cut step 0.7 s. The growth with extents of one article is the
banding's candidate pairs, as in `v3`.

## Labelled sets, before and after

`uv run pytest packages/debate_core/tests/evidence/test_short_card_recall.py -n0 -s -k test_report_short_card_recall`,
saved before the first change and after each one, compared with `diff`. True positive, false
positive and false negative pairs:

| Pairs | Before | After | Precision after | Recall after |
|---|---|---|---|---|
| Variant set, all | 75 / 0 / 0 | 75 / 0 / 0 | 1.000 | 1.000 |
| Variant set, with a short card | 6 / 0 / 0 | 6 / 0 / 0 | 1.000 | 1.000 |
| Variant set, long cards only | 69 / 0 / 0 | 69 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, all | 81 / 0 / 0 | 70 / 0 / 11 | 1.000 | 0.864 |
| Short-card set, full short cards | 24 / 0 / 0 | 19 / 0 / 5 | 1.000 | 0.792 |
| Short-card set, the full long card | 1 / 0 / 0 | 1 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, abbreviated with a full copy | 44 / 0 / 0 | 39 / 0 / 5 | 1.000 | 0.886 |
| Short-card set, abbreviated with abbreviated | 12 / 0 / 0 | 11 / 0 / 1 | 1.000 | 0.917 |
| Extended set, all | 104 / 0 / 12 | 86 / 0 / 30 | 1.000 | 0.741 |
| Extended set, full short cards | 35 / 0 / 2 | 23 / 0 / 14 | 1.000 | 0.622 |
| Extended set, full long cards | 2 / 0 / 2 | 2 / 0 / 2 | 1.000 | 0.500 |
| Extended set, abbreviated with a full copy | 51 / 0 / 4 | 46 / 0 / 9 | 1.000 | 0.836 |
| Extended set, abbreviated with abbreviated | 16 / 0 / 4 | 15 / 0 / 5 | 1.000 | 0.750 |

**Every lost pair is one of two cards'.** Worked out by hand from the rows and written into the
test before it ran (`AFTER_THE_PASSAGE_RULING_TABLE`); the measurement matched row for row and by
mechanism on the first run.

* **Brannock** (t06's rows): the original is the 13-word trimmed end followed by the 16-word trimmed
  start, word for word. The original and the typo copy each hold both trims, so neither trim has a
  witness. Lost: 5 full pairs (the trims with the original and the typo copy, and with each other),
  5 abbreviation-with-full pairs (each abbreviation links to the side whose opening and closing it
  matches), and the pair of abbreviations.
* **Kessler** (t08's rows): the original holds both trims. The OCR-joined copy holds the trimmed
  start and the dropped-word copy the trimmed end, and both copies join the original. Each trim
  then has one witness, that cluster, and the two share nothing, so it takes in neither. Lost: 7
  full pairs.

The first version of the passage rule cost more: a body holding two passages was no witness for
anything, so Kessler's own one-word copies lost the original too. The rule is now relative to the
cut: a container is no witness for a cut when it holds another passage sharing nothing with that
cut. A copy of the whole body shares text with both passages and is witnessed as before.

**t08's target fails on two rows**: 0.90 on "full short cards", now 0.792 and 0.622. Every other
target holds; "extended set, abbreviated with abbreviated" is exactly at its 0.75. The two checks
are `xfail(strict=True)` with the reason `PASSAGE_RULING_PENDING`, as is t08's mechanism test that
Kessler's trims join the original. Strict, so whichever way the PM rules, the suite says so.

## Shown failing first

Red runs, each against the code before the behaviour existed. The start commit's source was taken
with `git archive 47d454d` to the scratchpad and put first on `PYTHONPATH`, after printing a
changed module's `__file__` to confirm it was the one imported.

| What | Against | Red |
|---|---|---|
| The 13 tests of the ruling (`a295999`, committed red) | v3 | `14 failed, 4 passed`: t11's false join `[[A, B, C]]` in all six orders; the two-passage witness `[[0, 1, 2, 3]]`; three long-cut joins `[[0], [1]]`; two copies' passages `[[0, 1, 2, 3]]`; the copies' chain not sharing text throughout; the own-cluster cases `[[0, 1, 2]]` twice |
| The four that passed on v3 | | Two boundaries kept on purpose (a body holding one passage is its card; a copy that does not hold the cut does not block it), the lacking-an-end rule pinned, and the container count, which v3's banding satisfies for another reason. Mutants are their evidence |
| The version literal | v3 | `'card-fingerprint-v3' == 'card-fingerprint-v4'`, twice |
| A long cut lacking an end joins | v3, and the commit before it | `[[0], [1]]` on both |
| A card lacking a short copy's end is a second witness | v3 | `[[0], [1, 2]]` |
| The two round tests | v3; the commit before the fix | Both `[[0, 1, 2, 3, 4]]` on v3; the waiting cut `[[0, 1], [2], [3], [4]]` before the fix |
| The diagnosis (`test_cluster_diagnosis.py`) | v3's diagnosis | `14 failed, 20 passed`: the new outcomes and the v4 readings |
| The six new script tests | the start commit's script | `SystemExit: 2` for the four options it lacks, `TypeError` for `ask_shapes`, and no `within-the-rule` selector. A missing option proves little; the mutants are the evidence |

## Mutation runs

39 mutants, each one exact replacement that had to match exactly once, run one at a time against
the seven test files that read matching (`348 passed, 4 xfailed` unmutated, 10 s). Each run had a
new empty `HYPOTHESIS_STORAGE_DIRECTORY`, checked empty first; none of these tests is a Hypothesis
property, so the isolation cannot affect them. The file was restored from saved bytes and compared,
and `git status --porcelain` was checked after every batch. The final run, on the final code: **39
of 39 caught.**

| Group | Mutants (each caught) |
|---|---|
| The witness rule | witnesses in several clusters join the smallest's (11 failed); nested containers never count once (34); copies count as containers (4) |
| The two-passage refusal | the refusal gone (1); a container refusing every cut once it holds two disjoint passages (4); passages of any size (2) |
| The own-cluster witness | own-cluster containers ignored, as v3 did (3) |
| `MIN_CUT_SHARE` | 0.2 (28); 0.3 (30); not checked (22); checked for short cuts only (18) |
| `MAX_CONTAINER_CLUSTERS` | 7 (2); 9 (2); counting bodies, not clusters as they stand (2); one-word copies not held back when too common (1) |
| Lacking an end | short cuts compared by one end (2); long cuts need both ends (1) |
| Never two texts sharing nothing | copies joined unguarded (1); cut joins unguarded (1); joiners not checked against each other (6); joiners not waiting for their target (5); refused joins holding back their joiners (1) |
| The version | not bumped (3) |
| The diagnosis | no passage outcome (1); own cluster read as several (1); no unrelated-texts outcome (1); never "points elsewhere" (1); set-aside judged by its own copy (1); copies not holders (2); divided parts by first digest (3) |
| The script | `--ask-shape` not shown (2); also counted by rule (2); tallied with the rest (2); `--after` ignored by one-placement commands (1); ignored when comparing (1); `--save-after` saves *before* (2); `--preview` ignored (2); kept-apart kind without its band (3); sizes swapped (1) |

**What the earlier runs found**, each fixed before the final run:

* **Five survivors, each a missing test**, now written: a quote under the share is no passage
  (`passages-of-any-size`); a body lacking a short copy's end is a second witness
  (`short-lacking-an-end-compared`); a cut does not join a cluster already holding a passage sharing
  nothing with it (`cut-join-unguarded`); the diagnosis of a cut whose outside containers all hold
  another passage (`diagnosis-no-passage-outcome`); `--after` reads the file and does not place
  again (`after-ignored-when-comparing`).
* **A real defect, found while writing the third of those.** A cluster whose own join was refused
  beside a conflicting joiner still counted as joining, so a cut waiting on it waited forever.
  Fixed in `2be9063`, with a test that fails on the commit before.
* **Two mutants were first written so that they crashed** (an unpacking error, a missing key) and
  were rewritten as behaviour changes before being counted.
* **One branch deleted.** The handling of two clusters that would each join the other was never
  taken: the copies' step already joins two bodies that each hold the other, and I could build no
  such pair. Without it the two would wait for each other and join neither (`26e54cc`).
* **Two batches were cut by the alarm** under loads of 46 and 72 from other sessions, each leaving
  one file mutated. Each time the diff was checked to be the mutant alone and the file restored.
  The interrupted mutants were run again.

## Files changed

**Matching (`packages/debate_core/src/debate_core/evidence/`)**
* `near_duplicates.py`: the rules above; `CutIndex`, `Witnesses`, `witnesses`, `too_common` and
  `joining_target`, public for the diagnosis; the docstring rewritten around the ruling.
* `fingerprints.py`: `card-fingerprint-v4` and what it changed.
* `cluster_diagnosis.py`: reads containment from `CutIndex` and decides outcomes with the
  clusterer's functions. New outcomes, long and short alike; copies count as holders; divided parts
  explained by a cut of either size, the smallest first, or by a copy; `KeptApartBy.CUT_STEP` in
  place of `SHORT_BODY_STEP`.

**Tests**: `tests/evidence/test_near_duplicates.py` (a new section of 18 tests; t11's fixtures moved
from a 330-word to a 400-word card so its copy stays under a quarter of it, and the long-cut test
rewritten to the new rule); `test_cluster_diagnosis.py` (new outcomes; v4's readings);
`test_short_card_recall.py` (the hand-worked table and the pending-ruling xfails);
`test_fingerprints.py` (one literal); `tests/application/test_caselist_card_stats.py` (one case
through `place` moved to 400 words, one added at 330); `tests/scripts/test_compare_card_clusters.py`
(v4's placements and seven new tests); `tests/smoke/test_caselist_cards.py` (one literal).

**Operator tool**: `scripts/compare_card_clusters.py`: `counts --save-after`; `--after` on `counts`,
`sample`, `diagnose` and `shapes`; `shapes --preview`; `sample --ask-shape`; `--kept-apart-by`
names v4's outcomes; kept-apart pairs tallied by cut size and share band; copies in the divided-pair
explanation.

**Docs**: `docs/data/caselist-parse-report.md` (the re-cluster section, not run);
`docs/data/parsed-card-store.md` (the `v4` row, and which builds read and write which version).

## Deviations from the spec

1. **The ruling contradicts two hand-labelled cards, and t08's recall target on two rows fails.**
   The PM's notes say "recall must not fall without a reason I can rule on": this is the reason,
   above and in the relay prompt. I built to the ruling and did not edit t08's targets; the two
   failing checks are strict xfails until the PM rules.
2. **Outside `constraints.packages`**: `tests/scripts/test_compare_card_clusters.py`, the tests of
   the script the spec asks to change, and `tests/smoke/test_caselist_cards.py`, one literal the
   suite fails without. The same two t11 recorded and the PM accepted.
3. **The limits are not set, because the samples that set them are the operator's.** ac2 says
   "set from the recorded samples ... and re-measured after (1)". No such sample is recorded: t11's
   step 7 was optional and not taken, and under t21's rule a kept-apart sample is decided entirely
   by rule. The tools for both are built (steps 5 to 7), and each limit is pinned by a test and two
   mutants at its boundary.

## Decisions and assumptions

1. **The passage refusal is relative to the cut.** "A body that holds the passages of two or more
   clusters is not a witness for joining any of them" is read as: a container is no witness for a
   cut when it also holds a passage sharing nothing with that cut. A passage is a body it holds
   that is at least `MIN_CUT_SHARE` of it, the same line a cut must clear to join it. Read for the
   whole body instead, the labelled sets lost their one-word copies as well (Labelled sets).
2. **"Shares no text" is no five-word run in common**: the shape ac5 counts and the sampler decides
   by rule. Two passages sharing one run are not refused.
3. **Conflicting joiners are both refused.** Two clusters that would join a third, and share nothing
   with each other, both stay out: the cluster holds two passages through two bodies, and the ruling
   says such a holder witnesses neither. Letting one win by fingerprint would lose fewer pairs and
   make a digest decide.
4. **A long cut is found from either end.** A long body nine-tenths inside another that lacks its
   first or last shingle was joined by `v3` whenever the banding paired them; requiring both ends
   would have divided those joins. Item (4) and t08's guard are about short bodies, which still need
   both.
5. **"Holds" is one test everywhere**: at least as large, both ends (a long cut's either), and
   confirmed. `v3`'s nested check read nine-tenths alone, though its docstring said "by the same
   test a cut is confirmed by". The new test of a card lacking a short copy's end fails on `v3`.
6. **Copies of one size that each hold the other are joined as copies**, not as cuts, and are not
   containers of each other. Without that, two such copies inside a larger body each saw the other
   as their smallest witness, and neither ever joined it.
7. **The container count is taken as the clusters stand** each round, so a much-read card whose long
   copies have joined counts once (item 3). A body too common in round one may be compared later.
8. **The copies' Jaccard step is also refused when it would put two texts sharing nothing
   together**, joined most similar first, so an article's sliding extents break where the chain
   would reach a text sharing nothing with its start.
9. **The script's fixture store keeps its 330-word card**, so that its preview shows v4 joining the
   card, the copy and the cut. The core tests moved to 400 words to keep testing the nested rule.
10. **The preview's placement file holds digests, indices and ids**, as `--save-before`'s does
    (t21's Deviation 2, accepted).
11. **No session run against the operator's data directory.** Every figure here is from invented
    fixtures or invented corpora built in the scratchpad.

## Operator follow-ups

Nothing here writes to the parsed store until step 11. Don't run any of it while `caselist pull`
is running (`uv run debate-research caselist runs --last 1` shows the last run) or on a Wednesday
morning, when the agent runs. Every file these steps save holds counts, digests, indices and ids,
no text; the tallies files hold counts alone. The cards a sample shows are real disclosures, so
nothing from the screen goes into a message, a screenshot or a file.

### Before the merge: the preview, from this worktree

**Step 1. Check the worktree** (seconds).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
git branch --show-current
git status --short
git log --oneline -1
ls ~/.debate-research/dev/parsed/hsld26
uv run python -c "import debate_core.evidence.fingerprints as f; print(f.FINGERPRINT_VERSION)"
```

Expected: `task/v1-e31-t20-long-cuts-and-limits`; `git status` prints nothing; the last commit is
this report's; the newest directory is `2026.10.12-docx-3`; `card-fingerprint-v4`.

**Step 2. Place each caselist under `v4` in memory, compare it with the store's `v3` table, and
save the placement** (about as long as a rebuild: about 6, 4, 9 and 1 minutes on the 2026-10-16
rebuild timings, so about 20 in all; one command per caselist).

```zsh
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --save-after ~/.debate-research/dev/card-clusters-t20-preview > ~/t20-preview-counts-hsld26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist hspf26 --save-after ~/.debate-research/dev/card-clusters-t20-preview > ~/t20-preview-counts-hspf26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist hspolicy26 --save-after ~/.debate-research/dev/card-clusters-t20-preview > ~/t20-preview-counts-hspolicy26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist openev --save-after ~/.debate-research/dev/card-clusters-t20-preview > ~/t20-preview-counts-openev.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key} + (.value | {before_version, after_version, cards_only_before, cards_only_after, exact_fingerprints_changed, clusters_before, clusters_after, clusters_merged_into_another, clusters_made_of_several, clusters_divided, most_absorbed, absorbed, largest_before, largest_after, largest_after_distinct_texts, seconds})' ~/t20-preview-counts-*.json
```

Expected: `exit 0` four times; `before_version` `card-fingerprint-v3`, `after_version`
`card-fingerprint-v4`; `exact_fingerprints_changed`, `cards_only_before` and `cards_only_after` 0.
**`clusters_divided` above 0 is expected**: the chains `v3` built through bodies holding several
passages come apart, which is the task. So is `clusters_merged_into_another` above 0: long copies
joining. `largest_after` should be far under `largest_before` for hspf26 (682) and hspolicy26
(1,609). Anything under `absorbed` at `6 to 20` or above: send it before going on.
`shapes --preview` gives step 3 without this file, at this step's cost each time.

**Step 3. ac5: the three largest clusters' shapes** (seconds).

```zsh
uv run python scripts/compare_card_clusters.py shapes --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --largest-clusters 3 --after ~/.debate-research/dev/card-clusters-t20-preview > ~/t20-preview-shapes.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, placement: .value.placement, version: .value.fingerprint_version, clusters: [.value.described_clusters[] | {rank, cards, not_full: .cards_not_full, texts: .distinct_texts, pairs, nothing: .share_of_pairs_by_shape["sharing nothing"], words: [.words_smallest, .words_median, .words_largest]}]}' ~/t20-preview-shapes.json
```

Expected: `exit 0`; `placement` `a placement counts saved`, `version` `card-fingerprint-v4`, and
`nothing` 0 in all twelve clusters. Above 0 anywhere is a defect: send the line. hspf26's
long-bodied cluster may still be among the largest; the PM said to leave it alone, and nothing here
special-cases it.

**Step 4. ac1: the join sample** (seconds to read the store, then the person's time). The newly
joined pairs, the store's `v3` table against the saved `v4` placement. Each pair the rule cannot
decide is shown; press `s`, `d` or `u`, or `q` to stop and keep the tallies.

```zsh
uv run python scripts/compare_card_clusters.py sample --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-preview --save-tallies ~/t20-sample-tallies.txt
```

Expected: `Drew 20 of N newly joined pairs, seed S.` **Note the seed**: step 14 uses it. ac1 passes
when no pair is answered `different card`. By construction none is decided "different" by rule.

**Step 5. `MIN_CUT_SHARE` (ac2, ac6)** (seconds, then the person's time; the second reads every
caselist's bodies first, about 3 to 6 minutes). The first shows newly joined pairs that are a small
part of the other (under a third), which the rule calls the same card. The second shows cuts the
share keeps out, tallied by share band.

```zsh
uv run python scripts/compare_card_clusters.py sample --count 40 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-preview --ask-shape contained-under-a-third --save-tallies ~/t20-sample-tallies.txt
uv run python scripts/compare_card_clusters.py sample --kept-apart-by under-the-minimum-share --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-preview --ask-shape contained-under-a-third --save-tallies ~/t20-sample-tallies.txt
```

Expected: `asked of a shape the rule decides:` lines beside the rule's verdict. "Different card"
among the first says the share is too low; "same card" in the second's `a tenth to a quarter` band
says it could come down.

**Step 6. ac3: short bodies nine-tenths inside a body lacking one of their ends** (3 to 6 minutes
to read, then the person's). They are contained by construction, so every decided shape is asked.

```zsh
uv run python scripts/compare_card_clusters.py sample --kept-apart-by lacking-an-end --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-preview --ask-shape identical --ask-shape contained-under-a-third --ask-shape contained-a-third-or-more --save-tallies ~/t20-sample-tallies.txt
```

Expected: t11 counted 26 such bodies on the corpus. Mostly "same card" says they are copies with a
stray word at one end, and the rule should compare them; mostly "different card" keeps it.

**Step 7. ac2's re-measure, `MAX_CONTAINER_CLUSTERS`, and the divided pairs** (1 to 3 minutes a
caselist for the diagnoses, then the sample).

```zsh
uv run python scripts/compare_card_clusters.py diagnose --caselist hsld26 --after ~/.debate-research/dev/card-clusters-t20-preview --largest-clusters 3 > ~/t20-preview-diagnosis-hsld26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist hspf26 --after ~/.debate-research/dev/card-clusters-t20-preview --largest-clusters 3 > ~/t20-preview-diagnosis-hspf26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist hspolicy26 --after ~/.debate-research/dev/card-clusters-t20-preview --largest-clusters 3 > ~/t20-preview-diagnosis-hspolicy26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist openev --after ~/.debate-research/dev/card-clusters-t20-preview --largest-clusters 3 > ~/t20-preview-diagnosis-openev.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, short: .value.cuts.short_by_outcome, long: .value.cuts.long_by_outcome, under_share: [.value.cuts.short_under_the_minimum_share_by_share, .value.cuts.long_under_the_minimum_share_by_share], divided: .value.divided_pairs.pairs}' ~/t20-preview-diagnosis-*.json
jq -c 'to_entries[] | {caselist: .key, reasons: [.value.divided_pairs.by_reason[] | {pairs, kind, outcome}]}' ~/t20-preview-diagnosis-*.json
uv run python scripts/compare_card_clusters.py sample --kept-apart-by ends-held-by-too-many-clusters --count 10 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-preview --ask-shape identical --ask-shape contained-under-a-third --ask-shape contained-a-third-or-more --save-tallies ~/t20-sample-tallies.txt
cat ~/t20-sample-tallies.txt
```

Expected: `exit 0` four times. Each limit's count is the re-measure after (1): the short cuts under
`short: its ends are held by too many clusters` against t11's 5 of 81, and the cuts under the share,
by band. The divided pairs are explained by reason; one whose `kind` is `no cut or copy links this
part to the rest` is a cause the diagnosis does not know, and is the thing to send first.

**Step 8. Paste back** the `jq` lines of steps 2, 3 and 7 and the tallies file. They hold counts
only. The PM then rules on the limits; the session sets them, by test, before the merge.

### After the merge

**Step 9. Reinstall the agent on the first pre-release carrying this task, before the rebuild.**
Every build reads a `v4` table, since no code compares the version. But the agent's parse stage
rebuilds each caselist it imports into under its own build's version and publishes it to dev, so
`v1.1.0-dev.18` would put `v3` back the next week it ran. This finds the tag; then follow
[Reinstalling the agent](../runbooks/caselist-scheduled-sync.md#reinstalling-the-agent) with it.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git pull --ff-only origin dev
git fetch --tags origin
T20=$(git log -1 --format=%H --grep='^v1-e31-t20-long-cuts-and-limits:')
echo "${T20}"
git tag --list 'v1.1.0-dev.*' --contains "${T20}" --sort=v:refname | head -1
```

Expected: `dev`, one commit id, and one tag. No tag yet means the pre-release is still building.

**Step 10. Save the `v3` tables** (seconds).

```zsh
mkdir -p ~/.debate-research/dev/card-clusters-v3
for c in hsld26 hspf26 hspolicy26 openev; do cp -p ~/.debate-research/dev/parsed/${c}/2026.10.12-docx-3/occurrences.jsonl ~/.debate-research/dev/card-clusters-v3/${c}.jsonl; done
jq -r '.fingerprint_version' ~/.debate-research/dev/card-clusters-v3/*.jsonl | sort | uniq -c
```

Expected: one line, every row `card-fingerprint-v3`. Anything else, stop: the agent has run on
another build since 2026-10-16, or the directory has changed.

**Step 11. The dev rebuild, without publishing** (about 345, 219, 482 and 68 s, as the 2026-10-16
rebuild; no AWS session needed).

```zsh
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hsld26 > ~/t20-parse-dev-hsld26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspf26 > ~/t20-parse-dev-hspf26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspolicy26 > ~/t20-parse-dev-hspolicy26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist openev > ~/t20-parse-dev-openev.json; echo "exit $?"
for c in hsld26 hspf26 hspolicy26 openev; do jq -c '(.data // .error.details) | {caselist, version, fingerprint_version, attempted, store, elapsed_seconds}' ~/t20-parse-dev-${c}.json; done
```

Expected: `exit 0`; `fingerprint_version` `card-fingerprint-v4`; `attempted` 0 unless sources
arrived since; `store.clusters` equal to step 2's `clusters_after`.

**Step 12. The counts against `card-fingerprint-v3`** (seconds; both tables exist).

```zsh
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-v3 > ~/t20-counts-v4.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key} + (.value | {before_version, after_version, cards_only_before, cards_only_after, exact_fingerprints_changed, clusters_before, clusters_after, clusters_merged_into_another, clusters_divided, largest_before, largest_after})' ~/t20-counts-v4.json
```

Expected: step 2's figures exactly, if no source arrived between.

**Step 13. Shapes** (seconds).

```zsh
uv run python scripts/compare_card_clusters.py shapes --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --largest-clusters 3 > ~/t20-shapes.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, version: .value.fingerprint_version, clusters: [.value.described_clusters[] | {rank, cards, texts: .distinct_texts, pairs, nothing: .share_of_pairs_by_shape["sharing nothing"]}]}' ~/t20-shapes.json
```

Expected: step 3's figures, from the store's table: `version` `card-fingerprint-v4`, `nothing` 0.

**Step 14. The join sample, with step 4's seed** (seconds, then the person's time). The same 20
pairs as step 4. Put the seed step 4 printed in place of `SEED`.

```zsh
uv run python scripts/compare_card_clusters.py sample --count 20 --seed SEED --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-v3 --save-tallies ~/t20-sample-tallies.txt
cat ~/t20-sample-tallies.txt
```

**Steps 12 to 14 go to the PM before steps 15 and 16.**

**Step 15. The dev publish** (the rebuild again, about 19 minutes, since `caselist parse --publish`
always rebuilds; then one upload a caselist, the occurrence table).

```zsh
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/t20-publish-dev-hsld26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/t20-publish-dev-hspf26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/t20-publish-dev-hspolicy26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist openev --publish > ~/t20-publish-dev-openev.json; echo "exit $?"
for c in hsld26 hspf26 hspolicy26 openev; do jq -c '(.data // .error.details) | {caselist, fingerprint_version, attempted, publish: .publish.counts}' ~/t20-publish-dev-${c}.json; done
```

Expected: `exit 0`, `card-fingerprint-v4`, `attempted` 0, and one uploaded object a caselist.

**Step 16. Prod, only after the PM has read steps 12 to 14** (about 19 minutes), from the same dev
data directory, as the 2026-10-16 publish was:

```zsh
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/t20-publish-prod-hsld26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/t20-publish-prod-hspf26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/t20-publish-prod-hspolicy26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/t20-publish-prod-openev.json; echo "exit $?"
```

Expected: `exit 0` each.

**Step 17. Remove what the steps saved:**

```zsh
rm -r ~/.debate-research/dev/card-clusters-t20-preview ~/.debate-research/dev/card-clusters-v3
rm ~/t20-preview-counts-*.json ~/t20-preview-shapes.json ~/t20-preview-diagnosis-*.json ~/t20-parse-dev-*.json ~/t20-counts-v4.json ~/t20-shapes.json ~/t20-publish-*.json ~/t20-sample-tallies.txt
```

## Follow-up work

1. **The two pending-ruling xfails (E31, this task):** once the PM rules, either the expectations
   follow the ruling and the xfails go, or the design changes.
2. **Setting the limits (E31, this task, after step 8):** `MIN_CUT_SHARE`, `MAX_CONTAINER_CLUSTERS`
   and, from step 6, whether short bodies lacking an end are compared. Each change is a constant or
   one condition, and the tests that pin them are written.
3. **A publish-only path for the parsed store (E31 or E34).** `caselist parse --publish` always
   rebuilds, so the PM's order (rebuild, read, then publish) costs a second rebuild of about 19
   minutes, and prod a third.
4. **The agent rewrites a newer table with an older version (E34).** Any build older than the
   table's version puts its own back on the next parse stage. A guard could refuse to publish an
   occurrence table older than the one the bucket holds; today it is the reinstall in step 9.
5. **`tests/scripts/test_compare_card_clusters.py` has four pyright errors outside CI's scope**
   (`include = ["packages"]`): one unresolved import and three `object is not iterable`, the same in
   the start commit's file. Not this task's.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
