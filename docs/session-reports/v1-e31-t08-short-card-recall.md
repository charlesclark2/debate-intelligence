# Session report: v1-e31-t08-short-card-recall

| | |
|---|---|
| Task | `v1-e31-t08-short-card-recall` — Near-duplicate matching finds short cards and abbreviated disclosures |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t08-short-card-recall.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t08-short-card-recall.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t08-short-card-recall` |
| Session status | PARTIAL: ac1 to ac4 pass; ac5 (the operator's by-eye sample on the real corpus) is NOT RUN. The corpus-scale preview ran on all four caselists and shows no false-positive signal, on a store whose counts are provisional |

## Summary

All three mechanisms are fixed, one commit each, and precision is 1.000 on every row of both
labelled sets. On `v1-e31-t06`'s own rows, recall goes from 0.708 to 1.000 for full short cards,
from 0.250 to 1.000 for an abbreviated disclosure against a full copy, and from 0.583 to 1.000 for
abbreviated against abbreviated. On the set extended with 36 harder rows it is 0.946, 0.927 and
0.800, against targets of 0.90, 0.75 and 0.75. Cluster ids change, so `FINGERPRINT_VERSION` is
`card-fingerprint-v2`. The exact fingerprint is unchanged.

**Read these first:**

1. **Today's code already had a false positive, and fixing it is a fourth change the spec does not
   list.** One of the new hard negatives is a 13-word row that is only the opening two different
   cards share. Against the code as t06 left it, that row joined one of the two cards: the LSH
   banding happened to pair it with one and not the other, and containment was 1.0. Had the
   banding paired it with both, the two cards would have merged through it. So short bodies are
   no longer merged on containment through the banding at all. Every body that contains a short
   body is looked up, and it joins only when they are all one cluster (Deviation 1).
2. **Mechanism 2's fix moves nothing on t06's rows once mechanism 1 is fixed.** Every split among
   t06's full copies was mechanism 1's doing, so mechanism 1's fix healed all 33 abbreviated
   misses by itself. Measured alone on t06's clusterer, the linking rule takes that row from
   11 of 44 to 37 of 44. Its own value after mechanism 1 is on copies that stay split (two typos),
   which the new rows cover.
3. **Per-source records keep the old fingerprint stamp, by design.** They hold no fingerprint and
   no cluster id, so the skip key is unchanged and nothing is re-parsed. The next run rewrites
   every occurrence row under `v2`. `parsed-card-store.md` now says what the stamp means on each
   kind of record, and a test reads every record of every file after such a rebuild.
4. **Four files are outside `constraints.packages`** (Deviation 2): docstrings in
   `debate_core/domain/card_occurrence.py`, one literal in `tests/smoke/`, and the operator's tool
   `scripts/compare_card_clusters.py` with its test.

5. **On the real corpus as it is parsed today, the change moves little, and that figure is
   provisional.** The preview ran on all four caselists (openev in the session, the other three by
   the operator). No new cluster is made of more than 4 earlier ones, the largest clusters are
   unchanged, and no exact fingerprint changed: no false-positive signal. But across 207,056 cards
   only 105 clusters merged into another, 46 clusters shed short bodies, and **no abbreviated
   disclosure newly links to a full card**. The PM's heads-up of 2026-10-10 explains the last
   figure: `v1-e31-t09` found the parser marks a card `ABBREVIATED` whenever an ellipsis appears,
   so 21,278 of the 22,443 cards marked that way are whole cards, sent down the linking path and
   never compared as near-duplicates. Every count from the `2026.09.20-docx-1` store is therefore
   provisional, linked-abbreviation counts and cluster sizes most of all. See
   [Corpus-scale check](#corpus-scale-check).

**The Goal stays `InProgress`.** ac5 is the operator's run after the merge and cannot close in a
session. Merge with `scripts/task pr --partial`. The operator follow-up assumes one re-parse, t09's
under `2026.10.10-docx-2`, covers both tasks.

Commit ids in this report are as of the rebase onto `ddb1720`. A later `scripts/task sync` changes
them; the subject lines stay.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `short-card-matching` — Short cards and abbreviations cluster and link | Done, except the operator's part | The three fixes, the measurements before and after each, the version bump and the store's handling of it are done. The operator spot check (ac5) is not run. |

## Acceptance criteria

Every command ran from the task worktree on 2026-10-10.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — precision 1.000 on both labelled sets through `place`; recall at least 0.90 for full short cards, 0.75 abbreviated against a full copy, 0.75 abbreviated against abbreviated | PASS | `uv run pytest packages/debate_core/tests/evidence/test_short_card_recall.py -n0 --no-cov -s` → the table under [Recall, before and after](#recall-before-and-after). No row has a false positive. t06's rows: 24/24, 44/44, 12/12. Extended set: 35/37 (0.946), 51/55 (0.927), 16/20 (0.800). The variant set is 75/75. `test_recall_reaches_the_targets_with_precision_held` asserts the targets on both sets; `test_no_two_different_cards_share_a_cluster_on_either_labelled_set` asserts zero false positives. |
| **ac2** — each mechanism has a fixture case shown failing first against today's code and passing after | PASS | Commit `f878b6c` marks the cases `xfail(strict=True)` against the code as t06 left it: `25 passed, 16 xfailed`. A strict xfail fails the run if the test passes, so that commit is the red. Each fix's commit removes its marks: `d46e7ac` (mechanism 1: six cases, plus the shared-opening row and the zero-false-positive test), `ce76ef2` (mechanism 2: three), `090a9ef` (mechanism 3: four). One case listed under mechanism 2 at the baseline, t06's `a-s1-three-eight`, passed after mechanism 1 alone and was moved to a test that says so. |
| **ac3** — t06's table before and after, row for row; rebuild time on t06's fixture world and t03's 300-page synthetic file before and after, neither more than doubled | PASS | The table is below, with a column per fix. Timings under [Rebuild time](#rebuild-time): fixture world 2.59 ms before, 2.56 ms after; synthetic file 53.9 s before, 43.7 s after. On the real store, reading and placing took 196, 133, 285 and 39 s, against t06's whole rebuilds of 348, 214, 460 and 60 s. |
| **ac4** — if cluster ids change, `FINGERPRINT_VERSION` is bumped, and `parsed-card-store.md` and the t04 docstrings say what changed | PASS | `card-fingerprint-v2` (`bbdab52`). `fingerprints.py` lists both versions and what each changed. `near_duplicates.py`, `abbreviated_links.py`, `caselist_card_stats.py` and `domain/card_occurrence.py` describe the new rules. `parsed-card-store.md` has a "Fingerprint versions" section and the new meaning of `membership`. `grep -c card-fingerprint-v2 docs/data/parsed-card-store.md` → `3`. |
| **ac5** — operator-run: 20 newly joined pairs from the real corpus, drawn at random, checked by eye, tallies only | NOT RUN | Needs the merged code, the re-parsed store and a person. Steps are under Operator follow-ups. |
| Node: `uv run pytest packages/debate_core/tests/evidence` | PASS | `954 passed in 21.03s` |

Also run, not criteria of this task:

| Check | Result |
|---|---|
| Whole default suite, `uv run pytest -q --no-cov` | `5101 passed, 1 skipped, 1 warning in 97.33s`. The skip is the parser eval waiting on human corrections; the warning is the offline check that tries the network on purpose. Both are as on `dev`. |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff check .`, `uv run ruff format --check .` | `All checks passed!`, `576 files already formatted` |
| `uv run lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_command_blocks.py --base origin/dev`, `check_links.py`, `docs_index.py --check-descriptions` | all OK |
| `uv run scripts/validate_specs.py` | `OK: 327 files, 38 epics, 269 tasks, 20 releases` |
| Coverage of the rewritten modules, lines and branches | `near_duplicates.py` 99%, `abbreviated_links.py` 98%, `caselist_card_stats.py` 98%, `fingerprints.py` 100%. Every line this task wrote is covered. The lines that are not are t04's (an empty body in the banding loop, two cite-line overlap exits, the disclosure pager). |

## Recall, before and after

True positive / false positive / false negative pairs, through `CaselistCardStatsService.place`.
The first eight rows are t06's table, over t06's rows alone. "Before" is the code as t06 left it
(`1b9f94f`, `f878b6c`). Each later column adds one fix. Recall is in brackets where it is not
1.000; precision is 1.000 wherever the middle number is 0.

| Pairs | Before | + short bodies (mechanism 1) | + split-tolerant link (2) | + orphan groups (3) |
|---|---|---|---|---|
| Variant set, all | 71/0/4 (0.947) | 75/0/0 | 75/0/0 | **75/0/0** |
| Variant set, involving a short card | 2/0/4 (0.333) | 6/0/0 | 6/0/0 | **6/0/0** |
| Variant set, long cards only | 69/0/0 | 69/0/0 | 69/0/0 | **69/0/0** |
| Short-card set, all | 36/0/45 (0.444) | 80/0/1 (0.988) | 80/0/1 (0.988) | **81/0/0** |
| Short-card set, full short cards | 17/0/7 (0.708) | 24/0/0 | 24/0/0 | **24/0/0** |
| Short-card set, the full long card | 1/0/0 | 1/0/0 | 1/0/0 | **1/0/0** |
| Short-card set, abbreviated against a full copy | 11/0/33 (0.250) | 44/0/0 | 44/0/0 | **44/0/0** |
| Short-card set, abbreviated against abbreviated | 7/0/5 (0.583) | 11/0/1 (0.917) | 11/0/1 (0.917) | **12/0/0** |
| Extended set, all | 39/**1**/77 (0.336) | 93/0/23 (0.802) | 100/0/16 (0.862) | **104/0/12 (0.897)** |
| Extended set, full short cards | 18/**1**/19 (0.486) | 35/0/2 (0.946) | 35/0/2 (0.946) | **35/0/2 (0.946)** |
| Extended set, full long cards | 2/0/2 (0.500) | 2/0/2 (0.500) | 2/0/2 (0.500) | **2/0/2 (0.500)** |
| Extended set, abbreviated against a full copy | 12/0/43 (0.218) | 45/0/10 (0.818) | 51/0/4 (0.927) | **51/0/4 (0.927)** |
| Extended set, abbreviated against abbreviated | 7/0/13 (0.350) | 11/0/9 (0.550) | 12/0/8 (0.600) | **16/0/4 (0.800)** |

**Which mechanism each miss comes from**, the column the PM asked for. The test attributes every
missed pair from the labels, the clusters and t04's published rules, so it means the same thing
in every column:

| Pairs | Before | After all three |
|---|---|---|
| Variant set, all | 2 confirmation, 2 candidates | none |
| Short-card set, full short cards | 7 confirmation | none |
| Short-card set, abbreviated against a full copy | 33 split full copies | none |
| Short-card set, abbreviated against abbreviated | 4 split full copies, 1 no full copy | none |
| Extended set, full short cards | 15 confirmation, 4 candidates | 2 confirmation |
| Extended set, full long cards | 2 confirmation | 2 confirmation |
| Extended set, abbreviated against a full copy | 43 split full copies | 4 split full copies |
| Extended set, abbreviated against abbreviated | 5 split full copies, 8 no full copy | 4 no full copy |

"Confirmation" is two full copies under t04's thresholds; "candidates" is two that pass them and
were never compared (both mechanism 1). "Split full copies" is mechanism 2 and "no full copy"
mechanism 3.

**How the figures were measured.** Every expected figure in
`test_short_card_recall.py` was worked out by hand from the rows before the run that checked it,
with the reasoning in a comment beside it, and each matched. The one exception is recorded in the
file: the baseline false positive, which I did not predict.

**What each fix buys alone.** Fix 1 alone is the second column. Fix 2 alone, on t06's clusterer
(a scratch run that loads t04's module from git beside the new linking rule), gives the short-card
set 37/0/7 for abbreviated against a full copy and 11/0/1 for abbreviated against abbreviated.
Fix 3 only reaches cards with no full copy, so by construction it can add one pair to t06's rows;
I did not run it alone.

**The 12 pairs still missed on the extended set**, all of them rows this task added:

* **4, two typos in one copy** (Verran, 40 words; Ostrander, 85 words). The short rule tolerates
  one changed word, and the long card is t04's rule unchanged. Each copy stays its own cluster.
* **3, the abbreviations of those two cards against the two-typo copies.** The abbreviation joins
  the cluster with more copies and the split stays: it joins one cluster and merges none.
* **1, the Pryce 5 ... 5 cut.** It matches two different full cards, which share a third of their
  text. Not guessed.
* **3, the minimum 3 ... 3 cut of an orphan** against its three longer cuts. It shares no whole
  shingle with any of them, which is the price of a key a stock opening and closing cannot meet.
* **1, the Sable 4 ... 6 cut**, which two different orphans both open and close with. The set
  disagrees with itself, so none of the three is grouped.

### The labelled rows added

36 rows appended to `tests/fixtures/fingerprints/short_cards.jsonl`, marked `added_by`, committed
in `42c2ddf` before the measurement that uses them (`f878b6c`) and before any matching code. t06's
28 rows are byte-identical and are still measured on their own. All invented.

* **Fixture cases:** a short card with trimmed copies the banding cannot find, an OCR join and a
  dropped word (Kessler); full copies split by two typos, short and long, with their abbreviations
  (Verran, Ostrander); a card with no full copy, cut four ways (Quill).
* **Hard negatives, each the same author and year as a different card:**
  * a whole short card that is another card's first twelve words plus two;
  * two cards with thirteen shared opening words, and a third row that is only those words;
  * the next year's audit, the same sentence with two words different;
  * two full cards with the same five opening and thirteen closing words, and the 5 ... 5 cut both
    match;
  * orphan abbreviations that share an opening phrase, a closing phrase, or three words at each
    end;
  * a short cut two different orphans both open and close with;
  * an orphan that opens and closes like another card's linked 3 ... 3 cut.

## Rebuild time

Measured with a scratch script (not committed), `--no-cov`, on this Mac. "Before" is the source at
`1b9f94f`, put ahead of the worktree on `PYTHONPATH`.

| | Before | After |
|---|---|---|
| t06's structural fixture world (7 sources, 5 cards): a run that parses nothing and rebuilds, median of 20 | 2.59 ms | 2.56 ms |
| t03's 300-page synthetic file (5,250 cards), `place()` | 53.9 s | 43.7 s |

* **The pair above ran back to back on a quiet machine** (load average 4; the parse of the
  synthetic file, which this task does not touch, took 1.53 s in both).
* **Earlier runs on the same quiet machine** gave 54.1 s before and 44.9 s after mechanism 1.
* **Under load I could not get a comparison.** Another task was running, with a load average of
  12 to 16. Baseline took 66.6 s and the final code 72.4 s and 71.8 s in separate runs, while the
  untouched parse moved between 1.8 and 2.5 s. I discarded those and waited for the machine.
* **Why the synthetic file is faster.** Its 5,250 cards are 50 words each and near-copies of one
  another, so the banding makes millions of pairs. For a short pair the new code computes Jaccard
  and stops, where the old code went on to compute containment. The short step adds nothing here,
  because each card's first shingle holds its zone number and no other card has it.
* **The real rebuild does not double.** The short step's cost is one set intersection per body to
  find who holds each end shingle, then a handful of comparisons per short body, capped at 8 other
  clusters. On the real store, reading every stored card and placing it under the new rules took
  196 s (hsld26), 133 s (hspf26), 285 s (hspolicy26) and 39 s (openev). t06's whole rebuilds of the
  same store, which also write the aggregates and check the bucket, took 348, 214, 460 and 60 s. The
  two are not the same measurement, so this shows the new placement fits inside the old rebuild's
  time, not how much faster or slower it is.

## Corpus-scale check

`scripts/compare_card_clusters.py counts` reads a caselist's `occurrences.jsonl` as "before",
places the same stored cards in memory with the checked-out rules as "after", and prints counts.
It writes nothing. openev ran in the session; the operator ran the other three on 2026-10-10 from
the task worktree and pasted the file of counts back.

**Every figure here is provisional.** They are from the `2026.09.20-docx-1` store, in which most
cards marked `ABBREVIATED` are whole cards (Summary, point 5). When t09's parser fix re-parses the
corpus, those cards become `FULL` and are clustered, which will move cluster counts far more than
this task does.

| | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| Cards | 67,914 | 44,298 | 87,556 | 7,288 |
| Clusters before | 12,102 | 9,828 | 18,366 | 5,467 |
| Clusters after | 12,107 | 9,835 | 18,326 | 5,466 |
| Earlier clusters that merged into another | 37 | 18 | 49 | 1 |
| New clusters made of several earlier ones | 31 | 17 | 44 | 1 |
| ... made of 2 | 26 | 16 | 40 | 1 |
| ... made of 3 to 5 | 5 | 1 | 4 | 0 |
| ... made of 6 or more | 0 | 0 | 0 | 0 |
| Most earlier clusters in one new cluster | 4 | 3 | 4 | 2 |
| Earlier clusters now divided | 17 | 20 | 9 | 0 |
| Abbreviated newly linked to a full card | 0 | 0 | 0 | 0 |
| Abbreviated newly grouped with other abbreviated cards (card positions) | 580 | 170 | 862 | 2 |
| Abbreviated no longer linked | 0 | 0 | 0 | 0 |
| Largest cluster before: cards (distinct texts) | 620 (48) | 541 (72) | 1,165 (165) | 21 (14) |
| Largest cluster after | 620 (48) | 541 (72) | 1,164 (164) | 21 (14) |
| Exact fingerprints changed | 0 | 0 | 0 | 0 |
| Seconds to read and place | 195.9 | 133.1 | 284.6 | 39.1 |

What the figures say:

* **No false-positive signal.** The PM's stop line was one cluster absorbing hundreds of distinct
  cards. The most earlier clusters in any new cluster is 4, and 83 of the 93 new clusters made of
  several are made of two. The largest clusters did not grow.
* **The exact fingerprint did not change** for any of 207,056 cards, which is the forbidden-list
  item checked on real data.
* **The clusters went up in two caselists, not down.** 46 earlier clusters were divided: short
  bodies that `v1` had joined to a card by containment through the banding, and that `v2` leaves
  out because they are inside more than one cluster, or are under a quarter of the card's size, or
  do not have both ends inside it. In hsld26, 17 divided clusters became 59, which more than
  cancels its 37 merges. I cannot say from counts which of these were wrong joins removed and which
  were right joins lost. This is the cost side of Deviation 1, and `sample --divided` exists so a
  person can look (Operator follow-ups, step 4).
* **No abbreviation newly links to a full card.** Neither mechanism 1's healing of splits nor
  mechanism 2's rule linked one more abbreviated disclosure to a full copy, on any caselist. The
  labelled sets say the rules work when the situation arises; this store says it arises rarely
  there, or that the cards it would arise on are among the 21,278 mislabelled ones. The count that
  matters is the one after t09's re-parse.
* **Mechanism 3 is where the movement is:** 1,614 card positions in groups of abbreviated cards
  with no full copy. A position is one card in one file, and the same file is uploaded many times,
  so this is far fewer distinct cuts than positions. Under t09's fix many of these may turn out to
  be whole cards with an omission, which would then be clustered by text instead.
* **The largest clusters were already large**: 1,165 cards of 165 distinct texts in hspolicy26
  under `v1`. That is not this task's doing and I have not looked into it; it is listed under
  Follow-up work for whoever samples the corpus.

**`--before-rules` checked on real data.** For the combined re-parse the tool has to compute
"before" from the old rules (Operator follow-ups). On openev, the rules as they were at `8c082b5`
reproduce the stored `v1` table exactly: 5,467 clusters on both sides, nothing merged and nothing
divided, in 43 s.

## Mutation runs

Each mutant ran in a new `HYPOTHESIS_STORAGE_DIRECTORY` made with `tempfile.mkdtemp` and checked
empty first. None of these tests is a Hypothesis property, so the isolation is set as working
agreement 8 asks and cannot affect them. Each mutant was an exact replacement that had to be found
once, the suite ran without `-x`, the file was restored from git, and `git status --porcelain` was
empty after every run. Three batches of 95, 66 and 72 s, and one re-run of 10 s. The seven test
files that cover this change ran each time (246 tests).

The PM's five:

| Mutant | Result |
|---|---|
| The short-body step applied to long bodies (the length line removed) | CAUGHT: 2 failed. `test_a_long_bodys_cut_is_still_left_to_the_banding` and t04's `test_thresholds_are_configurable` |
| An abbreviation linked to two clusters, by merging the full-card clusters it matched | CAUGHT: 4 failed, among them `test_the_copies_two_typos_split_off_stay_split` and `test_linking_abbreviations_never_changes_a_full_cards_cluster` |
| The same, by placing the abbreviation in both clusters | CAUGHT, with a caveat: 1 failed on its assertion (`test_every_card_is_placed_once_in_the_order_given`). 49 more errored in the shared fixture, where a strict `zip` refused the extra placement. The errors are the mutant's effect at run time, not a collection failure, but only the one failure is counted as the catch |
| Abbreviation-to-abbreviation linking on cite alone | CAUGHT: 21 failed, every hard negative among orphans |
| The version bump skipped | CAUGHT: 3 failed. The store test (`..._leaves_no_old_stamp_on_a_new_cluster_id`), t04's literal and the smoke check |
| The exact fingerprint altered: no casefold | CAUGHT: 16 failed, t04's hand-written digests among them |
| The exact fingerprint altered: punctuation dropped | CAUGHT: 13 failed |

**On the first row.** The PM's mutant was "the short-body threshold applied to long cards". This
design has no separate threshold for a long card to be given by mistake. The one-changed-word rule
is never looser than t04's 0.9 containment at or above the line, which is how the line was chosen,
and `test_the_short_line_is_where_the_containment_threshold_admits_one_changed_word` shows it at 60
and 59 shingles. What the length line does guard is which bodies get the enumeration step, and that
is the mutant I ran.

The guards this task added:

| Mutant | Result |
|---|---|
| Short containment back through the banding (the false positive's cause) | CAUGHT: 9 failed |
| One-word rule without unchanged words after the change | CAUGHT: 3 failed, unit cases only. The labelled row built for this (a card that is another's first twelve words plus two) does not reach the rule, because its last shingle is not in the other card and it is never a candidate |
| A short body joins any container, not the one | CAUGHT: 9 failed |
| No size limit on the container | CAUGHT: 1 failed |
| No limit on container clusters | CAUGHT: 1 failed |
| A split tolerated without shared text | CAUGHT: 5 failed, t04's two-cluster test among them |
| A split never tolerated | CAUGHT: 7 failed |
| An orphan group kept although it disagrees with itself | CAUGHT: 9 failed |
| Orphans grouped on three words at each end | CAUGHT: 7 failed |
| Cite-line keys grouped | **SURVIVED, then caught.** The first test put the two keys in different buckets whatever the check did. Rewritten as two cite-only entries under one cite, one giving no opening words of its card: 1 failed |
| One text under two cites grouped | CAUGHT: 1 failed |
| A cut that matched two different full cards grouped with a third card's cut | CAUGHT: 1 failed. This test did not exist until I listed the guard for mutation |
| Grouping removed | CAUGHT: 14 failed |

**One check deleted.** Coverage showed the cite comparison inside `_same_card_by_key` could never
be reached: keys are bucketed by cite before any two are compared. No mutant could tell it from
its absence, so it is gone and the docstring says the caller only compares keys of one cite.

## Files changed

**Matching (`packages/debate_core/src/debate_core/evidence/`)**
* `near_duplicates.py`: the short-body step, `contained_but_for_one_word`, `word_shingles`, and the
  constants `SHORT_BODY_SHINGLES`, `MIN_CUT_SHARE`, `MAX_CONTAINER_CLUSTERS`.
* `abbreviated_links.py`: `link_abbreviated` tolerates a split; `matching_full_cards`;
  `group_unmatched_abbreviations`; `SPLIT_COPY_OVERLAP`; `FullCardWords.copies`.
* `fingerprints.py`: `card-fingerprint-v2`, and what a version names.

**Application (`packages/debate_core/src/debate_core/application/`)**
* `caselist_card_stats.py`: `place()` counts copies, links, then groups the unmatched.
* `ports/parsed_store.py`: the `fingerprint_version` field description and the skip-key docstring.

**Domain**: `domain/card_occurrence.py`, docstrings and field descriptions only (Deviation 2).

**Tests**: `tests/evidence/test_short_card_recall.py` (the measurement), `test_near_duplicates.py`
and `test_fingerprints.py` (new sections after t04's tests; one literal changed in t04's),
`tests/application/test_caselist_card_stats.py`, `tests/application/test_caselist_parse.py` (the
store test), `tests/smoke/test_caselist_cards.py` (one literal).

**Fixtures**: `tests/fixtures/fingerprints/short_cards.jsonl`, 36 rows appended.

**Operator tool**: `scripts/compare_card_clusters.py` and `tests/scripts/test_compare_card_clusters.py`.

**Docs**: `docs/data/parsed-card-store.md`; `docs/data/caselist-parse-report.md` (a note that its
cluster counts are `v1`'s, and the openev preview).

## Deviations from the spec

1. **A fourth mechanism, fixed.** The spec lists three. The adversarial rows found a false
   positive in the code as t06 left it (Summary, point 1), and the spec forbids any false positive
   on either labelled set, so it had to end at zero. The fix changes more than "candidates and
   confirmation for short bodies": a short body inside two clusters no longer joins either, where
   before it joined whichever the banding paired it with. The PM may want the spec's description
   to name it.
2. **Outside `constraints.packages`.**
   * `debate_core/domain/card_occurrence.py`: docstrings and field descriptions only. ac4 asks
     that "the t04 docstrings say what changed", and this is t04's file. No behaviour and no enum
     value changed.
   * `tests/smoke/test_caselist_cards.py`: the literal `card-fingerprint-v1` became `v2`.
   * `scripts/compare_card_clusters.py` and its test under `tests/scripts/`: ac5 is operator-run
     and needs a tool, and the corpus-scale check uses the same one. `scripts/parser_corpus_health.py`
     is the precedent.
3. **No new `ClusterMembership` value.** An abbreviated card grouped with other abbreviated cards
   is recorded as `ABBREVIATED_LINK`, whose documented meaning is widened to "placed by its link
   key". A separate value would be clearer to a reader, and is a domain and store-schema change
   outside this task. See Follow-up work 2.
4. **The banding is not changed.** The spec says t04's 32x4 banding "missed one pair outright".
   That pair is now found by looking up who holds a short body's end shingles, not by different
   bands. Two long bodies are banded and confirmed exactly as before.
5. **The script does more than the four counts the PM listed.** It also prints clusters divided,
   exact fingerprints changed, how many earlier clusters each new cluster is made of, distinct
   texts in the largest cluster, and cards present in only one table. Counts only. After the PM's
   heads-up about t09 it gained `--before-rules` (the earlier rules taken from git, for a store
   that never had a `v1` table), `--save-before` and `sample --divided`.
6. **A local rebase in place of `scripts/task sync`**, twice. `origin/dev` gained the
   generated-files refresh (#211) and a PM spec batch (#212) during the session. I ran
   `git fetch origin dev` and `git rebase origin/dev` in the worktree, which is what `sync` does for
   an unpushed branch. Nothing was pushed. t09 had not merged at either point, so the corpus counts
   have not been re-run against its fix.

## Decisions and assumptions

**Short bodies (mechanism 1).**

* **The line is 60 shingles, 64 words, and is derived.** The costliest change the rule tolerates
  is a word split in two inside a cut, which takes 6 shingles from the cut. That is a tenth of 60,
  so from 60 up t04's 0.9 containment already admits it. t06's 60-word reporting line is kept in
  the measurement so its table reads row for row.
* **One changed word, flanked.** Changed, split in two, run together, dropped or added, with five
  unchanged words on each side. Two cards from one article that open alike and then diverge differ
  from that point to the end; a typo does not.
* **A plain lower threshold would have been wrong, and a hard negative t04 wrote shows it.** A
  rule of "the smaller body may miss five shingles" merges t04's `f-trimmed-end` with `g-original`,
  two different cards that share eleven opening words.
* **Joined only when not a guess.** Every confirmed container must be in one cluster. This is
  t04's own rule for abbreviations, applied to short full cards.
* **At most four times its size** (`MIN_CUT_SHARE`, 0.25). This is a judgement, not a derivation.
  It keeps a body that is really a whole section of a file, parsed as one card, from gathering the
  short cards it contains into one cluster. Such a body still counts against a short body: inside
  it and inside one real card is inside two. The cost is that a 40-word cut of a 300-word card is
  not found, which the banding never found either.
* **Left alone past 8 other clusters** (`MAX_CONTAINER_CLUSTERS`). A body whose first and last
  shingles are both in more than eight other clusters opens and closes with stock phrases. This
  also bounds the step's cost on templated input.

**Which cluster an abbreviation joins, and why (mechanism 2).**

* **The cluster holding the most disclosed copies among its matches**, the smallest cluster id on
  a tie. That is where most of the card's disclosures are already counted, so the fewest pairs are
  left apart, and the choice does not depend on the order cards arrive in.
* **Only when the matches are one card.** Every match outside the chosen cluster must share at
  least half of the smaller body's shingles with a match inside it. The full cards' text is there
  to read, so the rule reads it. Same cite, same opening and closing words and most of the text is
  one card split; less is two cards and no link, which keeps t04's two-cluster test passing
  untouched.
* **One cluster, never two.** The clusters it matched keep their ids and their members. A full
  card's cluster does not depend on which abbreviations are present, and a test places the full
  cards alone to show it.

**The key among abbreviations with no full copy (mechanism 3).**

* Same short-cite key; consistent at both ends; at least three words shared at each end and a
  whole five-word shingle at one. Five consecutive words is the unit the clusterer itself treats
  as the same text. Three at each end is where a stock opening meets a stock closing.
* A group is a connected set under that rule, kept only if every pair in it is consistent.
  Otherwise the whole set stays unlinked.
* Only among cards that matched no full card. An orphan is never carried into a full card's
  cluster by a linked abbreviation it resembles.
* Keys read from the cite line take no part: their "opening words" start with cite text and may
  be nothing else.
* One text under two short cites joins neither author's group, since it could carry one into the
  other. Every unlinked card with a grouped text follows it, so identical text never splits.

**The version and the store.**

* `FINGERPRINT_VERSION` now names the matching rules as a whole, and `fingerprints.py` lists what
  each version changed. An exact fingerprint under `v1` is the same digest under `v2`.
* Per-source records hold nothing fingerprint-dependent. I checked `ParsedCard` and the two record
  models for any fingerprint or cluster field, and the store test scans every old-stamped record at
  any depth.
* After the rebuild, `--publish` uploads `occurrences.jsonl` alone: the index and failures rows are
  copied from the per-source entries, so their bytes do not change.

**What the session read from the real store.** The openev preview, twice, and the check of
`--before-rules` on openev: counts only. The other three caselists' counts were run and pasted by
the operator. Before any of that, while
writing the script, I printed the first five rows of openev's `occurrences.jsonl` to my own tool
output to see a row's shape. They hold digests, element indices and the `camp` field. Nothing from
them is in a commit, a log or this report, and the script never prints a row.

## Operator follow-ups

**Done already:** the corpus-scale preview for hsld26, hspf26 and hspolicy26 (2026-10-10, from the
task worktree, 196, 133 and 285 s). Its counts are in [Corpus-scale check](#corpus-scale-check).

**What is left is ac5, and it assumes one re-parse covers both tasks.** `v1-e31-t09` changes the
parser, so its own operator run re-parses every source into `parsed/<caselist>/2026.10.10-docx-2/`.
If this task has merged by then, that run builds the new directory's aggregates under
`card-fingerprint-v2` and publishes them, and this task needs no rebuild of its own. What it adds
is the comparison and the by-eye sample below.

One thing follows from that order: the new directory never has a `v1` table to compare with. So
"before" is computed, by placing the new directory's cards with the matching rules as they were
just before this task merged, taken from git.

Don't run any of this while `caselist pull` is running: `uv run debate-research caselist runs
--last 1` shows the last run.

**Step 1. Check both tasks are merged and t09's re-parse has run** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t08-short-card-recall:'
git log --oneline -1 --grep='^v1-e31-t09-first-corpus-parse-findings:'
ls ~/.debate-research/dev/parsed/hsld26
jq -r '.fingerprint_version' ~/.debate-research/dev/parsed/hsld26/2026.10.10-docx-2/occurrences.jsonl | sort | uniq -c
```

Expected: `dev`; `git status` prints nothing; each `git log` prints that task's squash-merge
commit; `ls` shows `2026.10.10-docx-2` beside `2026.09.20-docx-1`; and the last line is one count
of `card-fingerprint-v2`.

* **No `2026.10.10-docx-2` directory:** t09's re-parse has not run. Run t09's operator steps first.
* **It says `card-fingerprint-v1`:** t09's re-parse ran before this task merged. See "If the new
  directory was built under `v1`" below.
* **t09's directory has another name:** use that name here, and nowhere else. The script finds the
  newest directory by itself.

**Step 2. Compute "before" once and print the counts** (about 15 to 25 minutes; reads the store,
and writes four files of digests and cluster ids, no text, inside the dev data directory):

```zsh
T08=$(git log -1 --format=%H --grep='^v1-e31-t08-short-card-recall:')
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before-rules "${T08}^" --save-before ~/.debate-research/dev/card-clusters-before > ~/card-clusters-counts.json; echo "exit $?"
cat ~/card-clusters-counts.json
```

`"${T08}^"` is the commit just before this task's merge. On the old store this step's work took
196, 133, 285 and 39 s; the re-parsed store has more full cards, so allow longer.

Expected: `exit 0`, and for every caselist `before_version` `card-fingerprint-v1`, `after_version`
`card-fingerprint-v2`, `exact_fingerprints_changed` 0, `cards_only_before` and `cards_only_after`
0, and 0 under `absorbed` → `101 or more`. Paste the file back: it holds counts only. I have no
expected cluster counts to give, because the provisional ones above are from the old parse.
Anything under `21 to 100`, stop and send it before the sample.

**Step 3. The by-eye sample of newly joined pairs** (ac5; seconds to start, then about 15 minutes).
It draws 20 pairs at random across the four caselists and shows them one at a time. For each, press
`s` (same card), `d` (different card) or `u` (unsure), then Enter. Each pair is cleared from the
terminal, scrollback included, before the next. It will not run with its output redirected.

```zsh
uv run python scripts/compare_card_clusters.py sample --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before
```

When it ends it prints the counts again, how many pairs it drew, the seed, and the tallies by kind
and verdict. The last lines, from `Drew` on, are what is recorded: paste those back. The cards are
real disclosures, so nothing from them goes into a message, a screenshot, an issue or a file. One
"different card" is a false positive on the real corpus. If t09's prod publish has not run yet,
take this sample between its dev and prod steps, so that verdict comes before prod.

**Step 4. The same for pairs that were divided** (not part of ac5; about 10 minutes). These are
pairs that shared a cluster under `v1` and do not under `v2`. Here "same card" means a join was
lost and "different card" means a wrong join was removed:

```zsh
uv run python scripts/compare_card_clusters.py sample --divided --count 10 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before
```

Paste back the lines from `Drew` on.

**Step 5. Remove what step 2 saved:**

```zsh
rm -r ~/.debate-research/dev/card-clusters-before
rm ~/card-clusters-counts.json
```

### If the new directory was built under `v1`

That is, t09 merged and its re-parse ran before this task merged. The new directory then holds a
real `v1` table, which is a better "before" than a computed one, and one more run rebuilds it
under `v2`. Nothing is parsed again.

Save the tables first (seconds), with the directory name from step 1:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
mkdir -p ~/.debate-research/dev/card-clusters-before
for c in hsld26 hspf26 hspolicy26 openev; do cp -p ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/occurrences.jsonl ~/.debate-research/dev/card-clusters-before/${c}.jsonl; done
jq -r '.fingerprint_version' ~/.debate-research/dev/card-clusters-before/*.jsonl | sort | uniq -c
```

Expected: one line, every row `card-fingerprint-v1`.

Then rebuild and publish in dev, as the removal runbook's step 5 does (about 20 minutes on the old
store's timings):

```zsh
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/parse-dev-hsld26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/parse-dev-hspolicy26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/parse-dev-hspf26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist openev --publish > ~/parse-dev-openev.json; echo "exit $?"
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, fingerprint_version, attempted, store, elapsed_seconds, publish: .publish.counts}' ~/parse-dev-${c}.json; done
```

Expected for each: `exit 0`, `fingerprint_version` `card-fingerprint-v2`, `attempted` 0, and
`publish.uploaded` 1, because `occurrences.jsonl` is the only file whose bytes change.

Then the counts, which take seconds because both tables exist:

```zsh
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before
```

Then steps 3 and 4 above, then prod, from the same dev data directory, only if the sample found
no different card (each variable is on the command line, so nothing is left pointing at prod):

```zsh
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/parse-prod-hsld26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/parse-prod-hspolicy26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/parse-prod-hspf26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/parse-prod-openev.json; echo "exit $?"
```

Expected: `exit 0` each. Then step 5.

### If t09 is not going to merge soon

The same steps work on the `2026.09.20-docx-1` store with that directory name, and would let
`v1-e32-t03` start on `v2` aggregates. Their sample would be drawn from a store whose abbreviated
cards are mostly mislabelled, so I would not close ac5 on it. That is the PM's call.

## Follow-up work

1. **Long bodies can still be merged through a shared fragment (E31).** This task stopped it for
   short bodies. Two long bodies are still matched on containment through the banding, so a
   fragment of 64 words or more that two different long cards both contain joins whichever the
   banding pairs it with, and merges them if it pairs both. The banding also still misses a long
   cut that shares under about 40% of its card's shingles (t04's original follow-up). The fix is
   the same step without the length line, and its cost on the real corpus would need measuring
   first.
2. **A `ClusterMembership` value for abbreviation-only clusters (E32 to decide).** Today a reader
   tells them apart by whether the cluster holds a full card. If `v1-e32-t03` wants to show
   "nobody disclosed this card in full", a value of its own is the clean way, with a store schema
   note.
3. **`v1-e32-t03` and cluster ids.** It should check `fingerprint_version` on the occurrence rows
   it reads and refuse a mismatch, and key anything durable on `exact_fingerprint`, never on
   `cluster_id`. `parsed-card-store.md` now says both.
4. **The minimum cut.** A 3 ... 3 cut with no full copy links only to an identical 3 ... 3 cut.
   If the operator's counts show most unlinked abbreviations are that shape, the key is the thing
   to revisit, with more labelled negatives first.
5. **Identical abbreviated text under two cites is one exact fingerprint**, and so one cluster.
   This is t04's definition of the exact fingerprint, which this task may not change. It is right
   far more often than wrong (a cite typo), and is noted so nobody is surprised by it.
6. **`docs/data/caselist-parse-report.md`** needs the cluster counts after t09's re-parse and the
   sample's tallies (the PM's close-out, as for t06). The provisional preview counts are recorded
   there now, marked as such.
7. **The spec's `constraints.packages`** could name `debate_core.domain` (docstrings), `tests/smoke`
   and `scripts`, for the reasons in Deviation 2.
8. **The divided clusters (E31, after t09).** 46 clusters shed short bodies under `v2` on the old
   store. Step 4 of the operator follow-ups samples them. If most verdicts are "same card", the
   limit to revisit is `MIN_CUT_SHARE`, the one constant here that is a judgement.
9. **Re-measure after t09 (this task's own counts).** Every corpus figure in this report is from
   the old parse. Step 2 of the operator follow-ups produces the real ones.
10. **Very large clusters under `v1`.** hspolicy26's largest cluster is 1,165 cards of 165 distinct
    texts, before this task changed anything. It may be one much-read card and its cuts, or a chain
    of containment merges among long cards (Follow-up 1). Nobody has looked. `sample` could be
    pointed at a cluster by id with a small change if the PM wants that checked.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
