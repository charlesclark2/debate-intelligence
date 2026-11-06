# Session report: v1-e31-t10-incremental-aggregate-rebuild

| | |
|---|---|
| Task | `v1-e31-t10-incremental-aggregate-rebuild` — The weekly aggregate rebuild costs what the week added, not the whole store |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t10-incremental-aggregate-rebuild.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t10-incremental-aggregate-rebuild.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t10-incremental-aggregate-rebuild` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Proposal stage: nothing is built yet. The scaling is measured on four synthetic stores, set beside
every recorded real figure, and the proposal below waits for the PM's ruling. Look first at (b): the
clustering rules are not monotone, so a new card can split an older cluster as well as join or
rename one, and the only exact incremental placement re-clusters every dependency component a
new body reaches. Also (c): this needs a new file beside the aggregates, which a removal must
delete. Then (f): the spec's estimate of 6h does not cover it.

## Proposal for the PM's ruling (before any code)

Everything here is measured on synthetic stores of invented words, or read from records already in
`docs/`. No real card text was read. The scratch scripts and their raw output are kept, uncommitted,
in the worktree's ignored `.task/measurements/`.

### (a) How the rebuild scales, and where its time goes

**Synthetic stores.** Seed 20261106, twelve weeks. Cards are passages of invented articles, and
sources draw them by preferential attachment, so popular cards recur and distinct bodies grow more
slowly than sources, as they do in the real stores. Each drawn card is an exact copy (72%), a copy
with a word changed (8%), a cut (8%), a longer extent of the article (4%), abbreviated (5%), or
cite-only (3%). Bodies are 25 to 700 words, 15% of them short. Cards carry underline and highlight
spans. Each figure is the rebuild alone (`caselist parse` with nothing to parse, through the real
`CaselistParseService` and `LocalParsedStore`), timed by wrapping each step of the placer and the
clusterer. Worktree venv on the operator's Mac, load average 3 to 6.

| Sources | Cards | Distinct full bodies | Clusters | Rebuild | MinHash | `CutIndex` | Band pairs and Jaccard | Joins of copies | Cut step | Body words | Reading documents | Fingerprints | Linking | Writing | Plan, ordering |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 250 | 5,617 | 3,814 | 2,934 | 11.87 s | 9.89 | 0.29 | 0.27 | 0.03 | 0.10 | 0.40 | 0.48 | 0.22 | 0.01 | 0.06 | 0.10 |
| 500 | 11,066 | 6,877 | 4,970 | 21.93 s | 17.75 | 0.65 | 0.59 | 0.10 | 0.22 | 0.77 | 1.02 | 0.47 | 0.03 | 0.13 | 0.21 |
| 1,000 | 21,954 | 12,005 | 8,064 | 39.42 s | 30.90 | 1.36 | 1.19 | 0.27 | 0.51 | 1.36 | 2.17 | 0.90 | 0.08 | 0.26 | 0.41 |
| 2,000 | 44,073 | 21,293 | 13,311 | 72.78 s | 55.02 | 2.99 | 2.63 | 0.53 | 1.13 | 2.31 | 4.66 | 1.80 | 0.24 | 0.53 | 0.95 |

**The fit** (least squares on logs): rebuild time grows as sources^0.87 and as distinct full
bodies^1.05; distinct bodies grow as sources^0.83. MinHash is linear in bodies (exponent 1.00) and
takes 83%, 81%, 78% and 76% of the time. Everything else together grows as bodies^1.28, led by the
cut step (bodies^1.4), `CutIndex` and the band pairs. On these stores that part is a quarter of the
time at 2,000 sources and would pass MinHash only near a million bodies. **On synthetic stores the
rebuild is very slightly worse than linear in distinct bodies, from no particular size, and
sublinear in sources.** Writing the table is under 1%, and linking is under 0.5%.

**The real figures recorded so far**, for `hspolicy26` unless named:

| When, record | Code | Sources | Distinct full bodies | Rebuild |
|---|---|---|---|---|
| 2026-10-10, caselist-parse-report.md | `docx-1`, `v1` | 2,657 | | 460 s (hsld26 348, hspf26 214, openev 60) |
| 2026-10-11, the same and `v1-e34-t17` | `docx-2`, `v2` | 2,657 | | 473 s (314, 193, 71) |
| 2026-10-16, caselist-parse-report.md | `docx-3`, `v3` | 3,190 | | 482 s (345, 219, 68) |
| 2026-11-01, caselist-rebuild-memory.md (`v1-e40-t36`), run image | `docx-7`, `v4`, strings | 250 | 5,470 | 86.7 s |
| the same | the same | 3,869 | 29,866 | 536.1 s: reading 162, `CutIndex` 54, MinHash with pairs, joins and the cut step about 289, linking and writing 31 |
| 2026-11-01, `v1-e40-t39`, run image | `v4`, word numbers (today's code) | 250 | 5,470 | 54.4 s (strings 72.5 s) |
| 2026-11-02, `v1-e40-t39` ac2, operator | the same | 3,869 | 29,866 | 741 s |

* **In sources the real rebuild is sublinear too.** Its distinct bodies grew as sources^0.62
  (5,470 to 29,866 while sources went 250 to 3,869). The 900 s projection in the spec and in
  `v1-e34-t17` assumed time in proportion to sources, which the figures do not show.
* **In bodies the two real pairs disagree.** `v1-e40-t36`'s pair (strings) gives an exponent of
  1.07, close to the synthetic 1.05. `v1-e40-t39`'s pair, today's code, gives 1.54: 54.4 s at 250
  sources and 741 s for the whole store. The record cannot say whether that is load (each was one run
  on a busy Mac) or a term the synthetic corpus does not have. One candidate: since `v1-e40-t39` a
  body's shingle set is made again for each comparison beyond a cache of 262,144 shingles, real bodies
  average about 900 words to the synthetic 400, and a real store holds many passages of one article,
  so it compares far more pairs. **So whether today's code is materially worse than linear on the
  real store, and from what size, is not known.** The operator block under Operator follow-ups
  measures it: the same phase split over the Mac's `hspolicy26` store.
* **The 900 s line is near either way.** From 741 s at 3,869 sources, the line falls at about 5,200
  sources at the synthetic exponent and about 4,700 at the steeper one. The cloud store has grown
  since the Mac's copy was taken. No per-caselist rebuild time has been recorded from the cloud yet:
  `v1-e40-t43`'s progress lines count sources, not the rebuild.

**Where the time goes.** MinHash dominates (76 to 83% synthetic; about 45 of 55 s at 250 real
sources by `v1-e40-t39`). Reading the per-source documents is 4 to 6% synthetic and 30% of the real
whole-store run (162 of 536 s), because a real per-source file averages 1.1 MB. Clustering apart
from MinHash, linking and writing follow. An incremental rebuild therefore has to avoid both
re-signing the stored bodies and re-reading the stored documents.

### (b) The incremental placement

**Why "join, link or start a cluster" is not enough.** Placement is a function of the whole set of
cards, and it is not monotone in that set. A new body can change older rows in the three ways the
brief lists: a new smallest fingerprint renames a cluster, a body that holds two cuts joins their
clusters, an abbreviated card gains a link. It can also take rows apart:

1. It is a second witness, in another cluster, for a cut, so the cut's cluster joins nothing
   (`near_duplicates.py:709`).
2. It is a passage inside a container that the cut does not overlap, so that container is no longer
   a witness for the cut (`:668`).
3. It is a ninth other cluster holding both ends of a short cut, so the cut's whole cluster joins
   nothing (`:704`).
4. Copies join strongest first, and a join is refused if it would put two bodies that do not overlap
   in one cluster (`:805`). A new copy that joins early can make a later join fail.
5. Abbreviated cards. A new full card under the same short cite, in another cluster and sharing
   less than half, unlinks a linked card (`abbreviated_links.py:223`). A new abbreviated copy of the
   same text under a second short cite takes that text out of its group
   (`caselist_card_stats.py:398`). A new member can make a group inconsistent and dissolve all of it
   (`abbreviated_links.py:268`). A new copy changes the counts that choose between two clusters.

So an older row can change cluster, lose a link or gain one, or change its id, and through chains.
Patching rows forward from the stored table cannot be made exact. What can be exact is recomputing
everything a new body can influence.

**The dependency graph.** Following every read the clusterer makes, a decision about one body reads
only bodies joined to it by one of these:

* a band-candidate pair whose Jaccard is at least the threshold;
* one body holding the other, confirmed (`CutIndex.holds`);
* for a short body, a body that holds both of its ends (what `too_common` counts).

Clusters form only along the first two. So the clusterer run over the whole store, restricted to one
connected component of this graph, gives the same result as the clusterer run over that component
alone. The rounds, the strongest-first order, the overlap refusals and the smallest-root rule are all
decided inside a component. The cluster id is the smallest fingerprint of a cluster, so it is decided
inside a component as well. The report will carry the step-by-step argument and tests that hold each
step. Linking has a partition of its own. An abbreviated card's link reads the full cards under its
short-cite key, the abbreviated cards under that key, and those with its own fingerprint under any
key. So its partition is short-cite keys, tied together where one abbreviated text appears under two
keys.

**What the incremental run does:**

1. Read the placement state (below), the week's new per-source files, the manifests and the
   suppression list. It reads no stored document and no aggregate.
2. Sign the new distinct bodies only. Find the new bodies' edges: band buckets from the stored
   signatures; stored end shingles that a new body holds; new end shingles that a stored body holds
   (one pass over the stored word numbers, with a set lookup at each position); then confirmation and
   Jaccard against the stored words.
3. Re-cluster the new bodies and every stored component they reach, with the stored signatures, plus
   any stored short body that a new body holds both ends of. Every other body keeps its stored
   cluster.
4. Re-link every abbreviated card whose key group a new card, a changed copies count or a changed
   cluster id reaches. Every other card keeps its stored placement.
5. Make every row with today's code (spans from the manifests, the same ordering key) and write the
   table whole, then the new state.

**Stock phrases.** An edge from a short body whose both-end holders already span ten or more
components can be dropped. Clusters never cross components, so its too-common count stays above
eight whatever happens inside them, and the restricted run is told it is too common. On the
synthetic stores this changes nothing, because they have no stock openings. On real ones it may, and
the operator block measures it.

**The placement state** is a new file beside the aggregates, `placement-state.sqlite`, rewritten
whole at the end of every rebuild, full or incremental. It holds:

* for each live parsed source, each card's paragraph range, completeness, exact fingerprint,
  short-cite key, its link key if abbreviated, and its placement;
* for each distinct full body, its words as numbers in one vocabulary, its MinHash signature and its
  component;
* stamps: the fingerprint version, a digest of the clusterer's constants, the thresholds, the
  ellipsis markers, and the SHA-256 of the `occurrences.jsonl` it was written beside.

It holds what `CardPlacer.add` keeps of each card, and what placement reads is nothing more. It
holds no path, school or team. For `hspolicy26` I estimate about 150 MB: 27 million words at four
bytes, plus signatures and cards.

**Why the result is the full rebuild's, byte for byte.**

1. The state is exactly what placement reads of each card, for each source that is still live.
2. Each component's clusters equal the whole run's, by the graph above. Signatures are a function of
   a body's words, so storing them changes no result.
3. Rows are made from placements, card positions and the manifests by the same code in the same
   order.
4. A stopped source's cards are left out exactly as a full rebuild leaves them out, and the
   components of its bodies are re-clustered.
5. The state an incremental run writes must also equal the one a full run writes. That is tested, so
   no drift can accumulate from week to week.

Nothing is carried forward from any aggregate. The table is still made whole, from per-source data,
the manifests and the list, as `caselist_parse.py`'s "rebuilt, never carried forward" requires.

**What it should cost.** It reaches a share of the store, and the measured share stays flat as the
store grows. On the synthetic stores a 5% week reaches 10.2%, 10.3% and 13.4% of distinct bodies at
500, 1,000 and 2,000 sources, and the largest component is 19, 21 and 42 bodies. Confirmation
matters: with unconfirmed edges (any band pair, any held end shingle) the largest component grows
264 → 748 → 3,142 and a week reaches 17% → 21% → 29%. At 2,000 sources I estimate the incremental
run at about 9 s of the full 72.8 s (12%), against ac3's quarter.

What stays proportional to the store is loading and saving the state, one pass over the stored words,
and making and writing every row. Today that last part is about 1.5% of a rebuild.

**A fallback that is still exact.** When the reached set passes a share of the bodies (I propose 40%),
the run re-clusters everything from the state with the stored signatures. It reads no document and
signs no stored body. That is about 14 s at 2,000 sources (19%).

### (c) A table a removal rewrote

Since `v1-e30-t33` a removal rewrites the table in place, and surviving rows keep the cluster id and
membership a removed card gave them.

* **The removal deletes the placement state** in every directory it reaches: on this machine; in the
  bucket with every version; recorded in `removal-aggregates.jsonl` as a deleted aggregate is; and
  counted by `caselist status` as residue if any version survives. This is needed anyway, because
  the state holds the removed source's words and fingerprints. With no state, the next run is a full
  rebuild, the PM's default, and it writes a fresh state.
* **A second guard, independent of the first.** The state records the SHA-256 of the
  `occurrences.jsonl` it was written beside, as `camp_paths.jsonl` does. Any of these leaves the
  state not matching the table, and the next run rebuilds in full:
  * a removal's rewrite, from any build;
  * a deletion by a build from before `v1-e30-t33`;
  * a table written by a build that does not write the state.

  I prefer this to reading `removal-aggregates.jsonl`. That record sits beside the removal log, names
  directories rather than table bytes, and would miss a rewrite made by anything else.
* **Exact even where the state survives.** The incremental path never reads the table and leaves out
  stopped sources itself. It is therefore exact even on a machine where a removal made elsewhere left
  the state in place. The equivalence test covers that case, the rewrite case and the deleted-state
  case. Whichever path runs, the table after the next run is a full rebuild's.
* **This changes `v1-e30-t33`'s removal**, inside this task's packages. It changes the list of files
  a version directory holds, the plan's text, the plan's `--json` (pinned whole in tests and smoke
  checks, which would be updated), and the residue count. That is a change to removal, not just to
  the rebuild, so it needs the PM's approval.

### (d) When a full rebuild still runs

A full rebuild runs when:

* there is no placement state, it cannot be read, or its schema is not one this build knows;
* the fingerprint version, the clusterer's constants digest, the thresholds or the ellipsis markers
  differ from the state's stamps;
* `occurrences.jsonl` is missing, or its SHA-256 differs from the state's stamp;
* the state names a source that is not a parsed entry of the directory (defensive: per-source files
  are never rewritten);
* the run starts a new version directory: a parser version bump, `--reparse`, or a profile change.
  No state exists there. The 2026-11-11 `docx-9` re-parse is one of these;
* the setting `parse.incremental_rebuild` is false. It defaults to true. For a by-hand full rebuild,
  set `DEBATE_PARSE__INCREMENTAL_REBUILD=false` on the one command.

A `--full-rebuild` flag on `caselist parse` would belong to `debate_cli`, which is outside this
task's packages.

The run's log line says which path ran and why, in counts only. I propose no periodic full rebuild.
The path is exact, and ac4's by-hand full rebuild compares the two tables' SHA-256 on the real
store.

### (e) The equivalence oracle

* **The oracle** is the full rebuild as it is at the start commit, kept in the test module the way
  `v1-e40-t36` kept its oracle (working agreement 6). The new code's full path is checked against it
  too.
* **The Hypothesis property.** It generates a store as a sequence of two to five weeks. Each week adds
  one to four sources drawn from a small pool built to produce each kind of change in (b):
  * copies, changed words, cuts and nested cuts;
  * passages of one article;
  * short bodies with stock ends, enough to reach too-common;
  * abbreviated and cite-only cards under shared short cites;
  * one abbreviated text under two short cites.

  Between weeks it may stop a source, withdraw a disclosure, list an old source again, apply
  `v1-e30-t33`'s rewrite to the table, or delete the state. After each week, the incremental run is
  compared with a full rebuild of a copy of the same store. Every aggregate must be equal, byte for
  byte, and so must the state.
* **Directed cases**, with expectations written by hand:
  * a week that merges two clusters;
  * a new smallest fingerprint that renames a cluster;
  * a newly linked abbreviated card;
  * a week that splits a cluster through a second witness;
  * a too-common flip;
  * a week that a removal shrank.
* **What the property generates.** `event()` labels each week's kinds: merge, split, rename, link
  gained or lost, group dissolved, removal. `--hypothesis-show-statistics` is checked, so that each
  kind occurs in a real share of cases before the property is offered as evidence.
* **Red first.** The tests are run against a skeleton that places only the new bodies (the join-only
  approach) and must fail.
* **Mutants.** About 20, on the equivalence rules: each edge kind dropped, the saturation bound off by
  one, the copies count, the closure of linking keys, each stamp check, the pruning of stopped
  sources, the card positions.
* **The database rule (agreement 8).** Every run against a mutant sets `HYPOTHESIS_STORAGE_DIRECTORY`
  to a new, empty directory, and the report says so wherever it gives a catch time. A mutant that
  errors before it runs (at collection or import) is not a catch: it is redone or discarded.
* **ac3** is measured on the largest synthetic store by a committed script under `scripts/`: the
  incremental run against the full rebuild, for a week of 5% new sources.

### (f) The estimate, and dev's `docx-9` image

The 6h estimate does not cover this. By part:

| Part | Hours |
|---|---|
| The state: format, written by the full rebuild, read, stamps, publish order (aggregates, then state), the in-memory fake | 4 |
| The incremental placement: edges, components, re-clustering with stored signatures (two small hooks in `near_duplicates`, inert when unused), the linking partition | 7 |
| The removal: deleting the state, here and in the bucket, the record, residue, the plan's text and JSON pins | 3 |
| The oracle, the generator, directed cases, the red run, about 20 mutants | 6 |
| The scripts for ac1 and ac3, `parsed-card-store.md`, the report | 2 |
| **Total** | **about 22** |

That is about three working days. It splits cleanly into two stages, if the PM prefers:

* **Stage 1** is the state, with every body re-clustered from it each run: exact by construction,
  about 19% of a full rebuild at 2,000 synthetic sources, still in proportion to the store. About
  13h.
* **Stage 2** adds the components, so the cost tracks the week. About 9h more.

**The image.** Dev's `docx-9` run image is built before Tuesday 2026-11-10 06:00 Chicago, and this
task cannot be ready and reviewed by then. The 2026-11-11 run starts a new version directory at
`docx-9`, so it rebuilds in full under any build. **I recommend the image does not wait.**

The cost of not waiting is one week. The 2026-11-11 run then writes no state. The first run on a
build that has this task does one more full rebuild, which writes the state, and the run after it is
the first incremental one:

* 2026-11-25, if this task is in an image by 2026-11-18;
* 2026-11-18, if the image had waited.

**ac4 cannot close in a session.** It needs that first incremental weekly run, and a by-hand full
rebuild of a restored copy with the setting off, comparing the two tables' SHA-256. So the Goal will
stay `InProgress` at the end of this task.

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

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

**The real phase split and dependency components (read-only, after the weekend).** This waits for the
PM's word to commit `scripts/measure_rebuild_scaling.py`. The script reads the Mac's dev store and
writes nothing: the rebuild's aggregates are rendered to a digest in memory.

The block takes about 25 minutes. It measures two things:

* the phase split of a full `hspolicy26` rebuild on today's code;
* the dependency components (confirmed edges, with and without the stock-phrase bound) that the
  newest week's sources reach, and those reached by the last 5% of sources.

The Mac's copy is stale since the cutover, but what is measured is the store's shape. The block stops
with a plain message if:

* a `DEBATE_` variable is set in the shell;
* a `caselist pull` is running;
* it is Wednesday in Chicago.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t10-incremental-aggregate-rebuild
if env | grep -q '^DEBATE_'; then echo 'STOP: a DEBATE_ variable is set in this shell; open a new terminal'; elif pgrep -f 'caselist pull' > /dev/null; then echo 'STOP: a caselist pull is running'; elif [ "$(TZ=America/Chicago date +%u)" = 3 ]; then echo 'STOP: it is Wednesday in Chicago, the weekly run day'; else .venv/bin/python scripts/measure_rebuild_scaling.py real --data-dir ~/.debate-research/dev --caselist hspolicy26; fi
```

Success looks like exit 0 and one JSON line: the version directory, sources, cards, distinct full
bodies, the rebuild's seconds by phase, and the components' counts. Every value is a count, a number
of seconds or a share. Paste the JSON line back.

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
