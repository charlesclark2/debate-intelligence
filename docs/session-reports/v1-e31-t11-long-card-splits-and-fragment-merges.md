# Session report: v1-e31-t11-long-card-splits-and-fragment-merges

| | |
|---|---|
| Task | `v1-e31-t11-long-card-splits-and-fragment-merges` — Copies split apart by the short-body rule, and long bodies merged through a fragment |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t11-long-card-splits-and-fragment-merges.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t11-long-card-splits-and-fragment-merges.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t11-long-card-splits-and-fragment-merges` |
| Session status | PARTIAL: the diagnosis, the sampling tool and two fixes are done and tested. The operator's parts are NOT RUN, and are now written for the store after `v1-e31-t12`'s re-parse: the divided pairs explained pair by pair (the rest of ac1), the by-eye sample of the largest clusters (ac2), and the counts and samples under `v3` (ac4) |

## Summary

The hypothesis is right for about seven in ten of the 81 divided pairs, and `MIN_CUT_SHARE`
explains 7 of them. A counts-only diagnosis now says, for every body that a body outside its
cluster contains, which limit kept it out. It found two defects in the short-body step, both fixed
with a fixture shown failing first, so the matching rules are `card-fingerprint-v3`. Precision is
1.000 on every row of both labelled sets and no row's recall moved. Long-body matching is not
changed, and the largest clusters are not broken up: both need the by-eye sample first, and the
tool for it is built.

**Read these first:**

1. **The two fixes help, and they do not undo the divisions.** A short cut inside nested copies of
   a card now joins the smallest copy, where `v2` left it alone. But the pair the operator judged
   "same card" was the cut and the *longer* body, and those two are still apart, because the two
   long copies are still two clusters. The estimate is 45 clusters merging across the corpus, none
   divided, and the largest clusters unchanged but for 7 cards. See [The fixes](#the-fixes).
2. **The cause the diagnosis points at is in long-body matching, and I did not change it.** 3,563
   long texts are a cut of a body in another cluster, against 411 short ones. The banding pairs a
   cut with its container about nine times in ten at half the container's size and about one time
   in eight at a quarter. Joining long cuts the way short ones are joined would take 1,232 of
   them, and 288 of those would land in a cluster with a text they share nothing with. That is
   Decision 1, with the alternative.
3. **hspolicy26's largest cluster is not one passage.** 6,409 of its 13,695 pairs of distinct texts
   share no five-word run, and 127 of its 166 texts (755 of 1,172 cards) share nothing with its
   most-read text. It is a chain held together mostly by bodies that hold several unrelated parts.
   Whether that is one long source cut at many extents or several cards merged is for a person:
   `sample --largest 1 --least-alike` shows the pairs that share least.
4. **I ran more of the corpus diagnosis than the brief said to** (Deviation 1). The brief said
   openev in the session and the rest to the operator, because `--before-rules` takes 4 to 9
   minutes a caselist. The part that needs no "before" reads the store's own table and takes under
   a minute, so I ran it on all four. One run went over: see the deviation.
5. **`scripts/task sync` ran three times**: after `v1-e01-t27`, after `v1-e34-t22`, and after
   `v1-e31-t12`. The whole suite ran again each time, in four parts; on top of t12, 6,598 passed,
   1 skipped and t12's own 2 expected failures. t12 also appended to
   `docs/data/caselist-parse-report.md`, so the last rebase stopped there: both additions are
   kept, this task's as a subsection of the 2026-10-11 re-parse and t12's after it, and none of
   t12's lines changed.
6. **The operator steps are for the store after t12's re-parse** (PM's note of 2026-10-13). t12
   bumps the parser to `2026.10.12-docx-3`, and one re-parse covers both tasks: if this task
   merges first, the new directory is built under `card-fingerprint-v3` from the start, and
   "before" is computed from git. The figures in this report are from `2026.10.10-docx-2` and are
   a diagnosis of that store, not the figures to expect to the digit.

**The Goal stays `InProgress`.** Three criteria have parts only the operator can close. Merge with
`scripts/task pr --partial`.

Commit ids in this report are as of the sync onto `af18476`, the generated-files refresh after t12. A later sync changes them; the
subject lines stay.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `long-card-matching` — Long-card splits and merges fixed | Done, except the operator's parts and the long-body change | The diagnosis, the sample by cluster, two fixes with the version bump, and the operator's commands are done. Long-body matching and the largest clusters are diagnosed and not changed (Decisions 1 and 2). |

## Acceptance criteria

Every command ran from the task worktree on 2026-10-12.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — a read-only diagnosis of the divided pairs on the dev store, by counts: whether the longer copies are in more than one cluster, and which threshold kept them apart | PASS on the store's own table for all four caselists | `uv run python scripts/compare_card_clusters.py diagnose --caselist <caselist>` → the tables under [The diagnosis](#the-diagnosis). The banding pairs exactly 81 short cuts with a container outside their cluster (45, 23, 12, 1), the count of divided pairs on 2026-10-11, and each has its limit named. |
| **ac1**, matched pair by pair to the 81 divided pairs | PASS for openev; **NOT RUN** for the rest | openev: `counts --caselist openev --before-rules f5ad52b --save-before <scratch>` → 5,865 to 5,864 clusters, 2 merged, 1 divided, 58 s, the 2026-10-11 row exactly; then `diagnose --caselist openev --before <scratch>` → `"pairs": 1`, explained, nothing unexplained. The other three need the earlier placement, 4 to 9 minutes each. Rewritten for the re-parsed store as Operator follow-ups, step 6. The mechanism was checked again after the t12 sync: on openev the rules before `v1-e31-t08` give the same 2 merged and 1 divided, 79 s. |
| **ac2** — `sample` can be pointed at a cluster by id | PASS | `sample --cluster ID` takes an id or the start of one, and `sample --largest RANK` finds it by size. `uv run pytest tests/scripts/test_compare_card_clusters.py -n0 --no-cov` → `29 passed`, among them both forms shown to a terminal, each pair cleared, tallies alone at the end. On the real store, drawing without showing: 15 s to the first pair of hspolicy26's largest cluster, and 13,695 pairs available, the diagnosis's own figure. |
| **ac2**, the operator checks 10 pairs from each of the three largest clusters per caselist | **NOT RUN** | Needs a person at a terminal, and is to be taken on the re-parsed store. Operator follow-ups, step 5. |
| **ac3** — each defect has a synthetic fixture shown failing first; recall on both labelled sets does not fall; precision stays 1.000 | PASS | Commit `fec2841` marks the fixtures `xfail(strict=True)` against `v2`: `69 passed, 10 xfailed`. `47b3576` (fix 1) removes its mark: `188 passed, 9 xfailed`. `38508c0` (fix 2) removes the rest: `969 passed`. A third fixture, for a refinement of fix 2, was run against the committed rule before the change: `1 failed, 2 passed`, then `3 passed` (`b89e220`). The labelled table is identical before and after: [Labelled sets](#labelled-sets-before-and-after). |
| **ac4** — if clustering changes, `FINGERPRINT_VERSION` is bumped | PASS | `card-fingerprint-v3` (`38508c0`). `fingerprints.py` lists what it changed; `parsed-card-store.md` has its row. Mutant "the version bump skipped" → 3 tests fail. |
| **ac4**, operator-run: the counts and both samples again after the rebuild, recorded in `caselist-parse-report.md` | **NOT RUN** | Needs the merged code and t12's re-parse. Operator follow-ups, steps 2 to 4. The session's estimate and openev's full preview, on the old directory, are recorded there now, marked as such. |
| Node: `uv run pytest packages/debate_core/tests/evidence` | PASS | `1103 passed in 8.14s`, after the t12 sync (1,000 before it) |

Also run, not criteria of this task:

| Check | Result |
|---|---|
| Whole default suite after the sync onto t12, `uv run pytest --part K/4 -q` for K = 1 to 4, one command each | `1643 passed in 36.38s`, `1651 passed, 1 xfailed in 34.25s`, `1653 passed, 1 skipped, 1 warning in 31.42s`, `1651 passed, 1 xfailed in 31.93s`: 6,598 passed. The skip is the parser eval waiting on human corrections, and the two expected failures are t12's own, as on `dev`. The earlier syncs gave 5,895 and 5,976 passed. |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff check .`, `uv run ruff format --check .` | `All checks passed!`, `637 files already formatted` |
| `uv run lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `check_command_blocks.py --base origin/dev`, `check_links.py`, `docs_index.py --check-descriptions` | all OK |
| `uv run scripts/validate_specs.py` | `OK: 347 files, 38 epics, 289 tasks, 20 releases` |
| Coverage of the changed modules, lines and branches | `cluster_diagnosis.py` 100%, `fingerprints.py` 100%, `near_duplicates.py` 99% (line 310, `v1-e31-t04`'s empty-body exit in the banding loop), `caselist_card_stats.py` 98% (two lines of `v1-e31-t04`'s) |

## The diagnosis

`scripts/compare_card_clusters.py diagnose` reads a placement and prints counts. The logic is
`debate_core/evidence/cluster_diagnosis.py`, which confirms a container with the same function the
clusterer uses, so it cannot drift from the rule it explains.

**What it counts.** A body is a *cut* of another when the other is at least as large, holds its
first and last five-word runs, and holds nine-tenths of its five-word runs (or, for a body under 64
words, holds it but for one word). The diagnosis lists every body with such a container outside
its own cluster and names the limit that kept it out. For a short cut inside several clusters it
also reads the containers' own text: the clusters *read as one card* when a container of each
shares at least half of the smaller body's text with a container of the other, which is the test
`v1-e31-t08` already uses to tell a split card from two cards for an abbreviation.

### On synthetic stores

Every case is a run of numbered made-up words, so each expected figure is arithmetic: a body of
`n` words has `n - 4` five-word runs. 27 cases in `test_cluster_diagnosis.py`, one per limit and per
reading, each worked out by hand before it ran. 22 of the first 23 held on the first run; the one
that did not was a comparison I had written wrongly in the test. The script is tested on an
invented store of five cards built in a temporary directory.

### On openev

| | |
|---|---|
| `counts --before-rules f5ad52b` (the commit before `v1-e31-t08`) | 5,865 to 5,864 clusters, 2 merged, 1 divided: the 2026-10-11 row |
| `diagnose --before` that placement | 1 divided pair, explained: its part was joined to the rest only through a short body that is nine-tenths inside a longer one lacking one of its ends |
| Bodies with a container outside their cluster | 247 of 6,372 texts: 235 long, 12 short |

openev's one divided pair does not fit the hypothesis. It is a short body the earlier rules merged
on containment alone, which `v2` never compares because the longer body does not hold both its
ends. openev has 117 short texts, so it says little either way.

### On all four caselists, from the store's own table

The full tables are in
[`caselist-parse-report.md`](../data/caselist-parse-report.md#the-divided-pairs-and-the-largest-clusters-diagnosed-v1-e31-t11).
The figures that test the hypothesis:

| Short cuts the banding pairs with an outside container | hsld26 | hspf26 | hspolicy26 | openev | All |
|---|---|---|---|---|---|
| Witnesses in more than one cluster | 17 | 12 | 5 | 0 | 34 |
| One witness cluster, within the share, and still apart | 19 | 6 | 5 | 0 | 30 |
| Under a quarter of the smallest body that holds it (`MIN_CUT_SHARE`) | 3 | 2 | 2 | 0 | 7 |
| Ends held by more than eight clusters (`MAX_CONTAINER_CLUSTERS`) | 4 | 1 | 0 | 0 | 5 |
| Nine-tenths inside a body that lacks one of its ends | 2 | 2 | 0 | 1 | 5 |
| Total | 45 | 23 | 12 | 1 | 81 |

The rules before `v1-e31-t08` merged a short body with any container the banding paired it with,
so these 81 are the joins `v2` dropped. The total equals the 81 divided pairs counted on
2026-10-11, and on openev the one cut is the one pair. The other 80 could only be matched pair for pair
before the re-parse; step 6 of the operator follow-ups does the same on the re-parsed store.

**What it says about the hypothesis:**

* **It holds for about seven in ten.** 57 of the 81 are plain findings and 24 are in a cluster with
  a copy the outside body also holds. Of the 57, 44 have containers in more than one cluster. In
  all 44 those clusters read as one card that was split, and in none as two different cards.
* **Nested or not decides what can be done about it.** In 21 of the 44 the containers are nested:
  the cut is inside a copy, and the copy is inside the longer body. In 23 they overlap and neither
  holds the other.
* **What split the longer copies**, for the 44 (a cut can count under more than one): they pass
  the Jaccard or containment threshold and the banding never paired them, 19; they share at least
  half and are under both thresholds, 25; the smaller copy is itself a short body the short-body
  step left out, 13.
* **`MIN_CUT_SHARE` is not the cause:** 7 of 81. Across the corpus 272 short cuts are under the
  share, 181 of them under a tenth of the body that holds them.
* **Two defects.** 30 short cuts are apart although their only witness is one cluster and they are
  within the share, because their containers are nested copies in several clusters. 8 are apart
  because the share was tested against whichever container sorted first by fingerprint. 19 and 3
  of those are among the 81.

**The largest clusters.** hspolicy26's largest: 1,172 cards, 166 texts of 72 to 3,843 words.
6,409 of 13,695 pairs of texts share nothing. 92 texts each hold two smaller texts that share
nothing with each other; 41 are inside two larger texts that share under half. So the merges run
through bodies holding several parts more than through shared fragments, and both happen. hsld26's
two largest and hspf26's third have the same shape, smaller. Five of the twelve have no pair
sharing nothing.

### How long the session's runs on the real store took

All read-only, counts only, from the dev data directory.

| Run | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| `diagnose`, the cuts, final tool | 42 s | 32 s | 59 s | 8 s |
| `diagnose --only-largest-clusters` | 7 s | 7 to 22 s | 14 to 28 s | 1 to 2 s |
| The corrected step applied to the stored clusters (a scratch script) | 28 s | 16 s | 33 s | 5 s |
| `counts`, the store's `v2` table against the checked-out rules | not run | not run | not run | 66 s |
| `counts --before-rules f5ad52b` | not run | not run | not run | 58 s |

The machine was shared with three other sessions and its load average moved between 5 and 56, so
the final tool's run over hspf26's cuts took 20 s once and 32 s later. Earlier runs of the tool,
before I removed a quadratic step and stopped building every card model, are not in the table.

## The fixes

Both are in `_join_short_bodies_to_their_one_container`, the short-body step of `v1-e31-t08`.

**Fix 1: a short cut's share is measured against the smallest body that holds it** (`47b3576`).
Within one cluster the step stopped at the first container it confirmed, in fingerprint order, and
tested `MIN_CUT_SHARE` against that one. A cut that is a quarter of one copy and less of a longer
copy in the same cluster joined or not by which digest sorted first. Containers are now tried
smallest first. Fixture: `test_a_short_cut_is_measured_against_the_smallest_body_that_holds_it`,
the same three bodies under two orders of fingerprint.

**Fix 2: containers that hold one another are one witness** (`38508c0`, refined in `b89e220`). A
short cut inside two clusters stayed out of both. When every confirmed container outside the
cluster of the smallest one also holds a container inside that cluster, the larger ones say nothing
about the cut that the smaller did not, so the smallest is the cut's only witness and it joins that
cluster. Two containers neither of which holds the other are still two witnesses. The long bodies
do not move: the cut joins one cluster and merges none. Fixtures:

| Fixture | Before | After |
|---|---|---|
| A 30-word cut of a 90-word copy of a 330-word card, the two long bodies never paired | cut alone | cut with the copy |
| The same with a 45-word copy under a quarter of a 200-word card | cut alone | cut with the copy |
| The same, the card having one changed word inside the copy | cut alone | cut with the copy |
| The three bodies under all six orders of fingerprint | cut alone | cut with the copy in all six |
| The copy and a same-size twin of it in one cluster, the card holding only the copy, under both orders | joined in one order only | joined in both |
| The cut also inside a third body that does not hold the copy | cut alone | cut alone |
| Two overlapping copies, neither holding the other | cut alone | cut alone |
| A near-copy of the card, in the card's cluster, that holds the cut and not the copy | cut alone | cut alone |
| A cut under a quarter of the smallest nested copy | cut alone | cut alone |

The last four are the limits kept. The second-to-last row of the first group is the refinement:
the first version required the outside container to hold *the smallest* container, and with two
copies of one size in a cluster, which is smallest is a digest's choice.

**What the fixes do on the corpus.** No full rebuild fits in two minutes on three of the four
caselists, so there are two measures. On openev, the whole placement: `counts --caselist openev` →
0 merged, 0 divided, 0 exact fingerprints changed, 66 s. That is what the diagnosis predicted,
since it found no nested and no first-by-fingerprint case there. For all four, an estimate: the
corrected step applied to the stored `v2` clusters without recomputing the banding.

| Estimate | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| Clusters that merge into another | 18 | 10 | 17 | 0 |
| New clusters made of several | 17 | 10 | 13 | 0 |
| Most earlier clusters in one new cluster | 3 | 2 | 3 | 1 |
| Earlier clusters divided | 0 | 0 | 0 | 0 |
| Largest cluster, cards, before and after | 620, 620 | 543, 543 | 1,172, 1,179 | 22, 22 |

The diagnosis counted 38 cuts the fixes should move (30 nested, 8 first by fingerprint); the
estimate moves 45 clusters, the difference being cuts set aside with a copy and clusters that
follow a cut. It is an estimate because the stored clusters stand in for what the banding left.

**What the fixes do not do.** They put an orphaned cut with a copy of its card. The two longer
copies are still two clusters. So a comparison against the rules before `v1-e31-t08` will still
count most of those earlier clusters as divided, into one part fewer, and the operator's earlier
"same card" verdicts on a cut and its longer body are not answered by this change.

**Rebuild time.** The step alone, on hspolicy26's 22,527 texts, three runs each on the same stored
clusters: 0.27 to 0.67 s as `v2` had it, 0.76 to 1.09 s now. The rebuild it is part of took 473 s
on 2026-10-11.

## Labelled sets, before and after

`uv run pytest packages/debate_core/tests/evidence/test_short_card_recall.py -n0 --no-cov -s -k test_report_short_card_recall`,
saved before the first fix, after each fix, and at the end, and compared with `diff`: identical
every time. True positive, false positive and false negative pairs:

| Pairs | Before, and after each fix | Precision | Recall |
|---|---|---|---|
| Variant set, all | 75 / 0 / 0 | 1.000 | 1.000 |
| Variant set, involving a short card | 6 / 0 / 0 | 1.000 | 1.000 |
| Variant set, long cards only | 69 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, all | 81 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, full short cards | 24 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, the full long card | 1 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, abbreviated against a full copy | 44 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, abbreviated against abbreviated | 12 / 0 / 0 | 1.000 | 1.000 |
| Extended set, all | 104 / 0 / 12 | 1.000 | 0.897 |
| Extended set, full short cards | 35 / 0 / 2 | 1.000 | 0.946 |
| Extended set, full long cards | 2 / 0 / 2 | 1.000 | 0.500 |
| Extended set, abbreviated against a full copy | 51 / 0 / 4 | 1.000 | 0.927 |
| Extended set, abbreviated against abbreviated | 16 / 0 / 4 | 1.000 | 0.800 |

The labelled sets do not move because neither holds the cases: run through the diagnosis, the 62
distinct full texts of both sets (71 rows) have one body with a container outside its cluster,
`v1-e31-t08`'s shared-opening row, which is inside two different cards and stays out. So the labelled sets show
that nothing broke, and the synthetic fixtures show what changed (Decision 6).

## Mutation runs

Each mutant ran in a new `HYPOTHESIS_STORAGE_DIRECTORY` made with `tempfile.mkdtemp` and checked
empty first. None of these tests is a Hypothesis property, so the isolation is set as working
agreement 8 asks and cannot affect them. Each mutant was one exact replacement that had to be found
exactly once. The suite ran without `-x`, the file was restored byte for byte, and
`git status --porcelain` was empty after every run. Eight test files ran each time, 321 tests then
322, all passing unmutated in 30 s. Four batches of 72, 43, 39 and 32 s, and one re-run.

| Mutant | Result |
|---|---|
| Containers tried in fingerprint order, not smallest first (what `v2` did) | CAUGHT: 8 failed, among them `test_a_short_cut_is_measured_against_the_smallest_body_that_holds_it` |
| The share measured against the largest witness, not the smallest | **SURVIVED, then caught.** Nothing tested a cut with two witnesses that later become one cluster. Added `test_a_cut_with_two_witnesses_is_measured_against_the_smallest_once_they_are_one_cluster`, worked out by hand, passing on the real rule: 1 failed |
| No share limit at all | CAUGHT: 5 failed, `v1-e31-t08`'s quarter test among them |
| Nested containers never count once (what `v2` did) | CAUGHT: 15 failed |
| Containers always count once, nested or not | CAUGHT: 12 failed, `v1-e31-t08`'s two-different-cards test and the shared-opening row among them |
| A cut of nested copies joins the largest, not the smallest | CAUGHT: 15 failed |
| Only the smallest container of each other cluster must be accounted for | CAUGHT: 1 failed, the near-copy fixture |
| An outside container must hold the smallest one, not any container of its cluster | CAUGHT: 1 failed, the twin fixture |
| Held means nine-tenths of the five-word runs only, never but for one word | CAUGHT: 1 failed, the one-changed-word fixture |
| An outside container is accounted for by holding the cut itself | CAUGHT: 12 failed |
| The version bump skipped | CAUGHT: 3 failed: `test_fingerprints.py`'s literal, the smoke check, and the script's git-ref test |

**One check deleted.** The nested test had a size condition on which inside container an outside
one could hold. I could not build a case that told it from its absence, so it is gone (`ab8ead6`).

## Files changed

**Matching (`packages/debate_core/src/debate_core/evidence/`)**
* `near_duplicates.py`: the two fixes; `confirms_a_cut`, the one confirmation test, now public so
  the diagnosis shares it; the docstring's account of witnesses.
* `fingerprints.py`: `card-fingerprint-v3` and what it changed.
* `cluster_diagnosis.py`, new: `diagnose_cuts`, `tally_cuts`, `explain_divided_part`,
  `cluster_shape`. Reads bodies and cluster ids, returns outcomes, digests and numbers.

**Application**: `caselist_card_stats.py`, one sentence of its docstring.

**Tests**: `tests/evidence/test_near_duplicates.py` (a new section after `v1-e31-t08`'s),
`test_cluster_diagnosis.py` (new), `test_fingerprints.py` (one literal),
`tests/application/test_caselist_card_stats.py` (one case through `place`),
`tests/scripts/test_compare_card_clusters.py`, `tests/smoke/test_caselist_cards.py` (one literal).

**Operator tool**: `scripts/compare_card_clusters.py`: `diagnose`; `sample --cluster`, `--largest`,
`--least-alike`, `--kept-apart-by` and `--save-tallies`; `read_bodies`.

**Docs**: `docs/data/caselist-parse-report.md` (the diagnosis, the estimate and what is not run);
`docs/data/parsed-card-store.md` (the `v3` row).

## Deviations from the spec

1. **The session ran the diagnosis on hsld26, hspf26 and hspolicy26, not openev alone.** The brief
   said to run on openev and synthetic stores and to leave the full-corpus diagnosis to the
   operator, because `--before-rules` takes 4 to 9 minutes a caselist. The part that needs no
   "before" reads the store's own table and took 32 to 59 s, read-only, counts only, which working
   agreement 2 lets a session run. I judged that fixes resting on openev's one divided pair would
   rest on nothing. The alternative was to stop at openev and hand over every figure above.
   * **One run went over.** My first attempt on hsld26 was expected to take a minute and passed
     115 s under machine load; the harness moved it to the background and I stopped it, about two
     minutes in. It had written nothing. Every run on the real store after that had a hard stop
     at 105 s, and none reached it.
   * **What is still the operator's:** the earlier placement, and so the match of the 81 pair by
     pair on three caselists.
2. **Long-body matching and the largest clusters are diagnosed and not changed**, although the
   spec says "fix what is wrong". I could not call either wrong without a person's verdict, and
   the change that would fix the first feeds the second (Decisions 1 and 2).
3. **Outside `constraints.packages`.**
   * `tests/smoke/test_caselist_cards.py`: the literal `card-fingerprint-v2` became `v3`. The
     suite fails without it.
   * `tests/scripts/test_compare_card_clusters.py`: the tests of the script the spec asks to
     change. `v1-e31-t08`'s spec was amended to name `tests/smoke` and `tests/scripts` for the same
     two reasons.
4. **The tool does more than ac2 asked.** `diagnose` is ac1's tooling. `--least-alike`,
   `--kept-apart-by` and `--save-tallies` are additions: the first so a false merge in a large
   cluster is found in ten pairs and not left to chance, the second so the limits can be judged
   before they are moved, the third because each pair clears the terminal and the previous
   sample's tallies with it.

## Decisions and assumptions

1. **Long cuts are not joined the way short ones are.** This is the fix the diagnosis points at
   and `v1-e31-t08`'s Follow-up 1 named.
   * **What it would do:** 1,232 long cuts have one witness and are within the share. 944 share
     text with every text of the cluster they would join, and for 481 that cluster is a single
     text. 288 would be put in a cluster with at least one text they share nothing with.
   * **Why not now:** it adds to the same chains as the largest clusters, whose correctness
     nobody has judged. It cannot be previewed in the session on three of four caselists. And a
     naive version would make fragment merges certain where today they are chance: a long cut
     already in a cluster with one container would pull in the cluster of a second.
   * **The alternative**, which I would take once the samples are in: the same step for long cuts,
     with a cut's own cluster counted among its witnesses, and a join refused when it would put
     two texts that share nothing in one cluster. `sample --kept-apart-by long-cut-within-the-share`
     draws the pairs it would join.
2. **The largest clusters are not broken up.** Two bodies that share no five-word run are in one
   cluster only through others. By the labelled sets' convention, where a second card from the
   same article is a different card, most such pairs are different cards. But the same shape is
   what one long card cut at many extents looks like, and splitting would divide clusters nobody
   has looked at. The alternative was a rule that a body holding two unrelated bodies joins
   neither. That is the PM's call after ac2.
3. **`MIN_CUT_SHARE` stays 0.25.** It explains 7 of the 81. Lowering it to a tenth would let 91
   more short cuts join and still leave 181 out. The alternative needs the by-eye verdicts
   `sample --kept-apart-by under-the-minimum-share` would give.
4. **A cut inside two overlapping copies still joins neither.** This is the largest group left:
   71 short cuts on the corpus, 34 of the 81. The copies share much of their text and neither
   holds the other. The alternative was to join the cut when its containers share at least half,
   the line `v1-e31-t08` uses for abbreviations. There it has the cite and both ends agreeing as
   well; here it would have nothing else. The nearest labelled case is `v1-e31-t04`'s copy of one
   card cut long enough to run into the next: it shares 38% of the second card, so today it is
   under the line, and it would be over it had it run a little further. A sentence both hold
   would then be given to one of two different cards.
5. **`MAX_CONTAINER_CLUSTERS` and the both-ends rule are unchanged:** 5 of the 81 each. The first
   counts clusters before confirming any, so it counts a much-read card's split copies; it should
   fall when long copies merge. The second is `v1-e31-t08`'s guard against two cards that open
   alike and diverge.
6. **The fixtures are numbered made-up words, not new labelled rows.** `v1-e31-t08` appended prose
   rows to `short_cards.jsonl`. The cases here need a 330-word card and a banding outcome that
   only the seed decides, so each test asserts its own precondition (the two long bodies are two
   clusters) and the arithmetic is exact. One case goes through `CaselistCardStatsService.place`,
   the pipeline's step. The alternative was about 700 words of invented prose and a third tier in
   the recall table.
7. **"Holds" is the confirmation test itself**, in the nested rule and in the diagnosis: nine-tenths
   of the five-word runs, or but for one word when the held body is short.
8. **Ties.** Two containers of one size in different clusters that each hold the other: the
   smaller fingerprint is the one joined. Such bodies are near-identical, which Jaccard or the
   step itself puts in one cluster, and I could not build a case where they stay apart.
9. **I do not claim `v3` only adds joins to `v2`.** For a cluster as the banding left it, the
   witnesses under `v3` are a subset of `v2`'s and the share test is no stricter, so every join I
   can construct under `v2` happens under `v3`, and the estimate divides no cluster. A proof would
   need a case I could not rule out: a short body's cluster reaching its smallest container by
   another route first. `clusters_divided` in step 2 of the operator follow-ups is the check.
10. **The estimate's method.** The corrected step applied to the stored clusters. It skips the
    banding, which is nearly all of a rebuild's time and which the fixes do not touch.
11. **`domain/card_occurrence.py` is not edited.** A field description there names `v1` and `v2`.
    It is still true and now incomplete; the brief said to stay out of the domain (Follow-up 8).

**What the session read from the real store.** Counts and seconds from the runs above, printed to
my own tool output, and one file of digests and cluster ids saved to the session's scratch
directory for openev's earlier placement, deleted at the end. No card text, tag or cite was printed, and `sample` was
never run: it shows text and refuses anything but a terminal. Nothing from the store is in a
commit, a fixture or this report.

## Operator follow-ups

**Rewritten on 2026-10-13 after the PM's note:** `v1-e31-t12` bumps the parser to
`2026.10.12-docx-3`, so every step here is taken on the re-parsed store, and the PM combines them
with t12's. Nothing needs running before the merge. The session's figures above are from
`2026.10.10-docx-2` and stay valid as a diagnosis of that store. They are not the figures to
expect to the digit: the re-parse changes the text of 2,515 cards that keep their paragraph range
and replaces 1,109 card ranges with 1,274.

**The order these steps assume.** This task and t12 both merge, then t12's re-parse writes
`parsed/<caselist>/2026.10.12-docx-3/`. That one re-parse covers both tasks: it builds the new
directory's aggregates under `card-fingerprint-v3` from the start. If the re-parse ran before this
task merged, see [If the new directory was built under `v2`](#if-the-new-directory-was-built-under-v2).

**What the next rebuild will do.**

* **With t12, the first run is a full parse, not a rebuild.** A new parser version starts a new
  version directory that holds nothing, so every source is parsed again and the aggregates are
  built from that. They are built under `v3`, and the new directory never holds a `v2` table.
* **So "before" has to be computed.** There is no earlier table for these cards to compare with.
  Step 2 places the new directory's cards with the matching rules as they were just before this
  task merged, taken from git. On openev today the same mechanism, with the rules on `origin/dev`,
  reproduced the stored `v2` table exactly: 5,864 clusters on both sides, nothing merged or
  divided, 53 s.
* **The weekly pull's parse stage** (`v1-e34-t17`) would do that full parse itself on its first
  run with the new build, for each caselist it imports into: about 30 minutes where it takes 20,
  with `full_parses` above 0, and openev left on the old directory until a camp file arrives. The
  scheduled-sync runbook says to do the full parse by hand first, which is what t12's steps are.
* **Had this task merged alone**, with no parser bump, nothing would have been parsed again: the
  skip key has no fingerprint version in it. The next parse stage would have rewritten every
  occurrence row of each caselist it imported into under `v3`, and uploaded that one file.

Don't run any of this while `caselist pull` is running: `uv run debate-research caselist runs
--last 1` shows the last run. The script finds the newest version directory by itself, so no step
but the first names it.

**Step 1. Check both tasks are merged and the re-parse has run** (seconds).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t11-long-card-splits-and-fragment-merges:'
git log --oneline -1 --grep='^v1-e31-t12-cite-detection:'
ls ~/.debate-research/dev/parsed/hsld26
jq -r '.fingerprint_version' ~/.debate-research/dev/parsed/hsld26/2026.10.12-docx-3/occurrences.jsonl | sort | uniq -c
```

Expected: `dev`; `git status` prints nothing; each `git log` prints that task's merge commit; `ls`
shows `2026.10.12-docx-3`; and the last line is one count of `card-fingerprint-v3`.

* **No `2026.10.12-docx-3` directory:** the re-parse has not run. Run t12's operator steps first.
* **It says `card-fingerprint-v2`:** the re-parse ran before this task merged. Go to
  [If the new directory was built under `v2`](#if-the-new-directory-was-built-under-v2).

**Step 2. Compute "before" once and print the counts** (ac4's counts; 15 to 25 minutes on
2026-10-11's timings). It reads the store and writes four files of digests and cluster ids, no
text, inside the dev data directory.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
T11=$(git log -1 --format=%H --grep='^v1-e31-t11-long-card-splits-and-fragment-merges:')
echo "${T11}"
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before-rules "${T11}^" --save-before ~/.debate-research/dev/card-clusters-before-t11 > ~/card-clusters-counts-v3.json; echo "exit $?"
cat ~/card-clusters-counts-v3.json
```

`"${T11}^"` is the commit just before this task's merge. Only the four matching modules are taken
from it, so it does not matter which of the two tasks merged first.

Expected: `echo` prints one commit id and `exit 0`. For every caselist `before_version`
`card-fingerprint-v2`, `after_version` `card-fingerprint-v3`, `exact_fingerprints_changed` 0,
`cards_only_before` and `cards_only_after` 0, and `clusters_divided` 0. Nothing under `absorbed`
past `3 to 5`. `clusters_merged_into_another` near the session's estimate on the old directory: 18,
10, 17 and 0. Paste the file back: it holds counts only. Any divided cluster, or anything under
`6 to 20` or above, stop and send it before the sample.

**Step 3. The by-eye sample of what `v3` changed** (ac4's samples; seconds to start, then about 15
minutes). Each pair is shown one at a time. Press `s` (same card), `d` (different card) or `u`
(unsure), then Enter. Each pair is cleared from the terminal, scrollback included, so the tallies
go to a file of counts. It will not run with its output redirected.

```zsh
uv run python scripts/compare_card_clusters.py sample --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before-t11 --save-tallies ~/card-cluster-sample-tallies.txt
uv run python scripts/compare_card_clusters.py sample --divided --count 10 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before-t11 --save-tallies ~/card-cluster-sample-tallies.txt
```

Expected: the first draws 20 of about 45 newly joined pairs. The second should say `Drew 0 of 0
divided pairs`. The cards are real disclosures, so nothing from them goes into a message, a
screenshot, an issue or a file. **One "different card" among the newly joined pairs is a false
positive on the real corpus.** If t12's prod publish has not run yet, take this sample between its
dev and prod steps, so that verdict comes before prod.

**Step 4. The diagnosis of the new directory** (about 5 minutes; counts only).

```zsh
uv run python scripts/compare_card_clusters.py diagnose --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev > ~/card-clusters-diagnosis-v3.json; echo "exit $?"
jq 'map_values(.cuts.short_within_the_rule_and_apart)' ~/card-clusters-diagnosis-v3.json
```

Expected: `exit 0`, and in every caselist the `cuts` under `short_within_the_rule_and_apart` near
0 (on the old directory under `v2` they were 16, 10, 14 and 0; the two fixes leave only the ones
where another short body of the cluster points elsewhere, 2 in all). The other rows should be near
the old directory's table in `caselist-parse-report.md`. Paste the file back.

**Step 5. The by-eye sample of the largest clusters** (ac2; about an hour, 120 pairs). Each pair is
two different texts from one cluster of the new directory.

```zsh
for c in hsld26 hspf26 hspolicy26 openev; do for r in 1 2 3; do uv run python scripts/compare_card_clusters.py sample --caselist ${c} --largest ${r} --count 10 --save-tallies ~/card-cluster-sample-tallies.txt; done; done
```

Then the ten pairs that share the least text in each caselist's largest cluster, which is where
two cards merged into one would show:

```zsh
for c in hsld26 hspf26 hspolicy26 openev; do uv run python scripts/compare_card_clusters.py sample --caselist ${c} --largest 1 --count 10 --least-alike --save-tallies ~/card-cluster-sample-tallies.txt; done
cat ~/card-cluster-sample-tallies.txt
```

Paste the file back. Two notes:

* On the old directory hspf26's largest cluster held texts of 1,441 to 7,697 words. If it still
  does, its pairs are long to read, and `u` is an honest answer.
* To point at a cluster by its id instead of its rank,
  `diagnose --caselist hspolicy26 --only-largest-clusters --show-cluster-ids` prints the ids, and
  `sample --cluster` takes one or the start of one.

**Step 6. The pairs divided since before `v1-e31-t08`, each with its reason** (the rest of ac1;
15 to 25 minutes, then about 5). On the old directory there were 81. This places the new
directory's cards with the rules before `v1-e31-t08` and explains every part that has left its
earlier cluster.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
T08=$(git log -1 --format=%H --grep='^v1-e31-t08-short-card-recall:')
echo "${T08}"
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before-rules "${T08}^" --save-before ~/.debate-research/dev/card-clusters-before-t08 > ~/card-clusters-counts-since-t08.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before-t08 > ~/card-clusters-diagnosis-since-t08.json; echo "exit $?"
jq 'map_values(.divided_pairs)' ~/card-clusters-diagnosis-since-t08.json
```

Expected: `exit 0` twice. The count of pairs will not be 81: the cards differ, and `v3` has joined
some cuts. Most of the parts `v3` joined to a smaller copy are still counted as divided here, with
the detail `it is with a copy that the bodies it left also hold`. What matters is that **no entry
has the `kind` `no short cut links this part to the rest`**. One that does is a cause this
diagnosis does not know, and is the thing to send first. Paste both files back.

**Step 7. Optional: the limits, by eye** (about 4 minutes of reading the store before the first
pair of each, then the pairs). These are the evidence for Decisions 1, 3 and 4. Each pair is a cut
and the smallest body that holds it, which the rules keep apart.

```zsh
uv run python scripts/compare_card_clusters.py sample --kept-apart-by long-cut-within-the-share --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --save-tallies ~/card-cluster-sample-tallies.txt
uv run python scripts/compare_card_clusters.py sample --kept-apart-by under-the-minimum-share --count 10 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --save-tallies ~/card-cluster-sample-tallies.txt
uv run python scripts/compare_card_clusters.py sample --kept-apart-by witnesses-in-several-clusters --count 10 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --save-tallies ~/card-cluster-sample-tallies.txt
```

**Prod.** This task has no prod step of its own. t12's prod publish carries the `v3` aggregates
with it, from the same dev data directory. It goes ahead only if step 3 found no "different card".

**Step 8. Remove what the steps saved:**

```zsh
rm -r ~/.debate-research/dev/card-clusters-before-t11 ~/.debate-research/dev/card-clusters-before-t08
rm ~/card-clusters-counts-v3.json ~/card-clusters-diagnosis-v3.json ~/card-clusters-counts-since-t08.json ~/card-clusters-diagnosis-since-t08.json ~/card-cluster-sample-tallies.txt
```

### If the new directory was built under `v2`

That is, t12 merged and its re-parse ran before this task merged. The new directory then holds a
real `v2` table, which is a better "before" than a computed one, and one more run rebuilds it under
`v3`. Nothing is parsed again.

Save the tables first (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
mkdir -p ~/.debate-research/dev/card-clusters-before-t11
for c in hsld26 hspf26 hspolicy26 openev; do cp -p ~/.debate-research/dev/parsed/${c}/2026.10.12-docx-3/occurrences.jsonl ~/.debate-research/dev/card-clusters-before-t11/${c}.jsonl; done
jq -r '.fingerprint_version' ~/.debate-research/dev/card-clusters-before-t11/*.jsonl | sort | uniq -c
```

Expected: one line, every row `card-fingerprint-v2`.

Then, with this task merged and pulled, rebuild and publish in dev, as the removal runbook's
step 5 does (about 18 minutes on 2026-10-11's timings: 314, 473, 193 and 71 s):

```zsh
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t11-long-card-splits-and-fragment-merges:'
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/parse-dev-hsld26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/parse-dev-hspolicy26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/parse-dev-hspf26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist openev --publish > ~/parse-dev-openev.json; echo "exit $?"
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, fingerprint_version, attempted, store, elapsed_seconds, publish: .publish.counts}' ~/parse-dev-${c}.json; done
```

Expected for each: `exit 0`, `fingerprint_version` `card-fingerprint-v3`, `attempted` 0, and
`publish.uploaded` 1, because `occurrences.jsonl` is the only file whose bytes change.

Then the counts, which take seconds because both tables exist:

```zsh
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before-t11 > ~/card-clusters-counts-v3.json; echo "exit $?"
cat ~/card-clusters-counts-v3.json
```

Expected as in step 2. Then steps 3 to 8 above. Prod, from the same dev data directory and only if
step 3 found no "different card", as the removal runbook does it (each variable is on the command
line, so nothing is left pointing the shell at prod):

```zsh
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/parse-prod-hsld26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/parse-prod-hspolicy26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/parse-prod-hspf26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/parse-prod-openev.json; echo "exit $?"
```

Expected: `exit 0` each.

## Follow-up work

1. **Long cuts joined to the one cluster that holds them (E31).** Decision 1: the figures, the
   guard it needs, and the sample that would justify it. It is the change that would re-join the
   divided pairs proper, since it merges the two long copies a cut sits between.
2. **What one card is, when a source is cut at many extents (PM, then E31).** Decision 2. The
   answer decides whether hspolicy26's largest cluster is one card or many, and it changes what
   `v1-e32-t03`'s "most-read card" means. Step 5's tallies are the evidence.
3. **`MIN_CUT_SHARE` (E31).** 272 short cuts are under it, 91 of them between a tenth and a
   quarter. Step 7's second sample is the evidence.
4. **`MAX_CONTAINER_CLUSTERS` counts clusters before it confirms any (E31).** A much-read card
   whose long copies are split fills the count with copies of itself. Re-measure after
   Follow-up 1.
5. **A short body nine-tenths inside a body that lacks one of its ends (E31):** 26 on the corpus,
   5 of the 81. `v1-e31-t08` stopped comparing these on purpose. `sample --kept-apart-by
   lacking-an-end` would say whether they are copies with a stray word at one end.
6. **A short body's own cluster is not among its witnesses**, in `v2` and `v3` alike. A cut that
   is in a cluster with a near-twin by Jaccard, and is also inside a body in another cluster,
   joins the two clusters although the twin may not be inside that body. On the corpus this is as
   likely a copy with a stray ending as two cards, so I left it. It has to change with
   Follow-up 1, where it would make a fragment merge certain.
7. **`v1-e32-t03` and cluster ids.** They changed again. The advice in `parsed-card-store.md`
   stands: check `fingerprint_version` on the rows read, and key anything durable on
   `exact_fingerprint`.
8. **`debate_core/domain/card_occurrence.py`:** the `fingerprint_version` field description says
   the digest "is the same in card-fingerprint-v1 and card-fingerprint-v2". It is the same in
   `v3` too. One sentence, in a file I was asked to stay out of.
9. **A timing-sensitive test failed once under load.**
   `test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` in
   `test_caselist_parse.py` failed in one run at a load average of 50 and passed alone and in
   every run after, the whole suite included. It is not this task's, and `v1-e01-t27` was looking
   at slow tests.
10. **`test_counts_reads_the_earlier_rules_from_a_git_ref` reads `HEAD`**, so it fails in a working
    tree where the version constant is edited and not yet committed. It passes once committed. A
    session that bumps the version will meet it, as I did.
11. **`docs/data/caselist-parse-report.md`** needs the figures of steps 2 to 6 at close-out, from the re-parsed store.
    The places are marked `not run`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
