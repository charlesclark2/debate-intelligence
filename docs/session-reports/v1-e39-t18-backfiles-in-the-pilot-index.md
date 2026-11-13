# Session report: v1-e39-t18-backfiles-in-the-pilot-index

| | |
|---|---|
| Task | `v1-e39-t18-backfiles-in-the-pilot-index` — Backfile seasons searchable on the pilot, without slowing its cold start |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t18-backfiles-in-the-pilot-index` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped for the PM's ruling on the index's shape (ac1 done, ac2 not started). After hspolicy25's
cloud rebuild to `2026.11.03-docx-9`, the operator restored the dev run's copy with all four
backfiles, built today's index (byte for byte the one dev publishes) and a combined one, and loaded
both in the function's image ([The measurement so far](#the-measurement-so-far)). The combined index
breaks every size and cold-start target of ADR-0019: 3.97 GB of SQLite, 1.46 GB gzip, a 19.1 s load
against 6.96 s today, a swap needing 185% of the function's storage
([ac1](#ac1-the-counts-against-the-targets-and-the-options)). Nothing was published or deployed.
The restored copy and the two scratch indexes are kept, at the PM's request, for two other tasks'
read-only counts, and are deleted after them (policy 1.18).

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, sent to the PM with the options | PASS | The operator's blocks of 2026-11-12 (restore, two builds, two loads in the image) → [ac1](#ac1-the-counts-against-the-targets-and-the-options); relayed to the PM by the operator |
| ac2: after the ruling, a backfile card found with its season and provenance line, gone within five minutes of a removal, cold start within ADR-0019; tests failing first | NOT RUN | Waits for the PM's ruling on the shape |
| backfile-index: `uv run pytest packages/debate_api/tests` | NOT RUN | Waits for the ruling |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

**The PM's rulings of 2026-11-12, on the hold** (relayed by the operator):

1. hspolicy25 is rebuilt in the cloud by caselist-cloud-run.md's "Backfile imports" (dry run first),
   after the landscape republish then under way has published and deleted its copy. The index is
   measured once, with all four backfiles at `2026.11.03-docx-9`.
2. The brief's "hspolicy25 rebuilt to docx-9 on 2026-11-12" was a plan, not a record: no rebuild had
   run, so there is no failed task to look into.
3. The restore and every timing wait until the operator says the landscape work and the rebuild have
   both finished and the lock is free. Then: the bucket check again (all four backfiles docx-9 only,
   hspolicy25 about 14,343 objects), the restore, the measurements, one block at a time, then the copy
   and every scratch index are deleted (policy 1.18). Every block starts with `cd "${HOME}"`.

**The PM's relay of 2026-11-12, lifting the hold:**

* hspolicy25's rebuild has finished: ECS task `8e203907c93940a99ce84ea6dba01d9a`, started 00:53
  Chicago on task-definition revision 15 (parser `2026.11.03-docx-9`), run by caselist-cloud-run.md's
  "Backfile imports" after a clean dry run. Its result line: status ok, applied true,
  downloaded_bytes 0, sources_skipped 14,340, parsed 14,163, unsupported 176, failed 1, cards
  408,335, parsed_uploaded 14,343, no code; restore 7.2 s, parse 4,080.9 s, publish 69.6 s,
  publish_parsed 388.0 s.
* The landscape republish finished on 2026-11-10.
* hspolicy25's `2026.10.27-docx-7` directory is still in the bucket; the PM retires it in the next
  batch. So for hspolicy25 the check reads "docx-9 present and complete", not "docx-9 only".
* The restore size is recomputed from the second check's real docx-9 bytes (all eight stores), with
  25% headroom, against the Mac's free space; if it does not fit, measuring stops. The restore takes
  docx-9 directories only, never a docx-7 one. After measuring, the copy and every scratch index are
  deleted, and the deletion is recorded with what was removed.
* Unchanged: no index holding backfile cards is published to dev or prod, and no function is
  deployed with one, before the PM rules; nothing runs on a Wednesday; no AWS write of any kind; no
  pull request.

**The PM's relay of 2026-11-12, a pause before deleting:** the measurements go ahead, then this task
stops before deleting the restored copy and the scratch indexes. The copy is reused, after this
task's measurements have finished so that they never skew its timings, for two read-only counts the
PM hands the operator for other tasks: v1-e31-t32's after count (`scripts/count_tags_by_rule.py`)
and v1-e31-t23's ac3 count (`scripts/count_in_round_markers.py --expect-version
2026.11.03-docx-9`), both from the main clone, writing outside the copy. While they run, nothing is
deleted and no index build or other heavy command runs against the copy. When the operator says
both are done, the copy and every scratch index are deleted (policy 1.18) and the deletion recorded.

## The measurement so far

**The bucket check** (read-only: the run lock and a listing of each store's
`parsed/<store>/2026.11.03-docx-9/`), run by the operator on 2026-11-12 just after midnight, with the
lock free. Two earlier attempts stopped with `aws: [ERROR]: [Errno 2] No such file or directory`: the
terminal sat in a worktree deleted after its merge, and the AWS CLI stops on a missing working
directory before any request. Every block now starts with `cd "${HOME}"`.

| Store | docx-9 objects | docx-9 bytes | `occurrences.jsonl` | Version directories |
|---|---|---|---|---|
| hspolicy25 | 0 | 0 | 0 | `2026.10.27-docx-7` only |
| hsld25 | 23,660 | 10,986,908,792 | 1 | docx-9 only |
| hspolicy24 | 12,312 | 10,791,735,497 | 1 | docx-9 only |
| hsld24 | 23,976 | 11,104,528,527 | 1 | docx-9 only |
| hsld26 | 8,258 | 4,128,943,216 | 1 | docx-7 and docx-9 |
| hspolicy26 | 5,691 | 6,220,607,735 | 1 | docx-7 and docx-9 |
| hspf26 | 6,700 | 1,956,072,676 | 1 | docx-7 and docx-9 |
| openev | 110 | 201,266,870 | 1 | docx-7 and docx-9 |

The three backfiles at docx-9 hold 32,883,172,816 bytes, and the current four stores 12,506,890,497.
With hspolicy25 at its docx-7 size (13,510,680,041, from the backfile runbook), a restore of all eight
is about 58.9 GB, 73.6 GB with 25% headroom, against 112,754,421,760 bytes free on the Mac (memory
19,327,352,832 bytes; Docker VM 8,221,937,664 bytes, 11 CPUs, aarch64).

**The second bucket check**, run by the operator on 2026-11-12 (a Thursday) after the hold was lifted,
with the lock free. Every store is complete at `2026.11.03-docx-9`, each with its `occurrences.jsonl`;
hspolicy25's object count is the rebuild's parsed_uploaded exactly.

| Store | docx-9 objects | docx-9 bytes | Version directories |
|---|---|---|---|
| hspolicy25 | 14,343 | 13,525,536,662 | docx-7 (retired next batch) and docx-9 |
| hsld25 | 23,660 | 10,986,908,792 | docx-9 only |
| hspolicy24 | 12,312 | 10,791,735,497 | docx-9 only |
| hsld24 | 23,976 | 11,104,528,527 | docx-9 only |
| hsld26 | 8,258 | 4,128,943,216 | docx-7 and docx-9 |
| hspolicy26 | 5,691 | 6,220,607,735 | docx-7 and docx-9 |
| hspf26 | 6,700 | 1,956,072,676 | docx-7 and docx-9 |
| openev | 110 | 201,266,870 | docx-7 and docx-9 |

The restore size, recomputed: 58,915,599,975 docx-9 bytes across the eight stores, 73,644,499,968
with 25% headroom, against 119,436,075,008 bytes free. It fits. The installed `debate-research`
(1.1.0.dev413) parses at `2026.11.03-docx-9`, the version a restore takes, so no docx-7 directory is
restored.

**The first restore stopped when the Mac slept.** Started 11:02 Chicago into `~/t18-measure/copy`
(the seven caselists, openev with them). The lid was closed at 11:16:47 (`pmset` log: "Clamshell
Sleep"), which `caffeinate -i` does not prevent; the last file landed at 11:17:41. On a maintenance
wake at 11:57:52 the restore found no network and ended `STORE_UNAVAILABLE` (exit 3: "Could not
connect to the endpoint URL" on a `GetObject`). Its release of the lock failed the same way, so the
lease lapsed at 17:42:59Z; a later take treats a lapsed lease as free by design. It had landed the
current three caselists whole (8,258, 5,691 and 6,700 files, the bucket's counts) and 183 of
hspolicy25's files, 12,937,191,424 bytes on disk, no docx-7 directory: about 15 MB/s, so a full
restore takes about 65 minutes with the lid open.

**The partial copy, deleted** (policy 1.18) by the operator on 2026-11-12, after a check of its
restored-copy marker: `~/t18-measure` whole, 20,905 files and 12,827,660,288 bytes on disk
(hspolicy25 183 parsed files, hsld26 8,258, hspolicy26 5,691, hspf26 6,700; the rest the bundle and
state files). The folder is gone; 119,656,095,744 bytes free after.

**The second restore**, 2026-11-12 19:27:35 to 20:26:45 Chicago (3,546 s), on mains power with the
lid open, into a new `~/t18-measure/copy`: exit 0, parsed version `2026.11.03-docx-9`, 95,050 parsed
objects, 58,915,599,975 bytes (the bucket check's figure exactly), 65 manifests, 7 suppression
entries, dev's published index `f318149882fdd9c5`'s manifest. Every store's file count matches the
bucket check; no docx-7 directory; 59,252,776,960 bytes on disk, 53,152,571,392 free after.

It took the lock over from another Mac run of `caselist restore-run-state`, run id
`20261112T225959Z` (16:59:59 Chicago), whose lease lapsed at 2026-11-13T00:55:05Z. Its last renewal
was about 18:25 Chicago; the `pmset` log shows clamshell sleep at 18:26:01. A search of the home
folder, `/private/tmp` and `/Volumes` for restored-copy markers (45 s, complete) found only the new
copy. Which block that run was, and what became of what it wrote, is asked of the operator.

dev's published index, as its restored manifest gives it: four stores (hsld26, hspolicy26, hspf26,
openev) at docx-9, snapshot 2026-11-10, 63,705 documents (16,710, 26,678, 14,563 and 5,754), 465,001
occurrence rows read, SQLite 1,043,304,448 bytes, gzip 387,288,605.

**Build 1, current seasons only** (hsld26, hspolicy26, hspf26, openev), from the copy with the
installed `debate-research` 1.1.0.dev413, 2026-11-12 20:38:25 to 20:49:37 Chicago, on mains power;
load average 10.61 / 9.09 / 8.65 before it (the Mac was not quiet: build times here are upper
bounds). Exit 0, 671.16 s real (545.00 user, 41.24 sys), maximum resident set 1,481,129,984 bytes,
peak memory footprint 1,612,564,232. Index `f318149882fdd9c5`: byte for byte the index dev
publishes, so the method reproduces the weekly run's build. 63,705 documents (hsld26 16,710,
hspolicy26 26,678, hspf26 14,563, openev 5,754), 60,503 distinct card clusters, 465,001 occurrence
rows read, 459,285 occurrences, 166,394 provenance rows, none suppressed, no cluster left out;
2,088 left out as no card (1,684 cite only, 404 with no cite and under 25 words). SQLite
1,043,304,448 bytes, gzip 387,288,605; 1,446,481,920 bytes on disk for the folder.

**Build 2, current plus the four backfiles**, 2026-11-12 20:52:13 to 21:46:38 Chicago; load average
4.13 / 6.40 / 7.41 before it. Exit 0, 3,265.52 s real (2,165.38 user, 549.86 sys), maximum resident
set 4,440,457,216 bytes, peak memory footprint 4,588,392,384. Index `8eae91e2afa36c1d`: 237,146
documents, 173,441 more than build 1 (hspolicy25 53,883, hsld25 37,009, hspolicy24 48,414, hsld24
34,135; the current stores' counts unchanged), 210,533 distinct card clusters, 2,003,222 occurrence
rows read, 1,976,129 occurrences, 629,312 provenance rows, none suppressed, no cluster left out;
9,351 left out as no card (7,404 cite only, 1,947 with no cite and under 25 words). SQLite
3,973,885,952 bytes, gzip 1,462,856,642; 5,450,915,840 bytes on disk for the folder.

**What the current seasons already hold**, counted over build 2 and the copy's occurrence tables
(5.6 s). The current seasons keep 60,503 cluster ids, over 465,001 rows and 87,885 distinct exact
fingerprints. A backfile cluster is "new" when its id is no current document's, or when none of its
cards' exact fingerprints appears in a current row; every cluster new by fingerprint is new by id
too, so "lacked by both" is the fingerprint count. Exact matches only: a card re-cut between seasons
counts as new.

| Backfile | Documents | Rows | New by cluster id | New by exact fingerprint |
|---|---|---|---|---|
| hspolicy25 | 53,883 | 438,613 | 49,452 | 47,451 |
| hsld25 | 37,009 | 369,330 | 33,254 | 31,457 |
| hspolicy24 | 48,414 | 364,501 | 45,273 | 43,665 |
| hsld24 | 34,135 | 365,777 | 31,999 | 30,734 |
| All four, distinct ids | 173,441 | 1,538,221 | 150,030 | 144,372 |

Summed per store, 153,307 of the 173,441 backfile documents (88.4%) hold no card a current row
holds, and 20,134 (11.6%) do.

**Load in the function's image** (`debate-dev-tub:0d81c542…`, dev's merge-commit image, linux/arm64),
2026-11-12 about 21:50 Chicago, load average about 3.7 before each: `docker run --network none
--memory 2048m --memory-swap 2048m --cpus 1.16` (the vCPU share Lambda gives 2,048 MB), the
function's own `SearchIndexHolder` fed by a file-backed source (the scratchpad's `load_probe.py`):
manifest checks, the gzip object streamed through zlib and both sha256s into the container's `/tmp`,
the read-only open, then five searches of common words. No download: the load is the CPU part, which
ADR-0019 (c) 3 overlaps with the download.

| | Current (`f318149882fdd9c5`) | Combined (`8eae91e2afa36c1d`) |
|---|---|---|
| Load (first lease) | 6.96 s | 19.10 s |
| Process peak (`VmHWM`) | 45,016 KiB | 45,020 KiB |
| Container `memory.peak` | 1,499,865,088 bytes | 2,147,483,648 (the cap), 6,492 `max` events, no OOM kill |
| Five searches | 19, 15, 14, 12, 82 ms | 121, 221, 112, 83, 433 ms |
| Container exit | 0 after 8 s | 0 after 20 s |

The process itself stays near 45 MB; what fills the container is the page cache of the file in
`/tmp`, which in Lambda lives in the function's memory too. The combined file (3.97 GB) cannot stay
cached in 2 GB: the container sat at its cap, reclaiming, and the searches ran 5 to 15 times slower.

## ac1: the counts against the targets, and the options

| | Current seasons (today's index) | Current plus four backfiles | Target |
|---|---|---|---|
| Documents | 63,705 | 237,146 (+173,441) | |
| Distinct card clusters | 60,503 | 210,533 | |
| SQLite bytes | 1,043,304,448 | 3,973,885,952 | weekly warning 1,700,000,000 |
| Gzip bytes | 387,288,605 | 1,462,856,642 | revisit trigger about 800 MB |
| Download at 1,250 Mbps | 2.5 s | 9.4 s | about 5 s at the trigger |
| Load in the image | 6.96 s | 19.10 s | first search 6 to 8 s at the ceiling ((c) 7) |
| Two copies at a swap | 2,086,608,896 (48.6% of 4,096 MB) | 7,947,771,904 (185.0%) | under 4,294,967,296 |
| Container memory | 1.50 GB peak | at the 2 GB cap | 2,048 MB |
| Build time, peak memory | 671 s, 1.48 GB | 3,266 s, 4.44 GB | |
| Documents added per backfile | | hspolicy25 53,883; hsld25 37,009; hspolicy24 48,414; hsld24 34,135 | |

**Which targets the combined index breaks:** all of the size and cold-start ones. The SQLite file is
234% of the weekly warning; a swap needs 185% of the function's storage (one copy leaves 321 MB); the
gzip object is 1.83 times the revisit trigger; the load is 19.1 s against the 6 to 8 s (c) 7 allows
at the ceiling, before the 1 to 2 s app start; and the page cache sits at the 2,048 MB cap, which
slowed searches 5 to 15 times. **The shrink guard** (`v1-e39-t14`) lets a combined index be
published, since it only grows; but the weekly stage indexes the run's caselists and openev alone
(`search_index_stores`), so the next weekly build would drop four stores to 0 documents and be
refused, and the weekly refresh would stop, unless every weekly run restored (46.4 GB) and indexed
the backfiles too.

**Today's index, for the record:** within every target, but its 6.96 s load is already at the top of
(c) 7's band, and Lambda's arm64 cores may be slower than this Mac's. A follow-up below.

**Estimates, not measured** (the combined index's 16,757 bytes a document, gzip ratio 0.368, and the
two loads' 4.81 to 6.67 s a GB): a backfiles-only index about 2,930,581,504 SQLite bytes and
1,075,568,037 gzip, loading in about 14 to 20 s; one season's index 572 to 903 MB of SQLite (hsld24
the smallest, hspolicy25 the largest), 211 to 332 MB gzip, loading in about 3 to 6 s; option 3's index
about 217,012 documents, 3.64 GB SQLite and 1.34 GB gzip.

The options, as relayed to the PM (the relay in the session's operator message is the same text):

1. **One index.** A student searches every season at once; a backfile card's provenance line says
   its caselist and snapshot today (`[Disclosed: hspolicy25 <snapshot> — ...]`), plus a season label
   if the PM wants one. Removal: unchanged, the one suppression list rechecked every five minutes.
   Cold start: 19.1 s load, every target above broken, and the weekly run must carry the backfiles.
2. **A separate backfile index, searched on request** ("include earlier seasons"). Default search
   and its cold start unchanged; the first "include earlier seasons" search on an environment waits
   about 14 to 20 s. Removal: the second holder reads the same suppression list on the same
   five-minute check. Storage: live current, the backfile index and a swap of the current one need
   about 5.0 GB (117% of 4,096 MB), so the storage must rise, and searching both puts about 4 GB of
   file behind 2 GB of memory.
3. **Backfiles only for clusters the current seasons lack.** Saves 11.6% of the backfile documents:
   still about 3.64 GB SQLite, breaking the same targets as option 1, and a removal of the current
   copy of a card would leave its older copies unindexed.
4. **Another: one index per backfile season, loaded on request, one held at a time.** A student picks
   an earlier season to search (for example "2024–25 policy"); default search and its cold start
   unchanged; the first search of a season waits about 3 to 6 s; live current, one season and a swap
   need at most about 2.99 GB (69.6% of 4,096 MB). Removal: as option 2. Built once from the backfile
   stores, which no weekly run changes, so the weekly stage and its shrink guard are untouched; each
   season's pointer gets the guard of its own.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **Today's index already loads at the top of ADR-0019 (c) 7's band.** In the function's image at
  1.16 CPUs, the 1.04 GB index took 6.96 s to stream through gunzip and both sha256s, before the
  1 to 2 s app start, and Lambda's arm64 cores may be slower than this Mac's. The ADR's estimate
  takes the download as the long part (2.5 s here); the CPU part is. `v1-e39-t04`'s `REPORT`
  lines give init only, not the first search's wait. Belongs to `v1-e39-evidence-search-pilot`
  (the PM decides whether a measurement of the first search's wait on the function is a task).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
