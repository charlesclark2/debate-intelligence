# Session report: v1-e39-t21-one-call-recorder-for-deploy-tests

| | |
|---|---|
| Task | `v1-e39-t21-one-call-recorder-for-deploy-tests` — The tub deploy test records each stub call alone, as the caselist run's does |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t21-one-call-recorder-for-deploy-tests.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t21-one-call-recorder-for-deploy-tests.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t21-one-call-recorder-for-deploy-tests` |
| Session status | COMPLETE |

## Summary

**One shared recorder, `tests/scripts/stub_calls.py`, is now used by both deploy tests.** It is
v1-e40-t14's one-file-per-call recorder, moved out of `test_caselist_run_deploy.py` unchanged:
`STUB_PREAMBLE`, `write_stub`, `clear_calls` and `read_calls`. Both test files import it as
`tests.scripts.stub_calls`, the way `tests/smoke/installed_build.py` is already imported. I checked
three things before relying on it. It imports under `--import-mode=importlib` with
`python -m pytest`, with the `pytest` console script under xdist, and from another working directory.
And `affected_tests.py` follows the edge: a commit changing only a probe helper selected the probe
test as `imports tests/scripts/probe_helper_zz.py, which changed`.

**`test_tub_deploy.py` records each call alone and has a new test of the pipeline's two calls**
(`tub_deploy.sh:273`, `aws_pilot ecr get-login-password | docker login ...`). The test checks four
things:
* the `aws` call is recorded whole, with its region;
* `docker login` is given `--password-stdin`;
* what `docker login` actually read on stdin is the password (the docker stub now keeps it);
* no call's argument contains the password.

**Look first at:** the evidence table under ac1. The fixed pipeline test passed **150 of 150**
under `-n 6` at load averages 16 to 23. With the old shared log restored (the mutant), it failed
**8 of 100**, and then **5 of 60** in a run whose logs I kept. Those 60 logs hold exactly 5
interleaved records, one per failure. `tub_deploy.sh` is unchanged. Nothing retries, and no assertion
was loosened.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `one-call-recorder-for-deploy-tests` (Tub deploy recorder) | Done | Shared helper; caselist test moved onto it (`07664a3`); tub test moved onto it, with the pipeline test (`91defd0`); mutant caught under load |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the tub deploy test records each call alone, the pipeline's two calls are asserted, it passes 50 times under `-n 6` with the machine loaded, and the old recorder restored fails under load | PASS | Each call alone: `write_stub` from `tests/scripts/stub_calls.py` in every tub stub; `STUB_CALL_LOG` is gone. Pipeline asserted: `test_docker_signs_in_with_the_registry_password_on_stdin_never_as_an_argument`. 50 runs: `REPEAT_TEST_TIMES=50 ... pytest -p repeat_one_test -n 6 <the pipeline test>` → **50 passed in 41.63s**, load averages 16.46 before and 23.34 after. The mutant: **8 failed, 92 passed** of 100, then **5 failed, 55 passed** of 60. All the runs are under [The recorder under load](#the-recorder-under-load). |
| Node `one-call-recorder-for-deploy-tests`: Tub deploy recorder tests pass (`uv run pytest tests/scripts -k tub_deploy`) | PASS | **24 passed in 26.50s** (23 before this task, plus the pipeline test), at load average 26. |

## The recorder under load

All batches used v1-e40-t14's scratch plugin, `repeat_one_test.py`, copied verbatim from that report.
It parametrizes the selected tests N times (`REPEAT_TEST_TIMES=N`), because pytest runs a repeated
node id only once. It is not committed. Its full path was
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e39-t21-one-call-recorder-for-deploy-tests/0bda3d8e-7719-4a41-888b-62bc50291478/scratchpad/repeat_one_test.py`.

The machine sat at load averages 7 to 9 from other sessions (11 cores). As in v1-e40-t14, I added
six CPU-bound processes that stop themselves after ten minutes (`perl -e 'alarm 600; 1 while 1'`).
I stopped them when the batches finished and checked that none was left. Each batch put the time
limit on the interpreter:

```bash
REPEAT_TEST_TIMES=50 PYTHONPATH=<scratchpad> perl -e 'alarm 110; exec @ARGV' .venv/bin/python -m pytest -p repeat_one_test -n 6 -q --tb=short tests/scripts/test_tub_deploy.py::test_docker_signs_in_with_the_registry_password_on_stdin_never_as_an_argument
```

| Code | Tests, times each | Load averages (before → after) | Result |
|---|---|---|---|
| Fix (`91defd0`) | tub pipeline test ×50 (the ac1 run) | 16.46 → 23.34 | **50 passed** in 41.63s |
| Fix | tub order test (`test_a_deploy_waits_for_the_update_then_checks_healthz_through_cloudfront`) ×50 | 21.68 → 20.38 | **50 passed** in 42.69s |
| Fix | tub pipeline test ×100 | 19.47 → 17.22 | **100 passed** in 73.89s |
| Mutant: the shared append log restored in `test_tub_deploy.py` | tub pipeline test ×100 | 17.34 → 20.54 | **8 failed, 92 passed** in 78.49s, all at line 441 (`assert [] == [['--region', ...]]`) |
| Mutant, logs kept (`--basetemp` in the scratchpad) | tub pipeline test ×60 | 23.60 → 22.48 | **5 failed, 55 passed** in 50.19s, all at line 441 |
| Fix, on the shared helper | caselist region test (`test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1`) ×50 and caselist pipeline test ×50 | 39.74 → 37.13 | **100 passed** in 44.79s |
| Fix | the whole tub file (24 tests) ×4 | 34.88 → 27.90 | **96 passed** in 32.32s |

In total the fixed tub pipeline test passed 150 of 150. The order test passed 50 of 50, and 4 more in
the whole-file batch, so v1-e40-t14's call-order guarantee holds on the shared helper. The caselist
test's 50-run check passed on the helper too, for both its region test and its pipeline test.

**The mutant** (working agreement 8; no Hypothesis is involved, so there is no database to empty)
put the old recorder back into the committed `test_tub_deploy.py`. Its preamble is byte for byte
the original, except that it appends to `${STUB_CALL_DIR}` where the original appended to
`${STUB_CALL_LOG}`. It is defined in the test file in place of the helper's import, as a local
`write_stub`, `clear_calls` and `read_calls`, and reads the log back a line at a time. The new
pipeline test and everything else stayed as committed. After the runs I restored the file with
`git checkout HEAD -- tests/scripts/test_tub_deploy.py`, and `git status --porcelain` printed
nothing.

**What the mutant's logs show.** Pytest keeps only its three newest temp directories, and other
sessions' runs had cleared the first mutant batch's. So I ran the second batch with `--basetemp` in
the scratchpad. Of its 60 logs (not counting each worker's `_current` symlink), 55 had both records
whole and 5 had them interleaved, one log per failure. These were the 5 (⇥ marks a tab):

* `dockeraws ⇥ login ⇥ --region ⇥ --username ⇥ us-east-1 ⇥ ...`, twice: the `aws` call is lost inside a `docker` record;
* `dockeraws ⇥ login ⇥ --username ⇥ --region ⇥ ...`, once;
* `aws ⇥ --regiondocker ⇥ us-east-1 ⇥ ecr ⇥ get-login-password ⇥ login`, once: v1-e40-t14's region-test failure, here in the tub script;
* `aws ⇥ --region ⇥ us-east-1 ⇥ ecrdocker ⇥ get-login-password`, once, with the docker record's remaining words left on a line of their own.

All five fail the new test at its first `aws` assertion. Without that test, none of them fails
anything in the tub file today, which is what the spec said.

## Checks before the report

* Affected set: `uv run scripts/affected_tests.py --run` → `Affected set: 48 test files, pytest
  exited 0 after 133 s.` (**2,126 passed in 129.44s**). It took 2 min 33 s of wall-clock with uv's
  start and the selection, at load averages 16 rising to 62 from other sessions' runs. It reached the
  two-minute line at 94% with no failure, so I let it finish rather than discard it. The selection is
  mostly the spec and this report changing; the two changed test files are in it, and
  `test_validate_dev_workflow.py` (which names `scripts/tub_deploy.sh`). I did not touch it or any
  other workflow test.
* `.venv/bin/ruff format --check .` → `1615 files already formatted`. `.venv/bin/ruff check .` → `All checks passed!`
* `.venv/bin/pyright tests/scripts/stub_calls.py tests/scripts/test_tub_deploy.py tests/scripts/test_caselist_run_deploy.py` → `0 errors, 0 warnings, 0 informations`. No package under `packages/` changed.
* `.venv/bin/lint-imports` → `Contracts: 19 kept, 0 broken.`
* `uv run scripts/validate_specs.py` (after setting the Goal to `Succeeded`) → `OK: 509 files, 40 epics, 447 tasks, 22 releases`
* `.venv/bin/python scripts/check_command_blocks.py --base origin/dev` → `OK: no` comment `in 588
  shell code blocks in 199 Markdown files`, this report included. `.venv/bin/python
  scripts/docs_index.py --check-descriptions` → `All 59 indexed documents under docs/ have a
  description`. With this report written, `tests/docs` and `test_check_command_blocks.py` →
  `229 passed in 7.37s`.
* The task spec on `origin/dev` differs from this branch only in its status line. `origin/dev` has
  moved on by two commits (v1-e30-t30's merge and an index refresh), which touch none of this
  branch's files. I did not sync.

## Files changed

* **`tests/scripts/stub_calls.py` (new):** the one-file-per-call recorder from
  `test_caselist_run_deploy.py`, unchanged, with a docstring on why one shared log is not enough.
* **`tests/scripts/test_caselist_run_deploy.py`:** imports the recorder instead of defining it
  (`07664a3`, alone in its commit). Nothing it records or asserts changed: 23 passed before and after.
* **`tests/scripts/test_tub_deploy.py`:**
  * every stub is written with the shared `write_stub`; `World.call_log` became `World.call_dir`,
    `STUB_CALL_LOG` became `STUB_CALL_DIR`, and `deploy` reads the calls back with `read_calls`;
  * the docker stub's `login` keeps what it reads on stdin in `.stub-state/docker-login-stdin`,
    still reading it all, so the SIGPIPE comment above it still holds. `World.docker_login_stdin`
    reads it, and `write_state` clears it before each run;
  * the new `test_docker_signs_in_with_the_registry_password_on_stdin_never_as_an_argument`;
  * the module docstring: what the stubs do, and the new assertion in the list of what is worth
    asserting.
* **The spec:** Goal phase `Succeeded`.
* **This report.**

`scripts/tub_deploy.sh` and `scripts/caselist_run_deploy.sh` are unchanged.

## Deviations from the spec

None.

## Decisions and assumptions

* **A shared helper module, not a conftest fixture.** A `tests/scripts/conftest.py` would sit
  above every test in `tests/scripts`, about 1,800 tests, so any change to the recorder would select
  all of them. A module selects only its importers. v1-e39-t20 found helper modules beside
  `packages/debate_api/tests` not importable under `--import-mode=importlib`. Under `tests/` they
  are, as `tests.<dir>.<module>`, which `tests/smoke` and `tests/evals/parser` already rely on. I
  probed that before building on it (Summary).
* **The pipeline test checks what `docker login` read, not only its flags.** `--password-stdin` in
  argv says the script asked Docker to read stdin. The recorded stdin says the password arrived
  there through the pipe. The tub stub already read stdin (to avoid SIGPIPE), so keeping it costs
  one redirect. The caselist test's pipeline test is left as v1-e40-t14 wrote it.
* **The password check is a substring check.** The tub test asks whether any argument *contains*
  the password; the caselist test asks whether any argument *is* it. The substring form also catches
  `--password=<password>`. I did not change the caselist test's assertion, because moving it onto
  the helper was meant to change nothing there.
* **`profiles.log` keeps its append.** Only the `aws` stub writes it, one `echo` per call, and the
  script never runs two `aws` calls at once. So it cannot interleave today.
* **`test_site_deploy.py` keeps its own append recorder.** The PM ruled it needs no task (v1-e40-t14
  review, note 6): `site_deploy.sh` has no pipeline between two stubbed tools.

## Operator follow-ups

None.

## Follow-up work

* If `scripts/site_deploy.sh` ever gains a pipeline between two stubbed tools,
  `tests/scripts/test_site_deploy.py` can move onto `tests/scripts/stub_calls.py` with the same
  edits as the tub test (E39, or whichever epic owns the website deploy).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
