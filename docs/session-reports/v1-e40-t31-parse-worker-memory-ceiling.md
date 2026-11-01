# Session report: v1-e40-t31-parse-worker-memory-ceiling

| | |
|---|---|
| Task | `v1-e40-t31-parse-worker-memory-ceiling` — A parse worker over its share of memory fails its file, not the whole run |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t31-parse-worker-memory-ceiling.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t31-parse-worker-memory-ceiling.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t31-parse-worker-memory-ceiling` |
| Session status | BLOCKED <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The task's first step was to measure, and the measurement says **the main process is what grows**,
which the PM's context names as the point to say so and stop. A parse worker peaks at no more than
632 MiB of address space (604 resident) on the Mac's whole corpus of 13,528 packages, and the workers
are stopped before the aggregate rebuild begins. The rebuild then holds every card of the caselist
in the main process at once: 1.33 GB for 250 of `hspolicy26`'s sources, over 2.15 GB for 500 and
still climbing, and about 13 GB for the whole store of 3,869 by a straight line through those two.
A whole season's backfile, like the `hspolicy25` import killed on 2026-10-31, is larger again. A
per-worker ceiling would not have prevented that kill, so none was built, and neither was the
amendment's per-stage memory figures, pending the PM's ruling (the questions are below). The record
is [`docs/data/caselist-parse-memory.md`](../data/caselist-parse-memory.md). The Goal stays
`InProgress`: criterion ac2 is NOT RUN. Two things to read first: the rebuild's growth, and three
findings for whoever builds a ceiling later (Decisions and assumptions), one of which would break
every older build's reading of the parsed store.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parse-worker-memory-ceiling` (Worker memory ceiling) | NOT DONE: stopped after the measurement | The measurement is recorded. Nothing was built, because the measurement found the main process growing (the PM's stop rule). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the measurement is recorded in `docs/data`, counts and sizes only, before any rule | PASS | [`docs/data/caselist-parse-memory.md`](../data/caselist-parse-memory.md), committed before any code (there is none). Its figures come from the runs listed under "How it was measured" below. |
| ac2: a worker over its ceiling ends as a `WorkerFailure` naming memory, the source is failed, the next parses; unset, no ceiling; tests shown failing first | NOT RUN | Stopped before building, by the PM context's rule: "If the main process is what grows, say so and stop." |
| Node: "Worker memory ceiling tests pass" (`uv run pytest packages/debate_core/tests -k parse_worker`) | NOT RUN | No ceiling and no tests were written. |

### How it was measured

All read-only on the operator's store. The sources were mounted read-only, and every run that writes
(a parse or a rebuild) wrote into a copy-on-write clone of the dev data directory in the session's
scratch folder (`cp -c`, 13 s). The Linux runs used the cloud run's image `v1.1.0-dev.289`
(arm64, like the Fargate task) under `docker run --network none`. The three scripts are in the
session's scratch folder and were not committed. Each figure in the data document is from one of
these runs:

* Stored sizes: `find … | xargs stat` over the blob directory, 0.6 s. 15,327 sources, 13,528 zip.
* Per-source peaks: each source parsed in a child forked from a parent that had imported the parser,
  reading `VmHWM` and `VmPeak` from `/proc/self/status` and `ru_maxrss` from `wait4`. The 300 largest
  by stored size ran 136.6 s of parsing. The 12 largest by main document part ran 46 s.
* Limits: the hungriest source under `RLIMIT_AS` at 120, 200, 300, 450 and 600 MiB, and its main
  part alone through `etree.fromstring` with the parser's hardened `XMLParser` at 90 to 400 MiB.
  macOS `setrlimit` was probed with the worktree's Python.
* Parse loop: a real `debate-research --json caselist parse --reparse --caselist openev` on the clone,
  4 workers, `ps` once a second for the main process and its children: 91 s, exit 0.
* Rebuild: the CLI container's parse service over the clone (offline, local suppression list),
  `plan()` then the service's rebuild over the first 250 and 500 of `hspolicy26`'s per-source files,
  sampling `VmRSS` twice a second, in the Linux image capped at 7 GB. 250: 67 s, finished. 500:
  stopped at its 112 s limit while placing cards.

### Checks before the report

* `uv run scripts/affected_tests.py --run` (bounded by `scripts/hard_stop.py 115`): 42 files, the
  always-run list and the docs tests. It was stopped at its 115 s limit at 89%, with no failure by
  then. It runs past two minutes, so by agreement 10 it is left to the pull request's `ci` check.
* Within the limit: `pytest tests/docs tests/architecture tests/specs -n auto -m "not slow and not live"`
  → 510 passed in 21 s. `tests/architecture/test_single_interpreter_source.py` was run again after the
  commit, since it reads tracked files → 55 passed.
* `uv run ruff format --check .` → 1763 files already formatted. `uv run ruff check .` → all checks
  passed. `uv run lint-imports` → 20 kept, 0 broken. No Python changed, so pyright was not run.
* `uv run scripts/check_command_blocks.py --base origin/dev` → OK, this report included.
  `uv run scripts/validate_specs.py` → OK: 562 files, 41 epics, 499 tasks, 22 releases.

## Files changed

* `docs/data/caselist-parse-memory.md` (new): the measurement, counts and sizes only.
* `docs/session-reports/v1-e40-t31-parse-worker-memory-ceiling.md`: this report.

No code, test, setting or infrastructure changed. Nothing was added to the run record or its details,
so nothing here meets v1-e40-t29's changes to `sync_runs.py`.

## Deviations from the spec

* **Stopped after the measurement**, by the PM context's rule for a main process that grows. ac2, the
  node's criterion, and the amendment (the weekly run's memory high-water marks per stage and in its
  details) are not done. The amendment does not depend on which process grows, so whether it goes
  ahead in this task is the first question below.
* **The main process's growth was measured on subsets, not over a whole parse of a few thousand.**
  The spec asks for that as an operator block if it runs past two minutes. A whole `hspolicy26`
  rebuild needs about 13 GB: Docker Desktop's VM has 8 GB, and the Mac had 21.9 of 23.5 GB of swap in
  use. A run on it would have thrashed the operator's machine and given macOS resident sizes that
  leave out compressed memory. So the growth was measured in runs under two minutes each: openev's
  whole parse (104 sources), and `hspolicy26`'s rebuild over 250 and over 500 of its sources. The
  whole-store figure is a straight line through those, marked so in the document. It answers the
  task's question (which process grows), but it is not a size to provision the task by. The weekly
  run's own figures, once the amendment records them, would be.
* **One measurement outlived its time limit by about 30 seconds.** `scripts/hard_stop.py` stopped
  the `docker run` client of the 300-source run at 115 seconds, but the container runs under Docker's
  daemon, outside the process group, and went on to finish its last 58 sources. It only read, and
  wrote to the scratch folder. Every later container was named and stopped explicitly with
  `docker stop` after the bounded run, and none was left running (`docker ps`).

## Decisions and assumptions

* **Measured in the run image, on Linux,** because macOS does not enforce the limit a ceiling would
  use and does not report the address-space peak. The image's parser is the dev build's
  (`2026.10.27-docx-7`), the parser this tree has.
* **Three findings for whoever builds a ceiling later.** None were acted on.
  1. *The limit and its measure.* `RLIMIT_AS` is the limit Linux enforces on one process, and
     `VmPeak` measures it exactly: the hungriest source failed with `VmPeak` at the limit, every
     time. `RLIMIT_RSS` is not enforced on Linux, and `RLIMIT_DATA` has no peak to measure it by. On
     macOS, `RLIMIT_AS` is the same limit as `RLIMIT_RSS`, `setrlimit` refuses it with
     `ValueError`, and nothing is enforced. A worker there would have to run without a ceiling.
  2. *A memory failure can be recorded as a malformed file.* When libxml2 is the allocation that
     fails, lxml raises `XMLSyntaxError` with code `ERR_NO_MEMORY` (2), and the docx parser records
     `MALFORMED_XML` (seen at 120 MiB). Telling it apart needs a change in
     `debate_core/integrations/docx_parser/package.py`'s `_parse_xml`, outside this task's packages.
  3. *A new failure reason breaks older builds.* `SourceEntry` refuses a `reason` it does not know
     (`not a parse failure reason`), and `LocalParsedStore` raises `UnreadableParsedStore` for the
     whole caselist. One `MEMORY_LIMIT` row written to the shared store would make every earlier
     build, including the weekly run's pinned image and the Mac's, refuse to read that caselist.
     A new reason needs a release that reads it first, or a cross-build check like the run record's.
* **The reserve.** Not decided, since no ceiling was built. By the measurement, the reserve is the
  rebuild's whole need, which grows with the caselist, so no fixed reserve fits every caselist.
* **No real source in the report or document.** No digest, name, path or text: only ranks, sizes,
  counts, seconds and memory.

## Operator follow-ups

None required. If the PM wants the whole-store rebuild measured anyway, it needs a machine with
about 16 GB free and is about 10 minutes or more. The session can write that block once asked.

## Follow-up work

**For the PM, paste-ready:**

> v1-e40-t31 stopped at its measurement (docs/data/caselist-parse-memory.md): the main process is
> what grows. Workers peak at most 632 MiB each, and they are stopped before the aggregate rebuild,
> which holds every card of the caselist in the main process at once: 1.33 GB for 250 hspolicy26
> sources, over 2.15 GB for 500, about 13 GB for the whole 3,869 by a straight line. Three questions:
>
> 1. **A new task for a rebuild that does not hold the whole caselist.** `_occurrence_rows` in
>    `caselist_parse.py` reads every parsed card into one list before placing them. Options: (a) a
>    task to stream it (read cards source by source, keep only what fingerprinting and clustering
>    need); (b) size the run task to the largest rebuild instead. Recommendation: (a), in E40, ahead
>    of the backfile imports. A season's backfile is bigger than hspolicy26, and 32 GB is likely
>    not enough for it.
> 2. **The amendment (weekly run's memory high-water mark per stage and in its details).** Options:
>    (a) keep it in t31 and continue the session with it alone; (b) move it to its own task; (c)
>    drop it. Recommendation: (a). It measures the rebuild in the cloud, it does not depend on which
>    process grows, and it needs the dev.251/dev.200 cross-build check either way.
> 3. **The per-worker ceiling.** Options: (a) cancel it: on this corpus it would refuse nothing and
>    it would not have stopped the kill; (b) keep it as defence in depth after the rebuild fix,
>    knowing it needs a parser change outside t31's packages (lxml's `ERR_NO_MEMORY` is recorded as
>    `MALFORMED_XML` today) and a new failure reason that every older build refuses to read in the
>    parsed store. Recommendation: (a), or (b) only as a later task with the cross-build reading
>    built first.

**Also found:**

* `scripts/hard_stop.py` cannot stop a `docker run` container, which runs under Docker's daemon,
  outside the process group (Deviations). A note in working agreement 10, or a `--docker-name`
  option that stops the container too, would cover it. For E41 (upkeep).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
