# Session report: v1-e40-t14-deploy-script-region-test-under-load

| | |
|---|---|
| Task | `v1-e40-t14-deploy-script-region-test-under-load` — The deploy script's region test, which failed once under load, made deterministic |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t14-deploy-script-region-test-under-load.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t14-deploy-script-region-test-under-load.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t14-deploy-script-region-test-under-load` |
| Session status | COMPLETE |

## Summary

**The cause was in the test's recorder, not the script.** The deploy script runs one pipeline,
`aws_run ecr get-login-password | docker login --username AWS --password-stdin ...`
(`scripts/caselist_run_deploy.sh:307`). That puts the `aws` stub and the `docker` stub in two
processes at once. Each stub appended its argv to one shared `calls.log`, one `printf` per word,
so each word was a separate `write()`. When the two processes overlapped, their words
interleaved. In a failing run the log read:

```text
aws	--regiondocker	us-east-1	ecr	get-login-password
	login	--username	AWS	--password-stdin	111122223333.dkr.ecr.us-east-1.amazonaws.com
```

That line is an `aws` call whose first two words are not `--region us-east-1`, which is exactly
the line `test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1` failed on. I reproduced
it under load, both outside pytest and in pytest under `-n 6`.

**The fix:** each stub call is now recorded in a file of its own. It claims the next free call
number with `mkdir`, which creates the number's directory or fails because another call has it,
then writes its argv there. Nothing appends to a shared file any more. Call order is kept: a call
made after another has finished always gets a higher number. The script is unchanged, the region
assertion is unchanged, and nothing retries.

**Look first at:**
* the evidence table under ac1. The unfixed test failed about 2 in 100 under load, so the
  criterion's 50 passes alone would be weak evidence (0.98^50 ≈ 36% chance without a fix). The
  fixed test passed 300 times under `-n 6` at load averages 21 to 35;
* the one new test, of the pipeline's two calls. The old log hid a second symptom of the same race:
  most interleavings merged the two records into one `dockeraws ...` line, which silently dropped the
  `get-login-password` call from `calls_to("aws")`. The region test then passed vacuously for that
  call.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `deploy-region-test` (Deploy region test) | Done | Cause found and reproduced; recorder fixed in `tests/scripts/test_caselist_run_deploy.py`; mutant caught under load |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the cause is named with its evidence, the fix holds it, and the test passes 50 times under `-n 6` with the machine loaded | PASS | Cause and evidence: [Finding the cause](#finding-the-cause). 50 runs: `REPEAT_TEST_TIMES=50 ... pytest -p repeat_one_test -n 6 <the region test>` → **50 passed in 30.58s**, load averages 25.43 before and 26.56 after. Further batches and the mutant are in [The fix under load](#the-fix-under-load). |
| Node `deploy-region-test`: Deploy script tests pass (`uv run pytest tests/scripts/test_caselist_run_deploy.py`) | PASS | **23 passed in 7.33s** (22 before this task, plus the new pipeline test). |

## Finding the cause

**What I ruled out, from the code:**

* **`AWS_REGION` or `AWS_DEFAULT_REGION` leaking from another test or the shell.** `World.deploy`
  passes the script a complete environment of four names (`PATH`, `HOME`, `TMPDIR` and the
  recorder's), not a copy of the parent's. The stubs inherit only that. Also, the stub records argv,
  and the script passes `--region us-east-1` as a literal argument (`AWS_REGION_FOR_RUN`), so no
  environment variable could change what is recorded.
* **A recording shared between xdist workers, or a temp path collision.** The log was
  `tmp_path / "calls.log"`, which pytest makes unique per test and per worker (`popen-gwN/<test>N`).
  The script's staging directory is `mktemp -d` inside that test's own `tmp_path`.
* **A call that only sometimes runs.** Every `aws` call on the dev path runs on every run.
  `describe-images` swallows its error with `|| true`, but it still runs and is still recorded with
  `--region`.
* **A timeout.** A 60-second subprocess timeout would raise `TimeoutExpired`, not fail the region
  assertion, and `returncode == 0` is asserted on the line before it.

**What fits, and how it was reproduced:**

1. **Outside pytest.** A scratch script built the test's own `World` and ran the dev deploy 60 times,
   6 at a time, at load average about 4.5. **3 of 60** runs recorded the
   `aws --regiondocker us-east-1 ecr get-login-password` line above. Every malformed `aws` record was
   the pipeline's.
2. **In pytest, unchanged code.** A scratch plugin (below) ran the region test 100 times under `-n 6`
   at load averages 6 to 8: **2 failed, 98 passed in 42.05s**, both at line 504, the region
   assertion. A second batch with `-x` failed after 34 runs (**1 failed, 33 passed in 15.97s**).
3. **The failing run's log.** Pytest keeps recent `tmp_path` directories, so I read every
   `calls.log` that batch left behind. **36 of 40** had the pipeline's two records interleaved. Most
   interleaved as `dockeraws\tlogin\t--region\t--username...`, which loses the `aws` call without
   failing anything. **2 of 40** had `aws\t--regiondocker`, the form that fails the region assertion.
   That is why the test failed rarely while the race happened on most runs.

**Why load matters:** both stubs start within microseconds of each other, and each writes its
record in about a dozen small writes. With idle cores, the two bursts usually overlap only at the
first word (`dockeraws`), which the region test cannot see. Under load, a stub can be descheduled
between its writes, so the other stub's words can land after `--region`, and only then does the
assertion fail.

**Why the script is not the thing to change:** the pipeline is right. It keeps the registry password
off the command line and off disk. The defect is that the test's recorder could not record two
concurrent calls.

## The fix under load

All batches were run with a scratch plugin, `repeat_one_test.py`, that parametrizes the selected
test N times (`REPEAT_TEST_TIMES=N`), because pytest runs a repeated node id only once. It is not
committed. Its full path was
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e40-t14-deploy-script-region-test-under-load/e78093a7-0f1d-4e09-932f-1f2f0f97b5a9/scratchpad/repeat_one_test.py`,
and it reads, in full:

```python
import os

import pytest


@pytest.fixture
def repetition(request):
    return request.param


def pytest_generate_tests(metafunc):
    times = int(os.environ.get("REPEAT_TEST_TIMES", "1"))
    if times > 1:
        metafunc.fixturenames.append("repetition")
        metafunc.parametrize("repetition", range(times), indirect=True)
```

The machine already sat at load averages 4 to 8 from other sessions. For the runs below I added six
CPU-bound processes that stopped themselves after ten minutes (`perl -e 'alarm 600; 1 while 1'`),
and I stopped them when the runs finished. That took the load to 21 to 35, above the 11.8 of
v1-e32-t22's failure. Each batch ran with `PYTHONPATH` set to the plugin's directory, and the time
limit on the interpreter:

```bash
REPEAT_TEST_TIMES=50 PYTHONPATH=<scratchpad> perl -e 'alarm 110; exec @ARGV' .venv/bin/python -m pytest -p repeat_one_test -n 6 --tb=short tests/scripts/test_caselist_run_deploy.py::test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1
```

| Code | Tests, times each | Load averages (before → after) | Result |
|---|---|---|---|
| Unchanged | region test ×100 | 7.96 → 6.32 | **2 failed, 98 passed** in 42.05s |
| Fix (`459d633`) | region test ×50 (the ac1 run) | 25.43 → 26.56 | **50 passed** in 30.58s |
| Fix | region test ×100 and pipeline test ×100 | 25.12 → 34.23 | **200 passed** in 88.86s |
| Fix | region test ×150 | 25.97 → 21.52 | **150 passed** in 66.31s |
| Mutant: the shared append log restored | region test ×100 and pipeline test ×100 | 35.61 → 29.42 | **15 failed, 185 passed** in 83.71s: region test 2, pipeline test 13 |

In total the fixed region test passed 300 of 300 under `-n 6` and load, and the pipeline test 100 of
100. At the unfixed rate of about 2 in 100, 300 passes in a row would happen by chance about 0.2% of
the time (0.98^300).

**The mutant** (working agreement 8; no Hypothesis is involved, so there is no database to empty)
put the old recorder back in the committed test file: one shared log next to the call directory,
appended with `>>` a `printf` per word, read back line by line. The rest of the fix, the new test
included, stayed in place. Both tests caught it under load. The file was then restored with
`git checkout HEAD -- tests/scripts/test_caselist_run_deploy.py`, and `git status --porcelain`
printed nothing.

## Checks before the report

* Affected set: `uv run scripts/affected_tests.py --run` chose **51 of 570 test files** from 3
  changed files. It ran at load averages 28 to 31, alongside another session's affected run, and
  reached 52% after about two minutes with no failure or error. At that point it was clearly going
  past the two-minute line, so I stopped it: the xdist workers first, then pytest and the
  `affected_tests.py` parent, and checked that none was left. Under agreement 10 that set is left to
  the pull request's `ci` check. Within the two minutes I ran instead:
  * the always-run list, `.venv/bin/python -m pytest -q -n 6 -m "not slow and not live"
    tests/architecture tests/specs packages/debate_cli/tests/test_app.py
    packages/debate_cli/tests/test_help_rendering.py
    packages/debate_cli/tests/test_container_factories.py` → **366 passed in 17.51s**;
  * the changed test directory, `.venv/bin/python -m pytest -q -n 6 -m "not slow and not live"
    tests/scripts` → **1,823 passed in 84.65s**, at load averages 21 to 24.
* `uv run --frozen ruff format --check .` → 1,597 files already formatted. `uv run --frozen ruff
  check .` → all checks passed.
* `uv run --frozen pyright tests/scripts/test_caselist_run_deploy.py` → 0 errors, 0 warnings. No
  package under `packages/` changed.
* `uv run --frozen lint-imports` → 18 kept, 0 broken.
* `uv run scripts/validate_specs.py` (after setting the Goal to `Succeeded`) → OK: 493 files, 40
  epics, 431 tasks, 22 releases.
* `uv run scripts/check_command_blocks.py --base origin/dev` → OK, no `#` comments in 577 shell
  code blocks, this report included. `uv run scripts/docs_index.py --check-descriptions` → all 58
  indexed documents have a description.
* The task spec has no change on the local `origin/dev` ref except this branch's status line.
  `origin/dev` has moved on by v1-e39-t15's merge, which touches none of this branch's three files.
  I did not sync.

## Files changed

* **`tests/scripts/test_caselist_run_deploy.py`:**
  * the stub recorder: one file per call under `tmp_path / "calls"`, at the next call number free,
    claimed with `mkdir`. `World.call_log` became `World.call_dir`, and `STUB_CALL_LOG` became
    `STUB_CALL_DIR`. The comment above `STUB_PREAMBLE` says why;
  * `World.deploy` reads the calls back in call-number order and splits each on tabs. A multi-line
    argument, such as the image check's `sh -c` scripts, now stays inside its call; before, each of
    its lines became a bogus call. No assertion read those lines;
  * the new `test_docker_signs_in_with_the_registry_password_on_stdin_never_as_an_argument`: the
    pipeline's `aws` call is recorded whole with its region, `docker login` reads the password from
    stdin, and the password is never an argument of any call;
  * the module docstring's line on what the stubs do.
* **The spec:** Goal phase `Succeeded`.
* **This report.**

`scripts/caselist_run_deploy.sh` is unchanged.

## Deviations from the spec

None.

## Decisions and assumptions

* **The fix is in the test, not the script.** The spec allows either. The script's pipeline is the
  safe way to hand Docker the password, and v1.1.0-dev.164 was deployed with it on 2026-10-29.
* **`mkdir` to claim a call number, not a lock or a single write.** A single `printf` per record
  would still rely on how bash buffers stdout: it flushes at each newline, and some arguments
  contain newlines. A lock needs a wait loop and can be left stale. `mkdir` either creates the
  directory or fails, so two calls never get one number and no call ever waits on another. Each stub
  starts counting from the number of calls already recorded, so it usually takes one `mkdir`.
* **Order is kept** because `tests/scripts/test_tub_deploy.py`'s sibling recorder has a test that
  reads call order, and a future test here may too. The two calls of the pipeline get distinct
  numbers in either order, which is the truth: they run at the same time.
* **The new pipeline test** is the check this fix needed. Without it, the race's commoner symptom
  (the dropped `aws` call) fails nothing, and the mutant would be caught only about 2 times in 100.
  It strengthens the file's coverage and loosens nothing.

## Operator follow-ups

None.

## Follow-up work

* **`tests/scripts/test_tub_deploy.py` has the same recorder** (`STUB_PREAMBLE`, an append per word
  to one `STUB_CALL_LOG`), and `scripts/tub_deploy.sh:273` has the same pipeline,
  `aws_pilot ecr get-login-password | docker login ...`. No tub assertion reads those two calls
  today, so nothing there can fail from it yet. Its records interleave all the same, and the first
  test that asserts on either call will be flaky under load, as this one was. It is outside this
  task's spec, so I left it. It belongs with the tub deploy script's owner. The same recorder change
  applies; its order test (`test_a_deploy_waits_for_the_update_then_checks_healthz_through_cloudfront`)
  keeps working because call order is kept. The PM might also consider one shared recorder for
  `tests/scripts`.
* `tests/scripts/test_site_deploy.py` uses the same append recorder. `scripts/site_deploy.sh` has no
  pipeline between two stubbed tools (its one pipeline feeds `python3`, which is not stubbed), so it
  cannot race today.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
