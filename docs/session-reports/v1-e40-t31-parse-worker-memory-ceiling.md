# Session report: v1-e40-t31-parse-worker-memory-ceiling

| | |
|---|---|
| Task | `v1-e40-t31-parse-worker-memory-ceiling` — A parse worker over its share of memory fails its file, not the whole run |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t31-parse-worker-memory-ceiling.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t31-parse-worker-memory-ceiling.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t31-parse-worker-memory-ceiling` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The task measured first, and the measurement found **the main process is what grows**. A parse
worker peaks at no more than 632 MiB on the Mac's corpus and is stopped before the aggregate rebuild,
which holds every card of a caselist in the main process. The record is
[`docs/data/caselist-parse-memory.md`](../data/caselist-parse-memory.md). The session stopped there,
as the PM's context asked. The PM's ruling of 2026-11-01 then dropped the per-worker ceiling, moved
the streaming rebuild to its own task (`v1-e40-t36`), and kept the amendment. That ruling is now in
the spec as a dated paragraph. **The weekly run now records, as each stage ends, the container's
memory high-water mark (the cgroup's peak) and the main process's own**, with `v1-e40-t32`'s reader.
They are on the stage's entry in the run's summary and in its details. A figure that cannot be read
is left out, never zero. Offline builds of `v1.1.0-dev.251` and `v1.1.0-dev.200` read these details
with their own code, from the details file and from the bucket. The run record gains nothing, and
the details gain no key of their own. Wednesday 2026-11-04's run is on `v1.1.0-dev.251`, which
records no figures, so this report has none. The Goal is `Succeeded`. Worth reading first: the
cross-build check, and why the figures sit inside each stage entry (Decisions 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parse-memory-measurement` (Parse memory measured) | Done | Measured before any rule; the per-source peaks in the run image on Linux, the main process on subsets (Deviations) |
| `run-memory-figures` (Weekly run memory figures) | Done | Tests red against a skeleton, then the code, the in-repo schema check and the cross-build check under both earlier builds, 11 mutants, the runbook |

The two nodes replace the original `parse-worker-memory-ceiling` node, by the PM's amendment.

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the measurement is recorded in `docs/data`, counts and sizes only, before any rule | PASS | [`docs/data/caselist-parse-memory.md`](../data/caselist-parse-memory.md), committed (`78e73bb` before the sync) before any code. The runs behind it are under "How the parse was measured" |
| ac2 (PM amendment): each stage, in the summary and the details, carries the container's mark and the main process's own where they can be read, and leaves them out where they cannot; offline builds of dev.251 and dev.200 read those details; tests shown failing first | PASS | Red: 6 of 7 core tests and both CLI cases failed at assertions against the skeleton ("Red run" below). Green: `pytest … -k memory_figures` → 10 passed. Cross-build: `PASS` under both builds ("The cross-build check") |
| Node: "The measurement is recorded" (`artifact_exists docs/data/caselist-parse-memory.md`) | PASS | The file is committed |
| Node: "Run memory figure tests pass" (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k memory_figures`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k memory_figures -q -n auto -p no:randomly` after the sync → `10 passed in 27.49s`: the 7 core tests, the CLI test's two cases, and `v1-e40-t32`'s `test_the_memory_figures_are_on_each_end_and_progress_line_when_a_cgroup_reads`, whose name matches |
| Wednesday 2026-11-04's figures, recorded if the run has them | Not applicable | The run uses `v1.1.0-dev.251`, which records none |

### Red run

Against a skeleton with the fields and the `read_memory` parameter but nothing recorded (`92fb5f1`
before the sync). `test_caselist_sync_memory_figures.py`: 6 failed, 1 passed, each failure an
`AssertionError`:

```text
test_caselist_sync_memory_figures.py:108: AssertionError: the index stage's figures are read after it ran, not before
test_caselist_sync_memory_figures.py:125: AssertionError: assert {'schema_vers...des': [], ...} == {'schema_vers...des': [], ...}
test_caselist_sync_memory_figures.py:167: AssertionError: assert [{'finished_a...ted_at'}, ...] == [{'finished_a...ted_at'}, ...]
test_caselist_sync_memory_figures.py:188: AssertionError: assert [None, None, ...ne, None, ...] == [(7516192768,...8, 'v2'), ...]
6 failed, 1 passed in 0.29s
```

The other two failures were the round trip (`[None] * 9` against the figures) and the case with no
cgroup (`{"null"}` against the main process's figure). The one that passed is the schema test, which
holds for the skeleton too: it is the guard that mutants 3a and 3b break. The CLI test failed in
both cases: `[(None, None)…] == [(7516192768, 'v2')…]`, and `[[]…] == [['main_process_peak_bytes']…]`.

### The cross-build check

**The earlier builds.** I followed `v1-e30-t31`'s recipe (`<scratchpad>/build_earlier.sh`), 2 s for
both:

1. `git archive` of the tag;
2. `scripts/stamp_build.py stamp`;
3. `uv build --offline --package debate-core --wheel`;
4. `uv venv --offline`, then `uv pip install --offline --no-deps` of the wheel;
5. a plain-path `.pth` to the worktree's site-packages, for third-party packages only.

The tags are `a21bb68` for `v1.1.0-dev.251` and `761b571` for `v1.1.0-dev.200`. `debate_core`
resolved to each venv's wheel, with no `packages/*/src` path on `sys.path`.

**What they validate details with.** Each build printed `SyncRunDetails.model_json_schema()`. Both
are byte for byte `stored_run_records/details_schema_of_the_macs_installed_build.json`, so no new
stored file is needed. dev.251's record schema is byte for byte `record_schema_of_the_cloud_image.json`.
Both schemas leave a stage entry (`StageTiming`) open to keys they do not define. The stored README
says so (`stored_run_records/README.md`).

**Their own readers, on this build's details.** `check_an_older_build_reads_the_run_memory_figures.py`
reads `run_memory_figures/details_this_build_writes.json` through two readers:

* the details file reader, `SyncRunDetailsLog.read`, which `caselist runs` uses;
* the bucket reader, `read_remote_runs`, which `caselist runs --remote` uses, over the filesystem
  object store.

`test_caselist_sync_memory_figures.py` shows that file is what this build writes. The check ran
after the sync, with `"${VENV}/bin/python" -I <the check>`:

```text
== v1.1.0-dev.251
its stage entry keeps the figures: False
details file: the run read True; 9 stage(s), as written: True
bucket: 1 run(s), its details read True; stages as written: True
PASS
== v1.1.0-dev.200
its stage entry keeps the figures: False
details file: the run read True; 9 stage(s), as written: True
bucket: 1 run(s), its details read True; stages as written: True
PASS
```

This build prints the same, with `True` on the first line. Each run took under half a second.

**The check catches a refusal.** Mutant 3a's details, with `schema_version` 2, went through the same
check. Under both builds, both readers skipped them ("not details this build reads"), and the check
printed `FAIL: 2 reader(s)`. Mutant 3b puts the figures on the record's stage entries, and both
builds' `SyncRunRecord` refused that record: `extra_forbidden ('stages', 0, 'memory')`.

### Mutants

These are the PM's three kinds, in 11 forms. Each was run against the committed source, after the
sync, over `test_caselist_sync_memory_figures.py`, `test_caselist_sync_stage_times_and_volume.py`,
`test_pull_run_record_is_read_by_every_build.py` and the CLI's memory test. Each run had a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`; none of these tests uses Hypothesis. The source was restored from
`HEAD` after each (`git status` clean at the end). All 11 were caught, each at an assertion:

| Mutant | Result | Caught by (unique test names) |
|---|---|---|
| 1a no figures recorded in any stage | CAUGHT | 6, the core stage, details-file, round-trip, no-cgroup and reader tests and the CLI's |
| 1b the figures read as the stage starts | CAUGHT | 3: the stage test ("read after it ran, not before"), the hand-written file, the round trip |
| 1c the parse stage's figures missing | CAUGHT | 6, as 1a |
| 1d the details drop the figures (the summary keeps them) | CAUGHT | 4: the hand-written file, the round trip, no cgroup, the CLI's |
| 2a an unread container figure written as zero | CAUGHT | 4: `none_readable…never_zero`, no cgroup, the CLI's, and t03's exact stage pin |
| 2b an unread container figure written as `null` in the details | CAUGHT | 2: no cgroup, the CLI's |
| 2c an empty figures object in the details when none was read | CAUGHT | 1: `none_readable…never_zero` |
| 2d an empty figures object in the summary when none was read | CAUGHT | 2: `none_readable…never_zero`, t03's exact stage pin |
| 2e `"memory": null` on a details stage entry when none was read | CAUGHT | 1: `none_readable…never_zero` |
| 3a the details' version moved to 2 for the figures | CAUGHT | 4 in-repo, the schema test among them; and both earlier builds through the check |
| 3b the figures on the record's stage entries | CAUGHT | 7 in-repo, the stored record schema tests among them; and both earlier builds' record model |

### How the parse was measured

All of it was read-only on the operator's store. The sources were mounted read-only, and every run
that writes (a parse or a rebuild) wrote into a copy-on-write clone of the dev data directory in the
session's scratch folder (`cp -c`, 13 s). The Linux runs used the cloud run's image `v1.1.0-dev.289`
(arm64, like the Fargate task) under `docker run --network none`. The scripts are in the scratch
folder and were not committed.

* Stored sizes: `find … | xargs stat` over the blob directory, 0.6 s. 15,327 sources, 13,528 zip.
* Per-source peaks: each source parsed in a child forked from a parent that had imported the parser,
  reading `VmHWM` and `VmPeak` from `/proc/self/status` and `ru_maxrss` from `wait4`. The 300 largest
  by stored size took 136.6 s of parsing, the 12 largest by main document part 46 s.
* Limits: the hungriest source under `RLIMIT_AS` at 120 to 600 MiB; its main part alone through the
  parser's hardened `XMLParser` at 90 to 400 MiB; macOS `setrlimit` with the worktree's Python.
* Parse loop: a real `caselist parse --reparse --caselist openev` on the clone, 4 workers, `ps` once
  a second: 91 s, exit 0.
* Rebuild: the parse service's rebuild over the first 250 and 500 of `hspolicy26`'s per-source files,
  in the Linux image capped at 7 GB. 250 finished in 67 s. 500 was stopped at its 112 s limit while
  placing cards.

### Checks before the report

All after the sync onto `origin/dev` at `0fbc719`, which brought `v1-e40-t29` into `sync_runs.py`:

* **The affected set** is 309 of 643 test files (`uv run scripts/affected_tests.py`, 17 s to choose),
  because `caselist_sync.py` and `sync_runs.py` reach half the suite. That is well over two minutes,
  so by agreement 10 it is left to the pull request's `ci` check. Before the sync, a bounded
  `--run` over the docs-only change had already passed the two-minute line at 89%.
* **Within the limit:**
  * every test file that imports `caselist_sync`, `sync_runs` or `memory_high_water` directly:
    81 files in seven groups under `hard_stop.py 110`, 1,359 passed;
  * `tests/architecture tests/specs tests/docs` with the CLI's wiring tests: 554 passed;
  * the node's criterion: 10 passed;
  * the cross-build check under both builds: `PASS`.
* **The cheap checks:**
  * `uv run ruff format --check .` → 1766 files already formatted;
  * `uv run ruff check .` → all checks passed;
  * `uv run pyright packages/debate_core packages/debate_cli` → 0 errors;
  * `uv run lint-imports` → 20 kept, 0 broken;
  * `scripts/check_thin_handlers.py` → OK;
  * `uv run scripts/check_command_blocks.py --base origin/dev` → OK, this report included;
  * `uv run scripts/validate_specs.py` → OK, 567 files.
* **The runbook's block:** its Python ran against a hand-made `caselist runs --json` body (a stage
  without figures, a run without details) and printed one line a stage.

## Files changed

* `plan_specs/…/t31-parse-worker-memory-ceiling.yaml`: the PM's amendment, written in as asked; ac2
  and the plan's two nodes; the Goal `Succeeded`.
* `debate_core/application/caselist/memory_high_water.py`: `MemoryHighWater.as_json`, the readable
  figures only.
* `debate_core/application/caselist_sync.py`:
  * `StageTime.memory`;
  * the `read_memory` parameter, which defaults to `read_memory_high_water`;
  * `_timed` reads the figures as each stage ends;
  * `as_json` adds `memory` when anything was read;
  * a docstring section.
* `debate_core/application/sync_runs.py`: `MemoryFigures`, and `StageTiming.memory`, both left out
  with `exclude_if` when `None`. `details_for_summary` carries them. The module docstring has a
  bullet saying why they are not a key of the details' own.
* Tests:
  * `test_caselist_sync_memory_figures.py` (new);
  * the t03 helper takes a `memory` reader, which defaults to nothing readable, so t03's exact pins
    stand as written;
  * the CLI's `test_caselist_pull.py` gains one test with a stand-in cgroup, in two cases;
  * `caselist/run_memory_figures/` (the hand-written details and a README), the check file, and a
    sentence in `stored_run_records/README.md`.
* `docs/runbooks/caselist-cloud-run.md`: "The run's memory figures": what they are, how to read them
  with `caselist runs --remote --json`, what goes to the PM.
* `docs/data/caselist-parse-memory.md` (new): the measurement.

**For `v1-e40-t29`, now merged:** this task adds no field to the run record and no key to the
details. It adds one optional key, `memory`, inside each entry of the details' `stage_times`, and
the same in the summary's. The sync onto t29 rebased without a conflict.

## Deviations from the spec

* **Stopped after the measurement, then continued by the PM's ruling.** That is the rule the PM's
  context gave. The ruling (ceiling dropped, the amendment kept, `v1-e40-t36` for the rebuild) is
  written into the spec, with its plan nodes renamed to match. No ceiling, no `MEMORY_LIMIT` reason
  and no parser change were made.
* **The main process's growth was measured on subsets, not over a whole parse of a few thousand.**
  A whole `hspolicy26` rebuild needs about 13 GB. Docker Desktop's VM has 8 GB, and the Mac had 21.9
  of 23.5 GB of swap in use. So the growth was measured in runs under two minutes each, and the
  whole-store figure is a straight line through two subsets, marked so in the document. The weekly
  run's figures, from the first image with this task, are the measurement to size the task by.
* **One measurement outlived its time limit by about 30 seconds.** `scripts/hard_stop.py` stopped the
  `docker run` client of the 300-source run, but the container runs under Docker's daemon and finished
  its last 58 sources. It only read, and wrote to the scratch folder. Every later container was
  named and `docker stop`ped, and `docker ps` showed none left.
* **The hand-written details are beside `stored_run_records/`, not in it.** That directory's README
  says nothing in it is written by hand, so they went to a directory of their own,
  `run_memory_figures/`, with their own README.

## Decisions and assumptions

1. **The figures sit inside each stage's entry, not in a key of the details' own.** An existing test
   (`test_the_cloud_image_and_the_macs_build_read_every_record_and_details_line_these_runs_write`)
   pins that the details carry no top-level key the Mac's installed build does not define. Both earlier
   builds' schemas leave a stage entry open. The run-level high-water mark is the last stage's,
   because the marks only rise, so nothing is lost by keeping them per stage.
2. **Left out, not `null`.** `v1-e40-t32`'s log lines leave a figure out, and `v1-e40-t29`'s
   `skipped` uses `exclude_if` for the same reason. `MemoryFigures` and `StageTiming.memory` do the
   same, so details with nothing read are byte for byte what an earlier build writes for the stage.
3. **Read on every machine.** The reader is cheap (a file read and `getrusage`), so unlike the volume
   it needs no setting. The Mac records its main process's figure and no container figure.
4. **The default reader is proven through the CLI.** The core tests pass a reader explicitly. The
   CLI's test goes through the container's wiring, which passes none, so the service's default
   `read_memory_high_water` is what that test exercises (mutants 1a and 1c fail it).
5. **No new stored schema.** dev.251's details schema is byte for byte dev.200's stored one. A
   second copy would only be one more file to keep equal.
6. **What a reader on an earlier build sees.** dev.200's `caselist runs --remote --json` re-serialises
   the details with its own model, so it prints no figures. The runbook says to read them from a
   build with this task, and that `no figures` from an earlier build is not a run that recorded none.
7. **Findings left for later, from the measurement.** These matter for a future ceiling, now
   cancelled:
   * `RLIMIT_AS` is the Linux limit that `VmPeak` measures exactly;
   * macOS refuses to set it;
   * libxml2's `ERR_NO_MEMORY` is recorded as `MALFORMED_XML`;
   * a new failure reason in the parsed store is refused by every earlier build.

## Operator follow-ups

None. The first weekly run on an image with this task records the figures, and the runbook's
"The run's memory figures" reads them, after the next image apply ([A new image,
later](../runbooks/caselist-cloud-run.md#a-new-image-later)), which is outside this task.

## Follow-up work

* **The figures from the first run on an image with this task** go to `v1-e40-t36` (the streaming
  rebuild): its "peak before and after" is best taken from them.
* **`scripts/hard_stop.py` cannot stop a `docker run` container** (Deviations). A note in working
  agreement 10, or an option naming a container to stop as well, would cover it. For E41.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

Measuring first was the right call, and the measurement changed the task. A worker peaks at 632 MiB
at most. The main process grows by about 0.8 GB per 250 `hspolicy26` sources in the rebuild, so a
per-worker ceiling would not have stopped the kill of 2026-10-31. That finding is why `v1-e40-t36`
exists.

1. **ac1:** `docs/data/caselist-parse-memory.md` was committed before any code. It holds counts and
   sizes only. Deviation 2 is accepted: the whole-store figure is clearly marked as a straight line
   through two subsets, and Docker Desktop's 8 GB VM made a whole run impossible.
2. **ac2:**
   * The figures are read in `_timed`'s `finally` as each stage ends. Mutant 1b shows they are read
     after the stage, not before.
   * Unread figures are left out, never zero, `null` or an empty object (mutants 2a–2e).
   * Decision 1 is right. The figures sit inside each `stage_times` entry, which both earlier
     schemas leave open, instead of a new top-level key that the existing pin forbids.
   * The run record is unchanged, and mutant 3b shows both builds refuse figures placed on it.
   * The reader cannot raise: `_bytes_in` catches `OSError` and `UnicodeDecodeError`, and
     `getrusage` does not fail. So reading in `finally` never masks a stage's own result.
3. **The cross-build check** under the stamped `v1.1.0-dev.251` and `v1.1.0-dev.200` wheels reads
   through both their readers, the details file and the bucket. Mutant 3a shows the check fails on
   a refusal, which is what makes its `PASS` mean something.
4. **Red then green:** 6 of 7 core tests and both CLI cases failed at assertions against the
   skeleton. 11 mutants, all caught.
5. **Deviation 3** (a container outliving `hard_stop.py`) did no harm: it only read and wrote to
   scratch. Deviation 4 (a directory of its own for hand-written details) is accepted.
6. **Closing checks:**
   * The affected set (309 files) is left to the PR's `ci` under agreement 10.
   * Clean: the direct importers (1,359 passed), architecture/specs/docs (554), the node's criterion
     (10), ruff, pyright, lint-imports, thin handlers, command blocks and the specs.
7. **Follow-ups:**
   * The first figures go to `v1-e40-t36`. They arrive with the first image apply after this merges:
     Thursday's, if it carries this commit.
   * Follow-up 2, `hard_stop.py` and `docker run`: the PM files it under E41.
   * Decision 7's ceiling findings stay recorded here only. No ceiling task is filed.
8. **Merge:** a plain `scripts/task pr` once `ci` is green (the Goal is `Succeeded`, and there is no
   operator follow-up).
