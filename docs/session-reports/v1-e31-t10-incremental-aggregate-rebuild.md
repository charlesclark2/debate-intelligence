# Session report: v1-e31-t10-incremental-aggregate-rebuild

| | |
|---|---|
| Task | `v1-e31-t10-incremental-aggregate-rebuild` — The weekly aggregate rebuild costs what the week added, not the whole store |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t10-incremental-aggregate-rebuild.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t10-incremental-aggregate-rebuild.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t10-incremental-aggregate-rebuild` |
| Session status | PARTIAL: Stage 1 built; ac4 is the operator's, after the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**This task does not merge until dev's `docx-9` run image is built** (before Tuesday 2026-11-10
06:00 Chicago, the PM's ruling Q5). So the 2026-11-11 full re-parse runs the rebuild that ran on
2026-11-05. This task's rebuild first runs in the image built after that, where it rebuilds in full
once, since no directory holds a placement state yet; the run after that is the first placed from one.

**What was built (Stage 1, by the PM's second ruling of 2026-11-06).** The rebuild now keeps
`placement-state.sqlite` beside the aggregates. It holds what placing a card reads of it, each
distinct full body's words as numbers in one vocabulary, and each body's MinHash signature. A weekly
rebuild reads the documents of only the sources it added, signs only their new bodies, and places
every card again, so the occurrence table is today's full rebuild's, byte for byte. MinHash takes
column minima over one array of digests (the same signatures, 2.9 times faster). A removal deletes
the state wherever it reaches an aggregate, here and in the bucket, and records it.
`parse.incremental_rebuild` turns its use off.

**What it measures.** On the 2,000-source synthetic store, a week of 5% new sources:

* The week rebuilds in 10.6 to 10.9 s, against **76.05 s for today's full rebuild** of the same store
  (**0.14**, ac3).
* Against this build's own full rebuild, which got the faster MinHash too (38.8 to 41.7 s), it is
  **0.26 to 0.28**.

The remaining cost is re-clustering every body, which grows with the store. That is Stage 2's to
remove (Follow-up 1).

**The Goal stays `InProgress`.** ac4 is the first weekly run placed from a state and a by-hand full
rebuild, both after the merge.

**Look first at:**

* ac3's two denominators (below), which is the PM's to read.
* Decision 3: a record line naming a state is refused by an older build.
* Deviations: the `debate_cli` changes the ruling required.

## The PM's rulings (2026-11-06), as read here

**The first ruling.** Q1: Stage 1 here, Stage 2 a follow-up. Q2/Q3 deferred the state to Stage 2.
Q4: no switch. Q5: the image does not wait. Q6: commit the measurement script. Its Q1 and Q2/Q3
pointed different ways, since Stage 1 as proposed *was* the state, and the session asked. The
question and the stateless option it offered stay in this report's history (commit `670cd80`).

**The second ruling: (A), with (B)'s MinHash change riding along, estimate about 17h** (now the
spec's `estimatedEffort`).

1. The state sits beside the aggregates, published with them. It holds card words as numbers plus a
   vocabulary and digests only, and records the parser version, the fingerprint version and the set
   of per-source digests it was built from. Done (Decision 1).
2. It is used only when its versions, its digest set (less the week's additions) and the file all
   match. Anything else is a full rebuild that writes a new one. Each case is tested.
3. A removal deletes it wherever `v1-e30-t33` reaches an aggregate: both sides, every version,
   recorded in the aggregate record and counted as residue. It never edits it. The removal
   credential can already delete any key under `parsed/`, so no grant changes (Decision 4).
4. Restore, `--publish`, `--publish-only` and retention carry it. Confirmed under "What carries the
   state".
5. `parse.incremental_rebuild`, default on; off is a full rebuild that still writes a state; no CLI
   flag. Done.
6. The oracle is today's rebuild, reachable only from the tests, with Hypothesis properties, red
   runs, mutants and agreement 8. Below.
7. The state's size, and the estimates. Below.
8. ac2 and ac3 close here; Stage 2 is Follow-up 1.
9. The merge waits for the `docx-9` image, and the measurement block is as ruled before.

## What was built

* **The state's model**, `debate_core/application/ports/placement_state.py`.
  * `PlacementState`, `PlacedCard`, `PlacedAnchor`, `PlacedBody` and `UnreadablePlacementState`.
  * The `ParsedStore` port gains `read_placement_state` and `write_placement_state`, and
    `PLACEMENT_STATE_NAME` joins `REBUILT_NAMES`. That is how the publisher and the removal's
    directory listings reach it.
* **The file**, `integrations/local/placement_state_file.py`.
  * SQLite in 64 KiB pages, written fresh into a temporary file and renamed into place, never edited.
  * Read read-only and immutable, so a read leaves no journal beside it.
  * Checked whole before anything is returned: the layout, the stamps, every number inside the
    vocabulary, every full card's body present, every signature 128 values. Anything else is
    `UnreadablePlacementState`.
  * The in-memory fake keeps the object.
* **The placer**, `caselist_card_stats.CardPlacer`.
  * `add(card)` now returns the `PlacedCard` it kept.
  * `add_placed` takes a card as the state holds it.
  * `adopt` begins from a state's vocabulary and signatures.
  * `placements()` gives the clusterer the words as numbers (`BodyWords.from_numbers`) and the
    stored signatures.
* **The clusterer**, `evidence/near_duplicates.py`.
  * `minhash_signature` takes column minima.
  * `cluster_near_duplicates` takes stored signatures (`signatures=`) and words without text.
  * No rule changed.
* **The service**, `caselist_parse.CaselistParseService`.
  * `run` passes the digests it wrote.
  * `_rebuild` asks `_usable_state` whether the state may be used, takes each placed source's cards
    from the state or from its document, writes the aggregates, then the state.
  * It logs one line saying which way it placed the cards and, for a full rebuild, why
    (`FullRebuildReason`).
  * `incremental_rebuild` comes from `parse.incremental_rebuild`.
* **The removal**, `removal_plan.py` and `removal_service.py`.
  * `AggregateAction.DISCARD`: the plan lists each reached state on each side without reading it.
  * The execution deletes it here, and every version in the bucket, a re-run included.
  * It is recorded under `deleted` in `removal-aggregates.jsonl`, and the record's key pattern admits
    it.
  * The command shows the states under a heading of their own and counts them in `aggregates_done`.
* **The oracle**, under `packages/debate_core/tests`.
  * `tests/evidence/near_duplicates_at_start.py` is the clusterer as the task found it (`81ed12e`),
    the whole module.
  * `tests/application/rebuild_at_start.py` is today's `CardPlacer` and rebuild, giving the bytes
    of the index, failures file and table.
* **The measurement script** has an `incremental` mode (prepare, week, full) for ac3, and its `real`
  mode stays read-only (it now writes the state only to a temporary file, to size it).

## The proposal, as the PM ruled on it (before any code)

Everything here is measured on synthetic stores of invented words, or read from records already in
`docs/`. No real card text was read. The scratch scripts and their raw output are kept, uncommitted,
in the worktree's ignored `.task/measurements/`. The measurement is now committed as
`scripts/measure_rebuild_scaling.py`, which gives the same figures (its `synthetic` mode).

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

| Node | Status | Notes |
|---|---|---|
| `incremental-rebuild` (Incremental aggregate rebuild) | Done but for ac4 | Proposal and measurement first (`b24cd37`, no code); Stage 1 as ruled; red runs against two skeletons and the pre-task removal; 26 mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the scaling measured on synthetic stores of at least three sizes, with where the time goes, before any change | PASS | Four sizes (250, 500, 1,000, 2,000 sources), timed by phase, beside every recorded real figure: proposal (a), committed in `b24cd37` before any code. Reproducible with `scripts/measure_rebuild_scaling.py synthetic --sources 250 500 1000 2000`. The real phase split is the operator's block below, which adds to it and closes nothing |
| ac2: an incremental rebuild after a week's new sources gives an occurrence table equal, row for row, to a full rebuild of the same store, by a property over generated weeks, including a week that merges two existing clusters and one a removal shrank | PASS | See "ac2" below |
| ac3: on the largest synthetic store, an incremental rebuild for a week of 5% new sources takes under a quarter of the full rebuild's time, with the figures | PASS against the full rebuild the task replaces (0.14); **0.26 to 0.28 against this build's own full rebuild** | See "ac3" below. Which full rebuild ac3 means is the PM's to read |
| ac4: operator-run: the next weekly run's parse stage duration, and a by-hand full rebuild, recorded in `docs/data/caselist-parse-report.md` | NOT RUN | Needs this branch merged, imaged and a weekly run placed from a state, after the `docx-9` re-parse. Operator follow-up B |
| Node: Card stats tests pass (`uv run pytest packages/debate_core/tests -k "card_stats or rebuild or occurrence"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n auto -p no:warnings packages/debate_core/tests -k "card_stats or rebuild or occurrence"` → `226 passed in 40.49s` |

### ac2: equal to today's full rebuild, byte for byte

* **The oracle.** `tests/application/rebuild_at_start.py` and `tests/evidence/near_duplicates_at_start.py`
  are the rebuild and clusterer at `81ed12e`, copied whole. They give the index, failures file and
  occurrence table as bytes, and are reachable only from the tests.
* **The property.** `test_caselist_parse_incremental_equivalence.py::test_after_every_step_the_table_is_todays_full_rebuilds`.
  * A first week of two to five sources, then one to six steps.
  * The steps: weeks of one to three sources, perhaps re-listing an older one; a removal (source
    stopped, per-source file and state deleted); a source stopped elsewhere with the state left; the
    state deleted; a parser version change.
  * The cards come from four invented articles: copies, one, two or three words changed (two changed
    is a copy only the MinHash bands join), cuts, short cuts, longer extents, abbreviated cards (some
    under a second cite) and cite-only cards.
  * After every step, the index, failures file and table equal the oracle's.
  * Run with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, `--hypothesis-show-statistics`: 200
    passing, 18 invalid, 10.13 s. Events, as shares of all 218 cases:

    | Event | Share of cases |
    |---|---|
    | week: placed from the state | 54.59% |
    | state deleted: placed (NO_STATE) | 35.32% |
    | version change: placed (NO_STATE) | 33.03% |
    | remove: placed (NO_STATE) | 31.65% |
    | stop elsewhere: placed (SOURCES_DIFFER) | 26.61% |
    | **a week moved an older card to another cluster** | **18.35%** |
    | nothing new: placed from the state | 8.72% |
* **A week that merges two existing clusters**:
  `test_a_week_that_merges_two_existing_clusters_is_placed_as_a_full_rebuild_places_it`, worked by
  hand.
  * X and Y, three words apart (Jaccard 81/111 = 0.73), are two clusters.
  * A cut of X stays out of both, its witnesses being two clusters.
  * Z, a copy of each (0.81 from X, 0.90 from Y), joins them, and then the cut joins too.
  * All four take the smallest of the four fingerprints. The week reads one document, and the table
    equals the oracle's.
* **A week a removal shrank**: `test_a_week_a_removal_shrank_is_rebuilt_in_full_and_its_state_holds_none_of_the_removed`.
  Rebuilt in full (`NO_STATE`), reading the two remaining documents. The table equals the oracle's,
  and the new state holds the two sources only.
* **At scale**: on the 2,000-source synthetic store, the table the week placed from the state and the
  table the start commit's rebuild wrote over the same store have the same SHA-256 (clone c below).

### ac3: the figures

All on the operator's Mac, worktree venv, seed 20261106.

| What | How | Figures |
|---|---|---|
| The store | | 1,900 sources prepared, then a week of 100 (5%) added: 2,000 sources, 43,518 cards, 20,829 distinct full bodies, 6,582,963 words of them |
| Its week, placed from the state | `measure_rebuild_scaling.py incremental week`, four clones of one prepared store | **10.92, 10.60, 10.68, 10.84 s.** 100 of 2,000 documents read, 851 bodies signed |
| This build's full rebuild, setting off | `incremental full` after each week | **39.21, 38.78, 41.74 s**, and 38.87 s in `real` mode. The table equals the week's every time |
| The full rebuild the task replaces | the start commit's code (`git archive 81ed12e`) first on `PYTHONPATH`, `measure.py rebuild` over clone c after its week | **76.05 s** (MinHash 57.05 s). Its table equals the week's |

* Against the rebuild the task replaces: 10.68 / 76.05 = **0.14**.
* Against this build's full rebuild, which got the faster MinHash too: **0.26 to 0.28**.

Where the week's 10.84 s goes (clone d):

| Phase | Seconds |
|---|---|
| `CutIndex` | 3.26 |
| Band pairs and Jaccard | 2.88 |
| Cut step | 1.11 |
| Joins of copies | 0.58 |
| MinHash, new bodies only | 0.86 |
| Writing the table | 0.54 |
| Reading the state | 0.40 |
| Linking | 0.29 |
| Reading documents | 0.26 |
| Fingerprints | 0.22 |
| Writing the state | 0.15 |

Re-clustering every body is 72% of it, the same work the full rebuild does.

At the smaller sizes, the same three steps:

| Sources | Week | Full (setting off) | Ratio |
|---|---|---|---|
| 250 | 1.08 s | 5.62 s | 0.19 |
| 500 | 2.32 s | 11.63 s | 0.20 |
| 1,000 | 4.93 s | 22.16 s | 0.22 |
| 2,000 | 10.84 s | 41.74 s | 0.26 |

The ratio rises with the store because Stage 1 still re-clusters every body. That is what Stage 2
removes.

The machine was loaded: other sessions and the editor, load average 4 to 8 during these runs. One
earlier full run at a load near 100 took 74 s and is not used.

### The state's size (the ruling's item 7)

64 KiB pages; the 2,000-source state was 61.0 MB at the default 4 KiB pages.

| Sources | State | Occurrence table |
|---|---|---|
| 250 | 8.4 MB | 3.7 MB |
| 500 | 14.9 MB | 7.6 MB |
| 1,000 | 26.3 MB | 15.2 MB |
| 2,000 | 46.3 MB | 30.7 MB |

At 2,000 sources, 41.3 MB of it is content, and pages and indexes are the rest (12%):

| Content | Size | Per unit |
|---|---|---|
| Words | 26.3 MB | 4 B a word |
| Signatures | 10.7 MB | 512 B a body |
| Cards | 4.3 MB | 99 B a card |
| Vocabulary | 46 KB | |

**Estimates** (the operator block's `placement_state_bytes` gives hspolicy26's measured):

* **hspolicy26**, the store `v1-e40-t39` measured: 26,968,420 words in 29,866 distinct bodies,
  126,681 cards. That is 108 + 15 + 13 MB of content, about **150 MB**.
* **All four followed stores.** No word count is recorded for the other three. At hspolicy26's
  213 distinct-body words and 0.24 distinct bodies per card, the 349,977 cards of the 2026-11-05 run
  give about **420 MB**. That is an upper figure, since LD and PF cards are shorter.
* **A week.** Each weekly run rewrites the state of each caselist it parses, so the bucket gains one
  noncurrent version of each: up to about 0.4 GB a week.
  * Dev keeps noncurrent versions 30 days, about 1.7 GB held.
  * Prod keeps them 365 days, up to about 20 GB if a state were published there weekly.
  * Each cloud run's restore downloads the current states, about 0.4 GB.

### What carries the state (the ruling's item 4)

* **`caselist parse --publish`** sends it with the aggregates, through `REBUILT_NAMES`.
  * `test_publish_uploads_every_object_of_the_current_version_under_its_prefix`: the state is among
    the last four puts, with its SHA-256 recorded.
  * `test_publish_after_a_new_snapshot_uploads_only_the_new_source_and_the_aggregates`: the new
    source, the two changed aggregates and the state.
  * The pull's parse stage publishes it too (the smoke check counts 23 objects).
* **`--publish-only`**: `test_publish_only_sends_exactly_what_the_rebuilds_publish_sends_and_reports_it_alike`
  finds exactly one state in the second bucket, and the partial-publish test sends it again.
* **`caselist restore-run-state`**: `test_the_copy_holds_the_runs_state_and_the_data_directory_and_the_bucket_are_left_as_they_were`
  finds the state in the copy, with every parsed file's SHA-256 equal to the live one.
  * The restore lists every object under the version directory (`run_state._restore_parsed`).
  * It fetches through `S3EvidenceObjectStore.get_file`, which verifies the SHA-256 the publisher
    recorded (`integrations/s3/object_store.py`).
* **Retention's tagging**, guaranteed by the code and not tested here.
  `S3VersionDirectories._retag(prefix)` tags every object it lists under the directory's prefix
  (`integrations/s3/version_directories.py`), so the state is tagged with the aggregates. The
  lifecycle rule expires it with them, and a removal deletes a retired directory's state as `DELETE`
  with its tables.

### Red runs

Each was run with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`.

* **R1, checks that refuse nothing**: `_usable_state` returns any readable state.
  * Result: 7 failed and 10 passed in the directed file: every version, rules and sources case. The
    property passed.
  * Why: the table stays exact without the checks, because the rebuild takes from the state only the
    sources it places. So the checks are pinned by the way each run placed its cards (documents read,
    log reason), not by the table. Decision 2.
* **R2, the state plus the week's additions**: every source the state holds is placed.
  * Result: the property failed at a "stop elsewhere" step, where the stopped source's card moved a
    live card's cluster id.
  * The directed tests errored in that run, which disabled pytest's logging plugin; they are not
    counted.
* **The removal tests against the removal as it was before this task** (`20119f1`): 4 failed, at
  `removal_plan.py:1447`, `KeyError: 'placement-state.sqlite'`. That code could not plan a directory
  holding a state.
* **The script's read-only test** with a planted write: failed at its tree comparison.

### Mutants

`.task/mutants.py`, uncommitted: one exact replacement per mutant, the named test files under
`scripts/hard_stop.py 115`, the file restored from `HEAD` after each. **Every run used a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`** (agreement 8), so no example was replayed.

The final run, over the final code, caught all 26:

| # | Mutant | Caught by |
|---|---|---|
| 1 | the setting off is not honoured | the setting-off test |
| 2 | an unreadable state is not caught | the four unreadable cases (the run raises: the failure the check exists for) |
| 3–5 | parser, profile or fingerprint version not compared | the full-rebuild cases |
| 6 | the rules not compared | the full-rebuild cases |
| 7, 8 | a state of fewer, or of more, sources accepted | the full-rebuild cases |
| 9 | the week's additions not set aside | the week tests (every document read) |
| 10 | the state's cards taken in reverse | the week tests and the property |
| 11 | a stored body's words not given | the week tests and the property, by `add_placed` raising |
| 12, 13 | a full card's short-cite key dropped; an anchor's ends swapped | 19 to 21 tests each, the property among them |
| 14 | the words-held check reads every fingerprint | the shared-text test, by raising: the bug itself, found while writing the placer |
| 15 | the state's signatures not adopted | the test that a week signs only its new bodies |
| 16 | a stored signature is another body's (rotated) | the merge test, whose X–Z join only the bands make |
| 17 | the linker spells from another vocabulary | 20 tests |
| 18, 19 | MinHash's column beside; big-endian | the MinHash property against the old code |
| 20 | a body's words reversed | 20 tests |
| 21 | a missing body not refused | the inconsistent-state cases (the run raises) |
| 22 | the layout not checked | the layout test |
| 23 | a removal leaves the state here | the removal test |
| 24 | a removal leaves the state's versions in the bucket | the re-run test |
| 25 | a removal does not plan the state in the bucket | three removal tests |
| 26 | the container does not pass the setting | the command test |

**What the first runs changed.** Five survived at first (14, 15, 16, 17, and 24):

* 14, 15 and 24 found missing tests, now written:
  * a full card sharing its text with an abbreviated card seen first;
  * a week signs only its new bodies;
  * a re-run deletes every version.
* 16 was a weak mutant: it mirrored the signatures, so the middle body kept its own. It now rotates
  them. The property also gained the band-only copy.
* 17 removed the renumbering of word numbers and changed nothing. A word's number decides nothing
  in the clusterer, as the hash seed decides nothing. Under agreement 8 the renumbering was deleted
  (`58ac0e9`), and its test became the claim it stood for: clusters from numbers in any vocabulary
  order equal clusters from text, which joins bodies in 51% of examples.

### Before the report

* Ruff: `ruff format --check .` → 1995 files already formatted; `ruff check .` → All checks passed.
* `uv run pyright packages/debate_core packages/debate_cli` → 0 errors.
* `uv run lint-imports` → 20 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 72 handlers within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 643 files.
* `scripts/check_command_blocks.py --base origin/dev` and `scripts/check_links.py` → OK.

**The affected set** (`uv run scripts/affected_tests.py`) reaches **717 test files**, far over two
minutes, so by agreement 10 it is left to the pull request's `ci` check. Run within the limit
instead, each under `scripts/hard_stop.py 115 … -n auto`:

| Run | Result |
|---|---|
| The always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) | 378 passed |
| `packages/debate_core/tests/application/caselist/` | 1903 passed |
| `packages/debate_core/tests/application` (but caselist) | 3527 passed |
| `packages/debate_core/tests/evidence/` with `test_local_parsed_store.py` | 1826 passed |
| `packages/debate_core/tests/integrations` | 3894 passed, 2 xfailed |
| `packages/debate_cli/tests` (but bucket mode) | 1537 passed |
| `packages/debate_cli/tests/bucket_mode`, in three parts | 113, 59 and 103 passed |
| `tests/scripts/test_measure_rebuild_scaling.py` with the fakes-port check | 69 passed |
| `tests/smoke`: the pull, remove, camp identity, parse, parses owed, restore, retire and store checks | 9, 55 and 14 passed |

## Files changed

* **`debate_core.application`**:
  * `ports/placement_state.py` (new);
  * `ports/parsed_store.py` (the port's two methods, `REBUILT_NAMES`);
  * `ports/suppression.py` (the record's key pattern);
  * `caselist_card_stats.py` (the placer);
  * `caselist_parse.py` (the rebuild, the checks, the log line, the docstring);
  * `settings.py` (`parse.incremental_rebuild`);
  * `caselist/removal_plan.py` and `removal_service.py` (`DISCARD`).
* **`debate_core.evidence`**: `near_duplicates.py` (MinHash by columns, stored signatures, words
  without text).
* **`debate_core.integrations.local`**: `placement_state_file.py` (new), `parsed_store.py`.
* **`debate_core.testing`**: `fakes/parsed_store.py`.
* **`packages/debate_core/tests`**:
  * the oracle modules, `placement_world.py`;
  * the new placement-state, equivalence and MinHash tests;
  * removal tests;
  * the test placers made `CardPlacer` subclasses;
  * object-count pins (a published directory now holds one object more).
* **`scripts/`**: `measure_rebuild_scaling.py` (new).
* **`docs/data/parsed-card-store.md`**: the state, the layout, removal, publishing.
* **The spec**: `estimatedEffort` 17h, as ruled.
* **Outside the task's packages** (Deviations): `debate_cli` and its tests; `tests/scripts`,
  `tests/architecture`, `tests/smoke`.

## Deviations from the spec

1. **`debate_cli` changed**, outside `constraints.packages`, because the ruling requires it.
   * `container.py` passes `parse.incremental_rebuild` (item 5).
   * `commands/caselist_remove.py` gains the states' heading, the execution line's count, and
     `aggregates_done.placement_states_deleted` (item 3: the plan's text and the `--json` pins).
   * Their tests: `test_caselist_parse.py` (the setting through the command),
     `commands/test_caselist_remove_aggregates_output.py`, and
     `bucket_mode/test_restore_run_state.py` (item 4).
2. **Root `tests/` changed**, also outside the packages.
   * `tests/scripts/test_measure_rebuild_scaling.py` is the script's test.
   * `tests/architecture/test_fakes_reach_only_their_port.py`: the checker's own self-test pins the
     ports reached through the parsed-store fake, which now include the placement state's.
   * `tests/smoke/test_caselist_pull.py`: the published object count.
3. **ac3's denominator** is ambiguous once the full rebuild itself got faster: 0.14 against the
   rebuild the task replaces, 0.26 to 0.28 against this build's own. The PM decides which reading
   closes ac3.
4. **The state's digest set is the sources the rebuild places**, a refinement of item 1's "the set of
   per-source digests it was built from". Decision 1 gives the reason.
5. `git fetch origin dev` was run once, read-only, to diff this spec against dev before setting its
   estimate. Nothing differed but the phase.

## Decisions and assumptions

1. **The state holds the sources the rebuild places**: parsed, stored by the manifests, live under
   the suppression list. It does not hold every per-source file. A stopped source's file is never
   published (`v1-e31-t26`), so its words must not reach a published file either. A source stopped,
   reinstated or removed since the state was written changes the placed set, so the run rebuilds in
   full (`SOURCES_DIFFER`). Failed and unsupported sources have no cards to hold.
2. **The checks are the ruling's, though the table would be exact without them** (R1). The rebuild
   asks the state only for sources it places, and each card's projection depends only on its
   per-source file, which is never rewritten in a directory. The checks keep the rule simple and
   auditable, make a stale or foreign state a full rebuild rather than a partial reuse, and keep a
   stopped source out of the next state. Tests pin them by the path a run takes.
3. **A record naming a state is refused by an older build.** `removal-aggregates.jsonl` validates
   each key against a pattern, and a build carrying `v1-e30-t33` but not this task knows only the four
   tables. After a removal by this build, `caselist remove` and `caselist status --residue` must run
   from a build carrying this task. That is the rule `v1-e30-t33` set for itself; the weekly run's
   status does not read the record. `parsed-card-store.md` says so, and the removal runbook should
   (Follow-up 3).
4. **A removal deletes every version of a reached state**, a re-run included, as a retired
   directory's aggregates are deleted. That is safe, since the next run rebuilds in full. No grant
   changes: the takedown credential may delete any key under `parsed/*`, and the run role's everyday
   policy may put any key (`operator_access.tf`).
5. **No renumbering of words**: mutant 17 showed it decided nothing (above).
6. **Signatures are 32-bit arrays**, 512 B a body against 4.6 KB as a tuple of ints.
   `test_what_linking_holds_grows_by_a_few_bytes_a_word` held the placer to that.
7. **64 KiB pages**: 24% smaller, written faster, read back identically.
8. **A state that cannot be read never stops a run**: every failure to read or check it is
   `UNREADABLE`, a full rebuild.
9. **A full card can share its fingerprint with an abbreviated card**, the same first-and-last-words
   text parsed two ways. The placer first checked the wrong map for a body already held, and would
   have raised. It was found while writing the placer; mutant 14 now pins it.
10. **The measurement's `real` mode reads no state and writes none.** It times a full rebuild, and it
    sizes the state by writing it to a temporary file outside the data directory.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

**A. The real phase split, dependency components and state size (read-only, after the weekend).**
The script runs over this Mac's own dev data directory, `~/.debate-research/dev`.

* It times this branch's full rebuild of `hspolicy26`'s newest version directory
  (`2026.10.27-docx-7`, the store `v1-e40-t36` and `v1-e40-t39` measured).
* It counts the clusterer's dependency components (Stage 2's question).
* It sizes the placement state that store would get.
* Nothing is written to the data directory: the aggregates are rendered to a SHA-256 in memory, and
  the state to a temporary file elsewhere. `test_real_mode_reads_the_store_and_writes_nothing` holds
  it to that.

**Expected runtime: about 10 to 20 minutes, up to 30 on a busy Mac.** The rebuild is the bulk: 741 s
when `v1-e40-t39` measured this store, less now that MinHash is faster. Counting components reuses
the rebuild's own index and signatures (2.6 s against a 39 s rebuild at 2,000 synthetic sources). It
needs about 1 GB of memory.

The block stops with a plain message if a `DEBATE_` variable is set in the shell, or if a
`caselist pull` is running.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t10-incremental-aggregate-rebuild
if env | grep -q '^DEBATE_'; then echo 'STOP: a DEBATE_ variable is set in this shell; open a new terminal'; elif pgrep -f 'caselist pull' > /dev/null; then echo 'STOP: a caselist pull is running'; else .venv/bin/python scripts/measure_rebuild_scaling.py real --data-dir ~/.debate-research/dev --caselist hspolicy26; fi
```

**What success looks like:**

* After the rebuild, one line on stderr: `{"rebuild_seconds": ...}`.
* Then exit 0 and one JSON line on stdout. It holds:
  * the version directory, sources, cards, distinct full bodies and their words;
  * the rebuild's seconds by phase and `table_equals_the_stores`;
  * `placement_state_bytes`;
  * the component counts for the newest snapshot's sources and for the last 5%;
  * the peak memory.
* Every value is a count, a number of seconds, a share or `true`/`false`.

Paste both lines back. If `table_equals_the_stores` is `false`, the store's table was written by a
build other than this checkout; the timings still stand.

**B. ac4, after the merge.** Not a command yet: it needs this branch in a run image, the 2026-11-11
`docx-9` re-parse, one full rebuild on the new image (it writes the first states), and then the first
weekly run placed from a state. Then:

* Record that run's parse stage seconds from its stage lines, and its rebuild line ("placed from the
  placement state, N of M placed sources read").
* Make a by-hand full rebuild of a restored copy, by the restore sequence of
  `docs/runbooks/caselist-cutover.md`.
  * Take the SHA-256 of `occurrences.jsonl` as restored.
  * Run `caselist parse --caselist hspolicy26` over the copy with
    `DEBATE_PARSE__INCREMENTAL_REBUILD=false` for that one command.
  * Take the SHA-256 again. The two must be equal, and the line must say `rebuilt in full
    (TURNED_OFF)`.
* Record both in `docs/data/caselist-parse-report.md`.

The paste-ready block should be written from the runbook when the run exists, with its guards: the
copy's own `DEBATE_STORAGE__DATA_DIR`, unset afterwards, and no publish.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

1. **Stage 2: the placement re-clusters only what a week reaches (E31, by the PM's ruling Q1, about
   9h).** Stage 1 measured why it is needed: at 2,000 synthetic sources, 72% of a week placed from the
   state is re-clustering every body, and the ratio to a full rebuild rises with the store (0.19 at
   250 sources to 0.26 at 2,000).

   **The rule.** Placement is not monotone (proposal (b)), so the only exact incremental placement
   re-clusters every dependency component a new body reaches. Three kinds of edge join two distinct
   full bodies:
   * a band-candidate pair with Jaccard at the threshold;
   * a confirmed containment, either way;
   * for a short body, a body holding both its ends.

   The clusterer on the whole store, restricted to one component, equals the clusterer on that
   component alone. Edges from a short body whose both-end holders span ten or more components are
   dropped, and the restricted run is told it is too common. Linking is partitioned by short-cite
   keys, tied together where one abbreviated text appears under two keys.

   **What it adds to Stage 1's state:** each body's component and each card's placement. It already
   has each body's words and signature, the cards' keys and the stamps.

   **What a run does.** It signs only the new bodies, finds their edges, and re-clusters the new
   bodies, the stored components they reach, and the stored short bodies a new body holds both ends
   of. It re-links the key groups those changes reach, then makes every row and writes the table and
   the state whole.

   **The rest is Stage 1's:** the same checks give a full rebuild, the same removal handling, and the
   same oracle with a property over generated weeks.

   **The size of it.** On synthetic stores a 5% week reaches 10 to 13% of distinct bodies (12.7% at
   2,000 sources by the script's `real` mode), against today's 100%. Operator block A gives the real
   store's figure.
2. **A cheaper Stage 1 week, if ac3 is read against this build's own full rebuild (E31, under 1h).**
   Keep each body's shingle count in the state. It is a function of its words, as the signature is.
   `CutIndex` then skips its first pass over every body, about 1.5 of the week's 10.8 s at 2,000
   sources, which would bring the week to about 0.23 of this build's full rebuild. Not done: beyond
   the ruling.
3. **The removal runbook (E30).** `docs/runbooks/caselist-removal.md` should say that after a
   removal by a build carrying this task, `caselist remove` and `caselist status --residue` run from
   such a build (Decision 3). The runbook is outside this task's packages.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-06

**Notes:**

The equivalence is proven where it can be broken. The oracle is the rebuild as the task found it,
copied whole. The property compares every aggregate after every step, removals and version changes
included. 18% of its cases move an older card to another cluster, which is the case a join-only
approach gets wrong, and R2 shows it does.

1. **ac1 passes.** Four synthetic sizes were timed by phase, beside every recorded real figure, and
   committed before any code (`b24cd37`). The finding that the real rebuild is sublinear in sources
   corrects the 900 s projection in the spec and in v1-e34-t17. The 1.54 against 1.07 disagreement is
   left open, with the block that settles it.
2. **ac2 passes.** The property ran 200 cases on a fresh database, with each event in a real share
   of them. The directed merge and the removal-shrank cases were worked by hand. At 2,000 sources the
   SHA-256 equals the start commit's.
3. **ac3 passes at 0.14.** The criterion was written against the rebuild the weekly run had when it
   was filed, and that is what the week now costs: 76.05 s to 10.7 s at 2,000 sources. The 0.26 to
   0.28 against this build's own, faster full rebuild is recorded beside it. The rising ratio (0.19 at
   250 sources to 0.26 at 2,000) is exactly what Stage 2 exists to remove.
4. **Red runs and mutants.** R1's result, that the table stays exact without the checks, is reported
   honestly. Pinning the checks by the path a run takes is the right answer (Decision 2). All 26
   mutants are caught, and the five that first survived each led to a real test or to deleting code
   that decided nothing (17).
5. **Deviations accepted.** The `debate_cli` and root-`tests/` changes are the ones the ruling
   required. Item 5 (`git fetch origin dev`, read-only) is noted: sessions make no network call but
   `scripts/task sync`, and this one should have asked.
6. **Decisions accepted.** 1, the state holds only the sources placed, which keeps a stopped source's
   words out of a published file. 3 is moot until an image carries this task, because no bucket
   directory holds a state before then; Follow-up 3 covers the runbook. 4 needs no grant change. 8, an
   unreadable state is a full rebuild and never a stop.
7. **The state's cost is accepted for dev**: about 0.4 GB a week and about 1.7 GB held under 30 days of
   noncurrent versions. Prod would hold up to about 20 GB under 365 days. Since the state can always
   be rebuilt, the PM files a p3: a lifecycle rule that expires `placement-state.sqlite`'s noncurrent
   versions in days, in both buckets.
8. **Follow-ups, which the PM files in the next batch:** Stage 2 (E31, p2, about 9h), with Follow-up
   2's shingle count folded in; the removal runbook line (E30, p3); the lifecycle rule above (E31,
   p3).
9. **Operator follow-up A** runs before the merge, from this worktree, while its `.venv` is here. It
   is read-only and takes no lock, so it can run alongside other work.
10. **Merge:** `scripts/task pr --partial` once `ci` is green and dev's docx-9 run image is applied
    (ruling Q5). The Goal stays `InProgress` until ac4 is recorded after the first weekly run placed
    from a state.
