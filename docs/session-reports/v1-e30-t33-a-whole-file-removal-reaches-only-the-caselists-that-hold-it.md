# Session report: v1-e30-t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it

| | |
|---|---|
| Task | `v1-e30-t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it` — A whole-file removal deletes only the aggregates of the caselists that hold the file, and its rebuild works in bucket mode |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM ruled on the proposal on 2026-11-05 (below); the build follows the ruling.

## The PM's ruling (2026-11-05), as the build reads it

* **(a)** As proposed, with one addition: a version directory retention has tagged
  (`debate-retention=superseded`, parsed-store-retention.md) is not rewritten. Its reached aggregates
  are deleted with their versions, as before, and the plan says so per directory; nothing is rebuilt.
* **(b)** As proposed, with row counts in the dry run and each table's bytes; tagged directories under
  their own heading as deleted; the new `--json` key with the smoke pins updated.
* **(c) Q1** The rewrite in place, under the bucket's run lock (say where it is taken and held); each
  rewrite checked before it is written (rows after = rows before less the rows naming the removed file,
  every kept line byte-identical, an unreadable line stops the run `INCOMPLETE` with nothing written);
  and every file a version directory holds listed first, saying what each carries from one source.
  **Q2** Withdrawals use the same rewrite, in this task. **Q3** Surviving clusters keep their ids and
  membership. **Q4** A new record beside the log; residue counts only older versions other than the
  rewrite, in the directories reached; the runbooks say `caselist status` runs from a build carrying
  this task. **Q5** Withdrawals stay in; the PM sets the estimate to 8h.
* **(d)** As proposed; promotion item 8 uses the same check, and prod's removal runs from a build
  carrying this task.
* Tests on synthetic stores with moto, shown failing first, covering the eight cases the ruling lists;
  mutants on the rules. No `--execute` outside tests until the PM's word.

## Proposal for the PM's ruling (ac1)

Read first: `removal_plan.py` (`_objects`, the `REMOVE` branch at `parsed_caselists = [*disclosing, OPENEV]`
and the aggregate loop after it), `removal_service.py` (`execute`'s order), `removal_residue.py`
("Manifests and aggregates"), `caselist_parse.py` (`_rebuild`, `_occurrence_rows`), `near_duplicates.py`
(the cluster id), `search_index_build.py` (`_clusters`, `_card_of`), `ports/parsed_store.py`,
caselist-removal.md step 5 and P1b, evidence-search.md J7, v1-e39-t10's operator record of 2026-11-05,
v1-e40-t10's restore and policy 1.18.

### (a) Which aggregates a whole-file removal plans

**The rule.** On each side, the bucket and this machine, the aggregates (`index.jsonl`, `failures.jsonl`,
`occurrences.jsonl`, and `camp_paths.jsonl` in `openev`) of exactly the `(caselist, version directory)`
pairs where that side holds a per-source file of the digest, current or in any version
(`parsed/<caselist>/<version>/sha256/ab/cd/<digest>.jsonl`). Nothing else.

**Why the per-source file is the right witness.** A version directory's aggregates are rebuilt from that
directory's own per-source files and nothing else (`_rebuild` reads `read_entries(caselist, version)`), and
`parse --publish` sends the per-source files before the aggregates. So an aggregate that names the digest
has the digest's per-source file beside it, in the same directory on the same side. A caselist whose
manifest holds the file but never parsed it has no per-source file and no row to remove. The plan already
lists every known caselist's `parsed/` prefix to find the per-source files, so this costs no new listing.

**The executor's order changes so that the witness outlives the rows.** For each reached directory: the
aggregates are handled first, then the per-source file is deleted with all its versions. A run that stops
in between leaves the per-source file, and a re-run finds the directory by it.

**Re-runs (v1-e30-t19).** A first run by an earlier build deleted per-source files before aggregates, so
its per-source files may be gone while its aggregates remain. For a request with an earlier run in the
log, the plan therefore also reads the current aggregates of every version directory of (1) each
caselist that request's scopes name and (2) each caselist the withdrawal record names for the file. It
plans each one that still names the digest.

**The seed's case.** The plan reaches only the bucket's `parsed/testcl26/2026.10.27-docx-7/`
aggregates. It reaches nothing on this machine, whose own store never held the seed. It does not reach
`testcl26`'s older directory (RM-2026-90's weeks) or any other caselist.

**Withdrawals** already plan only the caselists they withdraw from, and get the same per-directory rule.

### (b) The plan's text

The file's own objects stay under **WILL BE REMOVED**: the local blob, the `raw/` objects and the
per-source parsed files. Aggregate lines leave that section for one of their own, **AGGREGATES REWRITTEN
WITHOUT THE REMOVED ROWS**, grouped by side and version directory. Each line gives the key, the rows
that name the file (counted from the current object, which the dry run downloads) and the older versions
to be purged (or "versions not counted"). **TO CARRY IT OUT** adds: "N aggregates in M version
directories are rewritten in place; nothing is rebuilt afterwards". `--json` gets the same section as a
new key. The smoke and loose-ends pins hold removal JSON shapes whole, so they are updated in the same
change.

### (c) How the aggregates come back in bucket mode

| Option | Holds? | Why |
|---|---|---|
| Delete, then `parse --publish` from a copy restored under the dev lock (v1-e40-t10) | Partly | The restore brings each caselist's *current* directory only, so an older directory the removal reached stays without aggregates. It also means a restore (J2 took 351.8 s) plus a clusterer rebuild (536 to 741 s recorded for a large caselist), and the aggregates are absent from the delete until the publish. A backfile still needs its cloud task |
| Delete, then the removal rebuilds from the bucket's per-source files | No | A rebuild needs every per-source file of the directory, about 4.7 GB for `hspolicy26` under `docx-6`, plus the manifests and the clusterer, all on the Mac |
| Delete, then a cloud task rebuilds | Works, slowly | It needs a new task entry point. A backfile rebuild ran about 95 min on 2026-11-02, the gap stays, and it has to fit around the cloud run's day and lock |
| **The removal rewrites each reached aggregate without the rows that name the removed digest, and purges the older versions, as it does for manifests** | **Yes** | See below |

**What each aggregate's rows carry:**

* `index.jsonl`: one `SourceEntry` per source, with `source_sha256`. Its fields are the store record,
  the format, size, outcome, reason, detail and that source's card count. Every field is the source's
  own.
* `failures.jsonl`: the same entries, for sources that have no document.
* `occurrences.jsonl`: one row per card per disclosure. Each row has `source_sha256`, `disclosure` (the
  disclosure digest, or `None` for a camp row), the span, `snapshot`/`last_snapshot` (per disclosure),
  `exact_fingerprint`, `completeness`, and two fields worked out across the whole directory:
  `cluster_id` and `membership`.
* `camp_paths.jsonl` (openev only): one line per camp path, with `source_sha256` and
  `occurrence_table_sha256`, the SHA-256 of the `occurrences.jsonl` bytes it was written beside.

**Where the rewrite is exact.** Every row names its source digest, so every removed row goes. For
`index.jsonl` and `failures.jsonl` the result is byte for byte what a rebuild gives: each row is decided
for its own source alone. No aggregate stores a statistic. Totals and cluster counts are run outputs,
and the index build recomputes its own counts and `occurrences_sha256`.

**Where it differs from a rebuild: the surviving rows' `cluster_id` and `membership`.** They were worked
out with the removed cards present:

1. The cluster id is the smallest exact fingerprint in the cluster. If a removed card held the
   smallest, the survivors keep its fingerprint as their id.
2. Two clusters joined through a removed body (a copy, or the one witness for a cut) stay joined.
   Every two bodies in a cluster still overlap, because `overlap_throughout` is checked pairwise.
   Clusters a removed body kept apart, as a second witness, stay apart.
3. An abbreviated card linked to a removed full card keeps `ABBREVIATED_LINK`, in a cluster with no
   full card left. One left `UNLINKED` because it matched a removed card and another stays `UNLINKED`.

**I do not think this makes the rewrite wrong.** These are not the removed file's rows, and no removed
text survives. The surviving table is the one every reader already sees right after a removal: the
index build drops suppressed rows and keeps the cluster ids (`_clusters`). So the index built from a
rewritten table is the one the pilot serves today between a removal and its rebuild. No reader assumes
a cluster id is one of its rows' fingerprints: `_card_of` picks the representative from the rows and
checks that row's own fingerprint. The caselist's next ordinary rebuild recomputes both fields.

**Mechanics.**

* Each reached table is streamed. Each line is parsed as JSON only to read `source_sha256` (and
  `disclosure` for a withdrawal). A line that is kept keeps its bytes, so a newer build's rows survive
  unchanged and the sort order holds. A line that is not a JSON object with a source digest stops the
  run `INCOMPLETE` before anything is written.
* The rewrite goes up through `put_file`, which records the SHA-256 as the publisher does, so a later
  restore's digest check passes. Once the bucket confirms the rewrite as the current version, the
  takedown credential deletes every other version. On this machine the rewrite is an atomic replace.
* `camp_paths.jsonl` is rewritten after its table, without the removed digest's lines and with the new
  table's SHA-256. Without that, every camp row would lose its camp path digests.
* In bucket mode all of this runs under the run lock that `--execute` already holds.
* A backfile such as `hspolicy25` goes the same way, with no cloud task.
* Cost: each reached table is downloaded and uploaded once. This Mac's stale tables measure up to
  95.0 MB (`hspolicy26` occurrences, sizes read with `stat` only). I have not measured the bucket's.
* No rebuild, no restored copy and no cloud task follow the removal. A table whose only rows were the
  removed file's is rewritten empty, which is also what a rebuild would give.

**What else has to change with it.**

* `caselist status` counts every aggregate version older than the removal's completion, in every
  caselist the removal touched, as residue. So it would count the rewrite itself, and every directory
  (a) leaves alone.
* The fix is to record each rewrite (key and version id) and count only the older versions other than
  the rewrite, in the reached directories.
* `removal-scopes.jsonl` is read by the installed build under `extra="forbid"`
  (`test_suppression_list_is_read_by_every_build.py`), so a new field there would make that build
  refuse the file. The record goes in a file of its own beside the log, for the reason the scopes went
  beside the log.
* An installed build older than this one will report the rewrite as residue until it is upgraded.

### (d) The runbooks

* **caselist-removal.md, step 5.** Drop "Then rebuild the parsed card store's aggregates" and the
  backfile paragraph. Say instead that the removal rewrites each aggregate the plan lists, in the bucket
  and here, purges the older versions, and prints the count. Nothing is rebuilt afterwards, backfiles
  included.
* **P1b.** Becomes "Right after `DONE`: the aggregates were rewritten": `DONE`'s aggregate count must
  equal the plan's, and no parse runs. P3's sentence on "aggregates hold no occurrence rows" now means
  the store's only rows were the removed file's.
* **caselist-backfiles.md.** "A removal adds a rebuild for each backfile" goes, since there is no
  rebuild.
* **evidence-search.md, J7.**
  * The dry run goes on only if **WILL BE REMOVED** lists the one file, its object under
    `raw/caselist/testcl26/` and its parsed file under `parsed/testcl26/2026.10.27-docx-7/`.
  * **AGGREGATES REWRITTEN** must list exactly that directory's three aggregates, in the bucket only.
  * Then step 5's `--execute`, as its own block, guarded on a set `DEBATE_` variable and a running pull.
  * No P1b parse.
  * J8 and J9 stay as they are. J9's check holds, since no other store's `occurrences_sha256` changes.
* **parsed-card-store.md and the module docstrings.** Every sentence that says a removal deletes the
  aggregates "until the next run" is corrected: `removal_plan`, `removal_residue`, and the port's
  `read_index`.

### Effort

This is more than the spec's 4h: the planner, a new plan section and JSON key, the executor's
rewrite, order and purge, the rewrite record and the residue rule, the CLI text, and three runbooks.

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

None.

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
