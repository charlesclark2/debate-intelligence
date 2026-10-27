# Session report: v1-e01-t38-ci-affected-tests-on-dev-pull-requests

| | |
|---|---|
| Task | `v1-e01-t38-ci-affected-tests-on-dev-pull-requests` — A pull request into dev runs the tests its changes reach; a push to dev and a pull request into main run them all |
| Spec | [`plan_specs/v1/e01-repo-foundation/t38-ci-affected-tests-on-dev-pull-requests.yaml`](../../plan_specs/v1/e01-repo-foundation/t38-ci-affected-tests-on-dev-pull-requests.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t38-ci-affected-tests-on-dev-pull-requests` |
| Session status | COMPLETE; the Goal stays InProgress, because ac3 is read off this pull request's run and the push run after its merge (operator) |

## Summary

ci.yml's `test` job now runs, on a pull request into `dev`, only the test files the pull request's
changes reach. Each of its five parts runs `scripts/ci_test_selection.py`, which reads
`scripts/affected_tests.py`'s selection against `github.event.pull_request.base.sha`, and then deals
that list round the parts as before. Every other run is the whole default selection: a pull
request into `main`, a push to `dev` or `main`, a dispatch. So is a pull request into `dev` that
changes shared test ground, has no base commit in the checkout, or whose selection fails or comes
back empty. The selection is handed to pytest as `@FILE`, and an empty file is the whole selection
(pytest then runs `testpaths`, exactly the old command), so almost every failure falls to more tests
by construction. A crash of the script itself also empties the file. The job summary says how many
test files ran and, for the whole selection, why.

**Counts first (ac1):** over the last 20 pull requests merged into `dev`, the **median share is
46.3% of test files and 40.9% of tests**. That is **below the PM's 60% line**. Six of the 20 are
the bot's refreshes of `ROADMAP.md` and `docs/README.md` (about 5% each). Without them the median of
the 14 task and PM pull requests is 50.1% of files and 45.6% of tests. Two of the 20 were the whole
selection (a `pyproject.toml`). What carries the large selections is named under ac1 below:
`debate_cli/app.py`, `application/settings.py`, `application/errors.py`, `debate_cli/container.py`
and two package-level test conftests.

**Look first at:** the `@FILE` design under Decisions (it is why `run_in_parts.py` did not change),
and the new rule in working agreement 10 about a red push run. Its last sentence, that the fixing
session runs the failing tests by name, is mine, not the PM's.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `ci-affected-tests` | Done | Script, workflow, tests, docs; acceptance command below passes. ac3 is the operator's, after the pull request and after the merge. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: over the last 20 pull requests merged into dev, the test files and tests each would have selected and their share of the whole selection, in the report | PASS | Table and method under [ac1](#ac1-the-last-20-pull-requests-into-dev). Median 46.3% of test files, 40.9% of tests; below 60%. |
| ac2: on synthetic diffs and events, the affected files for a pull request into dev, and the whole selection for a pull request into main, a push, shared test ground, a selection error or a missing base; the parts together exactly the selection given; tests shown failing first | PASS | `tests/scripts/test_ci_workflow_test_selection.py` (18 cases, synthetic git repositories whose HEAD is a merge commit like `refs/pull/N/merge`) and `tests/scripts/test_ci_workflow_test_job.py` (22, of which 7 are new or changed). **Red:** two skeleton `choose()` functions were swapped in from a byte copy and restored (`cmp` equal, `git status` clean). One trusts the selection on every event, with no fallbacks: `15 failed, 3 passed` (the three affected-set cases pass, as they should). The other always returns the whole selection: `18 failed`, and the three affected-set cases fail with `assert set() == {...}`. **Green:** see the node row. **Mutants:** 20, under [Mutation run](#mutation-run); all 19 aimed at the new tests caught, and the twentieth shows what the old proof missed. |
| ac3: this task's own pull request shows its selection in the job summary, and the push run after its merge runs the whole selection, read from the run pages (operator) | NOT RUN | Can only be read after the pull request is opened and after it merges. What to read is under Operator follow-ups 1 and 2. |
| Node: `uv run pytest tests/scripts -k "ci_workflow or affected"` | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts -k "ci_workflow or affected" -p no:cacheprovider -q` → `97 passed in 33.01s` at load average 5.8. Same interpreter and arguments as `uv run pytest`, with the time limit on the interpreter (agreement 10). |

### ac1: the last 20 pull requests into dev

**Method.** The 20 commits are `git log --first-parent origin/dev -20`, from `a077632` (#546) back
to `2110c13` (#527); each is a squash merge. Each row is
`.venv/bin/python scripts/affected_tests.py --diff <commit> --explain`: the commit against its first
parent, over the commit's own tree. This is t28's method. The runs went three at a time, each with
a 200 s alarm; each took 9 to 14 s at load average 7. Nothing was fetched: `origin/dev` as this
session found it.

"Tests" weights each selected file by its test count in today's default selection
(`.venv/bin/python -m pytest -n 0 -m "not slow and not live" --collect-only -q` →
`16845/16892 tests collected (47 deselected)`, 528 files with tests). For the older commits it is an
estimate, as in t28. A whole-selection row is 100% of both.

| Commit | Pull request | Test files | Share of files | Tests | Share of tests |
|---|---|---|---|---|---|
| `a077632` | #546 PM batch | 75 of 533 | 14.1% | 2,304 | 13.7% |
| `9c99f03` | #543 refresh | 25 of 533 | 4.7% | 1,352 | 8.0% |
| `030cc4c` | #545 usage telemetry | 433 of 533 | 81.2% | 12,834 | 76.2% |
| `1ace4e5` | #544 impact chains | 233 of 529 | 44.0% | 6,814 | 40.5% |
| `65f56d7` | #542 bucket-mode report counts | 268 of 528 | 50.8% | 6,440 | 38.2% |
| `8a597db` | #540 refresh | 25 of 526 | 4.8% | 1,352 | 8.0% |
| `8cf5e91` | #541 PM batch | 33 of 526 | 6.3% | 1,563 | 9.3% |
| `7e271ed` | #539 citation service | whole (`pyproject.toml`) | 100% | 16,845 | 100% |
| `57e3060` | #538 refresh | 25 of 522 | 4.8% | 1,352 | 8.0% |
| `321b5ee` | #537 scenario vocabulary | 258 of 522 | 49.4% | 7,728 | 45.9% |
| `f5a8221` | #536 style-profile refusal | 318 of 521 | 61.0% | 9,026 | 53.6% |
| `ad7f5a1` | #535 refresh | 25 of 521 | 4.8% | 1,352 | 8.0% |
| `206f2ec` | #533 fetch command | whole (`packages/debate_cli/pyproject.toml`) | 100% | 16,845 | 100% |
| `b3273fb` | #534 unlabelled plan affs | 235 of 516 | 45.5% | 6,956 | 41.3% |
| `d0cc9c3` | #530 refresh | 25 of 514 | 4.9% | 1,352 | 8.0% |
| `af7052e` | #531 Bedrock invoke access | 369 of 514 | 71.8% | 10,452 | 62.0% |
| `ec02c33` | #523 model classification | 248 of 513 | 48.3% | 7,624 | 45.3% |
| `2a33947` | #529 kritikal affs | 240 of 511 | 47.0% | 7,129 | 42.3% |
| `987fa89` | #528 refresh | 25 of 509 | 4.9% | 1,352 | 8.0% |
| `2110c13` | #527 article service | 368 of 509 | 72.3% | 11,103 | 65.9% |

| Summary | Share of test files | Share of tests |
|---|---|---|
| Median, all 20 | **46.3%** | **40.9%** |
| Mean, all 20 | 41.0% | 39.1% |
| Median, the 14 task and PM pull requests (no refreshes) | 50.1% | 45.6% |
| Mean, the 14 | 56.5% | 52.4% |

**The median is below 60%**, so by the PM's note e01-t32 need not go next on this account. The
14-row figures are the honest picture for task work, and are near half.

**The hub files behind the large ones.** I took the `--explain` chains of the five largest
selections that were not the whole selection. For each, I counted which changed file the selected
tests reach, and which files their chains pass through:

- `030cc4c` (81.2%): `debate_core/application/errors.py` reaches 292 of the 433 files, and
  `debate_cli/commands/__init__.py` reaches 68. They pass through `debate_cli/app.py` (50),
  `application/caselist_sync.py` (29) and `application/ports/suppression.py` (26).
- `2110c13` (72.3%): `debate_core/application/settings.py` reaches 314 of 368. The chains pass
  through `application/caselist/camp_metadata.py` (96), `debate_cli/app.py` (96), the caselist tests'
  `conftest.py` (47), `openev_manifest.py` (39) and `file_recipes.py` (37).
- `af7052e` (71.8%): `settings.py` reaches 160 files, `debate_cli/container.py` 104 and
  `integrations/s3/errors.py` 58. The chains pass through `debate_cli/app.py` (89),
  `camp_metadata.py` (58) and `integrations/s3/__init__.py` (56).
- `f5a8221` (61.0%): `application/ports/parsed_store.py` reaches 147 files and
  `debate_cli/container.py` 98. The chains pass through `debate_cli/app.py` (80).
- `65f56d7` (50.8%): `debate_cli/container.py` reaches 114 files and
  `application/caselist/status_service.py` 106. The chains pass through `debate_cli/app.py` (92).

All five share three things. The CLI composition root, `debate_cli/app.py`, imports the container,
and through it nearly everything; every test that imports it or runs `debate-research` reaches it,
including `tests/smoke/installed_build.py` and `test_pull_stage_failure_codes.py` and the tests
that import them. `application/settings.py` and `application/errors.py` are imported almost
everywhere. And two package-level conftests carry broad imports to every test beneath them:
`packages/debate_core/tests/application/caselist/conftest.py` and `packages/debate_api/tests/conftest.py`.
Of these, only the `commands/__init__.py` reach is in a spec (e01-t32). `app.py`, the conftests,
`settings.py` and `errors.py` are not yet (Follow-up work).

### Mutation run

20 mutants, each applied to a committed file, run against the tests that cover it, and restored with
`git checkout --` (the driver asserts `git status --porcelain` is empty after each). No Hypothesis
test is involved, so agreement 8's database rule does not apply. Selection mutants ran
`test_ci_workflow_test_selection.py` (about 2 s each), workflow mutants ran
`test_ci_workflow_test_job.py -k "not exactly_the_default_selection"` (about 7 s), and the parts
mutants ran the one proof named.

| # | Mutant | Result |
|---|---|---|
| 1 | **PM:** a pull request into main runs the affected set (`main` allowed beside `dev`) | caught: `..._into_main_is_a_promotion_...` |
| 2 | **PM:** a selection error runs fewer tests (falls back to one file) | caught: `test_a_selection_that_fails_...` |
| 3 | **PM:** a selection error runs nothing (exits 0 before writing the file) | caught: same test |
| 4 | **PM:** a missing base compares with HEAD, so only the always-run list runs | caught: 3 tests (empty sha, unknown sha, one-commit-deep clone) |
| 5 | a missing base is noticed only when the sha is empty | caught: unknown sha, and the shallow clone |
| 6 | a dispatched run runs the affected set | caught: `..._dispatched_run_..._[workflow_dispatch]` |
| 7 | a push loses its own rule | caught: both push cases |
| 8 | shared test ground is not reported as the whole selection | caught: 4 cases |
| 9 | an empty selection is reported as an affected set | caught: `test_an_empty_selection_...` |
| 10 | the output file leaves out the last test file | caught: the 3 affected-set cases |
| 11 | the checkout is one commit deep (`fetch-depth: 2` removed) | caught: `test_the_checkout_holds_the_base_commit_...` |
| 12 | pytest does not read the selection file | caught: 3 tests |
| 13 | pytest reads another file than the step wrote | caught: 3 tests |
| 14 | the selection is chosen in part 1 only (`if: matrix.part == 1`) | caught: `test_every_part_chooses_its_tests_...` |
| 15 | a failed script leaves the part of the selection it wrote | caught: `test_a_script_that_fails_leaves_the_whole_selection_...` |
| 16 | a failed script fails the part, which then runs nothing | caught: same test |
| 17 | the base commit is `github.event.before`, not the pull request's base | caught: `test_every_part_chooses_its_tests_...` |
| 18 | **PM:** a part leaves out a selected test when it is given files (`run_in_parts.py`) | caught by the given-selection proof: `in the selection given and in no part: 5, such as ['packages/debate_cli/tests/test_app.py::...` (an assertion, not a collection error) |
| 19 | the same mutant, against the old whole-selection proof alone | **passes**, `1 passed in 9.54s`. This is expected. The whole selection is given as directories, so the old proof never sees a part dealt from files. This is why the given-selection proof was added. |
| 20 | a part drops its last test whatever it is given | caught by the given-selection proof |

Mutants 7, 8 and 9 change only what the summary says: the file stays empty, which is still the whole
selection. The design makes those failures safe, and the summary is what the tests hold them to.

### What this session ran before the report (working agreement 10)

- `uv run scripts/affected_tests.py --run` → `The whole selection is affected: .github/workflows/ci.yml
  is shared test ground. CI runs it on the pull request; a session does not (working agreement 10).`
  Nothing more was run of it; this pull request's own `ci` runs the whole selection (that is ac3).
- Within the two minutes, the test directories of what changed and the always-run list:
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts tests/docs tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py -m "not slow and not live" -n auto -p no:cacheprovider -q`
  → `1919 passed, 2 warnings in 71.21s` at load average 12. The two warnings are pytest-socket's
  `SocketBlockedError` from elsewhere in those directories; the three test files this task touches
  run with none (`516 passed in 28.87s`, no warnings). After the last commit, which re-wrapped the
  session prompt in `task_helper.py`, its tests ran again:
  `tests/scripts/test_task_restart.py tests/scripts/test_task_validate_dev_status.py` → `491 passed`.
- The whole-selection proof alone, after the workflow change:
  `-k exactly_the_default_selection` → `1 passed in 31.32s`.
- `uv run --frozen ruff format --check .` → `1488 files already formatted`; `uv run --frozen ruff check .`
  → `All checks passed!`.
- pyright: no package under `packages/` changed, and pyright's `include` is `packages`. Run on the
  new and changed Python files by name:
  `uv run --frozen pyright scripts/ci_test_selection.py tests/scripts/test_ci_workflow_test_selection.py tests/scripts/test_ci_workflow_test_job.py`
  → `0 errors, 0 warnings, 0 informations`.
- `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.`;
  `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 67 CLI command and API route handlers within 25 statements`.
- `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 54 indexed documents under docs/ have a description`;
  `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → OK, no comments in 505 shell code blocks in 185 Markdown files (1 session report changed since `origin/dev`);
  `uv run --frozen pre-commit run check-merge-conflict --all-files` → `Passed`.
- The link check reads anchors: with the old agreement 10 anchor put back in task-workflow.md,
  `tests/docs` failed with `working-agreements.md#10-a-session-tests-what-it-changed-and-ci-tests-everything has no heading matching`;
  restored, `80 passed`.
- actionlint was not run here: `scripts/actionlint.sh` downloads its pinned release, and network
  calls are the operator's. This pull request changes a workflow, so CI's `workflow-lint` job runs
  it. ShellCheck from the venv over the new step's shell (`.venv/bin/shellcheck -s bash`) is clean.
- `uv run scripts/validate_specs.py` → `OK: 478 files, 40 epics, 416 tasks, 22 releases`.

## Files changed

- `scripts/ci_test_selection.py` (new): what one `test` part runs, and the job summary.
- `.github/workflows/ci.yml`: the `test` job checks out two commits deep, gains the selection step
  with its crash guard, and its pytest reads `@$RUNNER_TEMP/test-selection.txt`. The header
  describes the new rule. The `changes` filter, the `coverage` job and `ci` are unchanged.
- `tests/scripts/test_ci_workflow_test_selection.py` (new): ac2's events and diffs.
- `tests/scripts/test_ci_workflow_test_job.py`: the partition proof now runs both for the whole
  selection and for a given one, and checks that each part gets some of the always-run list. New
  tests cover the step's wiring, the checkout and its lack of secrets or fetches, and the crash guard
  (run under `bash -e` with a stand-in `uv`).
- `docs/process/working-agreements.md`: agreement 10's heading and first bullets, the red-push-run
  rule, its two-minute bullet, and agreement 1's paragraph on the parts. `docs/process/task-workflow.md`:
  the sentence and link that pointed at agreement 10.
- `scripts/task_helper.py` (the session prompt's item 9) and `scripts/affected_tests.py` (its
  docstring's first paragraph): they said CI runs the whole selection on every pull request.

## Deviations from the spec

- **Order of work in ac2.** I wrote the script and its tests together, then showed the tests red
  against two skeletons swapped in for `choose()`, before the workflow and the mutants. So "red
  first" is red against a skeleton, not red before the implementation existed.

## Decisions and assumptions

- **The selection goes to pytest as `@FILE`**, pytest's own arguments file (pytest 8.2 and later;
  the lock has 9.1.1). One path per line; an empty file adds no argument, so pytest runs
  `testpaths`, which is the command the parts ran before. That gave three things:
  - `run_in_parts.py` did not change. It deals per file, from a checksum of the file's path, so a
    file's tests go to the same parts whatever else is selected. That means the parts of a
    selection are each a subset of the parts of the whole selection.
  - "Nothing about how parts are dealt changes for the whole selection" holds by construction.
  - A selection that is missing or empty runs more tests, not none.
- **Each part chooses for itself**, rather than one `select` job feeding the parts through outputs
  or an artifact. Another job would add a runner start and a `uv sync` in series before every part,
  about half a minute. The choice is deterministic for the same commit and event. Even if it
  differed, a part that fell back to the whole selection would run a superset of its share (the
  point above).
- **The base commit comes with the checkout.** `fetch-depth: 2` fetches the merge commit GitHub
  tests and its two parents, and the first parent is `pull_request.base.sha` unless `dev` moved since
  the event. When it is not there (a re-run after `dev` moved, say), the run is the whole selection,
  and the summary says the base commit is not in the checkout. No `git fetch` was added. With
  `persist-credentials: false` a fetch would need credentials on a private repository, which the PM
  ruled out.
- **An empty selection is the whole selection whether or not Python changed.** The PM's rule names
  the case where Python changed. In practice a selection that is not the whole one always holds the
  always-run list, so an empty one is a broken state. The summary still says how many Python files
  changed.
- **No explicit union with the always-run list in the CI script.** `affected_tests.select()` already
  adds it to every selection that is not the whole one, so a second union could never be caught by a
  mutant (agreement 8). Instead the tests assert it is in the selection, and that each part of a
  selection holds some of it. That also rules out a part collecting nothing, which would be pytest's
  exit status 5 and a red part.
- **The summary is written by every part.** Each part chose its own list, and the job summaries sit
  side by side on the run page, so five identical blocks show the five agree.
- **The test file was named `test_ci_workflow_test_selection.py`** so that the plan node's
  `-k "ci_workflow or affected"` runs it.
- **The red-push-run rule's last sentence:** "That pull request's session runs the failing tests by
  name as well as its affected set, because the fix's own selection may not reach them." The PM's
  text did not have it. Without it, the fixing pull request's `ci` could pass without running the
  test that was red.

## Operator follow-ups

1. **ac3, on this task's pull request.** Open any `test (K)` job of the `CI` run and read its
   summary. It should read **"Tests: the whole default selection. Every part runs its share of every
   test file, because .github/workflows/ci.yml is shared test ground."** Each part's
   "Choose the tests" step log prints the same. The `workflow-lint` job (actionlint) runs on this pull
   request and should pass, since this session could not run actionlint offline.
2. **ac3, after the merge.** On the push run of `CI` on `dev` for the merge commit, every
   `test (K)` summary should say **"... because a push to dev runs the whole selection."**, and the
   `coverage` job should run. Paste both summaries, or say they match, into the session so ac3 can be
   marked.
3. **Afterwards (not an acceptance criterion):** on the next ordinary pull request into `dev` that
   does not touch shared test ground, the summary should read "Tests: the affected set", with N of
   about 530 test files, and `ci` should take less time than before. That is the first real
   measurement of the saving.

## Follow-up work

- **`CLAUDE.md` still says "CI runs everything on the PR (working agreement 10)".** It is outside
  this task's packages. Proposed wording: "CI runs the affected set on a pull request into dev and
  everything on dev's push run (working agreement 10)." This is for the PM to change.
- **What makes the selections large** (ac1): `debate_cli/app.py` reached by every CLI-running test,
  `application/settings.py` and `application/errors.py` imported almost everywhere, and the
  caselist and debate_api test conftests' broad imports. e01-t32 covers `commands/__init__.py`. The
  conftests and the settings/errors reach are a candidate for a later selection-reach task, if the
  PM wants the median lower than about 50% for task pull requests.
- **The refresh pull requests** (`ROADMAP.md`, `docs/README.md`) each select 25 files, about 8% of
  the tests: the docs checks, the spec tests and the always-run list. They could skip the test job
  entirely if the `changes` filter left out those two generated files. That is a separate decision,
  because `tests/specs` reads `ROADMAP.md`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

The operator's request built so that every failure falls toward more tests: an empty or missing
selection file is pytest's `testpaths`, which is exactly the old command.
1. **ac1 passes.** Over the last 20 merges the median is 46.3% of test files (50.1% for the 14 task
   and PM pull requests). That is below the 60% line, so `v1-e01-t32` is not forced next. The hub
   analysis names what carries the large selections: `debate_cli/app.py`, `settings.py`,
   `errors.py`, and two package-level conftests.
2. **ac2 and the node's criterion pass.**
   * Red against two skeletons: one trusts the selection everywhere, the other always runs the
     whole selection.
   * 20 mutants, the PM's three among them, all aimed at the new tests caught.
   * Mutant 19 rightly shows what the old whole-selection proof could not see, which is why the
     given-selection proof was added.
3. **Decisions accepted:**
   * `@FILE`, with `run_in_parts.py` unchanged. A file is dealt by its path's checksum, so a
     selection's parts are subsets of the whole selection's parts.
   * Each part chooses for itself, with no extra job in series.
   * `fetch-depth: 2`, with a missing base as the whole selection, and no fetch added.
   * An empty selection is the whole selection.
   * No second union with the always-run list, held instead by tests.
   * Every part writes the summary.
4. **The red-push-run rule's last sentence is accepted as the PM's own.** The fixing session runs the
   failing tests by name as well as its affected set.
5. **The Deviation (red against a skeleton) is accepted.**
6. **actionlint** is left to CI's `workflow-lint` job, since the session cannot download it.
7. **Follow-ups:**
   * `CLAUDE.md`'s line is changed by the PM in the next batch, in the wording proposed.
   * The two package-level conftests and `debate_cli/app.py`'s reach are added by the PM to
     `v1-e01-t32`. `settings.py` and `errors.py` are real imports, and are left alone.
   * Refresh pull requests keep their 25 files: `tests/specs` reads `ROADMAP.md`.
8. **ac3 is the operator's.** The pull request's own run should report the whole selection because of
   `ci.yml`, and the push run after the merge the whole selection because of the push. The PM
   records both.

No re-review is needed. The PR merges `--partial`, phase `InProgress`, until ac3's push run is read.
