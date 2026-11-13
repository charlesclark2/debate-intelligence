<!-- docs-index: What one ci.yml test part costs besides its tests (measured 2026-11-01), how many parts a selection gets, how whole files are dealt to parts by recorded durations (2026-11-02), what module fixtures and collection cost a part (2026-11-05), each part collecting only its own files, and the options for making parts cheaper, and what the slow-tests job costs (2026-11-13) -->
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
(about 300 s), `test_bucket_mode_kills.py` (190 s), `tests/cli/test_launchd_install.py`
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

## What v1-e41-t17 changed

Option 1 above, as the PM ruled it on 2026-11-02: whole test files are dealt to the parts by the
seconds each took on dev's last push run, so a file's module- and class-scoped fixtures are built in
one part. `scripts/ci_test_durations.py` holds the rules; `tests/pytest_plugins/run_in_parts.py`
follows the deal.

### The record

* Every part of a push run times its tests, setup, call and teardown summed per test file
  (`--record-durations`), from pytest's own reports; under xdist the controller writes the file.
* On dev's push run only, `ci.yml`'s `test-durations` job adds the parts' files up and saves the sum
  in GitHub's Actions cache under a key of its own (`test-durations-<run id>-<attempt>`). It writes no
  record unless every part of the matrix timed its tests, and it never fails the push run, so a
  broken record cannot hold the dev pre-release. It needs no permission beyond the workflow's
  `contents: read` and no secret.
* The seconds are a push part's, which measures coverage: about half again a pull request's. Only
  their proportions are read.

The Actions cache rather than an artifact: a pull request into dev can restore what dev's runs
saved, with no token and no API call, and a restore that misses is an ordinary empty result. An
artifact of another run would need the API, `actions: read` and the run's id.

### The deal

`test-selection` restores the newest record once and hands every part the same deal as its
`files_to_parts` output, beside the test files it chose. A part never reads the cache, so a record
saved while a run goes on cannot give two parts different deals.

* A chosen file the record does not name counts as the record's **median**.
* A file **heavier than a part's share** (the chosen files' seconds over N) is left out of the deal,
  and its tests are dealt round every part as before: no deal of whole files can make a part
  lighter than its heaviest file. This is the one change from the PM's floor, greedy longest-first,
  and the figures below are why.
* The rest go **heaviest first onto the lightest part**.

**The parts are dealt test by test, as before, and the job summary says why** when the record is
missing (nothing restored, or the cache could not be reached), unreadable, **stale** (recorded more
than 14 days ago, or with no duration for more than a quarter of the chosen files), when every chosen
file is heavier than a part's share, or when a part would hold no file with a recorded time. For the
whole selection the files dealt are every test file under `testpaths`, as `scripts/affected_tests.py`
lists them: 669 on 2026-11-02, against 662 the parts collect; the 7 others hold only slow or live
tests. The partition proof collects the parts under a deal by invented durations and under none, and
deals the real collection both ways at every size from one part to eight.

### The expected slowest part, on invented durations

On 2026-11-02, before any record exists, with the repository's own `parts_dealt` and
`by_durations`: an invented suite shaped like the figures above, 654 files and about 20,000 tests
with lognormal test counts and per-test costs, 2,600 s of worker time at the operator's Mac's pace
when every fixture is built once, five heavy files of 300, 190, 160, 160 and 140 s, and a long tail.
How much of the suite's time is module-scoped fixtures, which today's dealing builds again in every
part holding one of the file's tests, was not measured, so two shares are given. Worker seconds of the
slowest part over 8 parts (2 for the small set), and the slowest over the mean, for the deals that
follow a record made dealt whole (seed 17):

| Selection | Fixtures | Test by test (before) | Whole files, longest first | Whole files, a file over a share spread (built) |
|---|---|---|---|---|
| Whole selection, 654 files | none | 344 s (1.06) | 325 s (1.00) | 325 s (1.00) |
| Affected set of 301 files holding the heaviest | none | 145 s (1.08) | 289 s (2.15) | 143 s (1.07) |
| Affected set of 300 files, no heavy file | none | 105 s (1.06) | 99 s (1.00) | 99 s (1.00) |
| Small affected set, 46 files, 2 parts | none | 83 s (1.02) | 82 s (1.00) | 82 s (1.00) |
| Whole selection, 654 files | 10% | 567 s (1.05) | 325 s (1.00) | 325 s (1.00) |
| Affected set of 301 files holding the heaviest | 10% | 240 s (1.04) | 289 s (2.18) | 142 s (1.07) |
| Affected set of 300 files, no heavy file | 10% | 182 s (1.04) | 95 s (1.00) | 95 s (1.00) |
| Small affected set, 46 files, 2 parts | 10% | 100 s (1.01) | 84 s (1.00) | 84 s (1.00) |

What to read in it:

* **Dealt test by test, the parts are already level** (1.01 to 1.09 of the mean on three seeds), as
  the plugin's docstring measured. Dealing whole files gains only what it saves: each file's module
  fixtures built once instead of in every part. With none, the slowest part moves by a few percent;
  with a tenth of the suite in such fixtures, the whole selection's slowest part falls from 567 s to
  325 s and all eight parts' work from 4,341 s to 2,600 s.
* **Longest-first alone doubles the slowest part when a heavy file is in a smaller selection**: the
  300 s file in an affected set whose parts' mean is 127 to 141 s sets its part at 289 to 328 s, 2.15 to 2.52
  times the mean on the three seeds. Spreading a file heavier than a part's share keeps it at 1.06 to
  1.09. When the heaviest file is only just over its share (seed 3's whole selection, 328 s against
  325 s) spreading it costs a little: 337 s, where longest-first gave 328 s.
* **The first deal is the least level.** Its record was made dealt test by test, so a file's
  fixtures are counted once for each part that built them: at a 10% share (seed 17) its slowest part was 1.21
  to 1.45 of the mean (444 s for the whole selection, still under 567 s). Dev's first push run after
  the merge records them dealt whole, and the deals after it are the table's.

Whether the runners' 189-289 s slowest parts are fixtures built again, the per-test tail, or the
runner itself, these invented figures cannot say. The PM reads the slowest part's pytest step on three
task pull requests after the merge against three before it (the task's ac2).

## What module fixtures cost, measured before v1-e41-t18

Measured by the session on 2026-11-05 before any change, from three runs the operator downloaded
with `gh run view --log` and `--json jobs`, and on the operator's Mac.

| Run | Dealt | Coverage | pytest step per part, parts 1 to 8 (s) | Slowest | Total |
|---|---|---|---|---|---|
| dev push of `d84cf21` (run 41563571482), the last before `v1-e41-t17` | test by test | yes | 355, 365, 392, 372, 244, 270, 252, 375 | 392 | 2,625 |
| dev push of `6db251b` (run 41972928347) | whole files, by the record of `26f7e75` | yes | 403, 236, 389, 335, 269 (failed), 342, 250, 284 | 403 | 2,508 |
| dispatch on dev at `440f797` (run 41975449095) | whole files, by the record of `26f7e75` | no | 298, 222, 198, 224, 179, 225, 229, 226 | 298 | 1,801 |

Part 5 of the push failed one test (`test_search_command.py`, outside this page's subject), so the push run
saved no record; 269 s is the time pytest reported.

### The module-fixture share, from the parts' `--durations=25`

Each part prints its 25 slowest setups, calls and teardowns. A module- or class-scoped fixture
shows there as one large setup for the first test of its file in each worker that holds one; a
function-scoped fixture shows as a setup for every test.

| Run | Setups among a part's 25 slowest | Their seconds over the part's worker time (4 workers × pytest) |
|---|---|---|
| push, test by test | 5 to 10 in every part | 4.3% to 7.0% |
| push, whole files | 19, 0, 2, 1, 9, 0, 10, 0 | 17.6%, 0, 1.0%, 0.4%, 7.2%, 0, 5.0%, 0 |
| dispatch, whole files | 19, 0, 2, 5, 9, 0, 7, 0 | 22.2%, 0, 1.5%, 3.1%, 9.4%, 0, 4.2%, 0 |

* **No module- or class-scoped fixture is among any part's 25 slowest entries**, in any of the
  three runs. Every heavy setup there is function-scoped, built again for every test whichever way
  its file is dealt: `tests/smoke/test_caselist_remove_smoke.py`'s `installation`, `bucket` and
  `published` (11 to 15 s a test), then the bucket-mode files' (`test_bucket_mode_held_uploads.py`,
  `test_bucket_mode_removal.py`, `test_bucket_mode_openev_reimport.py`, `test_backfile_import.py`,
  5 to 9 s a test). Session-scoped smoke fixtures (`tests/smoke/conftest.py`) are built once a worker
  however the files are dealt.
* So the share `v1-e41-t17` set out to save, setup a file's whole-file dealing builds once, is too
  small to reach the durations: in every part it is less than the part's 25th slowest entry, 3.5 to
  12.4 s across the three runs. The invented figures on this page assumed none or a tenth of the
  suite; the runners are at the "none" end. The whole selection's pytest time fell from 2,625 s to
  2,508 s on the push runs, 4%, on commits two days apart with different tests, so that 4% is not
  a measure of fixtures either.
* **What dealing whole files changed is where the function-scoped setups land.** Before, the remove
  smoke file's 42 heavy setups among the parts' slowest were spread over all eight parts; since,
  all 19 are in part 1, with the rest of that file. It took 911 s of worker time on the push of
  `6db251b`, against the 775 s a part the record expected: the file sets the slowest part, 298 s on
  the dispatch against 179 to 229 s for the other seven, and 403 s on the push.

### Collection, per part

On the operator's Mac (load average 5 to 6), each of the 8 parts of the whole selection under a deal
of whole files (by invented durations; 696 files dealt, none spread), collected with
`pytest --collect-only -n 0` and the parts' markers:

| What each part collects | pytest's collection time, parts 1 to 8 | Wall |
|---|---|---|
| The whole selection, keeping its share (today) | 9.0, 8.3, 7.5, 7.4, 7.2, 7.5, 8.2, 7.3 s | 9.0 to 11.5 s |
| Only the files the deal gives it, named as paths (no code changed) | 1.6, 1.4, 1.9, 2.3, 1.7, 1.1, 3.2, 2.1 s | 2.7 to 4.6 s |

Both collected the same tests in each part (2,066, 1,907, 2,797, 2,385, 3,157, 2,602, 3,590 and
2,951 of 21,532). Under xdist each of a part's four workers collects for itself, so a part spends four
times that in CPU.

On a runner, a part's collection cannot be read from its log: pytest's output to a pipe is
block-buffered, and part 1's header, its `4 workers [2145 items]` line and its first 40% of results
carry timestamps within two seconds of each other, 62 s into the step. What the runners do show: the
partition proof's whole-selection test, which runs nine whole-selection collections side by side on
the job's 4 vCPUs, took 78.5 s on `d84cf21` and 121.6 s on `6db251b`, about 13.5 s of wall time a
collection; and the bot's pull-request parts of 2026-11-01, about 50 tests each, took 15 to 33 s of
pytest, most of it starting up and collecting the whole suite.

What follows for `v1-e41-t18`: collecting only a part's own files saves about 6 s of collection a
part on the Mac, more on a runner, and it shortens the partition proof, whose part collections become
an eighth of the suite each. It does not touch the slowest part's real cost, the remove smoke file's
function-scoped setups, which the session reports to the PM as a follow-up.

## What v1-e41-t18 changed

The costs page's option 1, as the deal now allows: each part collects only the test files the deal
gives it, and any file the deal does not name. `tests/pytest_plugins/run_in_parts.py`'s `collects`
is the rule. The paths a part's command names (an affected set's `@FILE`, or node ids) are trimmed
to its own when pytest is configured, in the controller and in every xdist worker; files pytest finds
walking `testpaths` (the whole selection) are skipped by `pytest_ignore_collect`, which pytest does
not ask about the paths a command names. `test-selection` still hands every part the one deal, so
the deal is each part's list of files.

* **A file the deal does not name** (a new file the record has not seen counts as the median and is
  named; a file heavier than a part's share is not, and a file pytest finds that the selection's
  list does not hold is not) is collected by every part and dealt test by test, as before.
* **No deal, or an empty one** (a record missing or stale) collects everything in every part, as
  before. A missing deal still fails no run.
* **The partition** holds for the same reason as before: `parts_dealt` puts every test in exactly
  one part, and the part it gives a test is always one that collects the test's file. The partition
  proof now also bounds what each part collects before it keeps its share, and checks at every size
  from one part to eight that each test is dealt to a part that collects its file.
* **Each part says how long it took to collect**, in a line of its summary (`part 1 of 8 collected in
  2.9 s, the last of 4 workers`), because a runner's log cannot show it.

### Before and after, on the operator's Mac

On 2026-11-05, load average 7 to 14 from other work, so both columns are high; they were run
alternately, part by part. The deal is the one `test-selection` makes for the whole selection from
the seven part records `6db251b`'s push run kept (part 5's was lost with its failure, so its files
count as the median): 697 files, 696 dealt whole, the remove smoke file spread. Each part was run as
CI runs it, `-n 4` and the parts' markers, with `-k` matching no test, so the time is starting up and
collecting:

| Part | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Before: whole selection collected, wall (s) | 15.0, 19.3 | 15.8 | 14.5 | 14.1 | 12.9 | 12.5 | 12.6 | 12.5 |
| After: own files collected, wall (s) | 10.8, 10.1 | 5.0 | 5.1 | 4.4 | 3.9 | 4.9 | 4.0 | 7.2 |
| After: the part's own line, "collected in" (s) | 8.8, 7.5 | 2.9 | 3.2 | 2.3 | 2.3 | 3.1 | 2.4 | 5.1 |

Part 1 was measured twice. It holds 84 files, among them the slowest to collect on their own
(`tests/scripts/test_task_restart.py` 2.8 s, against about 1 s for pytest starting up), so its
collection is the longest of the eight; no one file sets it.

The partition proof, run as its job runs it (`pytest -n auto -m "partition_proof and not slow and
not live" tests/scripts/test_ci_workflow_test_job.py`), before and after: the whole-selection proof
25.0 s and 14.7 s, the affected-set proof 5.0 s and 3.8 s. Its eight part collections are now about
an eighth of the suite each.

### What it does not change

The slowest part, 298 s on the dispatch against 179 to 229 s for the others, is the part that held
`tests/smoke/test_caselist_remove_smoke.py` whole, whose function-scoped setups are rebuilt for every
test. Collecting less takes a few seconds off every part, that one included. The slowest part's
pytest step on this task's pull request, a whole-selection run in eight parts dealt by dev's record
like the dispatch of `440f797`, is read after it runs, and on three task pull requests after the
merge (the task's ac2).

## The slow-tests job

Since `v1-e41-t29` a pull request into `dev` runs the slow tests its affected set reaches, in the
`slow-tests` job beside the parts ([working agreement 1](working-agreements.md#1-ci-stays-light)).
These figures sized it, and set its bound: the pytest step at most 120 seconds, and the job at most
60 seconds past the longest part.

**How often a pull request reaches each slow file.** Dev's last 11 commits that were not refreshes
(2026-11-12), each replayed over that day's import graph:

| Slow files | Reached by |
|---|---|
| `tests/scripts/test_affected_tests_planted_breaks.py` (left to validate-dev) | 11 of 11: every task pull request, through its own spec |
| the three `tests/integration` e2e files | 7–8 |
| the three environment-gated files (their slow tests left to validate-dev) | 7 |
| the two `packages/debate_api/tests/browser` files | 5 |
| `test_evidence_search_scale.py` | 2 |
| `test_structural_fixtures.py` | 1 |

**What they cost on the operator's Mac** (2026-11-12, load 5–13):

| Slow files | Tests | Time |
|---|---|---|
| the three e2e files, `-n 0` | 11 | 6.5 s |
| `test_evidence_search_scale.py`, `-n 0` | 1 | 52.0 s; one test, so it sets any run's critical path |
| `test_structural_fixtures.py`, `-n 0` | 1 | 2.2 s |
| the browser files, xdist auto | 30 | 21.4 s |
| all of the above at `-n 4 --dist worksteal`, a runner part's workers | 43 | 51.4 s |
| `scripts/ci_slow_tests.py` over the whole selection's 11 slow files, as the job runs it (2026-11-13, load 5) | 43 | 58 s wall, 43 passed, none skipped |

**validate-dev's slow job on a runner** (its last five runs, read by the operator with `gh` on
2026-11-13; 4 xdist workers, 60 tests each):

| Step | Seconds |
|---|---|
| Set up job, checkout, setup-uv, Python, `uv sync` (cached) | 8–14 |
| Playwright's Chromium with its system libraries | 21–32 |
| LibreOffice | 16–40 |
| QEMU and the Lambda image | 18–23 |
| pytest, the whole slow tier | 379–453 |

Its log gave no per-file times: the tier ran without `--durations`, and pytest's lines reach the log
through a pipe, timestamped when it is flushed. From this commit each tier prints its 25 slowest
tests. A runner's part runs at about a Mac's speed (about 0.09 s a test against 0.099 s at `-n 4`,
above), so the 43 tests the job runs take about 50–80 s there, and most of the runner's 379–453 s
are the planted-break cases.

**The estimate this gives** for the worst realistic pull request (a `debate_core` search change
reaching the browser files and the scale test): setup 8–14 s, Chromium 21–32 s, pytest 50–80 s, so
a job of about 1.5–2.5 minutes. Such a pull request's eight parts take 2–3 minutes each, so `ci`
takes 0–30 s longer. The usual reach, the e2e files alone, is a job of under a minute, under the
parts. Running the three environment-gated tests too would add 34–63 s of installs. Running the
planted-break cases would add most of 6–7 minutes, past the 5-minute budget. Both stay on
validate-dev (the PM's ruling, 2026-11-13).
