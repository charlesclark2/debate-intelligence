# Session report: v1-e01-t42-coverage-measured-in-the-parts

| | |
|---|---|
| Task | `v1-e01-t42-coverage-measured-in-the-parts` — Coverage measured in the test parts and combined, so the push run is never held by one unsplit job |
| Spec | [`plan_specs/v1/e01-repo-foundation/t42-coverage-measured-in-the-parts.yaml`](../../plan_specs/v1/e01-repo-foundation/t42-coverage-measured-in-the-parts.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t42-coverage-measured-in-the-parts` |
| Session status | PARTIAL: built and tested; one clause of ac2 can only be measured on the push run after the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

On a push to dev or main, each part of ci.yml's `test` job now runs its pytest with `--cov` (the
same `[tool.coverage]` settings, no per-part report). It writes its data to a file named for its
part out of the matrix total (`coverage-part-K-of-N`) and uploads it as an artifact. The `coverage`
job now `needs: test`, downloads every part's data and checks that it holds exactly parts 1 to N
before it runs `coverage combine` and prints the term-missing report the unsplit job printed. It has
no `continue-on-error` and a 10-minute limit. Pull requests and dispatches are unchanged: they
measure nothing, and the partition proof still collects every part against the unsplit command.

The counts came first (ac1). Coverage makes one part about 1.52 times as long (a median of three
interleaved runs a side), so a push part should take about 4.5 to 6.5 minutes against the job's
10-minute limit. That is the push run's figure; the 2-minute part figure is for pull requests,
which never measure coverage, so I did not add a ninth part (a relay question for the PM is below).
The PM's three mutants and ten more were all caught.

**The Goal stays `InProgress`.** ac2's clause "the push run's slowest job is a part" can only be
read from the first push run after this merges, as the PM's brief says. The operator block for it
is under Operator follow-ups.

Look first at the combining step in `.github/workflows/ci.yml` (its every-part check). I chose the
two action pins without network access; the operator has since confirmed that both tags exist
(operator follow-up 1, 2026-10-28).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `coverage-in-parts` (Coverage in parts) | Done | Counts first; tests committed red (`b8fe944`), then the workflow (`86fcadb`); 13 mutants caught. Its criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: "Counts first: the unsplit coverage job's time and each part's time with coverage on, in the report" | PASS | See [Counts](#counts-ac1). The unsplit job ran past its 20:00 limit on push run 40471817474 (from the PM's brief: I made no network calls). One part, with and without `--cov`, interleaved, three runs each: medians of 66.4 s without and 100.9 s with coverage, ×1.52. Estimated push part with coverage: 4.5 to 6.5 min. |
| ac2, in the workflow: "On a push, each part measures coverage and one job combines it into the report the unsplit job printed; … workflow tests pin it, shown failing first" | PASS | Red at `b8fe944` against the unchanged ci.yml: `.venv/bin/python -m pytest tests/scripts/test_ci_workflow_test_job.py -p no:randomly --tb=line -q` → `15 failed, 15 passed`. Green at `98d2ebc`: `30 passed`. The combined report's table equals the unsplit `--cov-report=term-missing` table for the same tests (`test_a_pull_request_part_keeps_no_coverage_and_the_push_parts_combine_into_the_unsplit_report`). See [Mutants](#mutants). |
| ac2, on the push run: "the push run's slowest job is a part" | NOT RUN | Can only be read from the first push run to dev after this merges, since a pull request runs no coverage. Operator block 2 below reads it. Expected: every `test (K)` at 4.5 to 6.5 min, `coverage` at about 1 to 1.5 min. |
| Node `coverage-in-parts`: CI workflow tests pass (`uv run pytest tests/scripts -k ci_workflow`) | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts -k ci_workflow -q` (the time limit goes on the interpreter, agreement 10) → `48 passed in 29.38s` at `98d2ebc`. |

### Counts (ac1)

**The unsplit job.** From the PM's brief: on push run 40471817474 the parts `test (1)` to `test (8)`
took 3:03 to 4:19 each, and `coverage` (the unsplit run of the whole selection) ran past its 20:00
limit. It did so on every push to dev from 2026-10-26. I made no network calls, so I have no unsplit
time from a run that finished. Operator block 2 reads the last unsplit run's time and total.

**What `--cov` adds to one part.** I measured on this Mac (11 cores), with the part's own CI command
and the push step's coverage arguments. One part of eight (`--part 3/8`, no coverage) took 100.7 s
here (`2174 passed in 99.70s`), so with coverage it would pass the two-minute line for a session
command. I measured a part of sixteen instead: `--part 3/16`, 1,106 tests, dealt the same way.
Each run was `.venv/bin/python -m pytest -n auto -m "not slow and not live" --part 3/16 -p no:cacheprovider -q`,
with `--cov --cov-report=` and `COVERAGE_FILE` in the scratchpad for the coverage runs, under
`perl -e 'alarm 115'`, interleaved:

| Run | Coverage | Wall-clock | pytest's own time | Load average (1 min) at start |
|---|---|---|---|---|
| 1 | without | 59.0 s | 58.08 s | 6.95 |
| 1 | with | 100.3 s | 98.52 s | 7.80 |
| 2 | without | 66.4 s | 65.33 s | 10.44 |
| 2 | with | 100.9 s | 99.19 s | 8.81 |
| 3 | without | 68.6 s | 67.61 s | 12.47 |
| 3 | with | 109.2 s | 107.46 s | 10.41 |

Medians: **66.4 s without, 100.9 s with, ×1.52** (pytest's own times give the same: 65.33 s and
99.19 s, ×1.52). v1-e01-t27 measured ×1.48 for the whole suite (182 s against 123 s). The load
climbed from 4 to 12 during the runs, which is why I interleaved them; the ratio is the number to
use, not the seconds.

**Each part with coverage on CI (estimate).** Without coverage the push parts took 3:03 to 4:19 per
job, setup included. If all of it were pytest, ×1.52 gives 4:38 to 6:34; setup does not grow, so the
true figure is a little lower. That is **about 4.5 to 6.5 minutes** per part against the job's
10-minute limit. The `coverage` job now runs no tests. It repeats the setup every job has, then
downloads and combines eight files, so I expect about 1 to 1.5 minutes. The push run should then
take about 7 to 8 minutes in all, where before it waited 20 to 40 minutes for the unsplit job.

**Against the 2-minute part figure.** The ci.yml header's 2-minute figure is for a part's pytest
step on ordinary pull requests. A push part with coverage passes 2 minutes by a wide margin, but so
did a push part without coverage: a push runs the whole selection. Pull requests measure no
coverage, so this change does not move their parts at all. A ninth part would cut every part by
about a ninth on pull requests and pushes alike and add a runner's setup to each, and no push part
would come near 2 minutes. So I built with eight parts and put the question to the PM below rather
than adding one.

### Mutants

Each mutant was a text change to the committed `.github/workflows/ci.yml`. For each one I ran
`.venv/bin/python -m pytest tests/scripts/test_ci_workflow_test_job.py -q --tb=no -rf -p no:randomly`
with `HYPOTHESIS_STORAGE_DIRECTORY` set to a new empty directory (agreement 8; this file has no
Hypothesis properties), then restored the file from `HEAD`. The script and its log are in the
scratchpad: `/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e01-t42-coverage-measured-in-the-parts/193c9481-1838-44a6-bad5-f2bc6afac488/scratchpad/mutants.py`.
All 13 were caught, each at an assertion.

| Mutant | Caught by |
|---|---|
| **PM (1)**, a part measuring coverage on a pull request: `--cov --cov-report=` added to the pull request's pytest step | 3 tests, including the end-to-end run (the pull request's command left a data file) |
| **PM (1)**, another way: the `--cov` step's `if` removed, so it runs on every event | 5 tests |
| **PM (2)**, the combining job reading fewer parts than the matrix has: the every-part check replaced by `if false` | 3 cases of `test_the_combining_step_fails_unless_it_has_exactly_every_part_of_the_matrix` |
| **PM (2)**, another way: download pattern `coverage-data-part-1*` | `test_the_coverage_job_waits_for_every_part_and_fails_the_push_run_when_it_fails` |
| **PM (3)**, `continue-on-error: true` left on the coverage job | the same test |
| Every-part loop stops before the last part (`part < parts`) | only the `last-part-missing` case, which was built for it |
| The count check removed (`${#files[@]} -ne $parts`) | only the `a-part-too-many` case, which was built for it |
| `coverage combine` given `"${files[@]:1}"` (the first part dropped after the check) | `test_the_combining_step_reports_when_every_part_of_the_matrix_is_there` |
| `needs: test` removed from the coverage job | `assert None in ('test', ['test'])` |
| Upload `if-no-files-found: warn` | the upload test |
| Coverage limit back to 40 minutes | the coverage job test |
| `COVERAGE_FILE` removed from the push step | the push-step test and the end-to-end test (`the push step names no data file of its own`) |
| Parts print their own report (`--cov-report=term-missing`) | the push-step test and the end-to-end test |

On the first pass, two catches failed on a `KeyError` (`coverage["needs"]`, a step's `["env"]`)
rather than at an assertion. I turned both lookups into assertions (`98d2ebc`) and re-ran the two
mutants. They now fail at `assert None in ('test', ['test'])` and
`AssertionError: the push step names no data file of its own`.

The red run at `b8fe944` failed because the steps the tests look up did not exist yet (14
`ValueError: not enough values to unpack` from the step lookups, and 1 `KeyError: 'needs'`). The
mutants above are what show each check failing for its own reason. Two checks were wrong in the red
commit and were fixed before green, and neither changed a red verdict (both tests had already failed
at a step lookup). One regex took the pull request step's name, "no coverage", for a coverage step.
The other read the word "coverage" in pytest's output, but this worktree's path contains it; it now
reads `coverage: platform`.

### Checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `The whole selection is affected: .github/workflows/ci.yml is shared test ground. CI runs it on the pull request; a session does not.` So nothing more from it (agreement 10). |
| Workflow tests and the always-run list: `perl -e 'alarm 118; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/scripts/test_back_merge_workflow.py tests/scripts/test_ci_workflow_test_job.py tests/scripts/test_ci_workflow_test_selection.py tests/scripts/test_dev_prerelease_workflow.py tests/scripts/test_refresh_generated_files_workflow.py tests/scripts/test_validate_dev_workflow.py tests/scripts/test_workflow_runners.py -q` | `481 passed, 1 warning in 34.16s` |
| `uv run --frozen ruff format --check .` | `1538 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `pyright` | Not run: no package under `packages/` changed, and pyright's `include` is `packages` only |
| `uv run --frozen lint-imports`; `scripts/check_thin_handlers.py` | `Contracts: 18 kept, 0 broken.`; `OK: 67 … handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 491 files, 40 epics, 429 tasks, 22 releases` |
| `scripts/check_command_blocks.py` (with `--base origin/dev` for this report); `scripts/docs_index.py --check-descriptions` | clean; `All 56 indexed documents under docs/ have a description` |
| ShellCheck 0.11.0 (the dev group's, which actionlint uses) over the `test` and `coverage` jobs' 8 `run:` blocks, expressions replaced, actionlint's exclusions | clean |
| actionlint (`scripts/actionlint.sh`) | Not run: it downloads actionlint from GitHub. The pull request's `workflow-lint` job runs it, since ci.yml changed. |

The whole selection is the pull request's `ci` run.

## Files changed

* `.github/workflows/ci.yml`: the `test` job's pytest step split in two by event (`!= 'push'` as
  before; `== 'push'` with `--cov --cov-report=` and its own `COVERAGE_FILE`), plus an upload step
  on a push. The `coverage` job now needs `test`, downloads, checks for every part, combines and
  reports, with a 10-minute limit and no `continue-on-error`. The header and the job's comment now
  say what is true.
* `tests/scripts/test_ci_workflow_test_job.py`: the workflow tests (docstring, helpers, the coverage
  section rewritten). The partition proof now compares every part with the part's own command
  without `--part`, where it used the unsplit coverage job's command, which is gone.
* `pyproject.toml`: one comment, saying where CI measures coverage now. No setting changed.
* `docs/session-reports/v1-e01-t42-coverage-measured-in-the-parts.md`: this report.
* `plan_specs/…/t42-coverage-measured-in-the-parts.yaml`: phase only (set to `InProgress` before
  the session; left there).

## Deviations from the spec

None. The forbidden list holds: no pull request measures coverage (pinned and mutated), no test was
deselected, and every job runs on `ubuntu-24.04`.

## Decisions and assumptions

* **Two pytest steps, not one with conditional arguments.** A part runs one of two steps by
  `github.event_name`, and the test pins that the push step's arguments are the pull request
  step's plus `--cov --cov-report=`, nothing else. So the partition proof, which collects the
  pull request's form, holds for the push form too.
* **Missing data is detected from the file names, not from ci.yml.** Each file is named
  `coverage-part-K-of-N`, with N from `strategy.job-total`. The combining step needs exactly N
  files, all for the same N, with every K from 1 to N present. Each of the two checks has a test
  case that only it refuses: a part too many, and the last part missing with another in its place.
* **Paths in `runner.temp`, combined with `--data-file`.** Nothing is written into the checkout, so
  the tests run the real commands (two push parts of one small file, then the combining step's own
  shell) without touching the repository.
* **The combining job runs `uv sync`.** `coverage report` finds the `source_pkgs` through the
  workspace's installed packages, as the parts did. The checkout path is the same on every hosted
  runner, so the parts' absolute paths combine without a `[paths]` mapping. I did not change
  `[tool.coverage]` (the PM asked for the same settings, and a test pins them whole).
* **`retention-days: 1`** for the part artifacts: the `coverage` job of the same run reads them
  once.
* **Action pins: `actions/upload-artifact@v6`, `actions/download-artifact@v7`.** These are major tags,
  as every action here is pinned. I chose them from what I know (both moved to Node 24 at those
  majors) because I could not check releases without the network. The pull request's `test` job
  only uses `upload-artifact` on a push, and nothing runs `download-artifact` before the merge, so
  operator block 1 checks both tags before the pull request. The operator ran it on 2026-10-28, at
  the PM's request, and both tags exist (result under Operator follow-ups).
* **`--show-missing` on `coverage report`** is redundant with `show_missing = true` in
  `pyproject.toml`, just as `term-missing` was for the unsplit job. I kept it so the step says which
  report it prints. No mutant targets it, since removing it changes nothing.

## Operator follow-ups

**1. Before the pull request: check that the two action tags exist** (about 5 seconds, read-only).
Where: your Mac, any directory.

```bash
git ls-remote --tags https://github.com/actions/upload-artifact refs/tags/v6
git ls-remote --tags https://github.com/actions/download-artifact refs/tags/v7
```

Success looks like: each prints one line ending in `refs/tags/v6` or `refs/tags/v7`. If either
prints nothing, paste that back into the session, which changes the pin to the tag that exists.

**Result (2026-10-28, run by the operator at the PM's request): DONE, both tags exist.** The output
was one line for each tag:

```text
b7c566a772e6b6bfb58ed0dc250532a479d7789f        refs/tags/v6
37930b1c2abaa49bbe596cd826c3c89aef350131        refs/tags/v7
```

The first line is `actions/upload-artifact`, the second `actions/download-artifact`. The pins in
`ci.yml` stay as they are.

**2. After the merge into dev: read the first push run's job times and coverage total, and compare
the total with the last unsplit run's** (about 1 minute, read-only). This is the evidence for ac2's
last clause. Where: your Mac, in the task worktree. First list the recent push runs:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t42-coverage-measured-in-the-parts
gh run list --workflow CI --branch dev --event push --limit 10 --json databaseId,conclusion,createdAt,displayTitle --jq '.[] | "\(.databaseId)\t\(.conclusion)\t\(.createdAt)\t\(.displayTitle)"'
```

The merge's run is the one titled with this task's pull request. Put its id in place of
`PASTE_THE_RUN_ID` and run:

```bash
RUN=PASTE_THE_RUN_ID
gh run view "$RUN" --json jobs --jq '.jobs[] | "\(.name)\t\(.conclusion)\t\((.completedAt | fromdateiso8601) - (.startedAt | fromdateiso8601)) s"'
gh run view --log --job "$(gh run view "$RUN" --json jobs --jq '.jobs[] | select(.name == "coverage") | .databaseId')" | grep -E 'Name +Stmts|TOTAL'
```

Success looks like:

* every `test (1)` to `test (8)` and `coverage` concluded `success`;
* each `test (K)` took about 270 to 400 s;
* `coverage` took about 60 to 90 s;
* the slowest job is a `test (K)`;
* the second command prints the report header and a `TOTAL` line.

Then run the same block again with `RUN` set to the newest push run before the merge, the last
unsplit one. If its `coverage` job finished, the grep prints that run's `TOTAL`, and the two totals
should be within about a point of each other: the same tests are measured, and only the commits
differ. If that `coverage` job timed out, it printed no total. Try older runs in the list, or record
that there is none to compare. Paste both outputs into the PM review.

## Follow-up work

* **Working agreements 1 and 10 (`docs/process/working-agreements.md`) still say the `coverage` job
  measures coverage.** Changing that file is outside this task's packages and goes through its own
  pull request. A sentence for agreement 1 that the PM could use: "`ci.yml`'s `test` parts measure it
  on every push to `dev` and `main`, each over its own share, and the `coverage` job combines them
  into one report over the whole selection."
* **The drift rule only watches pull request parts.** The rule, "one part's pytest step over 2",
  reads pull request parts. A push part with coverage is now the slowest thing in the push run, held
  by the job's 10-minute limit, at an estimated 4.5 to 6.5 minutes. A matching rule for the push run
  (for example, a push part over 8 minutes means one more part) would belong in agreement 1 (v1-e01).

**Relay prompt for the PM** (the brief's ninth-part question):

```text
v1-e01-t42 asks: should ci.yml's test matrix get a ninth part now that push parts measure coverage?

Measured: --cov makes a part 1.52x as long (median of 3 interleaved runs each, part 3/16 of the
whole selection, this Mac). Estimated push part with coverage: 4.5-6.5 min against the job's
10-minute limit. Pull request parts measure no coverage and are unchanged.

Options:
  A. Keep 8 parts (recommended). The 2-minute figure in ci.yml's header is for pull request parts,
     which this task does not change; no number of parts brings a whole-selection push part under 2
     minutes; the 10-minute limit has 3.5+ minutes of headroom.
  B. Add a ninth part now. About 11% off every part, on pull requests and pushes alike, for one
     more runner's setup (~15 s and a collection) on every pull request.
  C. Decide after operator block 2 reports the real push part times.

Why A: the change that caused the hold-up (one unsplit 20+ minute job) is gone either way, and B
spends pull-request runner time to buy push-run time that is not short.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
