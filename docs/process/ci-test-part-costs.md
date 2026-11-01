<!-- docs-index: What one ci.yml test part costs besides its tests, measured 2026-11-01, and the options for making parts cheaper -->
# What a CI test part costs besides its tests

`ci.yml`'s `test` job runs the selection in eight parts (working agreement 1). This page records
what each part spends on things other than its tests, against its test time, and the options for
cutting that cost. It was written by `v1-e41-t15`. That task built none of the options below; the
PM chooses which to file.

## What was measured

On GitHub, by the PM from the public API on 2026-11-01, eight pull-request runs:

| Run | Per part |
|---|---|
| Whole-selection pull request | pytest 190–290 s, job 190–340 s |
| Every part, before `v1-e41-t15` | "Choose the tests" 17–33 s, repeated in each of the eight parts |
| Bot refresh pull request (ROADMAP.md and docs/README.md only) | job 44–76 s, pytest 15–33 s, after 200–280 s waiting for a runner |
| Part 1, PR #769 | slowest test: the partition proof, 69.8 s |

On the operator's Mac, by the session on 2026-11-01. The machine's load average was 4 to 7 from
other work throughout, so the times are high; the proportions are what to read.

| What | Result |
|---|---|
| Whole default selection, collected in one process (`--collect-only -n 0`) | 19,791 tests in 6.5 s (7.4 s wall) |
| Part 1 of 8 collected, no test run (`-k` matching nothing), by worker count | 7.9 s at `-n 0`, 8.7 s at `-n 2`, 9.4 s at `-n 4` |
| Part 1 of 8 run under `-n 4`, the runner's worker count | first result at 8.3 s; 2,170 of about 2,474 tests (90%) done by 60 s; 2,408 done when stopped at 115 s |
| Worker time spent on part 1's 2,408 finished tests | 328 s: setup 98 s, call 231 s, teardown under 1 s |
| The partition proof, in its own job's command | 2 tests in 55.5 s, the whole-selection proof 53.8 s of it |

Every xdist worker collects the whole selection and keeps its part, so collection costs the same
wall time at any worker count, and four times the CPU at `-n 4`. A part's fixed cost is therefore
its setup (checkout, uv, Python, `uv sync`; agreement 1 puts it at about 15 seconds) plus a
whole-selection collection, about 8 seconds locally and more on a runner. Against 190–290 s of
pytest on a whole-selection run that is about a tenth to a sixth of the part. On an affected-set
pull request, whose pytest step takes 15–33 s, it is half the part or more.

The larger cost is the tail. Part 1 finished 90% of its tests in about half its time; the rest
was a few dozen heavy tests running side by side: the caselist removal and pull smoke tests, the
bucket-mode kill tests, `test_launchd_install.py`, each 5–11 s with its fixtures. Fixture setup
was 30% of the worker time, and because every file's tests are dealt round all eight parts, a
module-scoped fixture is built again in every part and every worker that holds one of its tests.

Estimated from part 1 times eight, the whole selection is about 2,600 s of worker time locally.
The heaviest files, by the same rough estimate, are `tests/smoke/test_caselist_remove_smoke.py`
(about 300 s), `test_bucket_mode_kills.py` (190 s), `tests/integration/test_launchd_install.py`
(160 s), `test_backfile_import.py` (160 s) and `test_bucket_mode_lock.py` (140 s).

## What v1-e41-t15 changed

* The tests are chosen once, by the `test-selection` job, not 17–33 s in each of eight parts:
  about two to four runner-minutes less per run.
* A change to the generated files alone runs no part: about eight jobs less per merge into dev.
* The partition proof left part 1 for a job of its own, run on pushes and when what it proves
  changes: about 55–70 s off part 1 on a whole-selection pull request.
* The parts now start after `test-selection` finishes rather than after `changes`, so the selection
  and its setup are on the parts' path once; a part's own setup follows. On an affected-set pull
  request the parts may start about 10–20 s later than before. The PM reads the next runs' timings
  (the task's ac3) to see the net effect.

## Options

1. **Deal whole files to parts by recorded durations.** The `test-selection` job would hand each
   part its own list of files, packed by the durations a push run records (longest first, onto the
   least-loaded part), and xdist would still spread each part's tests over its workers. A part would
   collect an eighth of the selection instead of all of it (about 8 s → 1 s locally), and a
   module-scoped fixture would be built in one part instead of eight (setup was 30% of worker
   time). The partition proof would become a check that the lists are disjoint and cover the
   selection, which needs no whole-suite collection. Costs: a durations file refreshed on dev's push
   run, which goes stale between refreshes and can unbalance the parts, and a heaviest file of about
   300 s of worker time, about 75 s for one part's four workers on its own. Gains the most; it is
   the largest change.
2. **Fewer parts, or as many parts as the selection needs.** Eight parts at 190–290 s means six
   parts at about 250–390 s, over agreement 1's 2-minute line, so fewer parts for every run is not
   recommended. Sizing the matrix to the selection is: `test-selection` already knows how many files
   it chose, and could hand `test` a part list of one or two parts for a small affected set and all
   eight for the whole selection. The bot's pull requests already run none; an ordinary task's
   affected set (pytest 15–33 s per part in the PM's figures) would save five or six jobs of about
   30–45 s setup and collection each, which is most of the queue the PM measured.
3. **The xdist worker count.** Collection's wall time hardly changes with it (7.9–9.4 s from no
   workers to four), because each worker collects in parallel. Fewer workers would save collection
   CPU on the 4-vCPU runner but halve test parallelism. More than four may help the heavy,
   subprocess-bound tests, but that was not measured on a runner. Not recommended without a runner
   measurement.
4. **Shorten the tail, a one-flag change.** The locked pytest-xdist has
   `--dist worksteal`, which moves queued tests from a busy worker to an idle one, where the
   default `load` sends fixed batches. A part's end is set by its slowest worker, and the heavy
   tests cluster at the end of collection order. It changes no selection and the partition proof
   is unaffected; its effect has to be read from runner timings.

**Recommendation:** option 2's matrix sized to the selection first, which is small and answers the
queue; option 4 alongside it, measured on a whole-selection run; option 1 when a whole-selection
part passes the 2-minute line again.
