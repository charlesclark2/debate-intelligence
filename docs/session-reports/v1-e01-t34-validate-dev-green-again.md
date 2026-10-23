# Session report: v1-e01-t34-validate-dev-green-again

| | |
|---|---|
| Task | `v1-e01-t34-validate-dev-green-again` — validate-dev is green again, and a red one is seen |
| Spec | [`plan_specs/v1/e01-repo-foundation/t34-validate-dev-green-again.yaml`](../../plan_specs/v1/e01-repo-foundation/t34-validate-dev-green-again.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t34-validate-dev-green-again` |
| Session status | PARTIAL: the cause is found and all the work is done, tested and committed. ac3's closing half, one green validate-dev run on dev after the merge, can only happen after the merge, so the Goal stays `InProgress` |

## Summary

validate-dev has been red since run 39363117892 (2026-10-20 03:13 UTC). That run validated
`v1.1.0-dev.67`, and the merge that broke it is #359 (`v1-e39-t04-pilot-infrastructure`). #359 added a
`debate_api` test that imports the package at module level, so the planted `debate_api` break began to
surface as a collection error. The planted-break check counted only a failed test. Three later merges
added the other failures: the file builder's break became a fixture error (#366), the `debate_api` break
became a conftest import error (#371), and three tests skipped (#368, #375).

This branch fixes all of them, without touching the rule that a skip fails a tier:
* The planted-break check now counts a failure, an error, a collection error or a conftest import
  error as caught. A permanent slow test plants a break nothing reaches and holds that it is not caught.
* The slow job pulls the arm64 Lambda image that `scripts/tub_deploy.sh --print-base-image` names, under
  QEMU, so the two SQLite checks run.
* The operator-only timing test is marked `operator_data`, and the tier leaves it out.
* `scripts/task ready` and `list` now print dev's head and its validate-dev status.
* conclude opens or comments on a `validate-dev` issue on a failure and closes it on a success.

Locally, the whole slow tier as the driver runs it gives **29 passed, 0 skipped**, and the driver's own
rule finds no problem. **The PM should look first at Deviation 1:** the deploy script pins the base
image by tag, not by digest, so the slow job pulls what the script names and the pull logs the digest.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `green` — validate-dev green | Done, except the closing run | Six commits, `0dcf90c` to `1c6c6dc`. Its criterion (`uv run pytest tests/scripts`) passes. The post-merge validate-dev run that closes ac3 is an operator follow-up. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the report names the first failing run and the merge that broke it | PASS | [What broke validate-dev](#what-broke-validate-dev), below: run **39363117892**, which validated `4013ee18` (`v1.1.0-dev.67`). The breaking merge is **`76e04a9`, #359 `v1-e39-t04-pilot-infrastructure`**. |
| ac2 — planted-break checks count an error and a collection error as caught and still fail on an uncaught break, by tests shown failing first | PASS | **Red, old rule:** `.venv/bin/python -m pytest tests/scripts/test_affected_tests_planted_breaks.py -q -n 0` against a `how_caught` that kept the old rule (exit 1 and `failed`) → `4 failed, 7 passed`. The four were the fixture error, the collection error under `-x` and when interrupted, and the conftest import error. **Red, uncaught break:** `UNREACHED_BREAK` added to `PLANTED_BREAKS` for one run, then the real check for it → `FAILED … [debate_core: a function nothing calls answers wrongly]`, `789 passed … caught: no`. The file was restored from the commit and `git status` was clean. **Green:** `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -m slow -n 0 -s tests/scripts/test_affected_tests_planted_breaks.py` → `8 passed in 102.29s`. The file builder's break is now `caught: a selected test errored`, `debate_api`'s is `(exit 4) … caught: a conftest the selected tests load failed to import`, and the unreached break is `(exit 0): 789 passed … caught: no`. The fast tests of `how_caught` → `11 passed`. |
| ac3 — the slow tier runs the two Lambda-image tests on the runner and leaves the operator-only test out by marker, by the workflow's own test | PASS | `tests/scripts/test_validate_dev_workflow.py` → `13 passed`. Against HEAD's workflow before each change: the pull tests went `3 failed`, the issue tests `6 failed`, and the RepoDigests guard `1 failed`. Its tests run the pull step's own shell against a stub Docker (`docker pull --platform linux/arm64 public.ecr.aws/lambda/python:3.12`), and a failed pull fails the step. They also collect the timing file with the tier's real expression: only the synthetic test is selected. Before the marker, that collection also listed `test_search_timings_on_the_operators_index`. Collecting the whole slow tier: `slow and not live and not eval` → 30 tests, with the new expression → 29; the diff is exactly the operator test. The two Lambda-image tests with the image present (arm64, native on the operator's Mac): `-m slow -k lambda_image` → `2 passed`. **The whole tier, as the driver runs it:** `.venv/bin/python -m pytest -m "slow and not live and not eval and not operator_data" --no-cov --junitxml=… -p no:cacheprovider -rfEs` under `alarm 115` → `29 passed in 59.43s`. `read_junit` gave `tests=29, failures=0, errors=0, skipped=0`, and `tier_problems` → `[]`. |
| ac3 — one validate-dev run on dev after the merge is green (operator) | NOT RUN | It can only run after the merge. On the runner, the image runs under QEMU, which this Mac cannot show. See [Operator follow-ups](#operator-follow-ups). |
| ac4 — `scripts/task ready` and `list` show dev's latest validate-dev result, and a failure opens or updates a GitHub issue, by test | PASS | `tests/scripts/test_task_validate_dev_status.py` → `15 passed` (`15 failed` against HEAD's `scripts/task` and `task_helper.py`). It runs the real `ready` and `list` with gh answering, failing (`validate-dev: unknown (gh could not read dev's commit status)`, exit 0) and absent (`validate-dev: unknown (gh is not installed)`, exit 0). The issue is covered in two places. `tests/scripts/test_validate_dev.py` → `81 passed` (`12 failed` against HEAD's driver): failure opens, failure with one open comments, success closes, success with none touches nothing, cancelled leaves it, the exact gh commands, and a token sentinel in `GH_TOKEN`, `GITHUB_TOKEN`, `ACTIONS_*`, AWS and `DEBATE_*` never reaches the text. `test_validate_dev_workflow.py` runs the conclude step's own shell with the real driver and a stub gh, for both states. |
| Node `green`: Script tests pass (`uv run pytest tests/scripts`) | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts -q`, with the alarm on the interpreter (agreement 10) → `1256 passed in 53.59s` |
| Forbidden: weakening the rule that a skipped check fails its tier | Held | `tier_problems` and `read_junit` are unchanged. The two Lambda tests now run instead of skipping. The timing test is deselected by a marker the tier excludes, so it is never collected as a skip. |
| Forbidden: marking a failing check slow, live or skipped to make the tier pass | Held | No check was failing for its own reason. The planted-break checks were fixed, not marked. The timing test was skipping because it needs the operator's index; it gets `operator_data`, not `slow`/`live`/`skip`. |
| Forbidden: planted-break checks that pass when nothing catches the break | Held | `test_a_break_no_selected_test_reaches_is_not_counted_as_caught` runs a real unreached break on every slow tier. The red run above shows the check failing on it. |
| Forbidden: network or AWS access in any test | Held | Every new test uses stubs: `docker`, `gh`, `uv` and `python3` are stub executables, GitHub is `FakeGitHub` or `RecordingRunner`, and repositories are throwaway git directories. The suite's `--disable-socket` was on for every run. |

### What broke validate-dev

Read with `gh run list --workflow validate-dev.yml` and `gh run view <id> --log` / `--log-failed`
(read-only, as the PM's note allowed). One thing to know when reading that list: its `headSha`
column is dev's head **when the run was dispatched**, not the commit it validated. The validated
commit and tag are in the `resolve` job's log.

* **Last green:** 39361784846 validated `be95ba7` (`v1.1.0-dev.66`): slow tier `8 passed`.
* **First red:** 39363117892, 2026-10-20 03:13 UTC, validated `4013ee18` (`v1.1.0-dev.67`). Smoke
  `100 passed`. Slow tier `1 failed, 7 passed`: the planted break
  `debate_api: the package fails to import`, with `assert (1 == 1 and ' failed' in '1 warning, 1 error in 0.54s')`.
  Two commits sit between `be95ba7` and `4013ee18`: **`76e04a9`, #359
  `v1-e39-t04-pilot-infrastructure`**, and `4013ee1` (#360), a ROADMAP/docs refresh that touched
  no test. #359 added `packages/debate_api/tests/test_pilot_placeholder_app.py`, which imports
  `debate_api.app` at module level. It sorted first among the ten nearest tests for that break, so
  `pytest -x` stopped at its collection error, and the check wanted `failed`.
* **Then, in order:**

| Pre-release | Merge | What changed in the slow tier |
|---|---|---|
| `v1.1.0-dev.69` | #366 `v1-e33-t04-file-quality-checks` | The file builder's reversed fingerprint now surfaces as an error at setup of `test_file_quality_mutations.py::test_a_file_built_by_t02_passes_every_check` (`7 deselected, 1 error`): a second planted-break failure. |
| `v1.1.0-dev.71` | #368 `v1-e39-t02-search-index-build` | First skip: `test_search_index_opens_in_the_lambda_image_sqlite` (`public.ecr.aws/lambda/python:3.12 is not on this machine`). |
| `v1.1.0-dev.73` | #371 `v1-e39-t05-accounts-and-sign-in` | `packages/debate_api/tests/conftest.py` arrives, so the `debate_api` break becomes `ImportError while loading conftest` (exit 4). |
| `v1.1.0-dev.76` | #375 `v1-e39-t03-search-core` | Two more skips: the reader's Lambda-image test, and `test_search_timings_on_the_operators_index` (`DEBATE_TUB_SEARCH_INDEX names no index`). |

From `dev.76` to `dev.103`, every run was the same: `2 failed, … passed, 3 skipped`. That makes 42
failing runs since 39361784846 by 2026-10-23 03:24 UTC, the PM's 39 and three since.

**The skips were always counted.** The rule that a skip fails a tier has been in
`scripts/validate_dev.py` since #160 (`v1-e01-t10-validate-dev-gate`, 2026-10-02):
`git log -S"no skip" -- scripts/validate_dev.py` names only that commit. The first skip came four
pre-releases after the tier was already red, so the skips were never the first cause, but each would
have kept it red on its own.

### Tests run before this report

`uv run scripts/affected_tests.py --run` → `The whole selection is affected: pyproject.toml is shared
test ground`. It ran nothing, because the last commit registers the marker in `pyproject.toml`.

Following agreement 10 and the memory note on `pyproject.toml` edits, that edit was committed last,
and the affected set was measured before it: `uv run scripts/affected_tests.py` at `aa96553` →
`40 of 405 test files`. Run with CI's markers under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python
-m pytest -n auto -q -m "not slow and not live" <the 40>` → `1690 passed in 62.50s`.

After the marker commit, these ran, each under the alarm:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest tests/scripts -q` | `1256 passed in 53.59s` |
| `.venv/bin/python -m pytest -q tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/smoke/test_smoke_harness.py` (the always-run list, the docs checks, and the smoke harness beside the README this changed) | `342 passed, 1 warning in 14.13s` |
| `.venv/bin/python -m pytest -q -n auto packages/debate_core/tests/application` (the directory of the one changed `debate_core` test) | `3139 passed in 82.77s` |
| `.venv/bin/python -m pytest -m slow -n 0 -s tests/scripts/test_affected_tests_planted_breaks.py` (what validate-dev runs; `-m slow` as the PM asked) | `8 passed in 102.29s`, load 13.9 |
| The whole slow tier, as above | `29 passed in 59.43s`, 0 skipped |
| `.venv/bin/ruff check .` / `.venv/bin/ruff format --check .` | `All checks passed!` / `1122 files already formatted` |
| `.venv/bin/pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `.venv/bin/lint-imports` | `Contracts: 15 kept, 0 broken.` |
| `.venv/bin/python scripts/check_thin_handlers.py` | `OK: 46 CLI command and API route handlers within 25 statements` |
| `.venv/bin/python scripts/validate_specs.py` | `OK: 423 files, 40 epics, 361 tasks, 22 releases` |
| `docs_index.py --check-descriptions`, `check_command_blocks.py --base origin/dev`, `check_links.py`, `pre-commit run check-merge-conflict --all-files` | All OK. The command-block check was re-run after this report was written. |
| `shellcheck scripts/tub_deploy.sh scripts/task` | clean |

Not run: `scripts/actionlint.sh`, which downloads actionlint from GitHub. CI's `workflow-lint` job
runs it on this pull request, because a workflow changed.

## Files changed

* **`tests/scripts/test_affected_tests_planted_breaks.py`:** `how_caught` reads pytest's exit code
  and its own words. The check is renamed `test_a_planted_break_is_caught_by_a_test_the_script_selects`.
  Added: the unreached-break test, and fast tests of `how_caught` on recorded pytest outputs.
* **`scripts/tub_deploy.sh`, `tests/scripts/test_tub_deploy.py`:** `--print-base-image` prints the base
  image and platform from `requires-python`, through the same derivation the build uses, now a
  function, and calls nothing.
* **`.github/workflows/validate-dev.yml`:**
  * slow job: QEMU and the image pull, and the tier's new expression;
  * conclude job: `issues: write` and the issue step;
  * header comments brought up to date.
* **`scripts/validate_dev.py`, `tests/scripts/test_validate_dev.py`:**
  * the `issue` subcommand, and four `GitHub` protocol methods with their `gh` implementations;
  * conclude writes `description` as an output;
  * `SLOW` gains `and not operator_data`.
* **`tests/scripts/test_validate_dev_workflow.py` (new):** the workflow's own tests.
* **`scripts/task`, `scripts/task_helper.py`, `tests/scripts/test_task_validate_dev_status.py`
  (new):** the validate-dev line in `ready` and `list`. `usage()` now prints lines 2 to 34, because
  the header grew by two lines.
* **`pyproject.toml`:** registers the `operator_data` marker.
* **`packages/debate_core/tests/application/test_evidence_search_scale.py`:** marks the timing test
  `operator_data`.
* **`docs/process/branching-and-environments.md`, `tests/smoke/README.md`:** the tier's expression,
  and what `operator_data` is for.

## Deviations from the spec

1. **The base image is not pinned by digest, because the deploy script does not pin it by digest.**
   The spec says "pinned by digest as the deploy script pins it", and the PM's note says "the same
   digest scripts/tub_deploy.sh uses (read it from there, don't copy it by hand)".
   `scripts/tub_deploy.sh` and `packages/debate_api/Dockerfile` pin the base image by **tag**,
   `public.ecr.aws/lambda/python:${PYTHON_VERSION}`, derived from `requires-python`. That is
   deliberate: ADR-0019 (a) 1 says the image "follows that declaration; it does not state a version
   of its own", and `test_the_base_image_follows_requires_python_and_states_no_version` holds the
   Dockerfile to it. The only digest there belongs to the Lambda Web Adapter.

   So I followed the real rule. The image is read from the script (`--print-base-image`, never
   copied by hand), the slow job pulls exactly what the deploy builds on, and `docker pull` logs the
   digest it got. A digest pin would mean changing the script, the Dockerfile and ADR-0019 together.
   That is the PM's call; see Follow-up work.
2. **`tests/smoke/README.md` is outside `constraints.packages`.** It documents the slow tier's
   expression and its exclusions, and would have been wrong without the edit. The change is two lines
   of the tier table and one paragraph on `operator_data`.
3. **`scripts/tub_deploy.sh` now has one use on a runner.** Its header says an operator runs it,
   "never CI". That still holds for the build, push and deploy. `--print-base-image` reads one file,
   calls nothing (the test runs it with Docker absent and records no tool call), and is the only mode
   the workflow uses. The header now says so.

## Decisions and assumptions

* **What counts as caught**, measured on real pytest runs:
  * A collection error exits 2, or 1 under `-x` as on `dev.67`, with `N error` in the summary and
    `ERROR collecting` in the output.
  * A conftest that fails to import exits 4 and prints `ImportError while loading conftest`, whatever
    the exception.
  * A usage error and a missing file also exit 4, without that message, so exit 4 counts only with it.
  * Exit 0, 3 and 5 never count, and neither does an interrupt.
* **The unreached break stays as a permanent slow test**, not only a one-off red run. Every slow tier
  then shows the check can still say "not caught". It costs a few seconds, because the clone is shared.
* **QEMU rather than an arm64 runner.** `tests/scripts/test_workflow_runners.py` pins every job to
  `ubuntu-24.04`. The two tests run the image with `--platform linux/arm64`, as the function runs, so
  the job registers arm64 emulation (`docker/setup-qemu-action@v3`, a new action in this workflow)
  and pulls the arm64 image. The emulated `python3` runs one short SQLite script per test.
* **The pull step's log line does not index `RepoDigests`.** Locally the image has none, and
  `{{index .RepoDigests 0}}` then fails, which would fail the job over a log line (fixed in
  `1c6c6dc`, with a test).
* **The marker is named `operator_data`, not after the one test,** because the smoke README already
  says a check needing what a runner lacks "belongs in another tier, not behind a skip". The timing
  test keeps `slow` as well. It still skips locally without `DEBATE_TUB_SEARCH_INDEX`, which is the
  operator's business, not the tier's.
* **The issue:**
  * It is acted on only for a run from `refs/heads/dev` that posted the status. A hotfix head, a
    release event at a tag, or a caller with `leave_status_to_caller` is not dev's verdict.
  * A cancelled run (`error`) leaves the issue alone.
  * A success closes the oldest open issue labelled `validate-dev`. The label is created with
    `gh label create --force` the first time an issue is opened. The repository has issues enabled
    and had no such label (`gh repo view`, `gh label list`, read-only).
  * The issue step runs after conclude with `always()`, because conclude exits 1 on exactly the runs
    it must act on.
  * An issue-step failure fails the run but cannot change the status already posted.
  * Out-of-order runs: a green result for an older commit finishing after a red one for a newer
    commit closes the issue, and the next red run opens a new one. The text always names the commit.
* **The status line** comes from GitHub's combined status for `dev`, which names dev's head itself,
  so `list` needs no fetch:
  * a red status adds a second line, saying no promotion can merge;
  * a head with no status yet reads `none yet (its pre-release may still be building)`. dev's head
    was in that state when I read it (`f809eca`, `total_count: 0`).
  * Parsing is in `task_helper.py`, tested on hand-written documents in the shape the API returned.

## Operator follow-ups

**After the merge: one green validate-dev run on dev's next pre-release** (closes ac3). The merge into
`dev` builds a pre-release, and `dev-prerelease.yml` dispatches validate-dev for it, about 3.5
minutes after the merge. The run then takes about 5 to 7 minutes; the image pull adds well under a
minute. Nothing needs to be started by hand if that run appears. These commands run anywhere `gh` is
signed in; they name the repository, so no `cd` is needed.

To find the run and watch it:

```bash
gh run list --repo charlesclark2/debate-intelligence --workflow validate-dev.yml --limit 3
```

```bash
gh run watch --repo charlesclark2/debate-intelligence --exit-status RUN_ID
```

Success looks like:
* the run concludes `success`;
* `gh run view RUN_ID --repo charlesclark2/debate-intelligence --log | grep -E "pulled linux/arm64|slow tier"`
  shows `pulled linux/arm64` and `== slow tier: passed`;
* the slow job's pytest line reads `N passed` with **no** `skipped`;
* `scripts/task list` prints `validate-dev: success on dev <that commit>`.

Paste the run id and that pytest line into this report, under ac3.

If no run appears within about 10 minutes of the pre-release, dispatch one yourself, in two steps.
First, read dev's head and check it has a published pre-release. The second command must list a
`vX.Y.Z-dev.N` tag for that commit; if it lists nothing, the pre-release is still building, so wait.

```bash
gh api repos/charlesclark2/debate-intelligence/commits/dev --jq .sha
```

```bash
gh release list --repo charlesclark2/debate-intelligence --limit 3
```

Then dispatch it for that commit. This posts a `validate-dev` status on the commit, and on a
failure opens or updates the `validate-dev` issue. Replace FULL_SHA with the 40 characters printed
above:

```bash
gh workflow run validate-dev.yml --repo charlesclark2/debate-intelligence --ref dev -f sha=FULL_SHA
```

If it comes back red, the conclude job will have opened an issue labelled `validate-dev`: that is
the new mechanism working. Paste the failed job's log into the session.

## Follow-up work

* **Pin the Lambda base image by digest, if the PM wants that** (E39, ADR-0019): `tub_deploy.sh`,
  the Dockerfile and ADR-0019 change together, and `--print-base-image` would then print the digest
  reference. Until then the slow tier tests whatever `python:3.12` is on the day it runs, as the deploy does.
* **validate-dev on a hotfix head reports nowhere but its status.** If that matters, the issue could
  carry the branch in its title (E01).
* **The planted-break check's nearest tests include its own test file**, because the file names
  `identifiers.py` by path. That is why the inner runs say `8 deselected`. It is harmless; noted
  because the PM's memory names exactly this kind of false selection edge.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted. Sync first (below), then open the pull request **with `--partial`**. ac3's green run can
only happen after the merge, and no task depends on this one. The PM records the run in a close-out.

**What the PM checked.**
* The branch is clean on origin/dev at `37bdaba`, and the diff is the 16 files listed.
* No other spec depends on `v1-e01-t34`.
* dev has since gained v1-e39-t14 and PM batch c. This branch edits `pyproject.toml`,
  which is shared test ground, so sync before the pull request: run `scripts/task sync`, then
  `tests/scripts`, the always-run list and the slow planted-break file once more, and record the
  results.

**What is good.**
* **ac1 is answered with a timeline, not a guess.** #359's module-level import made the `debate_api`
  break a collection error. #366, #371, #368 and #375 then each added a failure or a skip, and the
  skips were always counted (#160). You also caught that `gh run list`'s `headSha` is dev's head at
  dispatch, not the validated commit, which explains the confusing run list the PM read.
* **The check stays honest.** "Caught" is defined from measured pytest exits: exit 4 counts only
  with the conftest message, and 0, 3, 5 and an interrupt never count. A permanent unreached break
  proves on every slow tier that the check can still say "not caught".
* **The skip rule is untouched.** The two Lambda checks now run under QEMU, and the operator test is
  left out by a marker named for what it needs, `operator_data`, not by a skip.
* **A red result is now seen.** It reaches `scripts/task ready` and `list`, and a `validate-dev`
  issue opens on failure and closes on success, with a token sentinel proving no secret reaches the
  text.

**Rulings.**

1. **Deviation 1 is accepted: follow the real rule, not my wording.** The base image follows
   `requires-python` by tag, by ADR-0019 (a) 1, so the slow job pulls exactly what the deploy builds
   on and logs the digest it got.
   * **The digest-pin follow-up is declined.** A pin would contradict that ADR's decision, and the
     slow tier testing what the deploy builds on the same day is the property we want.
   * If an unannounced base-image change ever breaks a deploy, the PM revisits it then.
2. **Deviations 2 and 3 are accepted:** the smoke README's tier table, and `--print-base-image` as
   the one call-nothing mode a runner uses, with the header saying so.
3. **Decisions are accepted:** QEMU over a runner change, the `RepoDigests` guard, and the issue's
   scope (dev only, cancelled runs ignored, out-of-order runs explained in the text).
4. **Follow-ups.** The hotfix-head note and the self-selection edge are recorded. The self-selection
   edge belongs with v1-e01-t32 (quoted-word and path edges); the PM adds it to that task's brief.

**Operator follow-up: accepted as written.** After the merge, the auto-dispatched validate-dev run on
dev's next pre-release, or a dispatched one, must come back green, with `pulled linux/arm64`, the
slow tier passing and **no** `skipped`. That run unblocks the prod promotion. Paste its id and the
pytest line to the PM, who records them in this report's close-out.

## After the PM review: synced onto origin/dev

`scripts/task sync v1-e01-t34-validate-dev-green-again` rebased the nine commits cleanly onto
`41820ab` (PM batch 2026-10-22c, after v1-e39-t14). Between `37bdaba` and `41820ab`, dev changed
none of the files this task touches: `git diff --stat 37bdaba origin/dev` over `pyproject.toml`,
`uv.lock`, `scripts`, `.github`, `tests/scripts`, the smoke README, the timing test, `docs/process`
and the E01 specs printed nothing. Then `uv sync --all-packages`, and each run below under
`perl -e 'alarm 115; exec @ARGV'` on the interpreter:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest tests/scripts -q` | `1262 passed in 55.20s` (1256 before the sync; dev added six) |
| `.venv/bin/python -m pytest -q tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py` | `279 passed, 3 warnings in 15.52s` |
| `.venv/bin/python -m pytest -m slow -p no:randomly -n 0 -s -q tests/scripts/test_affected_tests_planted_breaks.py` | `8 passed, 11 deselected in 86.13s` at load 12.7. Five breaks are `caught: a selected test failed`. The file builder's is `caught: a selected test errored`, `debate_api`'s is `exit 4, caught: a conftest the selected tests load failed to import`, and the unreached break is `exit 0, caught: no`. |
| `ruff check .`, `ruff format --check .`, `lint-imports`, `scripts/validate_specs.py` | `All checks passed!`, `1124 files already formatted`, `Contracts: 15 kept, 0 broken.`, `OK` |

ac3's post-merge run is still `NOT RUN` and the Goal stays `InProgress`. The pull request goes in
with `--partial`, as the PM ruled.
