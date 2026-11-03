<!-- docs-index: What one ci.yml test part costs besides its tests (measured 2026-11-01), how many parts a selection gets (2026-11-02), and the options for making parts cheaper -->
# What a CI test part costs besides its tests

`ci.yml`'s `test` job runs the selection in parts (working agreement 1): eight until `v1-e41-t16`,
and since then one per 30 test files chosen, at most eight. This page records what each part spends
on things other than its tests, against its test time, and the options for cutting that cost. It
was written by `v1-e41-t15`, which built none of the options; what `v1-e41-t16` built from them is
at the end.

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

## What v1-e41-t16 changed

The PM chose option 2, sized by file count, and option 4 as a switch (rulings of 2026-11-02).

### As many parts as the selection needs

`test-selection` gives the `test` matrix one part per 30 test files it chose, at least one and at
most eight; the whole selection is always eight (`TEST_FILES_PER_PART` and `MOST_PARTS` in
`scripts/ci_test_selection.py`). It counts its own list, so nothing is added to the parts' path; an
exact count of tests would need a collection there, about 5–15 s on every pull request.

Why 30: on the operator's Mac, 2026-11-02, `fd48282`'s affected set ran 2,047 tests in 55.5 s at
`-n 4`, 203 s of worker time, 0.099 s a test, against about 0.13 s a test estimated above for the
whole selection. On a runner, a part's pytest step is about 15 s plus 0.09 s for each test in it
(whole-selection parts of about 2,510 tests take 190–290 s; the bot's parts, about 50 tests each,
15–33 s). About 1,000 tests to a part keeps the step near 100 s, under agreement 1's 2-minute line,
and 30 test files are about 1,000 tests on today's suite (30.7 tests a file on average; 24–44 in the
sets below).

The rule over the last twelve task merges into `dev` before this task, read with
`scripts/affected_tests.py --diff <commit>` against the 2026-11-02 tree and counted from one
collection of the whole selection (20,077 tests in 654 files). "By 1,000 tests" is the rule the
session first proposed, for comparison:

| Merge | Task | Test files | Tests | Of the suite | Parts | Tests a part | By 1,000 tests |
|---|---|---|---|---|---|---|---|
| `fd48282` | v1-e08-t09 | 46 | 2,047 | 10% | 2 | 1,023 | 3 |
| `51706db` | v1-e06-t08 | 110 | 4,084 | 20% | 4 | 1,021 | 5 |
| `28d4c88` | v1-e32-t39 | 233 | 5,854 | 29% | 8 | 731 | 6 |
| `b707b6a` | v1-e06-t07 | 238 | 6,745 | 34% | 8 | 843 | 7 |
| `ffce3fb` | v1-e08-t08 | 254 | 6,604 | 33% | 8 | 825 | 7 |
| `dedb908` | v1-e32-t40 | 308 | 8,501 | 42% | 8 | 1,062 | 8 |
| `4f91c9e` | v1-e40-t39 | 328 | 7,758 | 39% | 8 | 969 | 8 |
| `c8e02a3` | v1-e40-t35 | 362 | 9,094 | 45% | 8 | 1,136 | 8 |
| `792dd4a` | v1-e40-t36 | 412 | 11,397 | 57% | 8 | 1,424 | 8 |
| `c6e35fd` | v1-e08-t04 | 622 | 19,236 | 96% | 8 | 2,404 | 8 |
| `f66a450` | v1-e08-t05 | whole selection (shared test ground) | 20,077 | 100% | 8 | 2,510 | 8 |
| `1663d04` | v1-e06-t06 | whole selection (shared test ground) | 20,077 | 100% | 8 | 2,510 | 8 |

The always-run list alone, 11 files and 377 tests, is one part. So sizing saves runners and
the queue for them on small selections, and changes nothing for most task pull requests: ten of
these twelve still get eight parts. Their wait is the parts' fixed cost and the selection's size,
which option 1 above answers; the PM files it as its own task.

The parts still partition the selection at every size: the partition proof collects the parts the
rule gives for its selections and deals the real collection at every size from one to eight with
the plugin's own function (`parts_dealt`). On the operator's Mac it took 18.7 s and 17.7 s, against
36.5 s and 18.2 s for the proof before the change, run alternately at load averages of 4.5 to 16.

### worksteal, switchable for a dispatch

`ci.yml`'s `workflow_dispatch` has an input, `xdist_dist`, `worksteal` (the default since the PM's
decision of 2026-11-02) or `load`, which every test part passes to pytest as `--dist`. A push, a pull
request and the bot's dispatch run `worksteal`. To compare the two on one commit, dispatch `ci` on `dev` twice, once with each value,
without a merge into `dev` in between (a dispatch runs the whole selection in eight parts, without
coverage):

```bash
gh workflow run ci.yml --repo charlesclark2/debate-intelligence --ref dev -f xdist_dist=load
gh workflow run ci.yml --repo charlesclark2/debate-intelligence --ref dev -f xdist_dist=worksteal
```

Then check that both runs are of the same commit; a different `headSha` means `dev` moved between
them, and both are dispatched again:

```bash
gh run list --repo charlesclark2/debate-intelligence --workflow ci.yml --event workflow_dispatch --branch dev --limit 2 --json databaseId,headSha,createdAt,status
```

The PM reads the eight parts' pytest step times of each run from the public API. **The comparison of
2026-11-02** (dev at `cc41db60`, both green), pytest step per part in seconds:

| `--dist` | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | Slowest | Total |
|---|---|---|---|---|---|---|---|---|---|---|
| load | 259 | 257 | 279 | 240 | 228 | 266 | 261 | 286 | 286 | 2,076 |
| worksteal | 234 | 182 | 270 | 200 | 232 | 240 | 245 | 231 | 270 | 1,834 |

Each part held the same tests in both runs. worksteal was faster on 7 of 8 parts, 12% less in total
and 16 s on the slowest part, so it is the default. One run each, so runner noise is in these
figures; the direction held on all but one part.
