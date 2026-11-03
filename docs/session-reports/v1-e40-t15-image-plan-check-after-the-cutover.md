# Session report: v1-e40-t15-image-plan-check-after-the-cutover

| | |
|---|---|
| Task | `v1-e40-t15-image-plan-check-after-the-cutover` — A plan check for a new run image after the cutover, with the schedule left enabled |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t15-image-plan-check-after-the-cutover.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t15-image-plan-check-after-the-cutover.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t15-image-plan-check-after-the-cutover` |
| Session status | COMPLETE |

## Summary

A new run image's plan is now checked from `terraform show -json`, never from the plan's text. The
check is `ops/caselist_run/check_image_plan.py`, run as `python3 -I` with the plan's JSON and
`owner.auto.tfvars`, like the other `ops/caselist_run` scripts. It prints `PLAN OK` only for the
post-cutover shape: the login and run task definitions replaced, the two schedules and their
scheduler roles' policies repointed, and both schedules `ENABLED` before and after. Anything else
prints `PLAN STOP`, naming each address and its actions.

It sorts every change into exactly one of four buckets: an Identity Center change anywhere, a change
outside `module.caselist_run`, one of the six expected changes, or an unexpected change in the module.
Each rule is therefore the only one that can catch its own case. Within the six it reuses the cutover
runbook's IMAGEPLAN rules unchanged, since that check printed `PLAN OK` on the real cutover plan on
2026-10-26. The only change to those rules is the schedule state: `ENABLED` throughout, where
IMAGEPLAN expected `DISABLED`.

On the two shapes from 2026-10-29: 40 refreshed, unchanged Identity Center entries give `PLAN OK`.
The real plan's shape, the expected six plus the `task_stopped["run"]` update, gives `PLAN STOP`
naming that address.

The runbook's "A new image, later" now runs plan, `show -json` and the check in place of the `grep`
counts. A `PLAN STOP` still goes to the PM before any apply, and the apply still refuses a Wednesday.

**What to look at first:** two of the eight mutants aimed at your five items (1b and 2b in the
mutants table below) still print `PLAN STOP` and are caught only because the stop line stops naming
the right reason.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `image-plan-check` (Image plan check) | Done | Red at `6a551dc` (40 of 40 failed), check at `3596f80`, Identity Center by type at `abd42ab`, runbook at `f105642` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `PLAN OK` for the expected shape and `PLAN STOP` for each wrong one, on synthetic plans, shown failing first; the runbook's block uses it | PASS | Red: `uv run pytest tests/scripts/test_caselist_run_image_plan_check.py -p no:randomly -n 0 --tb=line` against a skeleton printing `PLAN OK` whatever it reads → **40 failed, 0 passed** (see "The red run"). Green: the same command → **41 passed** (40 plus the entry-without-a-type case added at `abd42ab`). The runbook block runs `check_image_plan.py` on the plan's `show -json` output; `test_the_runbook_checks_the_json_of_the_plan_it_saved_and_counts_nothing_in_its_text` pins that, and fails on the old block (red run) |
| Node `image-plan-check`: Ops tests pass (`uv run pytest tests/scripts -k caselist_run`) | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts -k caselist_run -q` → **63 passed in 33.04s** |

### The red run

At `6a551dc` the script was a skeleton with the real arguments that printed `PLAN OK` and exited 0
for any input. The tests ran against it, grouped by their failure line:

* **37 × `AssertionError: PLAN OK`**:
  * the 28 parametrized stop cases, the Identity Center "never apply" case, the owner file without a
    digest, and the three unreadable files, each of which wanted `PLAN STOP`;
  * the plan of 2026-10-29, which wanted `PLAN STOP` naming `task_stopped["run"]`;
  * the three `PLAN OK` cases. These fail on their wording alone, because the skeleton already said
    `PLAN OK`. Mutants 5 and 5b prove their behaviour.
* **1 × the one-line test**, which needs three named problems.
* **2 × the runbook tests**, on the by-eye block still in place (no `rm -f`, no `show -json`, no
  "`PLAN STOP` goes to the PM"). The apply-block test's Wednesday and `after the PM's word`
  assertions already held on the old runbook. Only its new sentence was red.

Nothing passed. There was no collection error: the tests run the script as a process.

### Mutants

Each mutant was a single string replacement on the committed script. After each one, the test file
ran alone (`-k "not runbook"`, `-n 0 -p no:randomly`), and `git checkout HEAD --` restored the
script. The tests use no Hypothesis, so agreement 8's database does not apply. 15 mutants, 15 caught.
The "verdict" column says whether the mutant turns a `PLAN STOP` into `PLAN OK` (caught on the
verdict) or keeps `PLAN STOP` but names a different reason (caught on the reason). For 1b, 2 and 2b
this was measured by printing the check's line under the mutant.

| Mutant | Caught by | Verdict |
|---|---|---|
| 1 Identity Center changes not checked (the rule's `if` off; the entries still sorted out of the other buckets) | 4 tests: the three Identity Center stop cases and "never apply" | flips to `PLAN OK` |
| 1b Identity Center never recognised (`identity_center()` returns False, so the entries fall into the other buckets) | the same 4 | stays `PLAN STOP` as "a change outside module.caselist_run …"; caught on the reason |
| 2 a schedule state change allowed (state rule off) | 5 tests | flips to `PLAN OK` only for a schedule `DISABLED` throughout; a state *change* is also stopped by the field rule ("changes ['state', 'target'], expected only target"), so those cases are caught on the reason |
| 2b the state rule reads only the after side | the login schedule turned on | stays `PLAN STOP` through the field rule; caught on the reason |
| 3 a change outside the module allowed | 3 tests | flips |
| 4 an in-place task definition update accepted as a replace | a task definition updated in place | flips |
| 5 no-op entries counted as changes | 9 tests, among them the refreshed-Identity-Center plan (the false 40) | flips the `PLAN OK` cases to `PLAN STOP` |
| 5b read entries counted as changes | 5 tests | the same |
| an unexpected in-module change allowed | 6 tests, among them the plan of 2026-10-29 | flips |
| a missing expected change allowed | 3 tests | flips |
| a deposed object keyed by its address alone | an old revision left deposed | caught on the reason |
| replace only in delete-then-create order | the create-before-destroy case | flips `PLAN OK` to `PLAN STOP` |
| the owner file's digest not compared | another image | flips |
| a schedule's target beyond the revision not compared | the schedule starting two tasks | flips |
| an unknown schedule state read as its before value | a schedule's state unknown | caught on the reason |

**One survivor before the final run, fixed.** The first run had a mutant 1b that disabled only the
address-pattern half of `identity_center()`, and it survived. The other half, `type` starting with
`aws_ssoadmin_` or `aws_identitystore_`, caught every case. Every `resource_changes` entry in
`terraform show -json` carries its `type`, so mutation could not tell the pattern from its absence,
and `abd42ab` removed it (agreement 8). To keep the check fail-closed, an entry without a `type` now
makes the file unreadable (exit 2, a new test). The table above is the rerun after that commit.

### The end checks

| Command | Result |
|---|---|
| The affected set: `uv run scripts/affected_tests.py` → 74 files, run as its `--run` runs them, `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 74>` | **Stopped by the alarm at 115 s** (load average 4 to 6 before it); no orphaned workers afterwards. Over the two-minute line, so per agreement 10 it is left to the pull request's `ci` check, which runs the same set |
| Within the two minutes: `tests/architecture` (the always-run list's architecture part, and the three source-walking tests that a new `ops/` script reaches) plus the 25 files `--explain` gives as always run, changed, or directly naming the runbook, `ops/README.md`, the spec or this report | **1456 passed in 96.10s** |
| `uv run pytest tests/docs/test_backfile_import_plan_check.py` (reads another section of the same runbook) | 20 passed |
| `uv run ruff format --check .` / `uv run ruff check .` | 1588 files already formatted / All checks passed |
| `uv run pyright ops/caselist_run/check_image_plan.py tests/scripts/test_caselist_run_image_plan_check.py` (no file under `packages/` changed) | 0 errors |
| `uv run lint-imports` / `uv run python scripts/check_thin_handlers.py` | 18 kept, 0 broken / 67 handlers within 25 statements |
| `uv run python scripts/check_command_blocks.py` / `uv run python scripts/check_links.py` | OK, 566 blocks in 196 files / exit 0 |
| `uv run scripts/validate_specs.py` | OK: 492 files, 40 epics, 430 tasks, 22 releases |

## Files changed

* `ops/caselist_run/check_image_plan.py` (new): the check.
* `ops/README.md`: one sentence in the `caselist_run/` row naming the check and its runbook section.
* `tests/scripts/test_caselist_run_image_plan_check.py` (new): 41 tests on hand-written plans in
  `terraform show -json`'s shape (`mode`, `type`, `name`, `module_address`, `change` with
  `after_unknown` and the sensitivity maps), plus the runbook block.
* `docs/runbooks/caselist-cloud-run.md`, "A new image, later": the plan block now removes the last
  plan and its JSON, saves a new plan, writes it with `show -json` and runs the check. "What to read,
  and what stops you" now says what `PLAN OK` and `PLAN STOP` mean. The digest-replacement and apply
  blocks are unchanged.
* The task spec's phase, and this report.

## Deviations from the spec

None.

## Decisions and assumptions

* **A script in `ops/`, not a runbook heredoc.** t06's checks are heredocs in the cutover runbook,
  tested from `tests/docs`. This task's packages are `ops`, `tests/scripts` and `docs/runbooks`, and
  its criterion runs `tests/scripts -k caselist_run`, so the check is an ops script, like
  `start_backfile_import.py`. The JSON reading is IMAGEPLAN's.
* **IMAGEPLAN's per-resource rules are kept** (your "reuse that"). They are the image matching the
  owner file's digest, nothing else in the container definitions or task, the schedules' target
  alone, and the policies' document alone. That makes the check need `owner.auto.tfvars` as its
  second argument. Your list did not name these rules. Without them, an image apply that also changed
  the run's environment or command would pass.
* **Both schedules `ENABLED` throughout, as your brief says.** So a plan made while the login's
  schedule is paused (`caselist_login_schedule_enabled = false`, which IMAGEPLAN allowed) is now
  `PLAN STOP`, and goes to you.
* **Replace in either order.** Both `["delete", "create"]` and `["create", "delete"]` count as a
  replace, as in IMAGEPLAN. A lone `create` or `delete` does not.
* **A deposed object is its own change.** An old instance left by a failed replace is keyed as
  `<address> deposed <key>`, so it reads as an unexpected in-module change. It can never stand in for
  the expected replace.
* **Exit codes**: 0 `PLAN OK`, 1 `PLAN STOP`, 2 for a file that is not a plan's JSON (also printed as
  `PLAN STOP`). The block removes the old plan and JSON first, so a failed plan leaves an empty JSON
  file, which gives a `PLAN STOP` with exit 2, never a stale `PLAN OK`.
* **The plan's text is still saved** (`tee /tmp/caselist-new-image-plan.txt`). On a `PLAN STOP` the
  runbook asks for the text of each address it names. Nothing counts lines in it.

## Operator follow-ups

None.

## Follow-up work

* The next image apply is the check's first run on a real post-cutover plan. Its rules have passed a
  real plan once, as IMAGEPLAN at the cutover. The new parts (both schedules `ENABLED`, the
  four-bucket sorting, `type` required) have run only on synthetic plans. If that apply prints
  `PLAN STOP` on a plan you judge correct, the line names the rule to look at. No task needed unless
  that happens.
* The cutover runbook's IMAGEPLAN still looks only for `aws_ssoadmin` and not `aws_identitystore`.
  The cutover is done and that block will not run again, so I left it alone (it is also tested from
  `tests/docs`, outside this task's packages). That is the PM's call.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

The image plan is now checked from its JSON, and both of 2026-10-29's weaknesses are tested cases.
1. **ac1 passes.** Red: 40 of 40 failed against a skeleton that always says `PLAN OK`. Green: 41 passed.
   The refreshed-Identity-Center plan (the false 40) gives `PLAN OK`. The real plan's shape with
   `task_stopped["run"]` gives `PLAN STOP` naming that address. The runbook block runs the check on
   the saved plan's JSON and counts nothing in its text, and a test pins that.
2. **Four buckets, each rule the only one that can catch its case:** Identity Center anywhere, outside
   the module, the expected six, or an unexpected in-module change. That is the right structure.
3. **Mutants:** 15, all caught.
   * **1b and 2b (the thing to look at first): accepted as caught.** Each still prints `PLAN STOP`,
     so no apply would follow, and the tests pin the reason, so a rule that stopped doing its job is
     still visible.
   * The survivor of the first run led you to drop the address-pattern half of `identity_center()`.
     You made a missing `type` fail closed (exit 2) rather than leave the pattern in. Good use of
     agreement 8.
4. **Decisions accepted:**
   * an `ops/` script tested from `tests/scripts`;
   * IMAGEPLAN's per-resource rules kept, so the check also reads `owner.auto.tfvars`, which catches
     an image apply that changes the run's environment or command;
   * both schedules `ENABLED` throughout, so a paused login comes to the PM;
   * replace in either order;
   * a deposed object as its own change;
   * exit codes 0, 1, 2, with the old plan removed first so a failed plan can never leave a stale
     `PLAN OK`;
   * the plan text still saved, for reading a stop.
5. **Follow-up work:** the first real run is the next image apply, and the PM reads its line. The
   cutover runbook's IMAGEPLAN will not run again: no task.
6. **The affected set** (74 files) was stopped by the alarm and is left to the PR's `ci`. The 25
   always-run, changed and runbook-naming files, the backfile plan-check tests, ruff, pyright,
   lint-imports, the command-block and link checks, and the specs pass.
7. **Merge:** any time.
