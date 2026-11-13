# Session report: v1-e39-t18-backfiles-in-the-pilot-index

| | |
|---|---|
| Task | `v1-e39-t18-backfiles-in-the-pilot-index` — Backfile seasons searchable on the pilot, without slowing its cold start |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t18-backfiles-in-the-pilot-index` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Shape (4) is built: one index per backfile season, loaded when a student picks that season on the
search page, one held at a time, each from its own pointer `reports/tub/search/seasons/<season>.json`
with its own shrink guard, and each screened by the one suppression list. Default search, its index,
its cold start, the weekly stage and its guard are untouched. Tests ran red against a skeleton first
(27 of 45 failing for their reasons), then green, and all 20 planted mutants and both Terraform
mutants were caught ([The build](#the-build-shape-4)). ac1's counts were measured and ruled on
([ac1](#ac1-the-counts-against-the-targets-and-the-options)). **ac2 is PARTIAL:** the after-measurement
of the real season indexes against ADR-0019's targets is the operator's, written below and not run,
so the Goal stays InProgress. Nothing was published or deployed, and no backfile index is current
anywhere. The restored copy and both scratch indexes are deleted (policy 1.18).

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| backfile-index | PARTIAL | Measured, ruled (shape 4), built and tested; the after-measurement is an operator follow-up |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, sent to the PM with the options | PASS | The operator's blocks of 2026-11-12 (restore, two builds, two loads in the image) → [ac1](#ac1-the-counts-against-the-targets-and-the-options); relayed, and ruled on the same day |
| ac2 (a): a backfile card is found, shows its season and its provenance line | PASS | `test_search_pages_seasons.py`: `..._is_found_in_its_seasons_search_with_its_season_and_provenance_line`, `..._page_names_its_season_above_its_provenance_line` → pass; red first (400, 404) |
| ac2 (b): gone within five minutes of a removal | PASS | `test_a_removed_backfile_card_is_gone_from_its_season_within_five_minutes` (4:59 still shown, 5:00 gone from results, page and copy), `test_a_season_first_loaded_after_a_removal_hides_the_card_at_once`, and the container test that every season holder reads the one list → pass; red first |
| ac2 (c): the cold start stays within ADR-0019's target | PARTIAL | Default search never reaches a season (`test_a_default_search_never_reads_a_season_pointer_or_finds_a_season_card`), so today's cold start is unchanged (6.96 s measured); each season's first-search wait and the storage at a swap are estimated at 3 to 6 s and 2.99 GB, and measured only by the [after-measurement](#operator-follow-ups), NOT RUN |
| ac2 (d): tests shown failing first | PASS | Red run at `3041f3b` on the skeleton of `73d2c24`: 27 failed, 18 passed (reasons in [The build](#the-build-shape-4)); green at `e7e4954`: 45 passed; 20 of 20 mutants caught |
| backfile-index: `uv run pytest packages/debate_api/tests` | PASS | `uv run --frozen pytest -q packages/debate_api/tests` → 1164 passed in 11.08 s |
| Affected set, once (working agreement 10) | NOT RUN in full | `scripts/affected_tests.py --base origin/dev`: 394 of 748 files; run once under `hard_stop.py 115`, stopped at 22% with no failure or error: over two minutes, so left to the pull request's CI |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

* `packages/debate_core/src/debate_core/application/season_indexes.py` (new): the season pointer key,
  a season's words, and `SeasonIndexes`, the shelf that holds one season's holder at a time.
* `packages/debate_core/src/debate_core/application/search_index_publish.py`: `season=` publishes to
  the season's pointer under its own shrink guard, and `SeasonIndexHoldsOtherStores` refuses any other
  store.
* `packages/debate_core/src/debate_core/application/search_index_prune.py`: keeps each season
  pointer's current index and version, deletes its superseded ones, refuses an unreadable or dangling
  season pointer, and re-reads the season pointers at execute.
* `packages/debate_core/src/debate_core/application/card_download.py`: a cart leases the current
  index first, then each season in turn.
* `packages/debate_core/src/debate_core/integrations/s3/search_index_source.py`: `pointer_key=`.
* `packages/debate_api/src/debate_api/` (`configuration.py`, `container.py`, `state.py`,
  `search_pages.py`, `templates/search.html`, `templates/card.html`, `static/app.js`):
  `TUB_BACKFILE_SEASONS`, a season holder per season under `/tmp/tub-index-seasons`, the *Season*
  choice, the season searched, "Earlier season:" on a card's page, and the loading line.
* `packages/debate_cli/src/debate_cli/` (`commands/tub_index.py`, `container.py`): `tub index publish
  --season`, and `season_index_publish(season)`.
* Tests: `packages/debate_core/tests/application/test_season_indexes.py`,
  `test_search_index_publish_season.py`, `test_search_index_prune_seasons.py` (new);
  `packages/debate_api/tests/test_search_pages_seasons.py` (new) and `conftest.py` (a seasons hook on
  every world, `SeasonWorld`, two invented seasons); `packages/debate_cli/tests/test_container_factories.py`
  (a season value).
* `infrastructure/modules/evidence_search/` (`main.tf`, `variables.tf`, tests): `backfile_seasons`,
  set on the function only when it names a season; four new offline test runs.
* `docs/runbooks/evidence-search.md` (Backfile seasons), `docs/runbooks/caselist-removal.md` (P4 keeps
  each season's current index).

## Deviations from the spec

* **ac2 is PARTIAL by design of the ruling.** Q3 makes the after-measurement of the real season
  indexes the operator's, from a fresh restore; it is written as blocks below and not run, so the
  Goal is not set to Succeeded.
* **No change outside the spec's packages.** `debate_core.domain` and `debate_core.testing` are not in
  `constraints.packages`, so the season key and words live in `debate_core.application.season_indexes`
  rather than beside `SEARCH_INDEX_POINTER_KEY`, and the test view of a season's pointer is in the API
  tests' conftest rather than `debate_core.testing.search_index`. A PM may prefer both moved; the
  move is mechanical.
* **The prune changed** (`search_index_prune.py`), which the ruling did not name: without it the
  removal runbook's next P4 would delete every season's index (it keeps only what `current.json`
  names), and with only that fixed it would never delete a season's superseded copies (gate items 1
  and 5). It is in `debate_core.application`, inside the spec's packages.
* **ADR-0019 is not amended**: `docs/adr` is not in the spec's packages. Its (c) 3 and 5 describe one
  index; a sentence naming the season indexes (one held at a time, its own pointer, the same list) is
  the PM's to add.

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

**The PM's rulings of 2026-11-12 on ac1** (relayed by the operator):

* **Q1, shape (4):** one index per backfile season, loaded when a student picks that season, one
  held at a time. Default search, its index and its cold start are unchanged and never touch a
  backfile index; the weekly stage and its shrink guard are untouched; each season's pointer has
  its own guard; every index reads the one suppression list (gate item 1). The student sees which
  season they are searching, and a short "loading <season>" line during that season's first search.
  Not (1) or (3): each breaks every ADR-0019 limit, and (3) also breaks removal. Not (2): about 8 GB
  of storage, more memory, and a 14 to 20 s first wait.
* **Q2:** the season in words after the slug on every caselist card's provenance line, pending the
  coach's word as the data-use policy's owner. Policy Attribution rule 2 spells the line out, so the
  amendment's words are written below for the PM to carry, and the line is not changed on the
  pilot before that approval.
* **Q3:** yes: ac2's after-measurement builds and probes the per-season index files from a fresh
  restore, under ac1's rules (scratch only, nothing published or deployed before the PM rules on
  the result, deleted after use, never on a Wednesday, mains power with the lid open in every
  restore block).
* **The copy:** three read-only counts run before the delete, not two: v1-e31-t32's, v1-e31-t23's
  and v1-e32-t51's (hsld26's 2026-11-10 snapshot), one after another, from the main clone.

**A season's words come from its slug's start year.** `docs/data/caselist-backfile-seasons.md`:
"A slug's two digits are the year its season starts", so hspolicy25 and hsld25 are 2025-26 and
hspolicy24 and hsld24 are 2024-25 (and hsld26 is the current 2026-27). The PM's Q2 example,
"hspolicy25 (2024–25)", is a year early; this build follows the recorded rule.

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
copy. The operator confirmed it was block 4's first run: it lost the network (the lid closed at
18:26, as the log shows), the restore failed, and the operator deleted `~/t18-measure` before running
block 4 again. That partial copy's contents were not counted before the deletion, so they are not
recorded; it held dev's run copy and part of the parsed stores, as the first partial copy did, and it
is gone (the marker search above). Its failed release left the lease that the second restore took
over.

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

**The copy and both scratch indexes, deleted** (policy 1.18) by the operator on 2026-11-12, after the
PM's three read-only counts (v1-e31-t32's, v1-e31-t23's and v1-e32-t51's) had finished and after a
check of the copy's restored-copy marker: `~/t18-measure` whole. The copy: 95,125 files,
59,241,553,920 bytes on disk (parsed files: hspolicy25 14,343, hsld25 23,660, hspolicy24 12,312, hsld24
23,976, hsld26 8,258, hspolicy26 5,691, hspf26 6,700, openev 110; the rest the bundle and state
files). The scratch index `f318149882fdd9c5` (current seasons): 5 files, 1,430,638,592 bytes. The
scratch index `8eae91e2afa36c1d` (combined): 5 files, 5,450,915,840 bytes. The folder is gone, no
restored-copy marker is left within four levels of the home folder, and 105,939,890,176 bytes are
free after. The probe and overlap scripts in the session's scratchpad hold no card data.

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

## The build (shape 4)

**What a student sees.** With seasons offered (`TUB_BACKFILE_SEASONS`), the search form has a *Season*
choice: *This season*, the default, then each season as `hspolicy25 (2025-26)`. A search of a season
says "Searching hspolicy25 (2025-26)." above its results, and searches that season's index alone; a
season not yet loaded on the environment carries "Loading hspolicy25 (2025-26). The first search of
an earlier season takes a few seconds.", which `app.js` shows under the form while that search waits.
A backfile card's page reads "Earlier season: hspolicy25 (2025-26)" above its provenance line, which
is unchanged ([Q2](#the-provenance-lines-season-for-the-pm-to-carry)). Its copy and its download read
its season's index. A season not offered is refused (400) as a filter outside its choices is.

**Removal (gate item 1).** Every season's holder reads the one suppression list on the same
five-minute check as the current index's, so a removed backfile card leaves its season's results, its
page and its copy within five minutes, and a season first loaded after the removal never shows it.
The prune keeps each season pointer's current index and deletes its superseded versions, so a
season rebuilt after a removal leaves no old copy behind P4.

**The red run** (`3041f3b`: the tests on `73d2c24`'s skeleton, whose shelf served no season, whose
publish ignored its season and whose prune knew none): **27 failed, 18 passed** of 45, each failure for
its reason: the shelf's `SearchIndexUnavailable` and an offered season it said it did not hold (8);
an index of another store published, and a season's publish guarded by `current.json`'s index ("would
shrink", 3); a backfile card 404 on its page, its season's search 400, no season card in results, the
loading line never cleared (9); a superseded season version kept, a season index deleted, an
unreadable or dangling season pointer not refused, a moved season pointer not noticed, the last check
passing a season's current index (7). The 18 that passed on the skeleton are the guards (default
search reads no season pointer, refusals, configuration, words), each caught by a mutant below.

**Green** at `e7e4954`: 45 passed (then 46 with the container test). Around it: 1,320 passed across the
prune, publish, shrink-guard, holder and CLI index tests and the whole API test directory; 134 passed
across the core and CLI index tests and the index smoke test; 22 of 22 Terraform runs offline
(`mock_provider`, providers from the main checkout's mirror). ruff, pyright (0 errors), lint-imports (20
kept) and `check_thin_handlers.py` (74 within 25 statements) pass.

**Mutants, 20 of 20 caught** (each planted alone, its tests run under `-n 0 -x`, the file restored from
`HEAD`; every catch an assertion or an expected refusal, none a crash): a season search reading the
current index; a search with no season going to a season; a season card looked up in the current
index; the held season not closed before the next; the held season rebuilt on every lease; no season
ever loaded; a season's words a year early; a season index of another store published; a season's
guard reading `current.json`; a season's pointer written to `current.json`; the prune keeping no
season's index; the prune keeping every version of a season pointer; an unreadable season pointer
skipped; a dangling season pointer kept; execute not re-reading the season pointers; the last check
forgetting the seasons; a season named twice in `TUB_BACKFILE_SEASONS`; the season dropped from the
way back; a cart's season cards sent to the current index; a season's holder built with no
suppression list. **Terraform, 2 of 2:** `TUB_BACKFILE_SEASONS` always set fails
`no_backfile_season_means_no_season_setting`; an always-true validation fails
`a_backfile_season_named_twice_is_refused` with "Missing expected failure".

## The provenance line's season, for the PM to carry

Q2 waits on the coach as the data-use policy's owner, and Attribution rule 2 spells the line out, so
nothing on the pilot changes before that approval. The amendment's words, for version 1.24:

> Attribution rule 2, the sentence "Disclosed cards name caselist slug, snapshot date, school, team
> code, side, tournament and round." becomes: "Disclosed cards name caselist slug **and its season**,
> snapshot date, school, team code, side, tournament and round; the season is written in words after
> the slug, from the year its season starts: `[Disclosed: hspolicy25 (2025-26) 2026-03-02 — Maple Grove
> QX, Aff vs. Riverbend Invitational Round 4]`." The example line under rule 2 gains the season the
> same way: `[Disclosed: hsld26 (2026-27) 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational
> Round 4]`. Change log: "1.24: a disclosed card's provenance line names its season after the slug
> (v1-e39-t18, so a backfile card says its season)."

The PM's example read hspolicy25 as 2024-25; the recorded rule (a slug's digits are its starting year)
makes it 2025-26, as above. Once approved, the change is `occurrence_provenance_line`'s alone, in
`debate_core.domain.evidence_search`, which this spec's packages do not include: a task of its own,
or an amendment of this one.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

**ac2's after-measurement** (the PM's Q3): the four season indexes built from a fresh restore and each
loaded in the function's image, against the targets ac1 used. Under ac1's rules: scratch only
(`~/t18-after`), nothing published or deployed before the PM rules on the result, never on a
Wednesday, mains power **with the lid open** for every restore (two restores stopped on clamshell
sleep on 2026-11-12), counts and sizes only, one block at a time, each starting with `cd "${HOME}"`.
Then delete the copy and the indexes (policy 1.18) and record it.

Before AM4, the session that runs it writes the probe below to its own scratchpad and puts that
folder in `Q`. The probe runs the holder every season's index is loaded by, `SearchIndexHolder`; the
shelf adds no step to a load.

**AM1, the bucket check** (read-only, about 30 s). Success: each store complete at docx-9 with its
`occurrences.jsonl`, and `FITS`. If hspolicy25's docx-7 directory is gone by then, that is the PM's
retirement. If a count differs from AM2's expected numbers, change AM2's numbers to these first.

```
cd "${HOME}"; B=s3://debate-dev-evidence-a7508de8; P=debate-dev-evidence; V=2026.11.03-docx-9; T="$(mktemp)"; tot=0; bad=0; if [ "$(TZ=America/Chicago date +%u)" = 3 ]; then echo "STOP: it is Wednesday in Chicago, the weekly run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif pgrep -fl 'debate-research.*(caselist (pull|backfile-import|restore-run-state|remove)|tub index)'; then echo "STOP: a debate-research command is running (above)"; elif ! k="$(aws s3 cp "${B}/reports/sync/run-lock.json" - --profile "${P}" 2>"${T}")"; then echo "STOP: the dev run lock could not be read. Its error:"; tail -n 5 "${T}"; elif e="$(printf '%s\n' "${k}" | sed -nE 's/.*"lease_expires_at": *"([^"]*)".*/\1/p')"; cut="$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ)"; printf '%s\n' "${k}" | grep -q '"state": *"held"' && { [ -z "${e}" ] || [[ "${e}" > "${cut}" ]]; }; then echo "STOP: the dev run lock has a live lease, until ${e:-no expiry}"; else for s in hspolicy25 hsld25 hspolicy24 hsld24 openev; do : > "${T}"; l="$(aws s3 ls --recursive --summarize "${B}/parsed/${s}/${V}/" --profile "${P}" 2>"${T}")"; if [ -s "${T}" ]; then echo "${s}: STOP, the listing failed:"; tail -n 3 "${T}"; bad=1; continue; fi; n="$(printf '%s\n' "${l}" | sed -n 's/.*Total Objects: *//p')"; z="$(printf '%s\n' "${l}" | sed -n 's/.*Total Size: *//p')"; o="$(printf '%s\n' "${l}" | grep -c "parsed/${s}/${V}/occurrences.jsonl$")"; d="$(aws s3 ls "${B}/parsed/${s}/" --profile "${P}" 2>/dev/null | awk '$1 == "PRE" {print $2}' | tr -d / | tr '\n' ' ')"; echo "${s}: ${V} objects ${n:-0}, bytes ${z:-0}, occurrences.jsonl ${o}; version directories: ${d}"; tot=$((tot + ${z:-0})); if [ "${o}" != 1 ]; then bad=1; fi; done; f="$(df -k "${HOME}" | awk 'NR == 2 {printf "%d", $4 * 1024}')"; need=$((tot * 5 / 4)); echo "docx-9 bytes: ${tot}; with 25 percent headroom: ${need}; free bytes on the home volume: ${f}"; if [ "${bad}" != 0 ]; then echo "STOP: a listing failed or a store has no occurrences.jsonl at ${V}"; elif [ "${need}" -gt "${f}" ]; then echo "STOP: the restore would not fit with 25 percent headroom"; else echo "FITS"; fi; fi; rm -f "${T}"
```

**AM2, the restore** (the four backfiles, openev with them, about 46.6 GB: about 50 minutes at the
15 MB/s of 2026-11-12; it holds the dev lock). Lid open, charger in. Success: `exit 0`, every store
`MATCH`, no docx-7 directory.

```
cd "${HOME}"; M="${HOME}/t18-after"; C="${M}/copy"; B=s3://debate-dev-evidence-a7508de8; P=debate-dev-evidence; V=2026.11.03-docx-9; T="$(mktemp)"; R="$(command -v debate-research)"; if [ "$(TZ=America/Chicago date +%u)" = 3 ]; then echo "STOP: it is Wednesday in Chicago, the weekly run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif pgrep -fl 'debate-research.*(caselist (pull|backfile-import|restore-run-state|remove)|tub index)'; then echo "STOP: a debate-research command is running (above)"; elif [ -e "${M}" ]; then echo "STOP: ${M} exists already"; elif [ -z "${R}" ]; then echo "STOP: debate-research is not on PATH"; elif [ "$("${R:A:h}/python" -I -c 'from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION as v; print(v)' 2>/dev/null)" != "${V}" ]; then echo "STOP: the installed debate-research does not parse at ${V}"; elif ! pmset -g batt | grep -q "'AC Power'"; then echo "STOP: the Mac is on battery; plug it in and keep the lid open"; elif [ "$(df -k "${HOME}" | awk 'NR == 2 {printf "%d", $4 * 1024}')" -lt 58262470435 ]; then echo "STOP: under 58262470435 bytes free on the home volume"; elif ! k="$(aws s3 cp "${B}/reports/sync/run-lock.json" - --profile "${P}" 2>"${T}")"; then echo "STOP: the dev run lock could not be read. Its error:"; tail -n 5 "${T}"; elif e="$(printf '%s\n' "${k}" | sed -nE 's/.*"lease_expires_at": *"([^"]*)".*/\1/p')"; cut="$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ)"; printf '%s\n' "${k}" | grep -q '"state": *"held"' && { [ -z "${e}" ] || [[ "${e}" > "${cut}" ]]; }; then echo "STOP: the dev run lock has a live lease, until ${e:-no expiry}"; else echo "restore started $(date -u +%Y-%m-%dT%H:%M:%SZ)"; mkdir -p "${M}"; caffeinate -ims env DEBATE_ENV=dev debate-research --json caselist restore-run-state --into "${C}" --caselist hspolicy25 --caselist hsld25 --caselist hspolicy24 --caselist hsld24 > "${M}/restore.json"; echo "exit $?"; echo "restore ended $(date -u +%Y-%m-%dT%H:%M:%SZ)"; grep -oE '"(parsed_version|parsed_objects|parsed_bytes|manifests|suppression_entries|seconds)": ("[^"]*"|[0-9.]+|null)|"code": "[A-Z_]+"' "${M}/restore.json"; for p in hspolicy25:14343 hsld25:23660 hspolicy24:12312 hsld24:23976 openev:110; do s="${p%%:*}"; w="${p##*:}"; g="$(find "${C}" -path "*/parsed/${s}/${V}/*" -type f | wc -l | tr -d ' ')"; if [ "${g}" = "${w}" ]; then r=MATCH; else r=DIFFERS; fi; echo "${s}: ${V} files ${g}, bucket ${w}, ${r}"; done; echo "docx-7 directories in the copy: $(find "${C}" -type d -name '2026.10.27-docx-7' | wc -l | tr -d ' ')"; df -k "${HOME}" | awk 'NR == 2 {printf "free bytes on the home volume: %d\n", $4 * 1024}'; fi; rm -f "${T}"
```

**AM3, the four season builds** (local, no AWS: each about 10 to 15 minutes by build 2's rate). Keep
the Mac quiet. Success: four `exit 0`, each index holding its one store.

```
cd "${HOME}"; M="${HOME}/t18-after"; C="${M}/copy"; R="$(command -v debate-research)"; Y="${R:A:h}/python"; if [ "$(TZ=America/Chicago date +%u)" = 3 ]; then echo "STOP: it is Wednesday in Chicago, the weekly run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif pgrep -fl 'debate-research.*(caselist (pull|backfile-import|restore-run-state|remove)|tub index)'; then echo "STOP: a debate-research command is running (above)"; elif [ ! -f "${C}/debate-research-restored-copy.json" ]; then echo "STOP: ${C} is not the restored copy"; elif ! pmset -g batt | grep -q "'AC Power'"; then echo "STOP: the Mac is on battery; plug it in and keep the lid open"; else for s in hspolicy25 hsld25 hspolicy24 hsld24; do O="${M}/index-${s}"; if [ -e "${O}" ]; then echo "${s}: STOP, ${O} exists already"; continue; fi; mkdir -p "${O}"; echo "=== ${s}; load before: $(uptime | sed 's/.*load averages*: //')"; caffeinate -ims /usr/bin/time -l env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="${C}" debate-research --json tub index build --caselist "${s}" --out "${O}" > "${O}/build.json" 2> "${O}/time.txt"; echo "exit $?"; grep -E ' real | maximum resident set size' "${O}/time.txt"; "${Y}" -I -c 'import json, sqlite3, sys, pathlib; e = json.load(open(sys.argv[1])); e["status"] == "ok" or sys.exit("STOP: the build failed: " + e["error"]["code"]); d = e["data"]; m = d["manifest"]; c = m["counts"]; print("index", m["index_id"], "| stores", [one["caselist"] for one in m["stores"]], "| documents", c["documents"], "| occurrences", c["occurrences"], "| sqlite bytes", m["sqlite_file"]["bytes"], "| gzip bytes", m["gzip_object"]["bytes"]); db = sqlite3.connect((pathlib.Path(d["directory"]) / m["sqlite_file"]["name"]).as_uri() + "?mode=ro&immutable=1", uri=True); print("distinct card clusters", db.execute("SELECT count(DISTINCT cluster_id) FROM documents").fetchone()[0])' "${O}/build.json"; done; df -k "${HOME}" | awk 'NR == 2 {printf "free bytes on the home volume: %d\n", $4 * 1024}'; fi
```

**AM4, the loads in the function's image** (local, `--network none`, 2,048 MB, 1.16 CPUs, about a
minute). Set `Q` to the folder holding the probe. Success: four `container exit 0`, no `oom_kill`, and
the storage line under 4,294,967,296 for every season.

```
cd "${HOME}"; M="${HOME}/t18-after"; Q=PROBE_FOLDER; G="debate-dev-tub:$(docker image ls debate-dev-tub --format '{{.Tag}}' | head -n 1)"; R="$(command -v debate-research)"; Y="${R:A:h}/python"; if [ "$(TZ=America/Chicago date +%u)" = 3 ]; then echo "STOP: it is Wednesday in Chicago, the weekly run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif [ ! -f "${Q}/load_probe.py" ]; then echo "STOP: the probe is not at ${Q}"; elif ! docker info > /dev/null 2>&1; then echo "STOP: Docker is not running"; elif [ -n "$(docker ps -aq --filter name=t18-after)" ]; then echo "STOP: a t18-after container exists already"; else echo "image ${G}"; for s in hspolicy25 hsld25 hspolicy24 hsld24; do I="$("${Y}" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["directory"])' "${M}/index-${s}/build.json")"; echo "=== ${s}; load before: $(uptime | sed 's/.*load averages*: //')"; docker run --rm --name "t18-after-${s}" --network none --memory 2048m --memory-swap 2048m --cpus 1.16 -v "${I}":/index:ro -v "${Q}":/probe:ro --entrypoint python3 "${G}" -I /probe/load_probe.py /index; echo "container exit $?"; "${Y}" -I -c 'import json, sys; m = json.load(open(sys.argv[1]))["data"]["manifest"]; s = m["sqlite_file"]["bytes"]; g = m["gzip_object"]["bytes"]; print("current two copies plus this season:", 2 * 1043304448 + s, "of 4294967296 |", "download at 1,250 Mbps:", round(g / 156250000, 1), "s")' "${M}/index-${s}/build.json"; done; fi
```

**AM5, the deletion** (policy 1.18, local). Success: `DELETED` and no marker left.

```
cd "${HOME}"; M="${HOME}/t18-after"; C="${M}/copy"; if pgrep -fl 'debate-research'; then echo "STOP: a debate-research command is running (above)"; elif [ ! -f "${C}/debate-research-restored-copy.json" ]; then echo "STOP: ${C} holds no restored-copy marker"; else echo "removing the restored copy: $(find "${C}" -type f | wc -l | tr -d ' ') files, $(du -sk "${C}" | awk '{printf "%d", $1 * 1024}') bytes on disk"; for s in hspolicy25 hsld25 hspolicy24 hsld24; do I="${M}/index-${s}"; [ -d "${I}" ] && echo "removing the scratch index of ${s}: $(find "${I}" -type f | wc -l | tr -d ' ') files, $(du -sk "${I}" | awk '{printf "%d", $1 * 1024}') bytes on disk"; done; rm -rf "${M}"; if [ -e "${M}" ]; then echo "STOP: ${M} is still there"; else echo "DELETED: ${M} is gone"; fi; echo "restored-copy markers left within depth 4 of home: $(find "${HOME}" -maxdepth 4 -name debate-research-restored-copy.json -not -path "*/Library/*" 2>/dev/null | wc -l | tr -d ' ')"; df -k "${HOME}" | awk 'NR == 2 {printf "free bytes on the home volume: %d\n", $4 * 1024}'; fi
```

**After the PM rules on the result:** publish each season with `tub index publish --env dev --season
<season> --index <dir>` from a restored copy, set `backfile_seasons` in dev's root and apply, and
deploy (the evidence search runbook's [Backfile seasons](../runbooks/evidence-search.md#backfile-seasons-v1-e39-t18)).

The probe, `load_probe.py` (tested in `debate-dev-tub:0d81c542…` on 2026-11-12; prints counts, sizes
and times only):

```python
"""Load one built search index the way the pilot's function does, inside its image, and say what it cost.

Run inside the function's image with no network (v1-e39-t18 ac1):

    docker run --rm --network none --memory 2048m --memory-swap 2048m \
      -v <index dir>:/index:ro -v <probe dir>:/probe:ro --entrypoint python3 <image> -I /probe/load_probe.py /index

`/index` is one directory `tub index build` wrote: `manifest.json` and the gzip object, and optionally
`suppression-list.jsonl` (the copy's list). The probe serves them through a file-backed
`SearchIndexSource`, so `SearchIndexHolder` runs its real fetch: the manifest's checks, the gzip object
streamed through zlib and both sha256s into `/tmp`, and the read-only open. Then a few searches of
common words.

It prints counts, sizes and times only: never a card, a school, a team, a file name or a result.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from debate_core.application.ports.search_index_source import PointerRead
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.domain.search_index import (
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SearchIndexManifest,
    SearchIndexPointer,
    index_object_key,
)
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

CHUNK = 1024 * 1024
QUERIES = ("economy", "nuclear war", "climate change", "china", "the")


class FileSource:
    """`reports/tub/search/` as three local files: a made-up pointer, the manifest and the gzip object."""

    def __init__(self, directory: Path) -> None:
        self._manifest_bytes = (directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes()
        manifest = SearchIndexManifest.model_validate_json(self._manifest_bytes)
        self._object = directory / SEARCH_INDEX_GZIP_NAME
        self._suppression = directory / "suppression-list.jsonl"
        self.manifest = manifest
        self._pointer = SearchIndexPointer(
            format_version=manifest.format_version,
            index_id=manifest.index_id,
            manifest_key=index_object_key(manifest.index_id, SEARCH_INDEX_MANIFEST_NAME),
            manifest_sha256=hashlib.sha256(self._manifest_bytes).hexdigest(),
            object_key=index_object_key(manifest.index_id, SEARCH_INDEX_GZIP_NAME),
            object_sha256=manifest.gzip_object.sha256,
            sqlite_sha256=manifest.sqlite_file.sha256,
        ).to_json_bytes()

    def read_pointer(self, *, if_none_match: str | None) -> PointerRead:
        if if_none_match == '"pointer"':
            return PointerRead(body=None, etag=if_none_match)
        return PointerRead(body=self._pointer, etag='"pointer"')

    def read_object(self, key: str, *, max_bytes: int) -> bytes:
        if len(self._manifest_bytes) > max_bytes:
            raise ValueError("manifest too long")
        return self._manifest_bytes

    def stream_object(self, key: str) -> Iterator[bytes]:
        with self._object.open("rb") as handle:
            while chunk := handle.read(CHUNK):
                yield chunk

    def read_suppression_list(self, *, if_none_match: str | None) -> PointerRead:
        if if_none_match == '"list"':
            return PointerRead(body=None, etag=if_none_match)
        body = self._suppression.read_bytes() if self._suppression.is_file() else b""
        return PointerRead(body=body, etag='"list"')


def status_kib(field: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1])
    return -1


def cgroup(name: str) -> str:
    path = Path("/sys/fs/cgroup") / name
    return path.read_text().strip() if path.is_file() else "unavailable"


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="log: %(message)s")
    logging.getLogger("debate_core.application.search_index_holder").setLevel(logging.INFO)
    source = FileSource(Path(sys.argv[1]))
    m = source.manifest
    print(f"index {m.index_id} format {m.format_version} documents {m.counts.documents}")
    print(f"sqlite bytes {m.sqlite_file.bytes} gzip bytes {m.gzip_object.bytes}")
    print(f"documents by store {json.dumps(m.counts.documents_by_store, sort_keys=True)}")
    print(f"before load: VmHWM {status_kib('VmHWM')} KiB, cgroup memory.current {cgroup('memory.current')}")
    holder = SearchIndexHolder(
        source,  # type: ignore[arg-type]
        directory=Path(tempfile.gettempdir()) / "tub-index",
        open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
        clock=lambda: datetime.now(UTC),
        suppression_list=source,  # type: ignore[arg-type]
    )
    started = time.perf_counter()
    with holder.lease() as search:
        loaded = time.perf_counter() - started
        print(f"first lease (load) {loaded:.2f} s; VmHWM {status_kib('VmHWM')} KiB, VmRSS {status_kib('VmRSS')} KiB")
        for query in QUERIES:
            t0 = time.perf_counter()
            page = search.search(query)
            count = (f"{page.count.matches}{'+' if page.count.capped else ''}" if page.count is not None else None)
            print(f"search {len(query.split())}-word query: {round((time.perf_counter() - t0) * 1000)} ms, "
                  f"{len(page.hits)} hits on the page, counted {count if count is not None else 'n/a'}")
    print(f"after searches: VmHWM {status_kib('VmHWM')} KiB, VmRSS {status_kib('VmRSS')} KiB")
    print(f"cgroup memory.peak {cgroup('memory.peak')} bytes, memory.max {cgroup('memory.max')}")
    print(f"oom events {cgroup('memory.events').replace(chr(10), ', ')}")
    holder.close()
    print(f"probe finished in {time.perf_counter() - started:.2f} s; pid {os.getpid()}")


if __name__ == "__main__":
    main()
```

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **Today's index already loads at the top of ADR-0019 (c) 7's band.** In the function's image at
  1.16 CPUs, the 1.04 GB index took 6.96 s to stream through gunzip and both sha256s, before the
  1 to 2 s app start, and Lambda's arm64 cores may be slower than this Mac's. The ADR's estimate
  takes the download as the long part (2.5 s here); the CPU part is. `v1-e39-t04`'s `REPORT`
  lines give init only, not the first search's wait. Belongs to `v1-e39-evidence-search-pilot`
  (the PM decides whether a measurement of the first search's wait on the function is a task).

* **The provenance line's season** (Q2): once the coach approves version 1.24's words above,
  `occurrence_provenance_line` in `debate_core.domain.evidence_search` writes the season after the
  slug. Outside this spec's packages. Belongs to `v1-e39-evidence-search-pilot`.
* **The annual purge and a backfile season.** `docs/runbooks/annual-purge.md` step 5 checks the
  current index holds no purged caselist; a purged caselist that is an offered season also has its
  own index and pointer. The retiring steps are in the evidence search runbook's Backfile seasons
  (take it out of `backfile_seasons`, delete its pointer, P4); step 5 should name them. Belongs to
  the annual purge's owner.
* **ADR-0019 (c) 3 and 5** describe one index; a sentence on the season indexes (each its own
  pointer, one held at a time, the same list) is the PM's to add.
* **dev moved 21 commits** past this branch's base during the session; `scripts/task sync` before
  the pull request.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted for a partial merge (`scripts/task pr --partial`, after `scripts/task sync`, since dev has
moved 21 commits). The Goal stays `InProgress` until ac2 (c), the after-measurement, is recorded and
ruled on.

* **ac1 is complete and honest.**
  * Two clamshell-sleep failures are recorded with their `pmset` evidence and their lapsed leases. The
    partial copies were deleted, and the one not counted first is said to be uncounted.
  * Build 1 reproduces dev's published index byte for byte, which validates the method.
  * Every target the combined index breaks is named with its number, and the shrink-guard consequence
    for the weekly stage is found, not assumed.
* **Shape (4) is built as ruled.**
  * Default search never reads a season pointer, pinned by a test.
  * One season is held at a time, each with its own pointer and its own shrink guard.
  * Every holder reads the one suppression list: a removed card is gone at 5:00, and a season first
    loaded after a removal never shows it.
  * A season card's page and copy read its season's index.
  * A season not offered is refused.
* **The evidence is enough:** the red run had 27 of 45 failing for named reasons, and 20 of 20
  mutants plus 2 of 2 Terraform mutants were caught.
* **The prune change is accepted and is the important catch.** Without it, the removal runbook's P4
  would have deleted every season's index, or kept their superseded copies for ever (gate items 1
  and 5).
* **Seasons by the slug's starting year is accepted.** The PM's Q2 example (hspolicy25 as 2024-25) was
  a year early, and the recorded rule makes it 2025-26.
* **Inert until ruled:** `TUB_BACKFILE_SEASONS` is unset, so no season is offered, and
  `backfile_seasons` is set on the function only when it names one. So merging and deploying this
  code changes nothing a student sees. No backfile index is published, and none will be before the
  PM rules on the after-measurement.
* **The deviations are accepted.** The season key living in `debate_core.application` and the API
  conftest are fine as they are. The ADR-0019 sentence is the PM's, in the next batch.
* **The after-measurement (AM1 to AM5) is accepted as written.** It runs after the coming dev install
  and its checks, never on a Wednesday, on mains power with the lid open, one block at a time, with AM5
  deleting everything (policy 1.18). The PM rules on its figures before any publish, Terraform apply
  or deploy.
* **Q2 (the provenance line's season)** waits on the coach's approval of version 1.24's words. Once
  approved, the domain change is a task of its own (outside these packages).
* **Follow-ups, into the next PM batch:**
  * today's index loads at the top of (c) 7's band: a task to measure the first search's wait on the
    function itself;
  * the annual purge's step 5 to name the season steps, as a PM doc edit;
  * the ADR-0019 note.

`scripts/task pr --partial`
