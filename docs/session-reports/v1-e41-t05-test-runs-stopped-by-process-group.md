# Session report: v1-e41-t05-test-runs-stopped-by-process-group

| | |
|---|---|
| Task | `v1-e41-t05-test-runs-stopped-by-process-group` — One hard stop for a session's test runs that kills the whole process group, named by agreement 10 |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t05-test-runs-stopped-by-process-group.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t05-test-runs-stopped-by-process-group.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t05-test-runs-stopped-by-process-group` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/hard_stop.py` is the one hard stop for a session's test runs:
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest ...`. It runs the command in
a new session, so the command leads its own process group. At the limit it sends TERM to the whole
group, waits a grace period (5 s, `--grace`), sends KILL to what is left, says on stderr that it
stopped the run at its N-second limit, and exits 124. A command that finishes in time passes its
exit code through, and its output too, which the script never touches. Working agreement 10 and
the session prompt (`task_helper.py`'s item 9) name it in place of the perl alarm. The PM may want
to look first at the probe under Decisions. With the alarm on the pytest controller, the xdist
workers exited on their own about 5 s later, but **the subprocesses their tests had started ran on
as orphans**. A group kill reaches those subprocesses and the alarm does not. The tests were run red
against a skeleton (13 failed), and four mutants were each caught. The affected set runs past two
minutes because of the planted-break harness, and the script itself stopped it at 115 s with nothing
left running, so under agreement 10 that run is the pull request's `ci`. The Goal is `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `test-runs-stopped-by-process-group` | Done | Script, 15 tests, agreement 10's bullet and the prompt's time-limit line |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: stops a command and every process it started (an xdist-like tree) within a few seconds of its limit | PASS | `test_hard_stop_kills_every_process_of_a_tree_that_ignores_term`: a leader, 2 children and 4 grandchildren, all ignoring SIGTERM, limit 2 s, grace 1 s. All 7 pids are gone, in under 7 s from the start. A real `pytest -n 2` run whose tests each start a subprocess: `test_hard_stop_reaches_xdist_workers_and_their_subprocesses_which_stay_in_the_run_s_group`, all 4 gone |
| ac1: exits non-zero saying so | PASS | Same test: exit `124`, stderr `hard_stop: stopped the run at its 2-second limit: sent TERM to process group …, then sent KILL after 1 s.` |
| ac1: passes a command that finishes in time through with its exit code | PASS | `test_hard_stop_passes_a_command_in_time_through[0]`/`[3]`: exact code, stdout and stderr; `…passes_output_through_while_the_command_runs`; `…killed_by_a_signal_as_a_shell_does` (137) |
| ac1: agreement 10 and the session prompt name it | PASS | `test_agreement_10_and_the_session_prompt_name_the_hard_stop_in_place_of_the_perl_alarm`: both hold `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest`, neither holds `perl -e` |
| ac1: by tests shown failing first | PASS | Red run against a skeleton that ran the command with no limit and returned 0: `13 failed, 2 passed in 64.83s`. Details under [Red run](#red-run) |
| Node: `uv run pytest tests/scripts -k hard_stop` | PASS | Run as written, under `.venv/bin/python scripts/hard_stop.py 115 …` → `15 passed in 15.24s`, nothing left running |

### Red run

`.venv/bin/python -m pytest tests/scripts -k hard_stop -n 4 -p no:randomly --tb=line`, against a
skeleton `hard_stop.py` that ran the command with `subprocess.call` and returned 0. It was bounded
by a scratch process-group wrapper, as the PM's context asked until this lands: `13 failed, 2
passed in 64.83s`, with nothing left running afterwards.

* Never stopped: the four tree tests and the xdist test (`hard_stop.py was still running after
  30.0 s`).
* Exit code not passed: `assert (0, …) == (3, …)`, and `assert 0 == 128 + SIGKILL`.
* Usage: `assert 0 == 2` three times (a limit of 0, -1 or `soon` was accepted), `assert 1 == 2` (no
  command), and `assert 1 == 127` (command not found).
* Docs: agreement 10 did not name the script.

The two that passed were the exit-0 pass-through and the live-output test. Any command runner
passes those, and the mutant below catches what they cannot.

A first red attempt hung past its 110 s bound. My test helper called `communicate()` again after
its own timeout, and orphaned grandchildren still held the pipes open. The helper now gives up on
the pipes. It also tells "the script never exited" apart from "the script exited, but processes it
should have stopped still hold its output open", so each mutant fails for its own reason.

### Mutants (agreement 8)

Each was applied to the working tree only and restored with `git checkout HEAD -- scripts/hard_stop.py`.
The whole file ran under a scratch copy of the committed script as the bound, so a mutant never
bounded its own run. After every run, `pgrep` found nothing left running.

| Mutant | Result | Failing tests (reason) |
|---|---|---|
| 1. Only the direct child is signalled (`os.kill` for `os.killpg`) | Caught, `4 failed` | The tree test (the script exited 124 but grandchildren held its output open 30 s later). The xdist test (`assert [5868, 5867] == []`: the two test subprocesses survived). The leftovers test, and the obeys-TERM test |
| 2. No KILL after TERM | Caught, `3 failed` | The tree test and the leftovers test (TERM-ignoring processes survive), and the escape test (its TERM-ignoring leader survives) |
| 3. Exit code not passed through (`0 if returncode == 0 else 1`) | Caught, `3 failed` | `…in_time_through[3]` (`assert (1, …) == (3, …)`), the signal test, the leftovers test (`5`) |
| 4. No new session (`start_new_session=False`), added by me | Caught, `5 failed` | `killpg` on a pid that leads no group finds nothing, so nothing is stopped |

Before the xdist test's tests started subprocesses, mutant 1 did not fail it. The workers exit on
their own after their controller dies, so a test of the workers alone could not tell the mutant from
the script. That gap is what led to the probe under Decisions, and it is closed.

### What this session ran before the report (working agreement 10)

| Run | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | `55 of 586 test files (9.4%) chosen in 11.9 s from 6 changed files`. Stopped at 115 s: `hard_stop: stopped the run at its 115-second limit: sent TERM to process group 6740, which ended.` Exit 124, at a load near 10, and no pytest or `affected_tests` process was left |
| The other 54 files, all but `test_affected_tests_planted_breaks.py` (whose docstring puts it at about two minutes alone), `-m "not slow and not live"`, under the same 115 s stop | Stopped at 97% with no failure shown, exit 124, nothing left running |
| `tests/scripts/test_hard_stop.py`, the readers of `task_helper.py` (`test_affected_tests.py`, `test_check_command_blocks.py`, `test_docs_index.py`, `test_task_restart.py`, `test_task_validate_dev_status.py`), `test_ci_workflow_site_changes.py` and `tests/docs` | `1027 passed in 27.71s` |
| Always-run list: `tests/architecture tests/specs` and the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | `369 passed in 20.26s` |
| `ruff format --check .` / `ruff check .` | `1642 files already formatted` / `All checks passed!` |
| `.venv/bin/pyright scripts/hard_stop.py tests/scripts/test_hard_stop.py` | `0 errors, 0 warnings, 0 informations` |
| `.venv/bin/pyright scripts/task_helper.py` | `2 errors`, both on dev already: the same two errors in dev's copy (lines 61 and 436 there). My edit is inside the `PROMPT` string. No package changed |
| `lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `scripts/check_command_blocks.py --base origin/dev` / `scripts/docs_index.py --check-descriptions` / `scripts/check_links.py` | `OK: no # comments in 592 shell code blocks in 199 Markdown files` / `All 59 indexed documents under docs/ have a description` / `OK: 3040 relative links and anchors in 471 Markdown files` |
| `uv run scripts/validate_specs.py`, after setting the Goal / `--require-succeeded v1-e41-t05-test-runs-stopped-by-process-group` | `OK: 524 files, 41 epics, 461 tasks, 22 releases` / `v1-e41-t05-test-runs-stopped-by-process-group: Succeeded` |

The affected set runs past two minutes, so under agreement 10 it is the pull request's `ci` check.
The planted-break harness is in it because `scripts/affected_tests.py` names this task's spec path.
The always-run list and the changed areas ran within the limit, above.

## Files changed

* `scripts/hard_stop.py` (new): the hard stop.
* `tests/scripts/test_hard_stop.py` (new): 15 tests: process trees, a real `pytest -n 2`, pass-through, usage, and the two documents.
* `docs/process/working-agreements.md`: agreement 10's time-limit bullet names the script in place of the perl alarm, keeping 115 s.
* `scripts/task_helper.py`: the session prompt's item 9 gets a time-limit line naming the script.
* The spec's phase and this report.

## Deviations from the spec

* **The session prompt had no time-limit line to replace.** The spec says to name the script "in
  the session prompt's time-limit line, in place of the perl alarm", but the prompt quoted no perl
  alarm and had no time-limit line. I added one to item 9, where the prompt already tells a session
  what to run while working. Agreement 10 was the only document outside session reports that quoted
  the perl form (`git grep alarm`). `task-workflow.md` and `CLAUDE.md` have no time-limit line.

## Decisions and assumptions

* **Python stdlib, not shell.** macOS has no `setsid` command. A shell script would need job-control
  tricks (`set -m`) to get a new group, and would differ between bash and zsh. Python's
  `subprocess.Popen(start_new_session=True)` calls setsid() on macOS and Linux alike, and
  `os.killpg` signals the group. The script uses only the standard library, so it runs under the
  worktree's `.venv/bin/python` (the documented form, which skips uv's sync) or any `python3`. No new
  dependency. Scripts here carry no shebang or exec bit, so it is run through an interpreter.
* **A new session, not just a new group.** With `setpgid` alone the run would be a background group
  on the operator's terminal, and a read from the terminal would stop it with SIGTTIN. A new session
  has no controlling terminal. Ctrl-C reaches only the script, which stops the group the same way:
  SIGINT, SIGTERM or SIGHUP to the script means TERM, grace, KILL, then exit 128 plus the signal's
  number.
* **Exit 124 at the limit**, as GNU `timeout` uses, distinct from pytest's 0 to 5. A child killed by a
  signal exits 128 plus its number, as a shell reports it. Not found is 127, not runnable 126, and
  usage is 2.
* **What a command that finishes in time leaves in its group is stopped too**, and the script says so.
  It keeps the command's exit code. The spec's forbidden entry is about "after the limit", but a
  worker left behind by a pytest that exited (or crashed) does the same harm.
* **The probe, and what it changes about the story.** I ran
  `perl -e 'alarm 6; exec @ARGV' .venv/bin/python -m pytest -n 2` over two tests that sleep 40 s,
  in a scratch project. The controller died (exit 142), and both workers were alive 1 s later, in
  the controller's process group. They exited on their own about 5 s after the controller (execnet
  noticing its controller had gone). When each test instead started a `sleep 45` subprocess, the
  workers again exited after about 5 s, but **both subprocesses were still running 20 s later**,
  orphaned, until I killed them. So the alarm's leak is the processes that tests start (commands,
  parse pools), and a group kill reaches them. Agreement 10's bullet and the script's docstring say
  this. I do not claim it is exactly what kept v1-e40-t22's run going for 30 minutes.
* **Does pytest-xdist create new groups? No.** The real `pytest -n 2` test asserts that each worker's
  parent is the controller, and that every worker and every test subprocess has the controller as
  its process group and session leader. A process that does call setsid() or setpgid() escapes the
  kill, with its children: `test_hard_stop_cannot_reach_a_child_that_started_its_own_session` pins
  that limit. It does not matter for pytest or xdist, only for a test that daemonizes something.
* **`uv run` too.** `hard_stop.py 3 uv run --frozen --offline --no-sync python -c 'sleep 30'`: the
  python was uv's child, in uv's group (pgid = uv's pid), and gone after the TERM. So the group kill
  also covers the old "stops uv, leaves pytest" case (v1-e39-t09). The agreement still puts the limit
  on `.venv/bin/python`, because that skips uv's sync.
* **Linux.** CI's `test` job runs on `ubuntu-24.04` with no container, where systemd reaps orphans,
  so a stopped group empties as it does on macOS. Linux's `kill(-pgid, 0)` still counts a zombie that
  has not been reaped. The script reaps its own child, and the tests treat a zombie as gone
  (`ps -o stat=`). Inside a container without an init, unreaped orphans would hold the group open, and
  the script would wait out the grace and say part of the group was still there. That case is not
  used here. The tests have run only on macOS. Their first Linux run is the pull request's `ci`.
* **Test timing.** Limits are 1 to 2 s and the grace is 1 s. No test waits near a real limit. The
  xdist test stops the script with SIGTERM once its workers have recorded themselves, rather than
  waiting for a limit, so it does not depend on how long xdist takes to start under load. The file
  takes about 9 s at `-n 4`.

## Operator follow-ups

None. Dev moved after this branch started (`af29b74`, v1-e01-t44, which changes
`scripts/affected_tests.py` and its tests). None of this task's files changed there, so
`scripts/task sync` before the pull request should apply cleanly.

## Follow-up work

* The two pyright errors in `scripts/task_helper.py` (lines 61 and 438 here) are on dev already.
  They belong to an E41 upkeep task if the PM wants `scripts/` clean under pyright.
* My memory notes, and some sessions' reports, still quote the perl form. Reports are records and
  stay as written.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

One hard stop now bounds a session's test runs. It kills the whole process group, and the probe
explains what the old alarm left behind.
1. **ac1 passes.**
   * A seven-process tree that ignores TERM is gone within the limit plus the grace.
   * A real `pytest -n 2` whose tests start subprocesses is gone whole, and the test asserts that
     every worker and subprocess shares the controller's group and session.
   * The exit code and the output pass through unchanged. Exit 124 at the limit, 128 plus the
     signal's number for a killed child, and 126, 127 and 2 as documented.
   * Red: 13 failed against a skeleton.
   * Four mutants were caught. Mutant 1 needed the xdist test's tests to start subprocesses before
     it could be told apart, and you found that rather than letting it pass.
2. **The probe is the key finding.** The alarm kills the pytest controller, and xdist's workers exit
   about 5 s later, but the processes their tests started run on as orphans. A group kill reaches
   them. That is the right story for agreement 10 to tell, without claiming it was the whole of
   v1-e40-t22's 30 minutes.
3. **The deviation is accepted.** The prompt had no time-limit line, so adding one to item 9 is
   right.
4. **Decisions accepted:**
   * Python stdlib for `start_new_session` on both platforms;
   * a session, not only a group, so a terminal read cannot stop the run;
   * Ctrl-C handled the same way;
   * leftovers stopped after a command that finishes in time;
   * the self-daemonizing escape pinned as a known limit;
   * `uv run` covered.
5. **Follow-up, the two pyright errors in `task_helper.py`:** the PM folds them into v1-e41-t07,
   which edits that file's `ready` and `prereqs`.
6. **Closing checks:** the affected set is over two minutes because of the planted-break harness. The
   script itself stopped that run at 115 s with nothing left, which is its own small proof. It is
   left to the PR's `ci`, which is also the tests' first run on Linux. The always-run list, the
   changed areas and the whole-repo checks pass.
7. **Merge:** once the PR's `ci` is green on Linux. It is a plain `scripts/task pr`. Dev moved by
   v1-e01-t44, which touches none of this task's files, so the PR merges without a sync. From then on every session prompt names
   `scripts/hard_stop.py`.
